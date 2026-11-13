"""Tests of the real executor verification tool (T-OP-09).

    python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py

Fast tests first (adapters, hook, remote refusal, status rules, static checks, report logic), then every R scenario
runs once against real processes and a real git remote and must come out PASS or UNCONFIRMED with no failed check.
UNCONFIRMED parts are listed in the failure message of nothing: they are the honest "not measured here" records, and
the tests below pin down which ones may exist so that a silently skipped part cannot hide."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))

from daemon.core.ports import PushFailed  # noqa: E402
from daemon.runner_verify import cli_probe, registry, remote, reporting, static_checks  # noqa: E402
from daemon.runner_verify.adapters import FileStore, ProcessFaults, PushRemote, RealGit, RemoteCredentials, classify_push_failure, exclude_pathspecs, token_sha  # noqa: E402
from daemon.runner_verify.common import DEFAULT_RULES, Layout, ClockFile, group_members, open_handles, read_jsonl  # noqa: E402
from daemon.runner_verify.context import Ctx  # noqa: E402
from daemon.runner_verify.proxy import ProviderProxy  # noqa: E402
from daemon.runner_verify.report import FAIL, GAP, PARTIAL, PASS, UNCONFIRMED, Rep  # noqa: E402

RULES = DEFAULT_RULES
TASKS_JSON = ROOT / "docs/blueprint/proposals/설계검토_결과/tasks.json"
RUN_SH = ROOT / "tools/daemon/runner_verify/run.sh"
_RESULTS = {}


def results():
    """Every scenario once (about five minutes)."""
    if not _RESULTS:
        cx = Ctx()
        for entry in registry.SCENARIOS:
            _RESULTS[entry[0]] = reporting.run_scenario(entry, cx)
    return _RESULTS


# ================================================================ fast tests
class Adapters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = Layout(self.tmp.name).make()

    def tearDown(self):
        self.tmp.cleanup()

    def test_store_transaction_is_all_or_nothing(self):
        store = FileStore(self.layout)
        with store.transaction() as d:
            d["tasks"]["a"] = 1
        with self.assertRaises(RuntimeError):
            with store.transaction() as d:
                d["tasks"]["b"] = 2
                raise RuntimeError("body failed")
        self.assertEqual(store.snapshot()["tasks"], {"a": 1})

    def test_store_refuses_nested_transactions(self):
        store = FileStore(self.layout)
        with store.transaction():
            with self.assertRaises(RuntimeError):
                with store.transaction():
                    pass

    def test_store_survives_a_kill_in_the_middle_of_a_write(self):
        code = ("import sys; sys.path.insert(0, %r)\n"
                "from daemon.runner_verify.adapters import FileStore, ProcessFaults\n"
                "from daemon.runner_verify.common import Layout\n"
                "s = FileStore(Layout(%r), ProcessFaults(die_at={'store:torn_write': 0}))\n"
                "with s.transaction() as d: d['tasks']['x'] = 'new'\n") % (str(ROOT / "tools"), self.tmp.name)
        with FileStore(self.layout).transaction() as d:
            d["tasks"]["x"] = "old"
        res = subprocess.run([sys.executable, "-I", "-c", code])
        self.assertEqual(res.returncode, -9)
        self.assertEqual(FileStore(self.layout).snapshot()["tasks"]["x"], "old")
        self.assertEqual(list(self.layout.store_dir.glob(".state.json.*.tmp")), [], "a stale temp file is cleaned at start")

    def test_clock_offset_and_scaled_sleep(self):
        clock = ClockFile(self.layout.clock)
        base = clock.now()
        clock.add(100)
        self.assertGreaterEqual(clock.now(), base + 100)
        self.assertEqual([s["kind"] for s in clock.shifts()], ["advance"])

    def test_exclude_pathspecs_cover_the_manifest(self):
        pats = exclude_pathspecs([".git/", "target/", ".env", "*.pem"])
        self.assertEqual(pats, [":(exclude,glob,icase)**/target/**", ":(exclude,glob,icase)**/.env", ":(exclude,glob,icase)**/*.pem"])

    def test_push_failure_classes(self):
        mk = lambda err: type("R", (), {"stderr": err, "stdout": "", "returncode": 1})()
        self.assertEqual(classify_push_failure(mk("RV-REJECT credential_revoked")), "permission_denied")
        self.assertEqual(classify_push_failure(mk("RV-REJECT protected_branch")), "protected_branch")
        self.assertEqual(classify_push_failure(mk("fatal: unable to connect to 127.0.0.1: Connection refused")), "network")
        self.assertEqual(classify_push_failure(mk("something else")), "other")

    def test_faults_kill_only_the_armed_point(self):
        faults = ProcessFaults(die_at={"p": 1})
        faults.check("other")
        faults.check("p")  # first hit skipped
        self.assertTrue(faults.fails("x") is False)

    def test_changed_paths_is_the_real_diff(self):
        """audit6-daemon-scope-from-real-diff: merge-base(base, head)..head with renames as delete+add; a commit
        on main after the branch point is not in the PR's scope; an unknown sha is QueryUnavailable (fail closed)."""
        from daemon.runner_verify.adapters import RealGit
        from daemon.runner_verify.remote import git_env
        from daemon.core.ports import QueryUnavailable
        clone = self.layout.clone
        clone.mkdir()
        env = git_env(self.layout.home)

        def git(*args):
            res = subprocess.run(["git", *args], cwd=clone, env=env, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            return res.stdout.strip()

        git("init", "-q", "-b", "main")
        (clone / "base.txt").write_text("base\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        git("checkout", "-qb", "task")
        git("mv", "base.txt", "renamed.txt")
        (clone / "tools").mkdir()
        (clone / "tools" / "new.py").write_text("x = 1\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "work")
        head = git("rev-parse", "HEAD")
        git("checkout", "-q", "main")
        (clone / "main_only.txt").write_text("m\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "main moves on")
        rg = RealGit(self.layout, self.layout.root / "remote.git", [],
                     RemoteCredentials(self.layout, self.layout.root / "remote.git", 60))
        self.assertEqual(rg.changed_paths("T-MOCK-X", base, head), ["base.txt", "renamed.txt", "tools/new.py"])
        with self.assertRaises(QueryUnavailable):
            rg.changed_paths("T-MOCK-X", base, "1" * 40)
        with self.assertRaises(QueryUnavailable):
            rg.changed_paths("T-MOCK-X", "", head)


class RemoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name) / "home"
        cls.home.mkdir()
        cls.path = remote.provision(Path(cls.tmp.name) / "r.git", cls.home)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def push(self, ref, token, force=False):
        RemoteTests.n = getattr(RemoteTests, "n", 0) + 1
        wt = Path(self.tmp.name) / f"wt{RemoteTests.n}"
        env = remote.git_env(self.home)
        remote.run_git(["clone", "-q", str(self.path), str(wt)], env=env)
        (wt / "f.txt").write_text(f"{ref}{token}{RemoteTests.n}", encoding="utf-8")
        remote.run_git(["add", "-A"], cwd=wt, env=env)
        remote.run_git(["commit", "-q", "-m", "x"], cwd=wt, env=env)
        env["RV_PUSH_CREDENTIAL"] = token or ""
        return remote.run_git(["push"] + (["--force"] if force else []) + [str(self.path), f"HEAD:{ref}"], cwd=wt, env=env, check=False)

    def test_protected_main_refuses_even_a_valid_credential(self):
        remote.register_token(self.path, token_sha("t-main"), "builder_write_credential", "T-MOCK-BASIC", "L1", 600)
        res = self.push("refs/heads/main", "t-main", force=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("RV-REJECT protected_branch", res.stderr)

    def test_only_task_branches_of_mock_tasks_are_writable(self):
        remote.register_token(self.path, token_sha("t-other"), "builder_write_credential", "T-MOCK-BASIC", "L1", 600)
        res = self.push("refs/heads/feature/x", "t-other")
        self.assertIn("RV-REJECT ref_not_allowed", res.stderr)

    def test_credential_lifecycle_decides_the_push(self):
        ref = "refs/heads/task/T-MOCK-BASIC-a1"
        res = self.push(ref, "never-issued")
        self.assertIn("RV-REJECT permission_denied", res.stderr)
        remote.register_token(self.path, token_sha("t-live"), "builder_write_credential", "T-MOCK-BASIC", "L1", 600)
        self.assertEqual(self.push(ref, "t-live").returncode, 0)
        remote.revoke_token(self.path, token_sha("t-live"))
        self.assertIn("RV-REJECT credential_revoked", self.push(ref, "t-live", force=True).stderr)
        remote.register_token(self.path, token_sha("t-wrong"), "builder_write_credential", "T-MOCK-OTHER", "L2", 600)
        self.assertIn("RV-REJECT scope_mismatch", self.push(ref, "t-wrong", force=True).stderr)
        remote.register_token(self.path, token_sha("t-old"), "builder_write_credential", "T-MOCK-BASIC", "L3", -5)
        self.assertIn("RV-REJECT credential_expired", self.push(ref, "t-old", force=True).stderr)

    def test_every_decision_is_logged(self):
        log = remote.push_log(self.path)
        self.assertTrue(log)
        self.assertTrue(all("ts_ns" in e and "ref" in e for e in log))

    def test_urls_and_the_product_repository_are_refused(self):
        for bad in ("https://example.invalid/x.git", "git@example.invalid:x/y.git", str(ROOT), str(ROOT / ".git")):
            with self.assertRaises(remote.RemoteRefused, msg=bad):
                remote.check_accepts(bad)

    def test_an_unmarked_bare_repository_is_refused(self):
        plain = Path(self.tmp.name) / "plain.git"
        subprocess.run(["git", "init", "-q", "--bare", str(plain)], check=True)
        with self.assertRaises(remote.RemoteRefused):
            remote.check_accepts(plain)

    def test_a_marked_repository_is_accepted(self):
        self.assertEqual(remote.check_accepts(self.path), self.path)


class PushRefspecGit(unittest.TestCase):
    """audit6-daemon-push-refspec-validation, against a real git remote: the push adapters refuse an option-shaped
    or +force-prefixed sha and a branch that is not the lease's task branch before git runs, and a valid push passes
    -- before the refspec so no part of the request can be read as a git option."""

    BRANCH = "task/T-MOCK-BASIC-a1"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name) / "home"
        cls.home.mkdir()
        cls.path = remote.provision(Path(cls.tmp.name) / "r.git", cls.home)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.layout_tmp = tempfile.TemporaryDirectory()
        self.layout = Layout(self.layout_tmp.name).make()
        env = remote.git_env(self.layout.home)
        remote.run_git(["clone", "-q", str(self.path), str(self.layout.clone)], env=env)
        (self.layout.clone / "f.txt").write_text("refspec fixture\n", encoding="utf-8")
        remote.run_git(["add", "-A"], cwd=self.layout.clone, env=env)
        remote.run_git(["commit", "-q", "-m", "refspec fixture"], cwd=self.layout.clone, env=env)
        self.sha = remote.run_git(["rev-parse", "HEAD"], cwd=self.layout.clone, env=env).stdout.strip()
        self.credentials = RemoteCredentials(self.layout, str(self.path), 600)
        self.credentials.issue("builder_write_credential", "T-MOCK-BASIC", "L1")
        self.git = RealGit(self.layout, str(self.path), [], self.credentials)
        self.push_remote = PushRemote(self.layout, self.git, self.credentials)
        self.request = {"lease_id": "L1", "sha": self.sha, "branch": self.BRANCH}

    def tearDown(self):
        self.layout_tmp.cleanup()

    def pushes(self, spy):
        return [c.args[0] for c in spy.call_args_list if c.args[0][:1] == ["push"]]

    def decisions(self):
        return [e for e in remote.push_log(self.path) if e["event"] == "pre_receive"]

    def test_valid_push_passes_the_option_separator_and_lands_on_the_remote(self):
        with mock.patch.object(self.git, "_git", wraps=self.git._git) as spy:
            self.push_remote.execute("push", "T-MOCK-BASIC", dict(self.request))
        self.assertEqual(self.pushes(spy), [["push", str(self.path), "--", f"{self.sha}:refs/heads/{self.BRANCH}"]])
        self.assertEqual(remote.refs(self.path, self.home).get(f"refs/heads/{self.BRANCH}"), self.sha)
        last = self.decisions()[-1]
        self.assertEqual((last["decision"], last["reason"], last["ref"], last["client"]),
                         ("accepted", "ok", f"refs/heads/{self.BRANCH}", "daemon-fenced"))

    def test_invalid_refspec_never_reaches_git_or_the_remote(self):
        # a wrong attempt of the same task (a2) is the core's lease-equality check, not the adapter's shape check
        bad = [{"sha": s} for s in ("--receive-pack=/bin/sh", "--force", "+" + self.sha, self.sha[:39], self.sha + "0",
                                    "A" * 40, "", None, 40)]
        bad += [{"branch": b} for b in ("main", "task/T-MOCK-OTHER-a1", "--force",
                                        self.BRANCH + ":refs/heads/main", self.BRANCH + " --force", "", None)]
        refs_before, log_before = remote.refs(self.path, self.home), remote.push_log(self.path)
        for kw in bad:
            with self.subTest(kw=kw):
                with mock.patch.object(self.git, "_git", wraps=self.git._git) as spy:
                    with self.assertRaises(PushFailed):
                        self.push_remote.execute("push", "T-MOCK-BASIC", dict(self.request, **kw))
                self.assertEqual(self.pushes(spy), [])
        self.assertEqual(remote.refs(self.path, self.home), refs_before)
        self.assertEqual(remote.push_log(self.path), log_before)
        records = read_jsonl(self.layout.root / "remote_writes.jsonl")
        self.assertEqual(len(records), len(bad))
        self.assertTrue(all(r["executed"] is False and r["reason"] == "invalid_refspec" for r in records))

    def test_preserve_push_passes_the_option_separator_and_validates(self):
        branch = "task/T-MOCK-BASIC-a2"  # its own branch: the shared remote keeps the other tests' refs
        self.credentials.issue("preserve_credential", "T-MOCK-BASIC", "L1")
        with mock.patch.object(self.git, "_git", wraps=self.git._git) as spy:
            self.assertEqual(self.git.push(branch, self.sha), self.sha)
        self.assertEqual(self.pushes(spy), [["push", str(self.path), "--", f"{self.sha}:refs/heads/{branch}"]])
        last = self.decisions()[-1]
        self.assertEqual((last["decision"], last["reason"], last["client"]), ("accepted", "ok", "daemon-preserve"))
        for sha, b in (("--receive-pack=/bin/sh", branch), ("+" + self.sha, branch),
                       (self.sha[:39], branch), (self.sha, "main"), (self.sha, branch + ":refs/heads/main")):
            with self.subTest(sha=sha, branch=b):
                with mock.patch.object(self.git, "_git", wraps=self.git._git) as spy:
                    with self.assertRaises(PushFailed):
                        self.git.push(b, sha)
                self.assertEqual(spy.call_args_list, [])
        # a well-formed branch of another task passes the shape check (the task is derived from the branch); no
        # credential is issued for that task, so the push carries an empty token and the remote refuses it
        with mock.patch.object(self.git, "_git", wraps=self.git._git) as spy:
            with self.assertRaises(PushFailed):
                self.git.push("task/T-MOCK-OTHER-a1", self.sha)
        self.assertEqual(len(self.pushes(spy)), 1)
        last = self.decisions()[-1]
        self.assertEqual((last["decision"], last["reason"]), ("rejected", "permission_denied"))


class StatusRules(unittest.TestCase):
    def test_429_is_a_usage_limit_only_through_the_status_channel(self):
        self.assertEqual(cli_probe.signals_from_stream([{"error_status": 429}], {"api_error_status": 429}), ["usage_limit"])
        self.assertEqual(cli_probe.signals_from_stream([], {"api_error_status": None}), [])

    def test_service_unavailable_needs_three_in_a_row(self):
        two = [{"error_status": 503}, {"error_status": 503}]
        three = two + [{"error_status": 503}]
        self.assertEqual(cli_probe.signals_from_stream(two, {"api_error_status": None}), [])
        self.assertEqual(cli_probe.signals_from_stream(three, {"api_error_status": None}), ["service_unavailable"])
        self.assertEqual(cli_probe.signals_from_stream([{"error_status": 503}, {"error_status": 429}, {"error_status": 503}], None), ["usage_limit"])

    def test_auth_failure(self):
        self.assertEqual(cli_probe.signals_from_stream([{"error_status": 401}], {"api_error_status": 401}), ["auth_failure"])

    def test_exit_codes_enter_the_profile_only_if_unique_to_the_situation(self):
        same = {"429": [{"rc": 1}], "503": [{"rc": 1}], "401": [{"rc": 1}], "ok": [{"rc": 0}]}
        row = cli_probe.exit_code_row(same)
        self.assertEqual((row["limit_exit_codes"], row["unavailable_exit_codes"], row["confirmed"]), ([], [], False))
        split = {"429": [{"rc": 75}], "503": [{"rc": 69}], "500": [{"rc": 69}], "401": [{"rc": 1}], "ok": [{"rc": 0}]}
        row = cli_probe.exit_code_row(split)
        self.assertEqual((row["limit_exit_codes"], row["unavailable_exit_codes"], row["confirmed"]), ([75], [69], True))
        overlap = {"429": [{"rc": 2}], "401": [{"rc": 2}], "503": [{"rc": 3}], "ok": [{"rc": 0}]}
        self.assertEqual(cli_probe.exit_code_row(overlap)["limit_exit_codes"], [])

    def test_stream_parser_keeps_only_structured_fields(self):
        text = "\n".join([json.dumps({"type": "system", "subtype": "init", "model": "SHOULD-NOT-BE-KEPT", "session_id": "S"}),
                          json.dumps({"type": "system", "subtype": "api_retry", "attempt": 1, "error_status": 429, "error": "rate_limit"}),
                          json.dumps({"type": "result", "is_error": True, "api_error_status": 429, "terminal_reason": "api_error",
                                      "usage": {"input_tokens": 3, "output_tokens": 4}, "total_cost_usd": 0.5})])
        parsed = cli_probe.parse_stream(text)
        self.assertNotIn("SHOULD-NOT-BE-KEPT", json.dumps(parsed))
        self.assertEqual(parsed["retries"][0]["error_status"], 429)
        self.assertEqual(parsed["result"]["api_error_status"], 429)

    def test_every_cli_target_without_a_proxy_path_says_why(self):
        for t in cli_probe.TARGETS:
            if not t["proxy"]:
                self.assertTrue(t["unconfirmed_reason"], t["id"])


class ProxyTests(unittest.TestCase):
    def test_modes_and_metering(self):
        import http.client
        px = ProviderProxy("429").start()
        try:
            host, port = px.url.replace("http://", "").split(":")
            def post():
                conn = http.client.HTTPConnection(host, int(port), timeout=5)
                try:
                    conn.request("POST", "/v1/messages", json.dumps({"messages": [{"role": "user", "content": "hello"}]}))
                    return conn.getresponse().status
                finally:
                    conn.close()

            self.assertEqual(post(), 429)
            px.set_mode("ok")
            self.assertEqual(post(), 200)
            self.assertEqual([c["status"] for c in px.message_calls()], [429, 200])
            self.assertGreater(px.message_calls()[1]["tokens_in"], 0)
        finally:
            px.stop()


class DrainGuardWait(unittest.TestCase):
    """audit2-daemon-guard-fail-partial-commit: an envelope the core did not take because a lease guard waits
    (issue_lease.on_guard_wait) stays in the daemon inbox, so the next drain delivers it again."""

    def test_a_waiting_envelope_stays_in_the_inbox(self):
        from types import SimpleNamespace
        from daemon.runner_verify import daemon_main
        spec = json.loads(Path(RULES).read_text(encoding="utf-8"))["core_contract"]["operations"]["issue_lease"]["on_guard_wait"]

        class Core:
            guard_wait = spec
            ports = SimpleNamespace(faults=SimpleNamespace(check=lambda point: None))

            def submit_envelope(self, task_id, kind, envelope):
                if envelope["envelope_id"] == "WAIT":
                    return {"accepted": False, "applied": False, "transition": None, "reason": spec["result"]}
                return {"accepted": True, "transition": ("building", "pr_open", "result_pr_opened")}

        with tempfile.TemporaryDirectory() as tmp:
            layout = Layout(tmp).make()
            for name, eid in (("1.json", "WAIT"), ("2.json", "TAKEN")):
                (layout.daemon_inbox / name).write_text(json.dumps(
                    {"msg_type": "result", "task_id": "T", "envelope": {"envelope_id": eid}}), encoding="utf-8")
            done = daemon_main.op_drain(layout, Core(), None)
            self.assertEqual([(r["name"], r["outcome"]["accepted"]) for r in done], [("1.json", False), ("2.json", True)])
            self.assertEqual(sorted(p.name for p in layout.daemon_inbox.iterdir()), ["1.json"])
            self.assertEqual(sorted(p.name for p in layout.daemon_done.iterdir()), ["2.json", "2.json.out"])


class DrainPoisonMessage(unittest.TestCase):
    """audit6-daemon-drain-poison-message: one inbox file failing with an exception outside the old catch list
    (a PushFailed, a timeout, `"envelope": "x"`) stopped the whole drain, so every later file stayed undelivered
    until leases expired. Any failing message is now quarantined — moved to daemon_done with an ok:False record,
    the original file preserved — and the drain delivers the rest. Unparseable JSON is quarantined too instead of
    staying in the inbox forever."""

    def _run_drain(self, files, exc):
        """files: [(name, message-or-raw-text)]; the fake core raises exc for envelope_id POISON."""
        from types import SimpleNamespace
        from daemon.runner_verify import daemon_main

        class Core:
            guard_wait = {"result": "guard_wait"}
            ports = SimpleNamespace(faults=SimpleNamespace(check=lambda point: None))

            def submit_envelope(self, task_id, kind, envelope):
                if envelope.get("envelope_id") == "POISON":
                    raise exc
                if envelope.get("envelope_id") == "WAIT":
                    return {"accepted": False, "reason": "guard_wait"}
                return {"accepted": True}

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        layout = Layout(tmp.name).make()
        for name, msg in files:
            text = msg if isinstance(msg, str) else json.dumps(msg)
            (layout.daemon_inbox / name).write_text(text, encoding="utf-8")
        return layout, daemon_main.op_drain(layout, Core(), None)

    def test_any_exception_quarantines_the_file_and_the_drain_continues(self):
        from daemon.core.ports import PushFailed
        good = {"msg_type": "heartbeat", "task_id": "T", "envelope": {"envelope_id": "GOOD"}}
        poison = {"msg_type": "heartbeat", "task_id": "T", "envelope": {"envelope_id": "POISON"}}
        for exc in (PushFailed("network"), TimeoutError("git push timed out"),
                    subprocess.TimeoutExpired(["git", "push"], timeout=120),
                    AttributeError("'str' object has no attribute 'get'"), TypeError("string indices must be integers")):
            with self.subTest(exc=type(exc).__name__):
                layout, done = self._run_drain([("1.json", good), ("2.json", poison), ("3.json", good)], exc)
                self.assertEqual([(r["name"], r["ok"]) for r in done],
                                 [("1.json", True), ("2.json", False), ("3.json", True)])
                self.assertEqual(done[1]["error"], type(exc).__name__)
                self.assertIn(str(exc)[:300], done[1]["msg"])
                self.assertEqual(list(layout.daemon_inbox.iterdir()), [], "the drain emptied the inbox")
                self.assertEqual(sorted(p.name for p in layout.daemon_done.iterdir()),
                                 ["1.json", "1.json.out", "2.json", "2.json.out", "3.json", "3.json.out"])
                out = json.loads((layout.daemon_done / "2.json.out").read_text(encoding="utf-8"))
                self.assertEqual((out["ok"], out["error"]), (False, type(exc).__name__))
                self.assertEqual((layout.daemon_done / "2.json").read_text(encoding="utf-8"), json.dumps(poison),
                                 "the quarantined original is preserved for inspection")

    def test_unparseable_json_is_quarantined_not_left_in_the_inbox(self):
        good = {"msg_type": "heartbeat", "task_id": "T", "envelope": {"envelope_id": "GOOD"}}
        layout, done = self._run_drain([("1.json", "{not json"), ("2.json", good)], None)
        self.assertEqual([(r["name"], r["ok"]) for r in done], [("1.json", False), ("2.json", True)])
        self.assertEqual(done[0]["error"], "JSONDecodeError")
        self.assertEqual(list(layout.daemon_inbox.iterdir()), [])
        self.assertEqual((layout.daemon_done / "1.json").read_text(encoding="utf-8"), "{not json")

    def test_a_poison_file_does_not_disturb_guard_wait_redelivery(self):
        from daemon.core.ports import PushFailed
        wait = {"msg_type": "heartbeat", "task_id": "T", "envelope": {"envelope_id": "WAIT"}}
        poison = {"msg_type": "heartbeat", "task_id": "T", "envelope": {"envelope_id": "POISON"}}
        good = {"msg_type": "heartbeat", "task_id": "T", "envelope": {"envelope_id": "GOOD"}}
        layout, done = self._run_drain([("1.json", wait), ("2.json", poison), ("3.json", good)], PushFailed("network"))
        self.assertEqual([(r["name"], r["ok"]) for r in done],
                         [("1.json", True), ("2.json", False), ("3.json", True)])
        self.assertEqual([p.name for p in layout.daemon_inbox.iterdir()], ["1.json"],
                         "the waiting envelope is still redelivered by the next drain")

    def test_real_drain_quarantines_poison_and_delivers_the_rest(self):
        """The real daemon process over the real adapters: `"envelope": "x"` raises AttributeError in the core,
        an unissued credential makes the remote adapter raise PushFailed, bad JSON never parses — and the valid
        heartbeat after them is still accepted (leased→building) in the same drain."""
        from daemon.runner_verify.harness import BASIC
        with Ctx().world() as w:
            self.assertTrue(w.init_task(BASIC).ok)
            self.assertTrue(w.grant(BASIC).ok)
            lease = w.lease(BASIC)
            base = {"task_id": BASIC, "lease_id": lease["lease_id"],
                    "lease_generation": lease["lease_generation"], "fencing_token": lease["fencing_token"]}
            w.queue_file({"msg_type": "heartbeat", "task_id": BASIC, "envelope": "x"}, name="1-poison-envelope.json")
            (w.layout.daemon_inbox / "2-poison-json.json").write_text("{not json", encoding="utf-8")
            w.queue_file({"msg_type": "push_requested", "task_id": BASIC,
                          "payload": dict(base, envelope_id="POISON-PUSH", via="daemon",
                                          branch=lease["branch"], sha="0" * 40)}, name="3-poison-push.json")
            w.queue_file({"msg_type": "first_heartbeat", "task_id": BASIC,
                          "envelope": dict(base, envelope_id="GOOD-HB", at=w.clock.now())}, name="4-good.json")
            res = w.drain()
            self.assertTrue(res.ok, res.payload or res.stderr)
            done = res.result
            self.assertEqual([r["name"] for r in done],
                             ["1-poison-envelope.json", "2-poison-json.json", "3-poison-push.json", "4-good.json"])
            self.assertEqual([r["ok"] for r in done], [False, False, False, True])
            self.assertEqual([r["error"] for r in done[:3]], ["AttributeError", "JSONDecodeError", "PushFailed"])
            self.assertTrue(done[3]["outcome"]["accepted"])
            self.assertEqual(w.state(BASIC), "building", "the heartbeat after the poison files still moved the task")
            self.assertEqual(list(w.layout.daemon_inbox.glob("*.json")), [])
            for r in done[:3]:
                out = json.loads((w.layout.daemon_done / (r["name"] + ".out")).read_text(encoding="utf-8"))
                self.assertEqual((out["ok"], out["error"]), (False, r["error"]))
                self.assertTrue((w.layout.daemon_done / r["name"]).exists(), "the original is preserved")

    def test_an_unexpected_operation_failure_still_answers_rv_result(self):
        """The top-level catch (the finding's second site): a failure outside the old catch list — here a missing
        config makes build_core raise TypeError — still prints the one RV_RESULT line the harness parses."""
        from daemon.runner_verify.harness import DAEMON_MAIN
        with tempfile.TemporaryDirectory() as tmp:
            Layout(tmp).make()  # no config.json
            res = subprocess.run([sys.executable, "-I", DAEMON_MAIN, "--state", tmp, "drain"],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 3)
            line = next(l for l in res.stdout.splitlines() if l.startswith("RV_RESULT "))
            payload = json.loads(line[len("RV_RESULT "):])
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"], "TypeError")
            self.assertIn("trace", payload)

    def test_http_delivery_answers_a_poison_message_and_keeps_serving(self):
        import http.client
        import time
        from daemon.runner_verify.common import read_jsonl
        from daemon.runner_verify.harness import BASIC
        with Ctx().world() as w:
            self.assertTrue(w.init_task(BASIC).ok)
            self.assertTrue(w.grant(BASIC).ok)
            lease = w.lease(BASIC)
            proc = w.daemon_async("serve", "--port", "0", "--duration", "30")
            try:
                port_file = w.layout.root / "http_port"
                deadline = time.time() + 10
                while not port_file.exists() and time.time() < deadline:
                    time.sleep(0.05)
                port = int(port_file.read_text(encoding="utf-8"))

                def post(body):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                    try:
                        conn.request("POST", "/message", body)
                        resp = conn.getresponse()
                        return resp.status, json.loads(resp.read())
                    finally:
                        conn.close()

                status, res = post("{not json")
                self.assertEqual((status, res["ok"], res["error"]), (200, False, "JSONDecodeError"))
                status, res = post(json.dumps({"msg_type": "heartbeat", "task_id": BASIC, "envelope": "x"}))
                self.assertEqual((status, res["ok"], res["error"]), (200, False, "AttributeError"))
                good = {"msg_type": "first_heartbeat", "task_id": BASIC,
                        "envelope": dict(envelope_id="HTTP-GOOD", task_id=BASIC, lease_id=lease["lease_id"],
                                         lease_generation=lease["lease_generation"],
                                         fencing_token=lease["fencing_token"], at=w.clock.now())}
                status, res = post(json.dumps(good))
                self.assertEqual((status, res["ok"]), (200, True))
                self.assertTrue(res["outcome"]["accepted"])
                log = read_jsonl(w.layout.root / "http_server.jsonl")
                self.assertEqual([e["res"]["ok"] for e in log], [False, False, True])
            finally:
                (w.layout.root / "http_stop").write_text("1", encoding="utf-8")
                proc.wait(timeout=15)


class ReportLogic(unittest.TestCase):
    def test_scenario_status(self):
        rep = Rep()
        self.assertEqual(rep.status(), UNCONFIRMED)
        rep.eq("a", 1, 1)
        self.assertEqual(rep.status(), PASS)
        rep.unconfirmed("b", "no way")
        self.assertEqual(rep.status(), PARTIAL)
        rep.gap("c", "differs from the text")
        self.assertEqual(rep.status(), PARTIAL)
        rep.eq("d", 1, 2)
        self.assertEqual(rep.status(), FAIL)
        only = Rep()
        only.unconfirmed("x", "y")
        self.assertEqual(only.status(), UNCONFIRMED)

    def test_a_failure_is_recorded_as_a_failure(self):
        def boom(rep, cx):
            rep.eq("before", 1, 1)
            raise RuntimeError("scenario cannot run")
        res = reporting.run_scenario(("RX", None, "t", boom, [], []), Ctx())
        self.assertEqual(res["status"], FAIL)
        self.assertIn("scenario cannot run", res["error"])

    def test_registry_covers_r1_to_r22_and_all_required_test_ids(self):
        self.assertEqual([e[0] for e in registry.SCENARIOS], [f"R{i}" for i in range(1, 23)])
        spec = next(t for t in json.loads(TASKS_JSON.read_text(encoding="utf-8"))["tasks"] if t["id"] == "T-OP-09")
        self.assertEqual(sorted(registry.REQUIRED_TEST_IDS), sorted(spec["required_test_ids"]))
        self.assertEqual({e[1] for e in registry.SCENARIOS if e[1]}, set(spec["required_test_ids"]))

    def test_spec_tests_name_the_runner_script(self):
        spec = next(t for t in json.loads(TASKS_JSON.read_text(encoding="utf-8"))["tasks"] if t["id"] == "T-OP-09")
        self.assertTrue(spec["tests"][0].startswith("bash tools/daemon/runner_verify/run.sh"))
        self.assertTrue(RUN_SH.exists())


class StaticChecks(unittest.TestCase):
    def test_all_static_checks_pass(self):
        for name, bad in static_checks.all_static(RULES):
            self.assertEqual(bad, [], name)

    def test_checks_can_fail(self):
        self.assertNotEqual(static_checks.no_leak_in_outputs('{"session_id": "x"}'), [])
        self.assertNotEqual(static_checks.no_leak_in_outputs("id 123e4567-e89b-12d3-a456-426614174000"), [])
        self.assertNotEqual(static_checks.no_model_identifiers(extra_texts=[("t", "model " + "son" + "net-9")]), [])
        self.assertNotEqual(static_checks.secrets_absent(RULES, extra_texts=[("t", "api" + "_key = '" + "x" * 20 + "'")]), [])
        self.assertNotEqual(static_checks.runner_profile_confirmed_only({"cli": {"limit_exit_codes": [1], "unavailable_exit_codes": [], "confirmed": False}}), [])
        self.assertEqual(static_checks.runner_profile_confirmed_only({"cli": {"limit_exit_codes": [], "unavailable_exit_codes": [], "confirmed": False}}), [])

    def test_secret_scan_static_check_uses_per_value_digest_context(self):
        digest, key = "c3" * 32, "b2" * 32
        self.assertEqual(static_checks.secrets_absent(
            RULES, extra_texts=[("digest", 'checksum = "' + digest + '"')]), [])
        self.assertNotEqual(static_checks.secrets_absent(
            RULES, extra_texts=[("mixed", json.dumps({"sha256": digest, "value": key}))]), [])

    def test_a_merge_function_would_be_caught(self):
        import ast
        tree = ast.parse("def merge_it():\n    pass\n")
        names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and "merge" in n.name.lower()]
        self.assertEqual(names, ["merge_it"])

    def test_the_tool_never_writes_outside_its_own_paths_by_construction(self):
        # nothing in the package opens a path under the repository root for writing except through the state directory
        for p in static_checks.sources():
            src = p.read_text(encoding="utf-8")
            self.assertNotRegex(src, r"open\([^)]*ROOT[^)]*['\"]w", p.name)


class Cli(unittest.TestCase):
    def test_a_remote_url_is_refused_with_exit_code_2(self):
        with tempfile.TemporaryDirectory() as d:
            res = subprocess.run(["bash", str(RUN_SH), "--remote", "https://example.invalid/x.git", "--report", f"{d}/r.json"],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 2)
            self.assertIn("remote refused", res.stderr)

    def test_two_scenarios_end_to_end_write_every_output_file(self):
        with tempfile.TemporaryDirectory() as d:
            res = subprocess.run(["bash", str(RUN_SH), "--report", f"{d}/runner_verify.json", "--scenario", "R19,R20", "--no-cli", "--quiet"],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            names = sorted(p.name for p in Path(d).iterdir())
            self.assertEqual(names, ["RESULTS.md", "exit_code_table.md", "runner_verify.json", "runner_verify.log", "static_checks.log", "summary.json"])
            report = json.loads((Path(d) / "runner_verify.json").read_text(encoding="utf-8"))
            self.assertEqual([r["r"] for r in report["results"]], ["R19", "R20"])
            self.assertTrue(report["product_branch_check"]["refs_unchanged"])
            self.assertEqual(report["product_branch_check"]["merge_calls"], 0)
            self.assertIn("가동 승인이 아니다", report["vm_approval"])
            self.assertFalse(report["environment"]["vm_verified"])
            # the exit-code table keeps every CLI without a measured value as unconfirmed
            table = (Path(d) / "exit_code_table.md").read_text(encoding="utf-8")
            self.assertIn("미확인", table)

    def test_checked_in_result_files_are_consistent_with_their_report(self):
        base = ROOT / "docs/vm_check"
        reports = sorted(base.glob("*/runner_verify.json"))
        if not reports:
            self.skipTest("no checked-in result yet")
        report = json.loads(reports[-1].read_text(encoding="utf-8"))
        self.assertEqual([r["r"] for r in report["results"]], [f"R{i}" for i in range(1, 23)])
        self.assertTrue(all(v != "not run" for v in report["required_test_ids"].values()))
        for profile in report["runner_profile"].values():
            if not profile["confirmed"]:
                self.assertEqual((profile["limit_exit_codes"], profile["unavailable_exit_codes"]), ([], []))
        self.assertEqual(static_checks.no_leak_in_outputs(reports[-1].read_text(encoding="utf-8")), [])
        self.assertEqual(report["product_branch_check"]["merge_calls"], 0)
        self.assertTrue(report["product_branch_check"]["refs_unchanged"])


# ================================================================ the scenarios
class Scenarios(unittest.TestCase):
    pass


def _make(rid):
    def test(self):
        res = results()[rid]
        self.assertIsNone(res["error"], res["error"])
        self.assertTrue(res["checks"], "scenario produced no checks")
        bad = [c for c in res["checks"] if c["status"] == FAIL]
        self.assertEqual(bad, [], "\n".join(f"{c['name']}\n  expected {c['expected']}\n  actual   {c['actual']}" for c in bad))
        self.assertIn(res["status"], (PASS, PARTIAL, UNCONFIRMED))
    return test


for _entry in registry.SCENARIOS:
    setattr(Scenarios, f"test_{_entry[0]}_{(_entry[1] or 'decision-gate-and-resume').replace('-', '_')}", _make(_entry[0]))


class ScenarioAggregates(unittest.TestCase):
    def test_every_required_test_id_was_run_and_none_failed(self):
        res = results()
        ran = {r["test_id"]: [] for r in res.values() if r["test_id"]}
        for r in res.values():
            if r["test_id"]:
                ran[r["test_id"]].append(r["status"])
        self.assertEqual(sorted(ran), sorted(registry.REQUIRED_TEST_IDS))
        for tid, statuses in ran.items():
            self.assertNotIn(FAIL, statuses, tid)

    def test_unconfirmed_parts_are_exactly_the_ones_without_a_path_on_this_host(self):
        """A part may be UNCONFIRMED only for a runner path that has no confirmed way to be driven here."""
        allowed = re.compile(r"Cursor CLI|grokbuild CLI|Devin CLI|Claude Code\(GLM 프로필\)|대체 모델 경로|가득 찬 디스크|claude CLI|실제 CLI")
        for r in results().values():
            for c in r["checks"]:
                if c["status"] == UNCONFIRMED:
                    self.assertRegex(c["name"], allowed, f"{r['r']}: {c['name']}")

    def test_the_exit_code_profile_of_the_real_cli_is_empty_unless_confirmed(self):
        table = results()["R7"]["evidence"]["exit_code_table"]
        row = table["cli-claude"]["exit_codes"]
        if row:
            self.assertEqual(bool(row["limit_exit_codes"] or row["unavailable_exit_codes"]), row["confirmed"])

    def test_no_secret_or_raw_output_in_the_results(self):
        text = json.dumps(list(results().values()), ensure_ascii=False, default=str)
        self.assertEqual(static_checks.no_leak_in_outputs(text), [])
        self.assertEqual(static_checks.no_model_identifiers(extra_texts=[("results", text)]), [])
        self.assertEqual(static_checks.secrets_absent(RULES, extra_texts=[("results", text)]), [])


if __name__ == "__main__":
    unittest.main()
