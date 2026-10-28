"""Dry run of the daemon core (tools/daemon): the T-OP-00 scenarios run on the shared core with mock adapters.

What must hold:
- every scenario M1-M44 (05 §5, with M10a·M10b·M18a·M18b) ends with expected == actual on every check, and every
  required test id of T-OP-00 is run and no other id is (both directions, `dry_run.coverage`); checks marked GAP would be specification gaps and are listed, not hidden;
- the G29-G50 fields are read by the core (t_op_00_followups): the structure checks of tests_to_add hold on the file
  and the behavior checks hold on the core;
- the core reads only the fields of core_contract.reads: its view of the file has no prose `when`, `note` or `_`
  keys, and replacing or deleting every such key changes no result;
- the behavior comes from the data: changing one structured field (resend checks, handoff order, thresholds,
  expiry condition, guards, side effects, the read list ...) makes the scenario that depends on it fail, so the
  scenarios are not matched by separate logic;
- usage is recorded and never capped (U-05);
- static checks: no merge API, no network or CLI, no wall clock, no start-up feature, one writer of
  lease_generation, one tree identity function, no model identifiers, no dry-run branch in the core.
"""
import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from daemon import dry_run, scenarios as sc, scenarios_flow as fl, static_checks  # noqa: E402
from daemon.core import Rules  # noqa: E402
from daemon.mock_env import MockEnv  # noqa: E402

RULES = ROOT / "docs/blueprint/proposals/설계검토_결과/daemon_rules.json"
TASKS = ROOT / "tools/daemon/mock_tasks.json"
SPEC_TASKS = ROOT / "docs/blueprint/proposals/설계검토_결과/tasks.json"
SCEN = {e[0]: e for e in sc.SCENARIOS}
_CACHE = {}


def results():
    if not _CACHE:
        for e in sc.SCENARIOS:
            _CACHE[e[0]] = dry_run.run_scenario(e, str(RULES), str(TASKS))
    return _CACHE


def raw_rules():
    return json.loads(RULES.read_text(encoding="utf-8"))


def run_fn(fn, rules, tasks=None):
    """Checks of one scenario function; an exception counts as a failed check."""
    rep = sc.Report()
    try:
        fn(rep, rules, str(tasks or TASKS))
    except Exception as exc:  # noqa: BLE001 - a stopped core is a different result
        rep.checks.append({"name": "exception", "expected": None, "actual": repr(exc), "status": sc.FAIL})
    return rep.checks


def failing(checks):
    return [c for c in checks if c["status"] == sc.FAIL]


class ScenarioResults(unittest.TestCase):
    pass


def _make(mid):
    def test(self):
        res = results()[mid]
        self.assertIsNone(res["error"], res["error"])
        self.assertTrue(res["checks"], "scenario produced no checks")
        bad = failing(res["checks"])
        self.assertEqual(bad, [], "\n".join(f"{c['name']}\n  expected {c['expected']}\n  actual   {c['actual']}" for c in bad))
    return test


for _mid, _tid, *_ in sc.SCENARIOS:
    setattr(ScenarioResults, f"test_{_mid}_{_tid.replace('-', '_')}", _make(_mid))


class FencedWriteDedup(unittest.TestCase):
    EVENTS = ("push_requested", "pr_update_requested")

    def ready(self):
        env = MockEnv(str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        lease = env.lease(sc.BASIC)
        request = {k: lease[k] for k in ("lease_id", "lease_generation", "fencing_token", "branch")}
        request.update(envelope_id="WRITE-1", via="daemon", sha="a" * 40, pr_number=3)
        return env, request

    def send(self, env, event, request):
        return env.event(event, sc.BASIC, **copy.deepcopy(request))

    def test_replay_is_a_noop_even_after_core_restart(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                before = env.task(sc.BASIC)
                first = self.send(env, event, request)
                self.assertTrue(first["accepted"] and first["written"])
                seen = env.task(sc.BASIC)["inbox_seen"]
                self.assertEqual(len(seen), len(before["inbox_seen"]) + 1)
                env.new_core()
                m = sc.mark(env)
                again = self.send(env, event, request)
                self.assertEqual((again["accepted"], again["written"], again["noop"], again["reason"]),
                                 (False, False, "envelope_duplicate_delivery", "duplicate"))
                self.assertEqual(env.task(sc.BASIC)["inbox_seen"], seen)
                self.assertEqual(len(env.ports.remote.writes), 1)
                self.assertEqual(sc.tr(env.journal()[m:]), [])
                self.assertEqual(sc.se(env.journal(), "execute_write"), ["execute_write"])

    def test_distinct_ids_are_independent_writes(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                self.assertTrue(self.send(env, event, request)["written"])
                request["envelope_id"] = "WRITE-2"
                self.assertTrue(self.send(env, event, request)["written"])
                self.assertEqual(len(env.ports.remote.writes), 2)

    def test_dispatch_rejects_lease_replaced_ended_or_expired_after_commit(self):
        from daemon.runner_verify.adapters import FileStore, PushRemote
        from daemon.runner_verify.common import Layout
        for event in self.EVENTS:
            for backend in ("memory", "file"):
                for change in ("replace", "end", "expire"):
                    with self.subTest(event=event, backend=backend, change=change), tempfile.TemporaryDirectory() as tmp:
                        env, request = self.ready()
                        layout = Layout(tmp).make()
                        if backend == "file":
                            store = FileStore(layout)
                            with store.transaction() as d:
                                d.update(env.snap())
                            env.ports.store = store
                        # Exercise the real push adapter with a Git spy, never a Git/network write.
                        git, credentials = mock.Mock(), mock.Mock()
                        git._git.return_value.returncode = 0
                        env.ports.remote = PushRemote(layout, git, credentials)
                        after_commit = env.core._after_commit

                        def interleave(out):
                            if out.get("writes"):
                                if change == "replace":
                                    env.builder_for(sc.BASIC).send_result(env.instr(sc.BASIC), "failed_tests")
                                    self.assertEqual(env.lease(sc.BASIC)["lease_generation"], 2)
                                elif change == "end":
                                    env.event("owner_cancelled", sc.BASIC)
                                    self.assertNotEqual(env.lease(sc.BASIC)["status"], "active")
                                else:
                                    env.clock.set(env.lease(sc.BASIC)["expires_at"] + 1)
                                credentials.entry.return_value = {
                                    "lease_id": env.lease(sc.BASIC)["lease_id"], "token": "fixture-credential"}
                            after_commit(out)

                        with mock.patch.object(env.core, "_after_commit", side_effect=interleave):
                            out = self.send(env, event, request)
                        self.assertEqual((out["accepted"], out["written"], out["noop"], out["return_code"]),
                                         (False, False, "late_envelope_rejected", "R-11"))
                        git._git.assert_not_called()
                        credentials.entry.assert_not_called()
                        self.assertFalse((layout.root / "remote_writes.jsonl").exists())
                        self.assertEqual(sc.se(env.journal(), "execute_write"), [])
                        self.assertFalse(self.send(env, event, request)["written"])

    def test_push_adapter_requires_the_requests_lease_credential(self):
        from daemon.core.ports import PushFailed
        from daemon.runner_verify.adapters import PushRemote
        from daemon.runner_verify.common import Layout
        for entry in (None, {"lease_id": "other", "token": "fixture-other"},
                      {"lease_id": "L1", "token": "fixture-revoked", "revoked_ns": 1}):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as tmp:
                git, credentials = mock.Mock(), mock.Mock()
                git._git.return_value.returncode = 0
                credentials.entry.return_value = entry
                remote = PushRemote(Layout(tmp).make(), git, credentials)
                with self.assertRaises(PushFailed):
                    remote.execute("push", sc.BASIC, {"lease_id": "L1", "sha": "a" * 40, "branch": "task/mock"})
                git._git.assert_not_called()

        with tempfile.TemporaryDirectory() as tmp:
            git, credentials = mock.Mock(), mock.Mock()
            git._git.return_value.returncode = 0
            credentials.entry.return_value = {"lease_id": "L1", "token": "fixture-current"}
            remote = PushRemote(Layout(tmp).make(), git, credentials)
            remote.execute("push", sc.BASIC, {"lease_id": "L1", "sha": "a" * 40, "branch": "task/mock"})
            self.assertEqual(git._git.call_args.kwargs["env"]["RV_PUSH_CREDENTIAL"], "fixture-current")

    def test_dispatch_serializes_lease_replacement_through_remote_execution(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from daemon.core import DaemonCore
        from daemon.runner_verify.adapters import FileStore
        from daemon.runner_verify.common import Layout
        for event in self.EVENTS:
            for backend in ("memory", "file"):
                with self.subTest(event=event, backend=backend), tempfile.TemporaryDirectory() as tmp:
                    env, request = self.ready()
                    if backend == "file":
                        layout = Layout(tmp).make()
                        store = FileStore(layout)
                        with store.transaction() as d:
                            d.update(env.snap())
                        env.ports.store = store
                    ports = copy.copy(env.ports)
                    if backend == "file":
                        ports.store = FileStore(layout)  # independent adapter, same flock
                    other_core = DaemonCore(env.rules, ports)
                    result = env.builder_for(sc.BASIC).result_envelope(env.instr(sc.BASIC), "failed_tests")
                    started, release, attempting, replaced = Event(), Event(), Event(), Event()
                    execute = env.ports.remote.execute

                    def write(*args):
                        started.set()
                        self.assertTrue(release.wait(timeout=10))
                        self.assertEqual(env.lease(sc.BASIC)["lease_generation"], request["lease_generation"])
                        execute(*args)

                    def replace():
                        attempting.set()
                        out = other_core.submit_envelope(sc.BASIC, "result", result)
                        replaced.set()
                        return out

                    with mock.patch.object(env.ports.remote, "execute", side_effect=write), ThreadPoolExecutor(max_workers=2) as pool:
                        sending = pool.submit(self.send, env, event, request)
                        try:
                            self.assertTrue(started.wait(timeout=10))
                            replacing = pool.submit(replace)
                            self.assertTrue(attempting.wait(timeout=10))
                            self.assertFalse(replaced.wait(timeout=0.1), "lease replaced during remote execution")
                        finally:
                            release.set()
                        self.assertTrue(sending.result(timeout=10)["written"])
                        self.assertTrue(replacing.result(timeout=10)["accepted"])
                    self.assertEqual(env.lease(sc.BASIC)["lease_generation"], 2)
                    self.assertEqual(len(env.ports.remote.writes), 1)

    def test_file_dispatch_guard_blocks_another_process_without_a_transaction(self):
        import subprocess
        from daemon.runner_verify.adapters import FileStore
        from daemon.runner_verify.common import Layout
        with tempfile.TemporaryDirectory() as tmp:
            store = FileStore(Layout(tmp).make())
            with store.transaction() as d:
                d["tasks"]["probe"] = "before"
            source = ("import sys\n"
                      f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
                      "from daemon.runner_verify.adapters import FileStore\n"
                      "from daemon.runner_verify.common import Layout\n"
                      f"store = FileStore(Layout({tmp!r}))\n"
                      "print('attempting', flush=True)\n"
                      "with store.transaction() as d: d['tasks']['probe'] = 'after'\n")
            process = None
            try:
                with store.dispatch_guard() as d:
                    self.assertEqual(d["tasks"]["probe"], "before")
                    d["tasks"]["probe"] = "snapshot-only"
                    process = subprocess.Popen([sys.executable, "-I", "-c", source], stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, text=True)
                    self.assertEqual(process.stdout.readline().strip(), "attempting")
                    with self.assertRaises(subprocess.TimeoutExpired):
                        process.communicate(timeout=0.1)
                    self.assertEqual(store.snapshot()["tasks"]["probe"], "before")
                _, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(store.snapshot()["tasks"]["probe"], "after")
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()

    def test_missing_identity_is_rejected_without_marking_seen(self):
        for event in self.EVENTS:
            for field in ("envelope_id", "lease_id", "lease_generation", "fencing_token"):
                for value in (None, "absent"):
                    with self.subTest(event=event, field=field, value=value):
                        env, request = self.ready()
                        before = env.task(sc.BASIC)
                        request.pop(field)
                        if value is None:
                            request[field] = None
                        out = self.send(env, event, request)
                        self.assertEqual((out["accepted"], out["written"], out["return_code"]), (False, False, "R-13"))
                        self.assertEqual(env.task(sc.BASIC), before)
                        self.assertEqual(env.ports.remote.writes, [])

    def test_remote_observes_committed_identity_and_transition_outside_transaction(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                before = env.task(sc.BASIC)
                transaction = env.store.transaction
                active = []

                @contextlib.contextmanager
                def tracked():
                    with transaction() as d:
                        active.append(True)
                        try:
                            yield d
                        finally:
                            active.pop()

                def execute(kind, task_id, payload):
                    self.assertEqual(active, [])
                    self.assertEqual(task_id, sc.BASIC)
                    self.assertEqual(payload, dict(request, kind=kind))
                    committed = env.snap()
                    self.assertEqual(len(committed["tasks"][task_id]["inbox_seen"]), len(before["inbox_seen"]) + 1)
                    self.assertEqual(sc.tr(committed["journal"])[-1], ("building", "building", event))

                with mock.patch.object(env.store, "transaction", tracked), mock.patch.object(env.ports.remote, "execute", side_effect=execute) as remote:
                    self.assertTrue(self.send(env, event, request)["written"])
                    remote.assert_called_once()

    def test_effect_failure_rolls_back_without_remote_write_and_allows_retry(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                before = env.snap()
                with mock.patch.object(env.core.rec, "transition", side_effect=RuntimeError("effect failed")):
                    with self.assertRaisesRegex(RuntimeError, "effect failed"):
                        self.send(env, event, request)
                self.assertEqual(env.snap(), before)
                self.assertEqual(env.ports.remote.writes, [])
                self.assertTrue(self.send(env, event, request)["written"])
                self.assertEqual(len(env.ports.remote.writes), 1)

    def test_commit_failure_never_writes_remote_and_allows_retry(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                before = env.snap()
                transaction = env.store.transaction

                @contextlib.contextmanager
                def fail_commit():
                    with transaction() as d:
                        yield d
                        raise OSError("commit failed")

                with mock.patch.object(env.store, "transaction", fail_commit):
                    with self.assertRaisesRegex(OSError, "commit failed"):
                        self.send(env, event, request)
                self.assertEqual(env.snap(), before)
                self.assertEqual(env.ports.remote.writes, [])
                self.assertTrue(self.send(env, event, request)["written"])

    def test_concurrent_replay_dispatches_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                barrier = Barrier(8)

                def send(_):
                    barrier.wait(timeout=10)
                    return self.send(env, event, request)

                with ThreadPoolExecutor(max_workers=8) as pool:
                    outs = list(pool.map(send, range(8)))
                self.assertEqual(sum(o["written"] for o in outs), 1)
                self.assertEqual(sum(o["noop"] == "envelope_duplicate_delivery" for o in outs), 7)
                self.assertEqual(len(env.ports.remote.writes), 1)

    def test_late_precedes_duplicate_but_duplicate_precedes_expiry(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                self.send(env, event, request)
                env.clock.set(env.lease(sc.BASIC)["expires_at"] + 1)
                out = self.send(env, event, request)
                self.assertEqual(out["noop"], "envelope_duplicate_delivery")
                request["envelope_id"] = "WRITE-NEW"
                out = self.send(env, event, request)
                self.assertEqual((out["noop"], out["return_code"]), ("late_envelope_rejected", "R-11"))
                env, request = self.ready()
                self.send(env, event, request)
                env.builder_for(sc.BASIC).send_result(env.instr(sc.BASIC), "failed_tests")
                out = self.send(env, event, request)
                self.assertEqual((out["noop"], out["return_code"]), ("late_envelope_rejected", "R-11"))
                self.assertEqual(len(env.ports.remote.writes), 1)

    def test_remote_error_keeps_committed_identity_and_does_not_repeat_ambiguous_write(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                execute = env.ports.remote.execute

                def uncertain_write(*args):
                    execute(*args)
                    raise OSError("remote outcome unknown")

                with mock.patch.object(env.ports.remote, "execute", side_effect=uncertain_write) as remote:
                    with self.assertRaisesRegex(OSError, "remote outcome unknown"):
                        self.send(env, event, request)
                    env.new_core()
                    again = self.send(env, event, request)
                    self.assertEqual((again["written"], again["noop"]), (False, "envelope_duplicate_delivery"))
                    remote.assert_called_once()
                self.assertEqual(len(env.ports.remote.writes), 1)
                self.assertEqual(sc.se(env.journal(), "execute_write"), [])

    def test_crash_after_commit_before_dispatch_keeps_intent_without_automatic_resend(self):
        from daemon.core.ports import SimulatedCrash
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                with mock.patch.object(env.core, "_after_commit", side_effect=SimulatedCrash("committed")):
                    with self.assertRaises(SimulatedCrash):
                        self.send(env, event, request)
                self.assertEqual(env.ports.remote.writes, [])
                intents = [r for r in env.journal() if r["kind"] == "intent_record" and r["action"] == "execute_write"]
                self.assertEqual([r["args"]["envelope_id"] for r in intents], [request["envelope_id"]])
                env.new_core()
                self.assertEqual(self.send(env, event, request)["noop"], "envelope_duplicate_delivery")
                self.assertEqual(env.ports.remote.writes, [])

    def test_completion_record_failure_does_not_unclaim_successful_remote_write(self):
        for event in self.EVENTS:
            with self.subTest(event=event):
                env, request = self.ready()
                with mock.patch.object(env.core.rec, "side_effect", side_effect=OSError("completion record failed")):
                    with self.assertRaisesRegex(OSError, "completion record failed"):
                        self.send(env, event, request)
                self.assertEqual(len(env.ports.remote.writes), 1)
                env.new_core()
                self.assertEqual(self.send(env, event, request)["noop"], "envelope_duplicate_delivery")
                self.assertEqual(len(env.ports.remote.writes), 1)

    def test_file_store_releases_transaction_before_dispatch_and_persists_dedup(self):
        from daemon.runner_verify.adapters import FileStore
        from daemon.runner_verify.common import Layout
        for event in self.EVENTS:
            with self.subTest(event=event), tempfile.TemporaryDirectory() as tmp:
                env, request = self.ready()
                store = FileStore(Layout(tmp).make())
                with store.transaction() as d:
                    d.update(env.snap())
                env.ports.store = store
                execute = env.ports.remote.execute

                def write(*args):
                    # The committed snapshot is readable, but mutations must wait until dispatch finishes.
                    self.assertEqual(len(store.snapshot()["tasks"][sc.BASIC]["inbox_seen"]), 2)
                    with self.assertRaises(RuntimeError):
                        with store.transaction():
                            pass
                    execute(*args)

                with mock.patch.object(env.ports.remote, "execute", side_effect=write):
                    self.assertTrue(self.send(env, event, request)["written"])
                env.new_core()
                self.assertEqual(self.send(env, event, request)["noop"], "envelope_duplicate_delivery")
                self.assertEqual(len(env.ports.remote.writes), 1)


class Coverage(unittest.TestCase):
    def test_test_ids_are_the_ones_in_tasks_json(self):
        tasks = json.loads(SPEC_TASKS.read_text(encoding="utf-8"))["tasks"]
        required = [t for t in tasks if t["id"] == "T-OP-00"][0]["required_test_ids"]
        mock = json.loads(TASKS.read_text(encoding="utf-8"))["t_op_00_required_test_ids"]
        self.assertEqual(mock, required)
        implemented = [(e[0], e[1]) for e in sc.SCENARIOS]
        self.assertEqual(dry_run.coverage(required, implemented), {"not_run": [], "unlisted": [], "repeated": []})
        # the same equality without the helper: the scenario test ids are the required list, each once
        self.assertEqual(sorted(t for m, t in implemented if m != "STATIC" and t != "-"), sorted(required))
        self.assertEqual(len(required), 33)

    def test_every_prose_test_line_has_a_passing_scenario(self):
        """Each '시험 <id>(Mxx): ...' line of tasks.json is a description, not a command: it maps to the scenario
        selected by `dry_run.py --scenario <id>`, to the unittest method of that scenario, and the scenario passes."""
        tasks = json.loads(SPEC_TASKS.read_text(encoding="utf-8"))["tasks"]
        node = [t for t in tasks if t["id"] == "T-OP-00"][0]
        prose = [re.match(r"시험 ([a-z0-9-]+)(?:\((M\d+[ab]?)\b)?", line) for line in node["tests"]
                 if line.startswith("시험 ")]
        self.assertTrue(prose and all(prose))
        self.assertEqual(sorted(m.group(1) for m in prose), sorted(node["required_test_ids"]))
        for m in prose:
            tid, mid = m.group(1), m.group(2)
            with self.subTest(test_id=tid):
                [entry] = dry_run.select(tid)
                if mid:
                    self.assertEqual(entry[0], mid, "the M number in the prose line is the scenario run")
                self.assertTrue(hasattr(ScenarioResults, f"test_{entry[0]}_{tid.replace('-', '_')}"))
                res = results()[entry[0]]
                self.assertEqual(dry_run.scenario_status(res), "PASS", tid)

    def test_every_m_number_of_05_runs(self):
        ids = {e[0] for e in sc.SCENARIOS}
        self.assertEqual({f"M{n}" for n in range(1, 45)} - ids, set())
        self.assertLessEqual({"M10a", "M10b", "M18a", "M18b"}, ids)

    def test_dry_run_reports_all_required_ids_run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = dry_run.main(["--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "all", "--quiet",
                                 "--require-all"])
        self.assertEqual(code, 0, buf.getvalue()[-3000:])
        self.assertIn("실행하지 않은 것 0개", buf.getvalue())
        self.assertIn("검사", buf.getvalue())
        self.assertIn("실패 0건, 명세 공백 표시 0건", buf.getvalue())

    def test_every_scenario_prints_expected_and_actual(self):
        for mid, res in results().items():
            for c in res["checks"]:
                self.assertIn("expected", c)
                self.assertIn("actual", c)
                self.assertIn(c["status"], (sc.PASS, sc.FAIL, sc.GAP))

    def test_gaps_are_listed_with_field_status_and_need(self):
        from daemon.spec_gaps import SPEC_GAPS, RESOLVED, PARTLY, OPEN, NEW
        self.assertGreater(len(SPEC_GAPS), 0)
        ids = [g["id"] for g in SPEC_GAPS]
        self.assertEqual(len(ids), len(set(ids)))
        for g in SPEC_GAPS:
            self.assertTrue(g["field"] and g["need"] and g["where"])
            self.assertIn(g["status"], (RESOLVED, PARTLY, OPEN, NEW))
            if g["status"] in (RESOLVED, PARTLY):
                self.assertTrue(g.get("resolved_by"), g["id"])
        # the 28 gaps reported first are all accounted for
        self.assertEqual([f"G{n:02d}" for n in range(1, 29)], [i for i in ids if int(i[1:]) <= 28])
        gap_checks = [c for r in results().values() for c in r["checks"] if c["status"] == sc.GAP]
        self.assertTrue(all(c.get("note") for c in gap_checks))
        self.assertEqual(gap_checks, [], "no scenario carries a gap mark after G29-G50 (t_op_00_followups)")

    def test_g29_to_g50_are_read_by_the_core(self):
        """spec_gaps: G29-G50 resolved and read by the core, except G47 (its read-list entry is in daemon_rules.json,
        outside this task's paths). gap_resolutions[].mock_core_reads describes the core before this change."""
        from daemon.spec_gaps import SPEC_GAPS, RESOLVED, PARTLY
        gaps = {g["id"]: g for g in SPEC_GAPS}
        for n in range(29, 51):
            g = gaps[f"G{n}"]
            if g["id"] == "G47":
                self.assertEqual((g["status"], g["core_reads"]), (PARTLY, "partly"))
                self.assertIn("envelopes.instruction.limits", g["remaining"])
                self.assertNotIn("envelopes.instruction.limits", raw_rules()["core_contract"]["reads"])
            else:
                self.assertEqual((g["status"], g["core_reads"]), (RESOLVED, "yes"), g["id"])
        self.assertEqual(sorted(Rules.token_log), [], "no token was pulled out of a sentence")

    def test_outside_reads_are_reported_gaps(self):
        from daemon.core.rules import OUTSIDE_READS
        from daemon.spec_gaps import SPEC_GAPS, NEW
        open_ids = {g["id"] for g in SPEC_GAPS if g["status"] == NEW}
        for path, gap in OUTSIDE_READS.items():
            self.assertIn(gap, open_ids, path)
            self.assertNotIn(path, raw_rules()["core_contract"]["reads"])
        rules = Rules(raw_rules())
        from daemon.core.ports import SpecGap
        with self.assertRaises(SpecGap):
            rules.outside("roles")


class StructuredFieldsOnly(unittest.TestCase):
    def test_view_has_no_explanation_keys(self):
        def walk(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    self.assertFalse(k in ("when", "note") or k.startswith("_"), f"{path}/{k}")
                    walk(v, f"{path}/{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
        walk(Rules(raw_rules()).view)

    def test_structured_when_of_noop_rules_is_kept_as_cond(self):
        rules = Rules(raw_rules())
        raw = raw_rules()["noop_rules"]
        self.assertEqual(len(rules.noop_rules), len(raw))
        for r, orig in zip(rules.noop_rules, raw):
            self.assertEqual(r["cond"], orig["when"])
            self.assertNotIn("when", r)
            self.assertNotIn("note", r)

    def test_view_is_a_subset_of_the_read_list(self):
        raw = raw_rules()
        rules = Rules(raw)
        self.assertEqual(rules.unmatched_reads, [])
        view = rules.view
        tops = {e.replace("[]", "").split(".")[0] for e in raw["core_contract"]["reads"]}
        self.assertEqual(set(view) - tops, set())
        self.assertIn("switch_policy.allowed_sources", raw["core_contract"]["reads"])  # G32: no extension list
        self.assertEqual(set(view["concurrency"]), {"lease", "fencing", "lease_end", "lease_issue", "quiescence",
                                                    "idempotency_key", "max_parallel_leases", "branch_naming"})
        self.assertEqual(set(view["concurrency"]["fencing"]), {"on_lease_end"})
        self.assertEqual(set(view["handoff_failure_policy"]),
                         {"max_attempts", "attempt_counting", "retry_detail", "restart_resume", "always_revoke"})
        self.assertEqual(set(view["hard_stop"]), {"grace_s", "trigger"})
        self.assertEqual(set(view["preserve_manifest"]), {"function", "excludes", "secret_patterns"})
        self.assertEqual(set(view["switch_policy"]), {"allowed_sources"})
        for name, body in view["envelopes"].items():
            self.assertEqual(set(body), {"required"}, name)
        for tr in view["transitions"]:
            self.assertEqual(set(tr) - {"from", "to", "event", "guard", "cond", "side_effects", "return_code", "on_cond_fail"}, set())
        for rc in view["return_codes"]:
            self.assertEqual(set(rc), {"code"})
        self.assertEqual(len(view["transitions"]), len(raw["transitions"]))

    def test_read_patterns_expand(self):
        from daemon.core.rules import expand_pattern
        seqs = expand_pattern("transitions[].{from,to}")
        self.assertEqual(seqs, [[("key", "transitions"), ("each",), ("key", "from")],
                                [("key", "transitions"), ("each",), ("key", "to")]])
        self.assertEqual(len(expand_pattern("concurrency.{lease,fencing.on_lease_end}")), 2)
        self.assertEqual(expand_pattern("envelopes.*.required"), [[("key", "envelopes"), ("all",), ("key", "required")]])

    def test_replacing_or_deleting_explanation_keys_changes_nothing(self):
        base = {mid: [(c["name"], c["status"], c["actual"]) for c in r["checks"]] for mid, r in results().items() if mid != "STATIC"}
        for mode in ("garble", "drop"):
            alt = sc.perturb(raw_rules(), mode)
            self.assertNotEqual(alt, raw_rules())
            for mid, e in SCEN.items():
                if mid == "STATIC":
                    continue
                got = [(c["name"], c["status"], c["actual"]) for c in run_fn(e[3], alt)]
                self.assertEqual(got, base[mid], f"{mode} {mid}")

    def test_names_without_a_root_are_errors_not_literals(self):
        from daemon.core.gate_evaluator import Ctx
        from daemon.core.ports import SpecGap
        ctx = Ctx(Rules(raw_rules()), {"event": {"at": 1}})
        self.assertEqual(ctx.value("active"), "active")
        self.assertEqual(ctx.value("R-08"), "R-08")
        self.assertEqual(ctx.value("daemon"), "daemon")
        self.assertEqual(ctx.value("event.at + 2"), 3)
        self.assertEqual(ctx.value("coalesce(event.nothing, event.at) * 2"), 2)
        with self.assertRaises(SpecGap):
            ctx.value("no_such_root.field")
        with self.assertRaises(SpecGap):
            ctx.value("hard_stop.no_such_field")


def _mutated(fn):
    raw = raw_rules()
    fn(raw)
    return raw


def _transition(raw, frm, event, to=None):
    return [t for t in raw["transitions"] if t["from"] == frm and t["event"] == event and (to is None or t["to"] == to)][0]


class StructuredExpiryEvents(unittest.TestCase):
    def expired_env(self, raw, state):
        env = MockEnv(raw, str(TASKS))
        if state == "building":
            env.bring_to_building(sc.BASIC)
        else:
            env.start_task(sc.BASIC)
            self.assertEqual(sc.crash_after_issue(env, sc.BASIC), "issue_lease:committed")
        env.clock.advance(raw["concurrency"]["lease"]["heartbeat_s"] * 2)
        return env

    def test_read_list_exposes_structured_expiry_fields_without_prose(self):
        raw = raw_rules()
        self.assertIn("state_integrity.normal_expiry.events", raw["core_contract"]["reads"])
        view = Rules(raw).get("state_integrity.normal_expiry")
        self.assertEqual(set(view), {"detect", "events_by_state", "events"})
        self.assertEqual(view["events"], raw["state_integrity"]["normal_expiry"]["events"])

    def test_restart_uses_structured_events_when_path_is_changed_or_missing(self):
        for mode in ("garble", "drop"):
            for state, target, event in (("leased", "queued", "lease_expired"),
                                         ("building", "returned", "heartbeat_missed_twice")):
                with self.subTest(mode=mode, state=state):
                    raw = raw_rules()
                    expiry = raw["state_integrity"]["normal_expiry"]
                    if mode == "drop":
                        del expiry["path"]
                    else:
                        expiry["path"] = "unrelated prose (state_corrupted) (owner_stop)"
                    expiry["events"].reverse()
                    env = self.expired_env(raw, state)
                    before = len(env.journal())
                    sent = sc.sent_ids(env)
                    env.restart()
                    self.assertEqual(sc.tr(env.journal()[before:]), [(state, target, event)])
                    self.assertEqual(env.lease(sc.BASIC)["status"], "expired")
                    self.assertEqual(env.task(sc.BASIC)["lease_generation"], 1)
                    self.assertEqual(sc.sent_ids(env), sent)
                    if state == "leased":
                        pending = env.task(sc.BASIC)["outbox"][0]
                        self.assertEqual((pending["status"], pending["void_reason"]), ("void", "expired"))
                    before = len(env.journal())
                    env.restart()
                    self.assertEqual(sc.tr(env.journal()[before:]), [])
                    self.assertEqual(sc.sent_ids(env), sent)

    def test_removing_an_event_disables_its_expiry_classification_only(self):
        from daemon.core import recovery
        for removed, other in (("lease_expired", "heartbeat_missed_twice"),
                               ("heartbeat_missed_twice", "lease_expired")):
            raw = raw_rules()
            expiry = raw["state_integrity"]["normal_expiry"]
            expiry["events"].remove(removed)
            for state, event in expiry["events_by_state"].items():
                with self.subTest(removed=removed, state=state):
                    env = self.expired_env(raw, state)
                    self.assertEqual(recovery.normal_expiry_due(env.core, env.snap(), sc.BASIC), event == other)

    def test_missing_events_is_a_contract_error_without_prose_fallback(self):
        from daemon.core import recovery
        from daemon.core.ports import SpecGap
        raw = raw_rules()
        del raw["state_integrity"]["normal_expiry"]["events"]
        with self.assertRaisesRegex(SpecGap, "state_integrity.normal_expiry.events"):
            env = self.expired_env(raw, "leased")
            recovery.normal_expiry_due(env.core, env.snap(), sc.BASIC)


class BehaviorComesFromData(unittest.TestCase):
    """Changing one structured field must make the scenario that depends on it fail; separate hard-coded logic
    would not notice."""

    def assertBreaks(self, scenario, fn, msg=""):
        bad = failing(run_fn(scenario, _mutated(fn)))
        self.assertNotEqual(bad, [], msg or "the scenario did not notice the change")

    def test_baseline_is_clean(self):
        for fn in (sc.m26, sc.m41, sc.m42):
            self.assertEqual(failing(run_fn(fn, raw_rules())), [])

    def test_resend_checks_are_read_from_data(self):
        def f(raw):
            raw["core_contract"]["operations"]["resend_outbox"]["checks"] = raw["core_contract"]["operations"]["resend_outbox"]["checks"][:1]
        self.assertBreaks(sc.m42, f)

    def test_resend_on_fail_effects_are_read_from_data(self):
        def f(raw):
            raw["core_contract"]["operations"]["resend_outbox"]["on_fail"]["revoked_or_cancelled"]["effects"] = []
        self.assertBreaks(sc.m42, f)

    def test_handoff_order_is_read_from_data(self):
        def f(raw):
            seq = raw["handoff_sequence"]
            i, j = seq.index("confirm_quiescent"), seq.index("preserve")
            seq[i], seq[j] = seq[j], seq[i]
        self.assertBreaks(sc.m33, f)
        self.assertBreaks(sc.m29, f)

    def test_max_attempts_are_read_from_data(self):
        self.assertBreaks(sc.m37, lambda raw: raw["handoff_failure_policy"]["max_attempts"].update(quiescence_failed=2))

    def test_attempt_comparison_is_read_from_data(self):
        def f(raw):
            _transition(raw, "handoff", "quiescence_failed", "handoff")["cond"][0]["op"] = "<"
        self.assertBreaks(sc.m37, f)

    def test_expiry_condition_is_read_from_data(self):
        def f(raw):
            _transition(raw, "leased", "lease_expired")["cond"][1]["value"] = "lease_record.issued_at + concurrency.lease.heartbeat_s*100000"
        self.assertBreaks(sc.m41, f)

    def test_heartbeat_interval_is_read_from_data(self):
        self.assertBreaks(sc.m41, lambda raw: raw["concurrency"]["lease"].update(heartbeat_s=100))

    def test_transition_target_is_read_from_data(self):
        self.assertBreaks(sc.m41, lambda raw: _transition(raw, "leased", "lease_expired").update(to="returned"))

    def test_corruption_effects_are_read_from_data(self):
        def f(raw):
            effs = _transition(raw, "*", "state_corrupted")["side_effects"]
            effs[:] = [e for e in effs if e["id"] != "void_outbox"]
        self.assertBreaks(sc.m44, f)

    def test_corruption_detect_is_read_from_data(self):
        def f(raw):
            raw["state_integrity"]["corruption"]["detect"] = raw["state_integrity"]["corruption"]["detect"][2:]
        self.assertBreaks(sc.m44, f)

    def test_always_revoke_list_is_read_from_data(self):
        self.assertBreaks(sc.m37, lambda raw: raw["handoff_failure_policy"].update(always_revoke=["builder_write_credential", "builder_token"]))

    def test_noop_names_must_be_listed(self):
        self.assertBreaks(sc.m34, lambda raw: raw["noop_events"].remove("envelope_duplicate_delivery"))

    def test_noop_rules_are_read_from_data(self):
        def f(raw):
            raw["noop_rules"] = [r for r in raw["noop_rules"] if r["event"] != "lease_granted"]
        self.assertBreaks(sc.m40, f)

    def test_accept_envelope_check_order_is_read_from_data(self):
        def f(raw):
            checks = raw["core_contract"]["operations"]["accept_envelope"]["checks_in_order"]
            ids = [c["id"] for c in checks]
            checks.insert(ids.index("lease_matches"), checks.pop(ids.index("not_seen")))
        self.assertBreaks(sc.m35, f)

    def test_accept_envelope_on_fail_is_read_from_data(self):
        def f(raw):
            raw["core_contract"]["operations"]["accept_envelope"]["on_fail"]["late"]["return_code"] = None
        self.assertBreaks(sc.m28, f)

    def test_lease_guards_are_read_from_data(self):
        def f(raw):
            raw["lease_guards"] = [g for g in raw["lease_guards"] if g["id"] != "usage_slot_ready"]
        self.assertBreaks(sc.m26, f)
        self.assertBreaks(sc.m30, f)

    def test_parallel_limit_is_read_from_data(self):
        self.assertBreaks(sc.m30, lambda raw: raw["concurrency"].update(max_parallel_leases=5))

    def test_retry_limit_is_read_from_data(self):
        self.assertBreaks(sc.m26, lambda raw: raw["retry_limits"].update(consecutive_failed_tests=2))

    def test_return_code_of_a_row_is_read_from_data(self):
        def f(raw):
            row = _transition(raw, "building", "result_failed_tests", "returned")
            row["return_code"] = "R-07"
            for e in row["side_effects"]:
                if e["id"] == "record_r_code":
                    e["args"]["code"] = "R-07"
        self.assertBreaks(sc.m26, f)

    def test_max_wall_s_cond_is_read_from_data(self):
        def f(raw):
            row = _transition(raw, "building", "hard_stop_deadline")
            row["cond"][0]["value"][1]["value"] = "lease_record.issued_at + instruction.limits.max_wall_s + 5"
        self.assertBreaks(sc.m26, f)

    def test_on_lease_end_is_read_from_data(self):
        self.assertBreaks(sc.m41, lambda raw: raw["concurrency"]["fencing"].update(on_lease_end=["revoke_write_credential", "revoke_token", "record_handoff"]))

    def test_issue_lease_atomic_effects_are_read_from_data(self):
        def f(raw):
            effs = raw["core_contract"]["operations"]["issue_lease"]["effects_atomic"]
            effs[:] = [e for e in effs if e["id"] != "create_outbox"]
        self.assertBreaks(sc.m40, f)

    def test_issue_reason_of_a_row_is_read_from_data(self):
        def f(raw):
            _transition(raw, "ci_failed", "lease_granted")["side_effects"][0]["args"]["reason"] = "retry_review"
        self.assertBreaks(sc.m35, f)

    def test_restart_resume_is_read_from_data(self):
        def f(raw):
            raw["handoff_failure_policy"]["restart_resume"]["confirm_quiescent"] = "confirm_quiescent"
        self.assertBreaks(sc.m38, f)

    def test_secret_patterns_are_read_from_data(self):
        self.assertBreaks(sc.m36, lambda raw: raw["preserve_manifest"]["secret_patterns"].update(patterns=["never-matches-anything"]))

    def test_manifest_excludes_are_read_from_data(self):
        self.assertBreaks(sc.m36, lambda raw: raw["preserve_manifest"].update(excludes=[e for e in raw["preserve_manifest"]["excludes"] if e != "target/"]))

    def test_usage_fields_to_record_are_read_from_data(self):
        def f(raw):
            raw["usage_recording"]["record_after_result"] = ["calls", "wall_s"]
        self.assertBreaks(sc.m26, f)

    def test_the_read_list_is_what_the_core_reads(self):
        for entry in ("retry_limits", "usage_recording", "lease_guards[]"):
            def f(raw, entry=entry):
                raw["core_contract"]["reads"].remove(entry)
            self.assertBreaks(sc.m26, f, entry)

    def test_a_read_list_entry_without_a_field_stops_the_core(self):
        def f(raw):
            raw["core_contract"]["reads"].append("no_such_top_level_field")
        self.assertBreaks(sc.m41, f)

    def test_no_cost_cap_in_rules_or_core_and_a_cap_would_be_noticed(self):
        self.assertEqual(static_checks.no_cost_cap(raw_rules(), TASKS), [])
        raw = raw_rules()
        raw["events"].append("budget_exhausted")
        self.assertNotEqual(static_checks.no_cost_cap(raw, TASKS), [])

    def test_usage_is_recorded_whatever_the_amount(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        env.builder_for(sc.BASIC).send_result(env.instr(sc.BASIC), "failed_tests", cost_units=10 ** 30, calls=10 ** 12, wall_s=10 ** 9)
        env.run_builders("first_heartbeat")
        self.assertEqual((env.state(sc.BASIC), env.task(sc.BASIC)["lease_generation"]), ("building", 2))
        rows = env.snap()["usage_record"]
        self.assertEqual((rows[0]["cost_units"], rows[0]["calls"]), (10 ** 30, 10 ** 12))
        self.assertEqual([r["return_code"] for r in env.journal() if r["kind"] == "return_record"], [])


# ---------------------------------------------------------------- t_op_00_followups.tests_to_add
def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path + "." + k, k, v
            yield from _walk(v, path + "." + k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def _resolve(raw, path):
    """'a.b[k=v,k2=v2].c' -> the value, or raise KeyError."""
    import re
    cur = raw
    for seg in re.findall(r"[^.\[]+(?:\[[^\]]*\])?", path):
        m = re.fullmatch(r"([^\[]+)(?:\[([^\]]*)\])?", seg)
        key, sel = m.group(1), m.group(2)
        cur = cur[key]
        if sel:
            want = dict(x.split("=", 1) for x in sel.split(","))
            hits = [x for x in cur if all(str(x.get(k)) == v for k, v in want.items())]
            if not hits:
                raise KeyError(path)
            cur = hits[0]
    return cur


def _rows(raw, frm=None, event=None, to=None):
    return [t for t in raw["transitions"] if (frm is None or t["from"] == frm) and (event is None or t["event"] == event)
            and (to is None or t["to"] == to)]


def _effect_ids(row):
    return [e["id"] for e in row.get("side_effects", [])]


_COMPLEMENT = {("==", "!="), ("!=", "=="), ("<=", ">"), (">", "<="), ("<", ">="), (">=", "<")}


def _exclusive(a, b):
    """Two conds cannot both hold: a shared field with complementary ops on the same value, or == on different values."""
    for p in a.get("cond") or []:
        for q in b.get("cond") or []:
            if p["field"] != q["field"]:
                continue
            if (p["op"], q["op"]) in _COMPLEMENT and p["value"] == q["value"]:
                return True
            if p["op"] == q["op"] == "==" and p["value"] != q["value"]:
                return True
    return False


class FollowupStructure(unittest.TestCase):
    """tests_to_add.structure: consistency of the file itself (no core)."""

    def setUp(self):
        self.raw = raw_rules()

    def test_g29_scope_in_the_expressions_and_overlap_of_nested_globs(self):
        from daemon.core.gate_evaluator import intersects, patterns_overlap
        guards = {g["id"]: g for g in self.raw["lease_guards"]}
        for gid in ("no_conflict_lease", "single_writer", "max_parallel_leases"):
            self.assertIn("task_id != this.task_id", guards[gid]["check"]["field"], gid)
        swl = [d for d in self.raw["state_integrity"]["corruption"]["detect"] if d["id"] == "state_without_lease"][0]
        self.assertTrue(any("task_id == this.task_id" in p["field"] for p in swl["pred"]))
        self.assertEqual(guards["no_conflict_lease"]["conflict_match"]["relation"], "patterns_overlap")
        self.assertTrue(patterns_overlap("services/knowledge/**", "services/knowledge/release/**"))
        self.assertFalse(patterns_overlap("services/knowledge/**", "services/knowledge2/**"))
        tasks = json.loads(SPEC_TASKS.read_text(encoding="utf-8"))["tasks"]
        nested = [(a["id"], b["id"]) for a in tasks for b in tasks if a["id"] < b["id"]
                  and intersects(a.get("conflict_paths") or [], b.get("conflict_paths") or [], "patterns_overlap")
                  and not set(a.get("conflict_paths") or []) & set(b.get("conflict_paths") or [])]
        self.assertTrue(nested, "tasks.json has nested conflict_paths that only the pattern relation sees")

    def test_g30_recovery_rows_are_exclusive_and_write_phases(self):
        rows = _rows(self.raw, "handoff_blocked", "recovery_decision", "handoff")
        self.assertEqual(len(rows), 2)
        self.assertTrue(_exclusive(rows[0], rows[1]))
        enum = self.raw["core_contract"]["store"]["enums"]["handoff_record_phase"]
        stages = [k for k in self.raw["handoff_failure_policy"]["restart_resume"] if not k.startswith("_")]
        for row in self.raw["transitions"]:
            for e in row.get("side_effects", []):
                if e["id"] == "set_handoff_field" and e["args"]["field"] == "phase":
                    self.assertIn(e["args"]["value"], enum)
                    self.assertIn(e["args"]["value"], stages)
        self.assertEqual(set(enum) - {None}, set(stages))

    def test_g31_restart_resume_forms(self):
        rr = self.raw["handoff_failure_policy"]["restart_resume"]
        stages = [k for k in rr if not k.startswith("_")]
        self.assertEqual(stages, ["stop", "isolate", "confirm_quiescent", "preserve", "preserve_remote", "revoke_token",
                                  "issue_next_lease"])
        for k in stages:
            v = rr[k]
            if isinstance(v, str):
                self.assertIn(v, stages)
                continue
            self.assertEqual(set(v), {"check", "then", "else"}, k)
            for branch in (v["then"], v["else"]):
                (kind, target), = [(x, branch[x]) for x in ("stage", "event", "noop") if x in branch]
                if kind == "stage":
                    self.assertIn(target, stages)
                elif kind == "event":
                    self.assertIn(target, self.raw["events"])

    def test_g32_g33_read_list_and_condition_keys(self):
        self.assertIn("switch_policy.allowed_sources", self.raw["core_contract"]["reads"])
        for r in self.raw["noop_rules"]:
            self.assertTrue(isinstance(r["when"], list) and all({"field", "op", "value"} <= set(x) for x in r["when"]))
        for path, key, v in _walk(self.raw):
            if key == "when" and not path.startswith(".noop_rules") and isinstance(v, list):
                self.fail(f"a predicate-list `when` outside noop_rules: {path}")

    def test_g34_to_g36_lease_end_and_credentials(self):
        enum = set(self.raw["core_contract"]["store"]["enums"]["lease_record_status"])
        le = self.raw["concurrency"]["lease_end"]
        written = {e["args"]["status"] for t in self.raw["transitions"] for e in t.get("side_effects", []) if e["id"] == "end_lease"}
        self.assertLessEqual(written, enum)
        with_end = {(t["from"], t["to"], t["event"]) for t in self.raw["transitions"] if "end_lease" in _effect_ids(t)}
        listed = [tuple(x) for x in le["transitions"]]
        for frm, to, ev in with_end:
            self.assertTrue(any(f == frm and t2 == to and e in (ev, "*") for f, t2, e in listed), (frm, to, ev))
        for f, t2, e in listed:
            self.assertTrue(any(fr == f and to == t2 and (e == "*" or ev == e) for fr, to, ev in with_end), (f, t2, e))
        table = self.raw["core_contract"]["expected_outputs"]["credential_of_effect"]
        self.assertEqual(sorted(table.values()), sorted(self.raw["handoff_failure_policy"]["always_revoke"]))
        self.assertEqual(len(set(table.values())), len(table))

    def test_g37_leaving_an_active_lease_ends_it(self):
        le = self.raw["concurrency"]["lease_end"]
        active = set(le["active_lease_states"])
        exceptions = {tuple(x) for x in le["handed_off_exceptions"]}
        conditional = {tuple(r["transition"]) for r in le["conditional_rows"]}
        for t in self.raw["transitions"]:
            key = (t["from"], t["to"], t["event"])
            if t["from"] in active and t["to"] not in active and key not in exceptions:
                self.assertIn("end_lease", _effect_ids(t), key)
            if t["to"] == "cancelled":
                self.assertIn("set_cancelled", _effect_ids(t), key)
            if t["from"] == "*" and t["to"] == "returned" and key not in conditional:
                self.assertIn("end_lease", _effect_ids(t), key)
        seen = {}
        for t in self.raw["transitions"]:
            seen.setdefault((t["from"], t["to"], t["event"]), []).append(t)
        for key, rows in seen.items():
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    self.assertTrue(_exclusive(rows[i], rows[j]), key)

    def test_g38_g39_secret_and_index_lock_rows(self):
        row = _rows(self.raw, "handoff", "secret_detected", "returned")
        self.assertEqual((len(row), row[0]["return_code"]), (1, "R-10"))
        for scan in self.raw["preserve_manifest"]["secret_patterns"]["scan"]:
            for st in scan["states"]:
                self.assertTrue(_rows(self.raw, st, "secret_detected"), (scan["id"], st))
        rows = _rows(self.raw, "handoff", "index_lock", "handoff")
        self.assertEqual(len(rows), 2)
        self.assertTrue(_exclusive(rows[0], rows[1]))
        stages = {e["args"]["stage"] for r in rows for e in r["side_effects"] if e["id"] == "resume_from_phase"}
        self.assertEqual(stages, {"handoff_failure_policy.retry_detail.index_lock.retry_from",
                                  "handoff_failure_policy.retry_detail.index_lock.owner_alive_then"})

    def test_g40_to_g44_order_enums_detect_events_values(self):
        cc = self.raw["core_contract"]
        ae = cc["operations"]["accept_envelope"]
        self.assertEqual([c["id"] for c in ae["checks_in_order"]],
                         ["required_present", "lease_matches", "not_seen", "lease_active_unexpired", "current_lease_rules",
                          "result_scope", "pr_body_fields"])
        reasons = set()
        for t in self.raw["transitions"]:
            reasons |= {e["args"]["reason"] for e in t.get("side_effects", []) if e["id"] == "void_outbox"}
        for v in cc["operations"]["resend_outbox"]["on_fail"].values():
            reasons |= {e["args"]["reason"] for e in v.get("effects", []) if e["id"] == "void_outbox"}
        reasons |= {e["args"]["reason"] for e in self.raw["state_integrity"]["corruption"]["effects"] if e["id"] == "void_outbox"}
        self.assertEqual(reasons, set(cc["store"]["enums"]["outbox_void_reason"]))
        ids = [d["id"] for d in self.raw["state_integrity"]["corruption"]["detect"]]
        self.assertEqual((len(ids), len(set(ids))), (5, 5))
        self.assertIn("outbox_lease_id_mismatch", ids)
        self.assertEqual(set(self.raw["state_integrity"]["corruption"]["bindings"]), {"lease_record", "outbox", "journal"})
        events = set(self.raw["events"])
        ne = self.raw["state_integrity"]["normal_expiry"]
        self.assertEqual(set(ne["events"]), set(ne["events_by_state"].values()))
        self.assertLessEqual(set(ne["events"]), events)
        for v in cc["operations"]["resend_outbox"]["on_fail"].values():
            self.assertLessEqual(set(v["then_events"]), events)
        self.assertEqual(ae["idempotency_key_fields"], ["task_id", "lease_generation", "envelope_kind", "envelope_id"])
        self.assertIn("kind", self.raw["envelopes"]["fence_violation_report"]["required"])
        self.assertEqual(set(ae["field_value_sets"]), {"fence_violation_report"})

    def test_g45_to_g50(self):
        cc = self.raw["core_contract"]
        lock = self.raw["concurrency"]["lease_issue"]["lock"]
        self.assertEqual(lock["acquire"]["writes"]["holder"], "core_contract.daemon_instance.id")
        self.assertIn("when a guard fails", lock["release"]["at"])
        self.assertIn("clears_rows_where", lock["restart"])
        ur = self.raw["usage_recording"]
        self.assertEqual(ur["record_semantics"]["columns"], "write_once (null → value)")
        self.assertEqual(ur["accepted_vs_rejected"]["late_envelope_rejected"], "not_recorded")
        self.assertEqual(self.raw["envelopes"]["instruction"]["limits"]["value_source_order"][0], "task definition limits.<key>")
        payloads = cc["events_in"]["payloads"]
        guard_states = {t["from"] for t in self.raw["transitions"] if t.get("guard")}
        for g in self.raw["lease_guards"]:
            if g["on_fail"].get("action") == "emit_event":
                self.assertIn(g["on_fail"]["event"], payloads)
                self.assertEqual(set(g["on_fail"]["only_in_states"]), guard_states)
        for st in guard_states:
            rows = _rows(self.raw, st, "envelope_invalid", "returned")
            self.assertEqual((len(rows), rows[0]["return_code"]), (1, "R-13"), st)
        vi = cc["operations"]["validate_instruction"]
        self.assertEqual((len(vi["rules"]), len(vi["derive"])), (8, 1))
        for step in self.raw["hard_stop"]["procedure"]:
            if "transition" in step:
                self.assertTrue(_rows(self.raw, *step["transition"][:2], to=step["transition"][1]) or True)
                self.assertTrue([t for t in self.raw["transitions"] if [t["from"], t["to"], t["event"]] == step["transition"]], step)
        self.assertTrue(_rows(self.raw, "building", "owner_stop", "building"))
        self.assertEqual({r["noop_event"] for r in self.raw["noop_rules"] if r["event"] == "owner_stop"},
                         {"owner_stop_already_requested", "owner_stop_ignored_during_handoff"})
        self.assertEqual(cc["operations"]["hard_stop"]["trigger_events"]["owner_stop"]["then"], "hard_stop_deadline")

    def test_g29_to_g50_resolved_by_paths_exist_and_07_lists_them(self):
        gr = self.raw["t_op_00_followups"]["gap_resolutions"]
        self.assertEqual(sorted(gr), [f"G{n}" for n in range(29, 51)])
        for gid, item in gr.items():
            for path in item["resolved_by"]:
                if path == "events":
                    continue
                try:
                    _resolve(self.raw, path)
                except (KeyError, TypeError, IndexError):
                    self.fail(f"{gid}: {path} not found")
        doc = (ROOT / "docs/blueprint/proposals/설계검토_결과/07_수정대응표.md").read_text(encoding="utf-8")
        for n in range(29, 51):
            self.assertIn(f"G{n}", doc)


class FollowupBehavior(unittest.TestCase):
    """tests_to_add.behavior: the same checks on the core (MockEnv)."""

    def env(self):
        return sc.MockEnv(str(RULES), str(TASKS))

    def tr(self, env, m):
        return sc.tr(env.journal()[m:])

    def test_g37_unmapped_condition_ends_an_active_lease(self):
        env = self.env()
        env.start_task(sc.BASIC)
        env.grant(sc.BASIC)
        env.event("owner_stop", sc.BASIC, stop_ref="S")  # owner_stop from leased: unmapped
        self.assertEqual((env.state(sc.BASIC), env.lease(sc.BASIC)["status"]), ("returned", "revoked"))
        env.event("owner_resolved", sc.BASIC, resolution_ref="R")
        env.grant(sc.BASIC)
        self.assertEqual((env.state(sc.BASIC), env.task(sc.BASIC)["lease_generation"]), ("leased", 2))
        env = self.env()
        env.start_task(sc.BASIC)
        m = sc.mark(env)
        env.event("owner_stop", sc.BASIC, stop_ref="S")  # queued: no lease
        js = env.journal()[m:]
        self.assertEqual((sc.tr(js), sc.se(js)), ([("queued", "returned", "unmapped_condition")], ["record_r_code"]))

    def test_g38_secret_during_handoff(self):
        env, path = sc.handoff_bench(str(RULES), str(TASKS))
        env.ports.worktree.write(path, "s.txt", sc.fake_secret("token"))
        env.clock.advance(1)
        sc.switch(env)
        self.assertEqual((env.state(sc.HANDOFF), env.ports.git.commit_count, env.ports.git.push_count,
                          env.lease(sc.HANDOFF)["status"]), ("returned", 0, 0, "revoked"))

    def test_g39_index_lock_owner_alive(self):
        from daemon.core.ports import IndexLockError
        for alive, stage in ((True, "isolate"), (False, "preserve")):
            env, _ = sc.handoff_bench(str(RULES), str(TASKS))
            env.ports.git.inject("commit", [IndexLockError(alive)])
            env.clock.advance(1)
            sc.switch(env)
            got = [r["args"]["stage"] for r in env.journal() if r["kind"] == "side_effect_record" and r["id"] == "resume_from_phase"]
            self.assertEqual(got, [stage])

    def test_g40_redelivered_result_is_duplicate_and_unseen_on_ended_lease_is_late(self):
        env = self.env()
        env.bring_to_building(sc.BASIC)
        b = env.builder_for(sc.BASIC)
        res = b.result_envelope(env.instr(sc.BASIC), "pr_opened")
        env.submit(sc.BASIC, "result", copy.deepcopy(res))
        self.assertEqual(env.submit(sc.BASIC, "result", copy.deepcopy(res))["noop"], "envelope_duplicate_delivery")
        late = env.submit(sc.BASIC, "result", b.result_envelope(env.instr(sc.BASIC), "failed_tests"))
        self.assertEqual((late["noop"], late["return_code"]), ("late_envelope_rejected", "R-11"))

    def test_g42_outbox_lease_id_mismatch_is_caught(self):
        env = self.env()
        env.start_task(sc.BASIC)
        sc.crash_after_issue(env, sc.BASIC)
        env.store.tamper(lambda d: d["tasks"][sc.BASIC]["outbox"][0].update(lease_id="OTHER"))
        m = sc.mark(env)
        env.restart()
        js = env.journal()[m:]
        self.assertEqual(sc.tr(js), [("leased", "returned", "state_corrupted")])
        found = [r for r in js if r["kind"] == "transition_record"][0]["cond_evaluated"]
        self.assertTrue(found and found[0]["result"])
        from daemon.core import recovery
        self.assertIsNone(recovery.detect_id(env.core, env.snap(), sc.BASIC))  # returned: not classified again

    def test_g46_rejected_results_change_no_usage(self):
        env = self.env()
        env.bring_to_building(sc.BASIC)
        b = env.builder_for(sc.BASIC)
        old = copy.deepcopy(env.instr(sc.BASIC))
        b.send_result(old, "failed_tests", calls=5, wall_s=5, cost_units=5)
        env.run_builders()
        before = env.snap()["usage_record"]
        env.submit(sc.BASIC, "result", b.result_envelope(old, "failed_tests", calls=9, wall_s=9, cost_units=9))  # late
        self.assertEqual(env.snap()["usage_record"], before)

    def test_g50_owner_stop(self):
        env = self.env()
        env.bring_to_building(sc.OTHER)
        env.event("owner_stop", sc.OTHER, stop_ref="1")
        at = env.task(sc.OTHER)["task_state"]["stop_requested_at"]
        env.clock.advance(5)
        out = env.event("owner_stop", sc.OTHER, stop_ref="2")
        self.assertEqual((out["noop"], env.task(sc.OTHER)["task_state"]["stop_requested_at"]), ("owner_stop_already_requested", at))
        env.clock.advance(int(env.rules.number("hard_stop.grace_s")))
        env.core.tick()
        self.assertEqual((env.state(sc.OTHER), env.task(sc.OTHER)["task_state"]["return_code"]), ("returned", "R-07"))

    def test_g48_invalid_instruction_returns_from_every_issuing_state(self):
        found = {}
        for label, build, _ in sc.PATHS:
            env = self.env()
            task, state0, attempt, _retry = build(env)
            env.ports.catalog.tasks[task]["inputs"] = None
            m = sc.mark(env)
            attempt()
            found[state0] = ([x for x in self.tr(env, m) if x[2] == "envelope_invalid"], len(env.ports.sender.sent))
            if state0 == "building":
                self.assertEqual(env.lease(task)["status"], "returned")
        self.assertEqual(sorted(found), sorted(["queued", "building", "ci_failed", "changes_requested", "handoff", "paused_no_builder"]))
        for state, (rows, _sent) in found.items():
            self.assertEqual(rows, [(state, "returned", "envelope_invalid")], state)

    def test_g49_validator_reads_the_received_value(self):
        from daemon.core.envelope_validator import validate_instruction
        env = self.env()
        env.start_task(sc.BASIC)
        env.grant(sc.BASIC)
        good = copy.deepcopy(env.ports.sender.inboxes["mock-runner-1"][0])
        env.ports.catalog.tasks[sc.BASIC]["decision_gates"]["real_data"] = ["D-X"]
        self.assertEqual(validate_instruction(env.core, sc.BASIC, dict(good, real_data_allowed=True), [])[0], "invalid")
        self.assertEqual(validate_instruction(env.core, sc.BASIC, dict(good, real_data_allowed=False), ["D-X"])[0], "invalid")
        self.assertEqual(validate_instruction(env.core, sc.BASIC, dict(good, real_data_allowed=True), ["D-X"])[0], "valid")
        missing = {k: v for k, v in good.items() if k != "real_data_allowed"}
        self.assertEqual(validate_instruction(env.core, sc.BASIC, missing, ["D-X"]), ("invalid", ["real_data_allowed"]))
        self.assertNotIn("real_data_allowed", missing)

    def test_journal_never_holds_matched_secret_text(self):
        from daemon.core import secret_scan
        rules = Rules(raw_rules())
        value, n = secret_scan.redact(secret_scan.patterns(rules), {"a": ["x", "AKIA" + "Z" * 16]})
        self.assertEqual((value, n), ({"a": ["x", secret_scan.REDACTED]}, 1))

    def test_redaction_looks_inside_tuples(self):
        from daemon.core import secret_scan
        rules = Rules(raw_rules())
        value, n = secret_scan.redact(secret_scan.patterns(rules), {"g": ("ok", ("AKIA" + "Z" * 16,))})
        self.assertEqual((value, n), ({"g": ("ok", (secret_scan.REDACTED,))}, 1))


class NewPathsComeFromData(unittest.TestCase):
    """The paths added for G29-G50 and M1-M32 read their fields from the data, too."""

    assertBreaks = BehaviorComesFromData.assertBreaks

    def test_baseline_is_clean(self):
        for fn in (fl.m6, fl.m27, fl.m32):
            self.assertEqual(failing(run_fn(fn, raw_rules())), [])

    def test_restart_resume_check_branch_is_read(self):
        def f(raw):
            raw["handoff_failure_policy"]["restart_resume"]["preserve"]["else"] = {"stage": "preserve"}
        self.assertBreaks(sc.m38, f)

    def test_credential_table_is_read(self):
        def f(raw):
            raw["core_contract"]["expected_outputs"]["credential_of_effect"]["revoke_preserve_credential"] = "builder_token"
        self.assertBreaks(sc.m44, f)

    def test_conflict_relation_is_read(self):
        def f(raw):
            [g for g in raw["lease_guards"] if g["id"] == "no_conflict_lease"][0].pop("conflict_match")
        self.assertBreaks(fl.m13, f)

    def test_validate_instruction_rules_are_read(self):
        def f(raw):
            vi = raw["core_contract"]["operations"]["validate_instruction"]
            vi["rules"] = [r for r in vi["rules"] if r["id"] != "decision_ref_recorded"]
        self.assertBreaks(fl.m32, f)

    def test_guard_on_fail_states_are_read(self):
        def f(raw):
            g = [g for g in raw["lease_guards"] if g["id"] == "instruction_envelope_valid"][0]
            g["on_fail"]["only_in_states"] = [s for s in g["on_fail"]["only_in_states"] if s != "building"]
        self.assertBreaks(sc.m30, f)

    def test_hard_stop_trigger_events_are_read(self):
        def f(raw):
            for trig in raw["core_contract"]["operations"]["hard_stop"]["trigger_events"].values():
                trig["states"] = []
        self.assertBreaks(fl.m27, f)

    def test_owner_stop_noop_rules_are_read(self):
        self.assertBreaks(fl.m27, lambda raw: raw.update(noop_rules=[r for r in raw["noop_rules"] if r["event"] != "owner_stop"]))

    def test_expiry_events_by_state_are_read(self):
        self.assertBreaks(sc.m41, lambda raw: raw["state_integrity"]["normal_expiry"]["events_by_state"].pop("leased"))

    def test_idempotency_key_fields_are_read(self):
        def f(raw):
            raw["core_contract"]["operations"]["accept_envelope"]["idempotency_key_fields"] = ["task_id", "lease_generation", "envelope_kind"]
        self.assertBreaks(sc.m39, f)

    def test_field_value_sets_are_read(self):
        self.assertBreaks(sc.m28, lambda raw: raw["core_contract"]["operations"]["accept_envelope"]["field_value_sets"]["fence_violation_report"].update(kind=["token_mismatch"]))

    def test_corruption_applies_to_is_read(self):
        def f(raw):
            raw["state_integrity"]["corruption"]["applies_to"]["cond"] = [{"field": "task_state.state", "op": "==", "value": "nowhere"}]
        self.assertBreaks(sc.m44, f)

    def test_end_lease_applies_when_is_read(self):
        self.assertBreaks(sc.m41, lambda raw: raw["concurrency"]["lease_end"]["applies_when"][0].update(op="!="))

    def test_secret_scan_states_are_read(self):
        def f(raw):
            for s in raw["preserve_manifest"]["secret_patterns"]["scan"]:
                if s["id"] == "result_envelope":
                    s["states"] = []
        self.assertBreaks(fl.m14, f)

    def test_lock_self_value_is_read(self):
        self.assertBreaks(sc.m41, lambda raw: [g for g in raw["lease_guards"] if g["id"] == "lock_acquired"][0]["check"].update(value=[None]))

    def test_outside_reads_are_read(self):
        self.assertBreaks(fl.m6, lambda raw: raw["audit_triggers"].update(immediate_audit_paths=[]))
        self.assertBreaks(fl.m7, lambda raw: raw["audit_triggers"]["periodic"].update(every=5))
        self.assertBreaks(fl.m19, lambda raw: raw.update(post_merge_states=["done"]))
        self.assertBreaks(fl.m31, lambda raw: raw["record_separation"]["merge_observation_fields"].pop("integration_check"))

    def test_rows_without_cond_follow_the_table(self):
        self.assertBreaks(fl.m4, lambda raw: _transition(raw, "merge_wait", "reviewer_available").update(to="pr_open"))
        self.assertBreaks(fl.m23, lambda raw: _transition(raw, "merged", "impl_counter_incremented", "done").update(to="audit_queued"))

    def test_switch_sources_are_read(self):
        self.assertBreaks(fl.m18, lambda raw: raw["switch_policy"]["allowed_sources"].append("target_site_http"))

    def test_predicate_ops_are_read(self):
        def f(raw):
            raw["core_contract"]["predicate_ops"]["added_by_G49"].pop("subset_of")
        self.assertBreaks(fl.m32, f)


class Static(unittest.TestCase):
    def test_static_checks(self):
        for name, bad in static_checks.all_static(RULES):
            self.assertEqual(bad, [], name)

    def _network_or_cli_in(self, source):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "probe.py").write_text(source, encoding="utf-8")
            return static_checks.no_network_or_cli(Path(d))

    def test_dynamic_code_execution_and_import_are_noticed(self):
        for source in ("eval('1')", "exec('x = 1')", "compile('1', 'f', 'eval')", "__import__('os')",
                       "import importlib", "from importlib import import_module", "import importlib.util",
                       "import runpy", "import builtins", "from builtins import eval", "f = eval",
                       "import os\nos.__import__('x')", "x.import_module('y')", "from . import importlib"):
            self.assertNotEqual(self._network_or_cli_in(source), [], source)

    def test_ordinary_code_and_re_compile_are_not_flagged(self):
        self.assertEqual(self._network_or_cli_in("import re\nimport json\nP = re.compile('a')\nv = json.loads('1')\n"), [])

    def test_existing_network_and_cli_bans_still_hold(self):
        for source in ("import subprocess", "import socket", "import os\nos.system('x')"):
            self.assertNotEqual(self._network_or_cli_in(source), [], source)

    def test_this_test_file_has_no_model_identifiers(self):
        self.assertEqual(static_checks.no_model_identifiers([__file__]), [])

    def test_core_does_not_name_prose_keys(self):
        self.assertEqual(static_checks.no_natural_language_reads(), [])


class Journal(unittest.TestCase):
    def test_journal_is_append_only_and_ordered(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        first = env.journal()
        env.submit(sc.BASIC, "heartbeat", env.builder_for(sc.BASIC).heartbeat_envelope(env.instr(sc.BASIC)))
        env.restart()
        later = env.journal()
        self.assertEqual(later[: len(first)], first)
        self.assertEqual([r["seq"] for r in later], list(range(1, len(later) + 1)))
        kinds = {r["kind"] for r in later}
        self.assertLessEqual(kinds, {"transition_record", "side_effect_record", "noop_record", "return_record",
                                      "intent_record", "result_record", "diagnostic_record"})

    def test_transition_record_has_the_contract_fields(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        env.start_task(sc.BASIC)
        rec = [r for r in env.journal() if r["kind"] == "transition_record"][0]
        for k in ("task_id", "from", "to", "event", "at", "cond_evaluated"):
            self.assertIn(k, rec)
        grant = env.grant(sc.BASIC)
        rec = [r for r in env.journal() if r["kind"] == "transition_record"][-1]
        self.assertTrue(rec["cond_evaluated"] and all("result" in c for c in rec["cond_evaluated"]))

    def test_clock_is_virtual(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        t0 = env.clock.now()
        env.clock.advance(10)
        self.assertEqual(env.clock.now(), t0 + 10)
        env.clock.set(5)
        self.assertEqual(env.clock.now(), 5)


class ResultGates(unittest.TestCase):
    """R-01 and R-09 must be evaluated from structured predicates before a PR is recorded."""

    def ready(self, rules=None, status="pr_opened", **fields):
        env = MockEnv(rules or raw_rules(), str(TASKS))
        env.bring_to_building(sc.BASIC)
        envelope = env.builder_for(sc.BASIC).result_envelope(env.instr(sc.BASIC), status, **fields)
        envelope.setdefault("pr_body", {"task_id": sc.BASIC, "authors": [envelope["builder"]],
                                        "target_sha": envelope["head_sha"], "test_log_ref": envelope["test_log_ref"]})
        return env, envelope

    def submit(self, env, envelope):
        return env.submit(sc.BASIC, "result", envelope)

    def assert_scope_return(self, env, envelope):
        out = self.submit(env, envelope)
        self.assertEqual(out["transition"], ("building", "returned", "result_out_of_scope"))
        self.assertEqual(env.state(sc.BASIC), "returned")
        self.assertEqual(env.task(sc.BASIC)["task_state"]["return_code"], "R-01")
        self.assertEqual(env.lease(sc.BASIC)["status"], "returned")
        self.assertNotIn(sc.BASIC, env.core.snapshot().get("pr", {}))

    def test_outside_mixed_forbidden_and_invalid_paths_return_r01(self):
        for paths in (["docs/BLUEPRINT.md"], ["tools/mock/basic/ok.py", "docs/out.md"],
                      ["tools/mock/basic/../../../docs/out.md"], ["/tools/mock/basic/ok.py"],
                      ["tools/mock/basic/*"], [""], [7]):
            with self.subTest(paths=paths):
                env, envelope = self.ready(touched_paths=paths)
                self.assert_scope_return(env, envelope)

    def test_malformed_path_containers_fail_closed(self):
        for paths in (False, 0, "", {}, {"tools/mock/basic/ok.py": True}, "tools/mock/basic/ok.py"):
            with self.subTest(paths=paths):
                env, envelope = self.ready(touched_paths=paths)
                self.assert_scope_return(env, envelope)

    def test_missing_paths_are_an_invalid_envelope(self):
        env, envelope = self.ready()
        del envelope["touched_paths"]
        out = self.submit(env, envelope)
        self.assertEqual((out["accepted"], out["return_code"]), (False, "R-13"))
        self.assertEqual(env.state(sc.BASIC), "building")

    def test_scope_applies_to_failed_results_too(self):
        env, envelope = self.ready(status="failed_tests", touched_paths=["docs/out.md"])
        self.assert_scope_return(env, envelope)

    def test_normalized_and_exact_allowed_paths_open_pr(self):
        for allowed, paths in ((["tools/mock/basic/**"], ["tools/mock/./basic//sub/ok.py"]),
                               (["tools/mock/basic/ok.py"], ["tools/mock/basic/ok.py"]),
                               (["tools/mock/basic/**"], [])):
            with self.subTest(paths=paths):
                env, envelope = self.ready(touched_paths=paths)
                env.ports.catalog.task(sc.BASIC)["allowed_paths"] = allowed
                out = self.submit(env, envelope)
                self.assertEqual(out["transition"], ("building", "pr_open", "result_pr_opened"))
                self.assertEqual(env.lease(sc.BASIC)["status"], "completed")

    def test_forbidden_wins_inside_allowed_paths(self):
        env, envelope = self.ready(touched_paths=["tools/mock/basic/private/x.csv"])
        env.ports.catalog.task(sc.BASIC)["forbidden_paths"] = ["tools/mock/basic/private/*.csv"]
        self.assert_scope_return(env, envelope)

    def test_missing_empty_and_wrong_type_pr_fields_reject_with_r09(self):
        for field in ("task_id", "authors", "target_sha", "test_log_ref"):
            for value in (None, "", "  ", [], {}, False, 0):
                with self.subTest(field=field, value=value):
                    env, envelope = self.ready()
                    if value is None:
                        del envelope["pr_body"][field]
                    else:
                        envelope["pr_body"][field] = value
                    before = env.task(sc.BASIC)
                    out = self.submit(env, envelope)
                    self.assertEqual((out["accepted"], out["return_code"]), (False, "R-09"))
                    self.assertEqual(env.task(sc.BASIC), before)
                    self.assertNotIn(sc.BASIC, env.core.snapshot().get("pr", {}))

    def test_missing_or_malformed_pr_body_rejects_then_same_envelope_can_retry(self):
        for body in (None, "task_id authors target_sha test_log_ref", [], {}, False):
            with self.subTest(body=body):
                env, envelope = self.ready()
                valid = envelope.pop("pr_body")
                if body is not None:
                    envelope["pr_body"] = body
                out = self.submit(env, envelope)
                self.assertEqual((out["accepted"], out["return_code"]), (False, "R-09"))
                envelope["pr_body"] = valid
                self.assertEqual(self.submit(env, envelope)["transition"],
                                 ("building", "pr_open", "result_pr_opened"))
                self.assertEqual(self.submit(env, envelope)["noop"], "envelope_duplicate_delivery")

    def test_pr_body_is_only_required_for_pr_opened(self):
        env, envelope = self.ready(status="failed_tests")
        del envelope["pr_body"]
        out = self.submit(env, envelope)
        self.assertEqual(out["transition"], ("building", "building", "result_failed_tests"))

    def test_scope_failure_precedes_body_failure(self):
        env, envelope = self.ready(touched_paths=["docs/out.md"])
        del envelope["pr_body"]
        self.assert_scope_return(env, envelope)

    def test_stale_result_cannot_trigger_scope_or_body_rejection(self):
        env, envelope = self.ready(touched_paths=["docs/out.md"])
        envelope["fencing_token"] = "stale"
        del envelope["pr_body"]
        before = env.task(sc.BASIC)
        out = self.submit(env, envelope)
        self.assertEqual((out["accepted"], out["return_code"]), (False, "R-11"))
        self.assertEqual(env.task(sc.BASIC), before)

    def test_required_body_fields_are_read_from_rules(self):
        raw = raw_rules()
        raw["core_contract"]["operations"]["accept_envelope"]["pr_body_required_fields"].append("extra_evidence")
        env, envelope = self.ready(raw)
        self.assertEqual(self.submit(env, envelope)["return_code"], "R-09")
        envelope["pr_body"]["extra_evidence"] = "mock://extra"
        self.assertEqual(self.submit(env, envelope)["transition"], ("building", "pr_open", "result_pr_opened"))

    def test_predicates_recheck_the_pr_transition(self):
        # Even if an accept check is accidentally removed, the transition's cond must block the PR.
        for check_id, fields in (("result_scope", {"touched_paths": ["docs/out.md"]}),
                                 ("pr_body_fields", {"pr_body": {}})):
            with self.subTest(check_id=check_id):
                raw = raw_rules()
                checks = raw["core_contract"]["operations"]["accept_envelope"]["checks_in_order"]
                checks[:] = [c for c in checks if c["id"] != check_id]
                env, envelope = self.ready(raw, **fields)
                self.assertIsNone(self.submit(env, envelope)["transition"])
                self.assertEqual(env.state(sc.BASIC), "building")
                self.assertNotIn(sc.BASIC, env.core.snapshot().get("pr", {}))

    def test_body_text_values_must_be_nonblank_including_list_items(self):
        for value in ([""], ["  "], ["author", None], [False], [42]):
            with self.subTest(value=value):
                env, envelope = self.ready()
                envelope["pr_body"]["authors"] = value
                self.assertEqual(self.submit(env, envelope)["return_code"], "R-09")

    def test_malformed_scope_configuration_fails_closed(self):
        for field, value in (("allowed_paths", None), ("allowed_paths", "tools/mock/basic/**"),
                             ("allowed_paths", [None]), ("forbidden_paths", None),
                             ("forbidden_paths", [42])):
            with self.subTest(field=field, value=value):
                env, envelope = self.ready(touched_paths=["tools/mock/basic/ok.py"])
                env.ports.catalog.task(sc.BASIC)[field] = value
                self.assert_scope_return(env, envelope)


class ScopeForbiddenFirst(unittest.TestCase):
    """R-01 (G54): a forbidden glob that is not <dir>/** still wins over a broader allowed <dir>/**."""

    def out_of_scope(self, task, touched):
        from types import SimpleNamespace
        from daemon.core.observation import out_of_scope
        core = SimpleNamespace(ports=SimpleNamespace(catalog=SimpleNamespace(task=lambda _tid: task)))
        return out_of_scope(core, "T-X", touched)

    def test_single_star_forbidden_glob_is_not_skipped(self):
        task = {"allowed_paths": ["data/**"], "forbidden_paths": ["data/registry/*.csv"]}
        self.assertTrue(self.out_of_scope(task, ["data/registry/x.csv"]))
        self.assertFalse(self.out_of_scope(task, ["data/other/x.csv"]))

    def test_dir_star_star_and_exact_forbidden_still_win(self):
        task = {"allowed_paths": ["docs/**"], "forbidden_paths": ["docs/decisions/**", "docs/BLUEPRINT.md"]}
        self.assertTrue(self.out_of_scope(task, ["docs/decisions/d.md"]))
        self.assertTrue(self.out_of_scope(task, ["docs/BLUEPRINT.md"]))
        self.assertFalse(self.out_of_scope(task, ["docs/notes.md"]))

    def test_approved_canon_scope_is_the_only_exception(self):
        task = {"allowed_paths": ["data/**"], "forbidden_paths": ["data/registry/*.csv"],
                "canon_change": {"approval": {"scope_paths": ["data/registry/x.csv"]}}}
        self.assertFalse(self.out_of_scope(task, ["data/registry/x.csv"]))
        self.assertTrue(self.out_of_scope(task, ["data/registry/y.csv"]))


class ScopePathsAreNormalized(unittest.TestCase):
    """R-01: a touched path is normalized before it is compared; what cannot be normalized is out of scope."""

    def out_of_scope(self, touched, task=None):
        return ScopeForbiddenFirst.out_of_scope(self, task or {"allowed_paths": ["tools/mock/basic/**"],
                                                                "forbidden_paths": ["docs/**"]}, touched)

    def test_dot_dot_that_leaves_the_allowed_directory_is_out_of_scope(self):
        self.assertTrue(self.out_of_scope(["tools/mock/basic/../../../docs/x"]))
        self.assertTrue(self.out_of_scope(["tools/mock/basic/../../../docs/BLUEPRINT.md"]))

    def test_dot_dot_is_refused_even_when_it_would_stay_inside(self):
        self.assertTrue(self.out_of_scope(["tools/mock/basic/../basic/ok.py"]))

    def test_absolute_backslash_glob_and_empty_paths_are_out_of_scope(self):
        for bad in ("/tools/mock/basic/ok.py", "C:/tools/mock/basic/ok.py", "tools\\mock\\basic\\ok.py",
                    "tools/mock/basic/*", "tools/mock/basic/ok.p[y]", "", ".", "./", None, 7):
            self.assertTrue(self.out_of_scope([bad]), repr(bad))

    def test_dot_segments_and_double_slashes_are_dropped(self):
        self.assertFalse(self.out_of_scope(["tools/mock/./basic//sub/ok.py"]))
        self.assertTrue(self.out_of_scope(["tools/./docs//x"], {"allowed_paths": ["tools/**"], "forbidden_paths": ["tools/docs/**"]}))

    def test_forbidden_wins_after_normalization(self):
        task = {"allowed_paths": ["docs/**"], "forbidden_paths": ["docs/decisions/**"]}
        self.assertTrue(self.out_of_scope(["docs/./decisions//d.md"], task))

    def test_normalize_path(self):
        from daemon.core.observation import normalize_path
        self.assertEqual(normalize_path("a/./b//c"), "a/b/c")
        for bad in ("../a", "a/../b", "/a", "a/..", "a\\b", "a*", ""):
            self.assertIsNone(normalize_path(bad), bad)

    def test_the_approved_scope_exception_is_normalized_too(self):
        task = {"allowed_paths": ["data/**"], "forbidden_paths": ["data/registry/*.csv"],
                "canon_change": {"approval": {"scope_paths": ["data/registry/x.csv", "data/registry/../registry/y.csv"]}}}
        self.assertFalse(self.out_of_scope(["data/./registry/x.csv"], task))
        self.assertTrue(self.out_of_scope(["data/registry/y.csv"], task))


class ReviewerFamilyIsRegistered(unittest.TestCase):
    """self_review_rejected fails closed: the family is read from the reviewer registry, not from the payload."""

    def family(self, pr, payload):
        from types import SimpleNamespace
        from daemon.core.observation import reviewer_family
        pool = [{"name": "r-a", "family": "fam-a", "available": True}, {"name": "r-b", "family": "fam-b", "available": True}]
        core = SimpleNamespace(ports=SimpleNamespace(reviewers=SimpleNamespace(candidates=lambda: pool)))
        return reviewer_family(core, pr, payload)

    def test_family_comes_from_the_registry(self):
        self.assertEqual(self.family({"reviewer": None}, {"reviewer": "r-b", "reviewer_family": "fam-b"}), ("fam-b", None))

    def test_missing_or_empty_family_is_rejected(self):
        for payload in ({"reviewer": "r-b"}, {"reviewer": "r-b", "reviewer_family": ""}, {"reviewer": "r-b", "reviewer_family": None}):
            self.assertEqual(self.family({"reviewer": None}, payload), (None, "reviewer_family_missing"))

    def test_claimed_family_must_match_the_registry(self):
        self.assertEqual(self.family({"reviewer": None}, {"reviewer": "r-a", "reviewer_family": "fam-b"}),
                         (None, "reviewer_family_mismatch"))

    def test_unregistered_or_missing_reviewer_is_rejected(self):
        self.assertEqual(self.family({"reviewer": None}, {"reviewer": "nobody", "reviewer_family": "fam-b"}),
                         (None, "reviewer_not_registered"))
        self.assertEqual(self.family({"reviewer": None}, {"reviewer_family": "fam-b"}), (None, "reviewer_not_registered"))

    def test_only_the_assigned_reviewer_may_report(self):
        pr = {"reviewer": "r-b"}
        self.assertEqual(self.family(pr, {"reviewer": "r-b", "reviewer_family": "fam-b"}), ("fam-b", None))
        self.assertEqual(self.family(pr, {"reviewer": "r-a", "reviewer_family": "fam-a"}), (None, "reviewer_not_assigned"))
        self.assertEqual(self.family(pr, {"reviewer_family": "fam-b"}), (None, "reviewer_not_assigned"))

    def test_self_review_of_an_assigned_author_family_is_rejected_end_to_end(self):
        """The reviewer assigned earlier shares a family with an author who joined later (handoff): rejected."""
        env = sc.MockEnv(str(RULES), str(TASKS))
        fl.open_pr(env, fl.BASIC)
        env.observe(fl.BASIC, "ci", conclusion="success", sha=fl.H1)
        self.assertEqual(fl.pr_of(env, fl.BASIC)["reviewer"], "mock-builder-2")
        env.store.tamper(lambda d: d["journal"].append({"kind": "side_effect_record", "id": "issue_lease", "task_id": fl.BASIC,
                                                         "args": {"builder": "mock-builder-2"}, "seq": 10**6}))
        mark = len(env.journal())
        env.observe(fl.BASIC, "review_result", verdict="approved", sha=fl.H1, reviewer="mock-builder-2", reviewer_family="mock-family-b")
        whats = [r["what"] for r in env.journal()[mark:] if r["kind"] == "diagnostic_record"]
        self.assertEqual(whats, ["self_review_rejected"])
        self.assertEqual(env.state(fl.BASIC), "review_in_progress")
        self.assertEqual(fl.pr_of(env, fl.BASIC)["review_results"], [])


class LandingValidation(unittest.TestCase):
    """A missing SHA is never a match, and landings without a merge commit are not taken for one landing."""

    def ready(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        fl.approve_to_wait(env, fl.BASIC)
        return env, fl.pr_of(env, fl.BASIC)

    def landing(self, env, **kw):
        base = {"integration_check": "mock://ci/base"}
        base.update(kw)
        return env.observe(fl.BASIC, "landing", **base)

    def test_complete_landing_is_valid(self):
        env, pr = self.ready()
        self.landing(env, head_sha_at_merge=pr["approved_head_sha"], base_sha_at_merge=pr["approved_base_sha"], merge_commit_sha="e" * 40)
        self.assertEqual(env.state(fl.BASIC), "audit_queued")
        self.assertTrue(env.snap()["completion_facts"][0]["valid"])

    def test_missing_head_or_base_at_merge_is_invalid(self):
        for missing in ("head_sha_at_merge", "base_sha_at_merge"):
            env, pr = self.ready()
            kw = dict(head_sha_at_merge=pr["approved_head_sha"], base_sha_at_merge=pr["approved_base_sha"], merge_commit_sha="e" * 40)
            kw.pop(missing)
            self.landing(env, **kw)
            self.assertEqual(env.state(fl.BASIC), "merged_invalid_approval", missing)
            self.assertFalse(env.snap()["completion_facts"][0]["valid"], missing)

    def test_none_equal_none_does_not_validate(self):
        env, pr = self.ready()
        env.store.tamper(lambda d: d["pr"][fl.BASIC].update(approved_head_sha=None, approved_base_sha=None))
        self.landing(env, merge_commit_sha="e" * 40)
        self.assertEqual(env.state(fl.BASIC), "merged_invalid_approval")
        self.assertFalse(env.snap()["completion_facts"][0]["valid"])

    def test_empty_strings_do_not_validate(self):
        env, pr = self.ready()
        env.store.tamper(lambda d: d["pr"][fl.BASIC].update(approved_head_sha="", approved_base_sha=""))
        self.landing(env, head_sha_at_merge="", base_sha_at_merge="", merge_commit_sha="e" * 40)
        self.assertEqual(env.state(fl.BASIC), "merged_invalid_approval")

    def test_landings_without_merge_commit_are_told_apart(self):
        from daemon.core.observation import _landing_key
        a = _landing_key("T", {"head_sha_at_merge": "1", "base_sha_at_merge": "b", "integration_check": "c"})
        b = _landing_key("T", {"head_sha_at_merge": "2", "base_sha_at_merge": "b", "integration_check": "c"})
        self.assertNotEqual(a, b)
        self.assertEqual(a, _landing_key("T", {"head_sha_at_merge": "1", "base_sha_at_merge": "b", "integration_check": "c"}))
        self.assertNotEqual(_landing_key("T", {"merge_commit_sha": "x"}), _landing_key("T", {}))
        self.assertEqual(_landing_key("T", {"merge_commit_sha": "x", "head_sha_at_merge": "1"}),
                         _landing_key("T", {"merge_commit_sha": "x", "head_sha_at_merge": "2"}))

    def test_two_different_landings_without_merge_commit_are_both_recorded(self):
        env, pr = self.ready()
        self.landing(env, head_sha_at_merge=fl.H2, base_sha_at_merge="b" * 40)
        self.landing(env, head_sha_at_merge=fl.H3, base_sha_at_merge="b" * 40)
        self.assertEqual(len(env.snap()["completion_facts"]), 2)
        self.landing(env, head_sha_at_merge=fl.H3, base_sha_at_merge="b" * 40)
        self.assertEqual(len(env.snap()["completion_facts"]), 2)


class FollowupRound8(unittest.TestCase):
    def test_restart_with_unreadable_phase_counts_the_restart_once(self):
        res = results()["M38"]
        rows = [c for c in res["checks"] if "restart_count" in c["name"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], sc.PASS)

    def test_tick_settles_secret_hits_after_a_normal_expiry(self):
        res = results()["M41"]
        rows = [c for c in res["checks"] if "비밀값 검출" in c["name"]]
        self.assertEqual([c["status"] for c in rows], [sc.PASS])

    def test_mock_tasks_are_marked_as_fixture(self):
        cfg = json.loads(TASKS.read_text(encoding="utf-8"))
        self.assertEqual(cfg["origin"], "fixture")
        self.assertIs(cfg["fixture_only"], True)

    def test_readme_does_not_claim_mock_tasks_has_no_numbers(self):
        text = (ROOT / "tools/daemon/README.md").read_text(encoding="utf-8")
        row = [ln for ln in text.splitlines() if ln.startswith("| `mock_tasks.json`")][0]
        self.assertIn("fixture", row)
        self.assertNotIn("수치는 두지 않는다(G01)", row)
        self.assertIn("max_wall_s", row)


class StartGateEnforcement(unittest.TestCase):
    """audit1-start-gates-enforcement: blocked -> queued (prereqs_satisfied) carries a structured cond
    task.decision_gates.start subset_of task_state.decisions_recorded, and the core enforces it. The observation
    layer raises the event once the prerequisite tasks hold; a direct prereqs_satisfied event is held to the same cond
    (the prerequisite part is PrereqAndMergeGateCond)."""

    def env(self, start, rules=None):
        env = MockEnv(rules if rules is not None else str(RULES), str(TASKS))
        gates = env.ports.catalog.tasks[fl.GATED]["decision_gates"]
        if start is None:
            del gates["start"]
        else:
            gates["start"] = start
        return env

    def record(self, env, dec):
        env.observe(None, "decision_record", decision_id=dec, recorded_at=env.clock.now(), recorded_by="mock-owner",
                    source_ref=f"mock://decision/{dec}")

    def unmet(self, env):
        return [r for r in env.journal() if r["kind"] == "diagnostic_record" and r["what"] == "cond_not_met"
                and r.get("event") == "prereqs_satisfied" and r["task_id"] == fl.GATED]

    def transitions(self, env):
        return [(r["from"], r["to"], r["event"]) for r in env.journal()
                if r["kind"] == "transition_record" and r["task_id"] == fl.GATED]

    def test_row_carries_the_structured_start_cond(self):
        row = [t for t in raw_rules()["transitions"] if (t["from"], t["to"], t["event"]) == ("blocked", "queued", "prereqs_satisfied")]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["cond"], [{"field": "prereq_tasks_in(post_merge_states)", "op": "==", "value": True},
                                          {"field": "task.decision_gates.start", "op": "subset_of",
                                           "value": "task_state.decisions_recorded"}])
        self.assertIn("task.decision_gates.start", json.dumps(Rules(raw_rules()).transitions, ensure_ascii=False))

    def test_start_gate_blocks(self):
        env = self.env(["D-X"])
        env.start_task(fl.GATED)
        self.assertEqual(env.state(fl.GATED), "blocked")
        self.assertEqual(self.transitions(env), [])
        diag = self.unmet(env)
        self.assertEqual(len(diag), 1)
        self.assertEqual([(c["field"], c["left"], c["result"]) for c in diag[0]["cond"]],
                         [("prereq_tasks_in(post_merge_states)", True, True), ("task.decision_gates.start", ["D-X"], False)])

    def test_start_gate_blocks_a_direct_event(self):
        """The reviewer's reproduction: prereqs_satisfied fed straight to the core, D-X not recorded."""
        env = self.env(["D-X"])
        env.core.register_task(fl.GATED, "blocked")
        out = env.event("prereqs_satisfied", fl.GATED)
        self.assertFalse(out.get("applied"), out)
        self.assertEqual(env.state(fl.GATED), "blocked")

    def test_start_gate_opens(self):
        env = self.env(["D-X"])
        env.start_task(fl.GATED)
        self.record(env, "D-X")
        self.assertEqual(env.state(fl.GATED), "queued")
        self.assertEqual(self.transitions(env), [("blocked", "queued", "prereqs_satisfied")])
        rec = [r for r in env.journal() if r["kind"] == "transition_record" and r["task_id"] == fl.GATED][0]
        self.assertEqual([(c["field"], c["result"]) for c in rec["cond_evaluated"]],
                         [("prereq_tasks_in(post_merge_states)", True), ("task.decision_gates.start", True)])

    def test_start_gate_partial_record_stays_blocked(self):
        env = self.env(["D-X", "D-Y"])
        env.start_task(fl.GATED)
        self.record(env, "D-X")
        self.assertEqual(env.state(fl.GATED), "blocked")
        self.record(env, "D-Y")
        self.assertEqual(env.state(fl.GATED), "queued")

    def test_start_gate_empty(self):
        """start=[] (59 of the 63 spec tasks, e.g. T-CT-01) is not held back."""
        env = self.env([])
        env.start_task(fl.GATED)
        self.assertEqual(env.state(fl.GATED), "queued")
        self.assertEqual(self.unmet(env), [])

    def test_start_gate_null(self):
        for start in (None, "missing"):
            env = self.env(None) if start == "missing" else MockEnv(str(RULES), str(TASKS))
            if start is None:
                env.ports.catalog.tasks[fl.GATED]["decision_gates"]["start"] = None
            env.start_task(fl.GATED)
            self.assertEqual(env.state(fl.GATED), "blocked", start)
            self.assertEqual([c["left"] for c in self.unmet(env)[0]["cond"]], [True, None], start)

    def test_prereq_tasks_still_checked_first(self):
        env = MockEnv(str(RULES), str(TASKS))
        env.start_task("T-MOCK-SUCC")
        self.assertEqual(env.state("T-MOCK-SUCC"), "blocked")
        self.assertEqual([r for r in env.journal() if r["kind"] == "diagnostic_record" and r["task_id"] == "T-MOCK-SUCC"], [])

    def test_removing_the_cond_reopens_the_gap(self):
        """The block comes from the rules file: without the cond the direct event moves the task (the finding)."""
        raw = raw_rules()
        row = [t for t in raw["transitions"] if (t["from"], t["event"]) == ("blocked", "prereqs_satisfied")][0]
        del row["cond"]
        env = self.env(["D-X"], rules=raw)
        env.core.register_task(fl.GATED, "blocked")
        env.event("prereqs_satisfied", fl.GATED)
        self.assertEqual(env.state(fl.GATED), "queued")

    def test_spec_tasks_with_a_start_gate_are_held(self):
        """Every task of the spec catalog has a list start gate (none is unevaluable), and the gated ones
        (T-OP-03 D-02, T-OP-04 D-04, T-OP-07 D-03, T-UX-01 D-16) would be held by the cond until their decision is recorded."""
        tasks = json.loads(SPEC_TASKS.read_text(encoding="utf-8"))["tasks"]
        self.assertTrue(all(isinstance(t["decision_gates"]["start"], list) for t in tasks))
        gated = {t["id"]: t["decision_gates"]["start"] for t in tasks if t["decision_gates"]["start"]}
        self.assertEqual(gated, {"T-OP-03": ["D-02"], "T-OP-04": ["D-04"], "T-OP-07": ["D-03"], "T-UX-01": ["D-16"]})
        for tid, start in sorted(gated.items()):
            env = self.env(list(start))
            env.start_task(fl.GATED)
            self.assertEqual(env.state(fl.GATED), "blocked", tid)
            for dec in start:
                self.record(env, dec)
            self.assertEqual(env.state(fl.GATED), "queued", tid)


class PrereqAndMergeGateCond(unittest.TestCase):
    """audit2-spec-check-reads-prose-when: spec_check G6b and G5c read the rows' `when` text, which the core never
    reads. The prerequisite part of blocked -> queued and the merge gate of the rows into merge_wait were applied
    only by the observation layer, so a direct event skipped them. Both are now the rows' cond."""

    MERGE_ROWS = {("review_approved", "audit_not_required"): "subset_of", ("review_approved", "decision_pending"): "not_subset_of",
                  ("audit_pending", "audit_pass"): "subset_of", ("audit_pending", "decision_pending"): "not_subset_of",
                  ("merge_wait", "decision_recorded"): "subset_of"}

    def unmet(self, env, task_id, event):
        return [r for r in env.journal() if r["kind"] == "diagnostic_record" and r["what"] == "cond_not_met"
                and r.get("event") == event and r["task_id"] == task_id]

    def test_prereq_cond_blocks_a_direct_event(self):
        """T-MOCK-SUCC waits for T-MOCK-BASIC; prereqs_satisfied fed straight to the core does not move it."""
        env = MockEnv(str(RULES), str(TASKS))
        env.start_task(fl.BASIC)
        env.core.register_task(fl.SUCC, "blocked")
        out = env.event("prereqs_satisfied", fl.SUCC)
        self.assertFalse(out.get("applied"), out)
        self.assertEqual(env.state(fl.SUCC), "blocked")
        self.assertEqual([(c["field"], c["result"]) for c in self.unmet(env, fl.SUCC, "prereqs_satisfied")[0]["cond"]],
                         [("prereq_tasks_in(post_merge_states)", False), ("task.decision_gates.start", True)])

    def test_prereq_cond_unknown_prereq(self):
        """A prerequisite the store does not hold is not satisfied."""
        env = MockEnv(str(RULES), str(TASKS))
        env.core.register_task(fl.SUCC, "blocked")
        self.assertFalse(env.event("prereqs_satisfied", fl.SUCC).get("applied"))
        self.assertEqual(env.state(fl.SUCC), "blocked")

    def test_prereq_cond_opens_in_post_merge_states(self):
        for state in raw_rules()["post_merge_states"]:
            env = MockEnv(str(RULES), str(TASKS))
            env.core.register_task(fl.BASIC, state)
            env.core.register_task(fl.SUCC, "blocked")
            self.assertTrue(env.event("prereqs_satisfied", fl.SUCC).get("applied"), state)
            self.assertEqual(env.state(fl.SUCC), "queued", state)

    def test_removing_the_prereq_cond_reopens_the_gap(self):
        raw = raw_rules()
        row = [t for t in raw["transitions"] if (t["from"], t["event"]) == ("blocked", "prereqs_satisfied")][0]
        row["cond"] = [c for c in row["cond"] if c["field"] != "prereq_tasks_in(post_merge_states)"]
        env = MockEnv(raw, str(TASKS))
        env.core.register_task(fl.SUCC, "blocked")
        env.event("prereqs_satisfied", fl.SUCC)
        self.assertEqual(env.state(fl.SUCC), "queued")

    def test_merge_rows_carry_the_merge_gate_cond(self):
        rows = {(t["from"], t["event"]): t for t in raw_rules()["transitions"] if t["to"] == "merge_wait"}
        for key, op in self.MERGE_ROWS.items():
            self.assertEqual(rows[key].get("cond"), [{"field": "task.decision_gates.merge", "op": op,
                                                       "value": "task_state.decisions_recorded"}], key)

    def gated(self, state, recorded=(), rules=None):
        env = MockEnv(rules if rules is not None else str(RULES), str(TASKS))
        env.ports.catalog.tasks[fl.BASIC]["decision_gates"]["merge"] = ["D-M"]
        env.core.register_task(fl.BASIC, state, decisions=recorded)
        return env

    def test_merge_gate_blocks_ready_events(self):
        """Unrecorded D-M: the ready events are rejected (the finding's direct route), decision_pending applies."""
        for state, event in (("review_approved", "audit_not_required"), ("audit_pending", "audit_pass")):
            env = self.gated(state)
            self.assertFalse(env.event(event, fl.BASIC).get("applied"), event)
            self.assertEqual(env.state(fl.BASIC), state)
            self.assertEqual([(c["field"], c["left"], c["result"]) for c in self.unmet(env, fl.BASIC, event)[0]["cond"]],
                             [("task.decision_gates.merge", ["D-M"], False)])
            env = self.gated(state)
            self.assertTrue(env.event("decision_pending", fl.BASIC).get("applied"), state)
            self.assertEqual(env.state(fl.BASIC), "merge_wait")

    def test_merge_gate_recorded(self):
        for state, event in (("review_approved", "audit_not_required"), ("audit_pending", "audit_pass")):
            env = self.gated(state, ["D-M"])
            self.assertFalse(env.event("decision_pending", fl.BASIC).get("applied"), state)
            self.assertEqual(env.state(fl.BASIC), state)
            self.assertTrue(env.event(event, fl.BASIC).get("applied"), event)
            self.assertEqual(env.state(fl.BASIC), "merge_wait")

    def test_decision_recorded_needs_the_gate(self):
        env = self.gated("merge_wait")
        self.assertFalse(env.event("decision_recorded", fl.BASIC).get("applied"))
        self.assertEqual(len(self.unmet(env, fl.BASIC, "decision_recorded")), 1)
        env = self.gated("merge_wait", ["D-M"])
        self.assertTrue(env.event("decision_recorded", fl.BASIC).get("applied"))

    def test_removing_the_merge_cond_reopens_the_gap(self):
        raw = raw_rules()
        for t in raw["transitions"]:
            if (t["from"], t["event"]) == ("review_approved", "audit_not_required"):
                del t["cond"]
        env = self.gated("review_approved", rules=raw)
        self.assertTrue(env.event("audit_not_required", fl.BASIC).get("applied"))
        self.assertEqual(env.state(fl.BASIC), "merge_wait")


class TerminalStatesIgnoreUnmapped(unittest.TestCase):
    """audit2-daemon-wildcard-from-terminal: the * -> returned unmapped_condition rows applied to done and cancelled
    too, so a re-delivered pr_merged_observed sent a done task back to returned (R-03), out of post_merge_states, and
    the tasks that depend on it stayed blocked. In a terminal state an unmapped event is now only recorded."""

    NOOP = "event_after_terminal_state"
    TERMINAL = {"done", "cancelled"}

    def done_task(self, task_id, rules=None):
        """BASIC: the 10th implementation PR closes the batch and the batch audit passes (audit_queued -> done).
        DOCS: a docs-only PR goes merged -> done directly."""
        env = MockEnv(rules if rules is not None else str(RULES), str(TASKS))
        if task_id == fl.BASIC:
            fl._land_series(env, 9)
            fl.approve_to_wait(env, fl.BASIC)
            fl.land(env, fl.BASIC, merge_commit="f" * 40)
            env.observe(None, "batch_audit_result", batch_id="B1", verdict="pass")
        else:
            fl.approve_to_wait(env, fl.DOCS, touched=["docs/mock/guide.md"])
            fl.land(env, fl.DOCS)
        self.assertEqual(env.state(task_id), "done")
        return env

    def redeliveries(self, env, t):
        pr = fl.pr_of(env, t)
        merged = dict(head_sha_at_merge=pr["head_sha"], base_sha_at_merge=pr["base_sha"], integration_check="mock://ci/base")
        return [("landing observed again without a merge commit", lambda: env.observe(t, "landing", **merged)),
                ("landing observed again with another merge commit",
                 lambda: env.observe(t, "landing", merge_commit_sha="9" * 40, **merged)),
                ("pr_merged_observed fed to the core", lambda: env.event("pr_merged_observed", t)),
                ("ci failure on the merged head", lambda: env.observe(t, "ci", conclusion="failure", sha=pr["head_sha"])),
                ("an observation kind no row maps", lambda: env.observe(t, "no_such_observation"))]

    def test_wildcard_rows_exclude_the_states_without_rows_of_their_own(self):
        raw = raw_rules()
        terminal = {s for s in raw["states"] if not _rows(raw, frm=s)}
        self.assertEqual(terminal, self.TERMINAL)
        rows = _rows(raw, frm="*", event="unmapped_condition")
        self.assertEqual(len(rows), 2)
        for row in rows:
            excl = [c for c in row["cond"] if c["field"] == "task_state.state"]
            self.assertEqual([(c["op"], set(c["value"])) for c in excl], [("not_in", terminal)])
        rule, = [r for r in raw["noop_rules"] if r["event"] == "unmapped_condition"]
        self.assertEqual([(c["field"], c["op"], set(c["value"])) for c in rule["when"]],
                         [("task_state.state", "in", terminal)])
        self.assertIn(rule["noop_event"], raw["noop_events"])
        self.assertEqual(rule["noop_event"], self.NOOP)
        cr, = raw["concurrency"]["lease_end"]["conditional_rows"]
        active, = [r for r in rows if "end_lease" in _effect_ids(r)]
        other, = [r for r in rows if "end_lease" not in _effect_ids(r)]
        self.assertEqual((cr["end_lease_when"], cr["complement_row_cond"]), (active["cond"], other["cond"]))

    def test_done_stays_done_and_dependents_start(self):
        for task_id in (fl.BASIC, fl.DOCS):
            env = self.done_task(task_id)
            for label, deliver in self.redeliveries(env, task_id):
                with self.subTest(task=task_id, delivery=label):
                    m = sc.mark(env)
                    deliver()
                    js = env.journal()[m:]
                    self.assertEqual((env.state(task_id), sc.tr(js), sc.rets(js), sc.se(js, "record_r_code", "end_lease")),
                                     ("done", [], [], []))
                    self.assertIn((self.NOOP, None), sc.noops(js))
            if task_id == fl.BASIC:
                # SUCC's prerequisite is BASIC: it is still a post_merge_states task, so SUCC starts and is leased
                env.start_task(fl.SUCC)
                self.assertEqual(env.state(fl.SUCC), "queued")
                env.grant(fl.SUCC)
                self.assertEqual(env.state(fl.SUCC), "leased")

    def test_cancelled_stays_cancelled(self):
        env = MockEnv(str(RULES), str(TASKS))
        env.start_task(sc.BASIC)
        env.grant(sc.BASIC)
        env.event("owner_cancelled", sc.BASIC)
        self.assertEqual((env.state(sc.BASIC), env.lease(sc.BASIC)["status"]), ("cancelled", "revoked"))
        for label, deliver in (("owner_stop", lambda: env.event("owner_stop", sc.BASIC, stop_ref="S")),
                               ("lease_granted", lambda: env.grant(sc.BASIC)),
                               ("pr_merged_observed", lambda: env.event("pr_merged_observed", sc.BASIC))):
            with self.subTest(event=label):
                m = sc.mark(env)
                deliver()
                js = env.journal()[m:]
                self.assertEqual((env.state(sc.BASIC), sc.tr(js), sc.rets(js), sc.noops(js)),
                                 ("cancelled", [], [], [(self.NOOP, None)]))
        self.assertEqual(env.task(sc.BASIC)["lease_generation"], 1)

    def test_non_terminal_states_are_still_returned(self):
        env = MockEnv(str(RULES), str(TASKS))
        fl.approve_to_wait(env, fl.BASIC)
        fl.land(env, fl.BASIC, merge_commit="f" * 40)
        self.assertEqual(env.state(fl.BASIC), "audit_queued")
        m = sc.mark(env)
        env.event("pr_merged_observed", fl.BASIC)
        js = env.journal()[m:]
        self.assertEqual((sc.tr(js), sc.rets(js), sc.noops(js)), ([("audit_queued", "returned", "unmapped_condition")], ["R-03"], []))

    def test_removing_the_exclusion_reopens_the_finding(self):
        """Without the state predicate and the noop rule the redelivery sends done to returned and SUCC stays blocked."""
        raw = raw_rules()
        for row in _rows(raw, frm="*", event="unmapped_condition"):
            row["cond"] = [c for c in row["cond"] if c["field"] != "task_state.state"]
        raw["noop_rules"] = [r for r in raw["noop_rules"] if r["event"] != "unmapped_condition"]
        env = self.done_task(fl.BASIC, rules=raw)
        m = sc.mark(env)
        env.event("pr_merged_observed", fl.BASIC)
        js = env.journal()[m:]
        self.assertEqual((env.state(fl.BASIC), sc.tr(js), sc.rets(js)), ("returned", [("done", "returned", "unmapped_condition")], ["R-03"]))
        env.start_task(fl.SUCC)
        self.assertEqual(env.state(fl.SUCC), "blocked")


class DocsOnlyLandingCond(unittest.TestCase):
    """audit2-daemon-docs-pr-never-done (docs-pr-complete): merged -> audit_queued and merged -> done share
    (merged, impl_counter_incremented) and had no cond, so the first row always won and only a destination named by
    the caller (`to`) reached done. The rows now carry cond event.docs_only and nobody names the destination."""

    def merged(self, task_id, touched=None):
        """The task in merged without the observation layer counting it (pr_merged_observed fed to the core)."""
        env = MockEnv(str(RULES), str(TASKS))
        fl.approve_to_wait(env, task_id, touched=touched)
        env.event("pr_merged_observed", task_id)
        self.assertEqual(env.state(task_id), "merged")
        return env

    def landed(self, task_id, touched=None, labels=()):
        env = MockEnv(str(RULES), str(TASKS))
        fl.open_pr(env, task_id, touched)
        with env.ports.store.transaction() as d:
            d["pr"][task_id]["labels"].extend(labels)
        env.observe(task_id, "ci", conclusion="success", sha=fl.H1)
        fl.review(env, task_id)
        m = sc.mark(env)
        fl.land(env, task_id)
        return env, env.journal()[m:]

    def test_rows_sharing_from_and_event_are_told_apart_by_cond(self):
        raw = raw_rules()
        groups = {}
        for row in raw["transitions"]:
            groups.setdefault((row["from"], row["event"]), []).append(row)
        for key, rows in groups.items():
            if len(rows) > 1:
                with self.subTest(row=key):
                    self.assertEqual([r["to"] for r in rows if not r.get("cond")], [])
        impl = _transition(raw, "merged", "impl_counter_incremented", "audit_queued")
        docs = _transition(raw, "merged", "impl_counter_incremented", "done")
        self.assertEqual(docs.get("cond"), [{"field": "event.docs_only", "op": "==", "value": True}])
        self.assertEqual(impl.get("cond"), [{"field": "event.docs_only", "op": "!=", "value": True}])
        self.assertTrue(_exclusive(impl, docs))
        self.assertEqual(raw["core_contract"]["events_in"]["payloads"]["impl_counter_incremented"], ["docs_only"])

    def test_the_core_picks_the_row_from_the_event(self):
        for payload, want in (({"docs_only": True}, "done"), ({"docs_only": False}, "audit_queued"), ({}, "audit_queued")):
            with self.subTest(payload=payload):
                env = self.merged(fl.DOCS, touched=["docs/mock/guide.md"])
                m = sc.mark(env)
                env.event("impl_counter_incremented", fl.DOCS, **payload)
                self.assertEqual(sc.tr(env.journal()[m:]), [("merged", want, "impl_counter_incremented")])

    def test_no_caller_names_the_destination(self):
        import inspect
        from daemon.core import transition_engine
        self.assertNotIn("to", inspect.signature(transition_engine.apply_event).parameters)
        env = self.merged(fl.BASIC)
        m = sc.mark(env)
        env.core.handle_event({"event": "impl_counter_incremented", "task_id": fl.BASIC, "to": "done",
                               "payload": {"docs_only": False}})
        self.assertEqual(sc.tr(env.journal()[m:]), [("merged", "audit_queued", "impl_counter_incremented")])

    def test_docs_pr_completes_without_count(self):
        cases = (("docs/** paths", fl.DOCS, ["docs/mock/guide.md"], ()),
                 ("label docs-only", fl.BASIC, None, ("docs-only",)))
        for label, task_id, touched, labels in cases:
            with self.subTest(case=label):
                env, js = self.landed(task_id, touched, labels)
                self.assertEqual(sc.tr(js), [("merge_wait", "merged", "pr_merged_observed"),
                                             ("merged", "done", "impl_counter_incremented")])
                self.assertEqual((fl.counter(env)["merged_impl_counter"], fl.counter(env)["batches"]), (0, []))
                self.assertEqual(sc.se(js, "increment_counter"), [])

    def test_implementation_pr_is_counted(self):
        env, js = self.landed(fl.BASIC)
        self.assertEqual(sc.tr(js)[-1], ("merged", "audit_queued", "impl_counter_incremented"))
        self.assertEqual(fl.counter(env)["merged_impl_counter"], 1)
        self.assertEqual(fl.counter(env)["batches"][0]["tasks"], [fl.BASIC])
        self.assertEqual(len(sc.se(js, "increment_counter")), 1)

    def test_removing_the_cond_reopens_the_finding(self):
        """Without the cond the first row wins: the docs-only PR goes to audit_queued and is counted."""
        raw = raw_rules()
        for row in _rows(raw, frm="merged", event="impl_counter_incremented"):
            row.pop("cond", None)
        env = MockEnv(raw, str(TASKS))
        fl.approve_to_wait(env, fl.DOCS, touched=["docs/mock/guide.md"])
        m = sc.mark(env)
        fl.land(env, fl.DOCS)
        js = env.journal()[m:]
        self.assertEqual((env.state(fl.DOCS), sc.tr(js)[-1], fl.counter(env)["merged_impl_counter"]),
                         ("audit_queued", ("merged", "audit_queued", "impl_counter_incremented"), 1))


def _fields(node):
    """Every field path a cond names, on either side of a predicate."""
    if isinstance(node, dict):
        out = [node["field"]] if isinstance(node.get("field"), str) else []
        if isinstance(node.get("value"), str):
            out.append(node["value"])
        return out + [f for v in node.values() if isinstance(v, (dict, list)) for f in _fields(v)]
    if isinstance(node, list):
        return [f for x in node for f in _fields(x)]
    return []


class HandleEventFencing(unittest.TestCase):
    """audit2-daemon-handle-event-fencing: handle_event applied the transition table to any event name, so an
    envelope-born event (result_pr_opened) sent without its envelope moved building -> pr_open with no lease, token
    or duplicate check. Only core_contract.operations.handle_event.without_envelope may now arrive bare."""

    ENVELOPE_ROOTS = ("envelope.", "signal.", "report.", "request.")
    CORE_EMITTED = {"envelope_invalid", "unmapped_condition", "state_corrupted"}

    def entry(self, raw=None):
        return (raw or raw_rules())["core_contract"]["operations"]["handle_event"]

    def envelope_born(self, raw):
        """The events accept_envelope produces (result_<status>, and the signal/heartbeat message types), and every
        event whose rows compare envelope fields."""
        out = {"result_" + s for s in raw["envelopes"]["result"]["status_values"]} | {"switch_signal", "first_heartbeat",
                                                                                       "heartbeat", "result_out_of_scope"}
        for row in raw["transitions"]:
            if any(f.startswith(self.ENVELOPE_ROOTS) for f in _fields(row.get("cond"))):
                out.add(row["event"])
        return out

    def building(self):
        env = MockEnv(str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        self.assertEqual(env.state(sc.BASIC), "building")
        return env

    def assert_rejected(self, env, task_id, name, payload=None):
        before = env.task(task_id)
        m = sc.mark(env)
        env.clock.advance(1)
        out = env.core.handle_event({"event": name, "task_id": task_id, "payload": payload or {}})
        js = env.journal()[m:]
        self.assertEqual((sc.tr(js), sc.noops(js)), ([], [("envelope_rejected_invalid", "R-13")]))
        self.assertEqual((out["applied"], out["noop"], out["return_code"], out["rejected"]),
                         (False, "envelope_rejected_invalid", "R-13", ("envelope_required", name)))
        rec, = [r for r in js if r["kind"] == "noop_record"]
        self.assertEqual((rec["event"], rec["reason"]), (name, "envelope_required"))
        after = env.task(task_id)
        for key in ("task_state", "lease_record", "lease_generation", "outbox", "inbox_seen", "handoff_record"):
            self.assertEqual(after[key], before[key], key)

    def test_the_entry_is_catalog_data(self):
        raw = raw_rules()
        entry = self.entry(raw)
        catalog = set(raw["events"]) | set(raw["noop_events"]) | set(raw["event_catalog"]["operation_events"])
        self.assertEqual(entry["routes"], {"daemon_restart": "restart_recovery", "fence_violation": "accept_envelope",
                                           "push_requested": "fenced_write", "pr_update_requested": "fenced_write"})
        self.assertEqual(entry["on_reject"], {"noop_event": "envelope_rejected_invalid", "return_code": "R-13",
                                              "reason": "envelope_required"})
        bare = set(entry["without_envelope"])
        self.assertEqual(len(bare), len(entry["without_envelope"]))
        self.assertLessEqual(bare, set(raw["events"]))
        self.assertLessEqual(set(entry["routes"]), catalog)
        self.assertEqual(bare & set(entry["routes"]), set())

    def test_envelope_born_and_core_emitted_events_are_not_listed(self):
        raw = raw_rules()
        bare = set(self.entry(raw)["without_envelope"])
        born = self.envelope_born(raw)
        self.assertLessEqual({"result_pr_opened", "result_failed_tests", "switch_signal", "first_heartbeat"}, born)
        self.assertEqual(bare & born, set())
        self.assertEqual(bare & self.CORE_EMITTED, set())
        self.assertEqual(bare & set(raw["noop_events"]), set())

    def test_the_core_s_own_bare_events_are_listed(self):
        """handoff.py feeds its step results through handle_event; each of them must be on the list."""
        src = (ROOT / "tools/daemon/core/handoff.py").read_text(encoding="utf-8")
        sent = set(re.findall(r'"event": "([a-z_]+)"', src)) | set(re.findall(r'return \("([a-z_]+)", ', src))
        sent &= set(raw_rules()["events"])
        self.assertLessEqual({"preserve_commit_ok", "preserve_push_ok", "preserved", "no_builder"}, sent)
        self.assertLessEqual(sent, set(self.entry()["without_envelope"]))

    def test_envelope_born_events_without_an_envelope_are_rejected(self):
        raw = raw_rules()
        routed = {"daemon_restart", "fence_violation", "push_requested", "pr_update_requested"}  # routed, not rejected
        names = sorted((self.envelope_born(raw) & set(raw["events"]) | self.CORE_EMITTED | {"heartbeat", "no_such_event"})
                       - routed)
        self.assertLessEqual({"result_pr_opened", "state_corrupted", "unmapped_condition", "heartbeat"}, set(names))
        for name in names:
            with self.subTest(event=name):
                self.assert_rejected(self.building(), sc.BASIC, name)

    def test_lease_fields_in_the_payload_are_not_an_envelope(self):
        """Even with the current lease's id, generation and token, a bare event does not pass accept_envelope."""
        env = MockEnv(str(RULES), str(TASKS))
        env.start_task(sc.BASIC)
        env.grant(sc.BASIC)
        lease = env.lease(sc.BASIC)
        fence = dict(lease_id=lease["lease_id"], lease_generation=lease["lease_generation"],
                     fencing_token=lease["fencing_token"], envelope_id="E-BARE")
        self.assertEqual(env.state(sc.BASIC), "leased")
        self.assert_rejected(env, sc.BASIC, "first_heartbeat", fence)
        env = self.building()
        lease = env.lease(sc.BASIC)
        fence.update(lease_id=lease["lease_id"], lease_generation=lease["lease_generation"],
                     fencing_token=lease["fencing_token"])
        self.assert_rejected(env, sc.BASIC, "result_pr_opened", dict(fence, status="pr_opened", pr_number=1))

    def test_the_envelope_path_still_applies(self):
        env = self.building()
        b = env.builder_for(sc.BASIC)
        out = env.submit(sc.BASIC, "result", b.result_envelope(env.instr(sc.BASIC), "pr_opened"))
        self.assertEqual((out["accepted"], out["transition"]), (True, ("building", "pr_open", "result_pr_opened")))
        env = self.building()
        m = sc.mark(env)
        env.event("owner_stop", sc.BASIC, stop_ref="S")  # on the list: reaches the table
        self.assertEqual((sc.noops(env.journal()[m:]), env.task(sc.BASIC)["task_state"]["stop_requested_at"] is not None),
                         ([], True))

    def test_result_events_cannot_be_enabled_on_the_bare_entry(self):
        """audit3: configuration must not reopen the result envelope bypass, including via checked routes."""
        from daemon.core.ports import SpecGap
        names = sorted(n for n in raw_rules()["events"] if n.startswith("result_"))
        self.assertIn("result_pr_opened", names)
        for name in names:
            for route in (None, "restart_recovery", "accept_envelope", "fenced_write"):
                with self.subTest(event=name, route=route):
                    raw = raw_rules()
                    entry = self.entry(raw)
                    if route is None:
                        entry["without_envelope"].append(name)
                    else:
                        entry["routes"][name] = route
                    with self.assertRaisesRegex(SpecGap, "result events require submit_envelope"):
                        MockEnv(raw, str(TASKS))

    def test_result_events_without_any_lease_are_rejected(self):
        """The reported building -> pr_open bypass must also be refused when there is no lease at all."""
        for name in sorted(n for n in raw_rules()["events"] if n.startswith("result_")):
            with self.subTest(event=name):
                env = MockEnv(str(RULES), str(TASKS))
                env.core.register_task(sc.BASIC, "building")
                self.assertIsNone(env.lease(sc.BASIC))
                self.assert_rejected(env, sc.BASIC, name)

    def test_complete_result_payload_still_requires_the_envelope_entry(self):
        env = self.building()
        b = env.builder_for(sc.BASIC)
        envelope = b.result_envelope(env.instr(sc.BASIC), "pr_opened")
        self.assert_rejected(env, sc.BASIC, "result_pr_opened", envelope)
        out = env.submit(sc.BASIC, "result", envelope)
        self.assertEqual((out["accepted"], out["transition"]), (True, ("building", "pr_open", "result_pr_opened")))
        before = env.task(sc.BASIC)
        out = env.submit(sc.BASIC, "result", envelope)
        self.assertEqual((out["accepted"], out["noop"], out["transition"]),
                         (False, "envelope_duplicate_delivery", None))
        self.assertEqual(env.task(sc.BASIC), before)

    def test_rules_that_break_the_entry_contract_are_refused(self):
        from daemon.core.ports import SpecGap
        breaks = {"unknown event listed": lambda e: e["without_envelope"].append("no_such_event"),
                  "routed and listed": lambda e: e["without_envelope"].append("push_requested"),
                  "unknown operation": lambda e: e["routes"].update(fence_violation="apply_directly")}
        for label, fn in breaks.items():
            with self.subTest(case=label):
                with self.assertRaises(SpecGap):
                    MockEnv(_mutated(lambda r: fn(self.entry(r))), str(TASKS))


class SendMarkCompareAndSet(unittest.TestCase):
    """audit2-daemon-envelope-sent-after-void: resend_outbox sends outside any transaction and then marked the row
    sent without looking at it again, so a row an expiry, revoke or corruption had voided in between became sent
    (with its void_reason still set). core_contract.operations.resend_outbox.mark_sent is now a compare-and-set on
    checks[pending]."""

    def spec(self, raw=None):
        return (raw or raw_rules())["core_contract"]["operations"]["resend_outbox"]

    def race(self, during, raw=None):
        """Issue a lease for BASIC; `during(env, task_id)` runs after the send and before the marking transaction."""
        env = MockEnv(raw or str(RULES), str(TASKS))
        env.start_task(sc.BASIC)
        env.ports.sender.during_send = lambda task_id: during(env, task_id)
        m = sc.mark(env)
        env.grant(sc.BASIC)
        return env, env.journal()[m:]

    @staticmethod
    def marks(js):
        return [r["outcome"] for r in js if r["kind"] == "result_record" and r["action"] == "send_envelope"]

    @staticmethod
    def conflicts(js):
        return [(r["status"], r["void_reason"], r["trigger"]) for r in js
                if r["kind"] == "diagnostic_record" and r["what"] == "outbox_not_pending_at_mark"]

    @staticmethod
    def expire(env, task_id):
        env.clock.advance(sc.TTL + 1)
        env.core.tick()

    @staticmethod
    def cancel_and_restart(env, task_id):
        """Another daemon instance takes over while the old one is still sending."""
        env.event("owner_cancelled", task_id)
        env.restart()

    @staticmethod
    def corrupt_and_restart(env, task_id):
        env.store.tamper(lambda d: d["tasks"][task_id]["outbox"][0].update(lease_generation=7))
        env.restart()

    def test_mark_sent_is_data(self):
        spec = self.spec()
        self.assertEqual(spec["mark_sent"]["compare_and_set"], "pending")
        cas, = [c for c in spec["checks"] if c["id"] == "pending"]
        self.assertEqual((cas["pred"], cas["fail_key"]), ({"field": "outbox.status", "op": "==", "value": "pending"}, "not_pending"))
        self.assertEqual(spec["mark_sent"]["set"], {"status": "sent", "sent_at": "clock.now"})
        self.assertEqual(spec["mark_sent"]["on_conflict"], {"writes": [], "diagnostic": "outbox_not_pending_at_mark",
                                                            "result": "not_marked"})
        self.assertIn("compare-and-set", spec["on_pass"][1])

    def test_a_row_voided_during_the_send_stays_void(self):
        for label, during, want in (("expired", self.expire, ("queued", "expired", "expired")),
                                    ("revoked", self.cancel_and_restart, ("cancelled", "revoked", "revoked")),
                                    ("corrupt", self.corrupt_and_restart, ("returned", "revoked", "corrupt"))):
            with self.subTest(case=label):
                env, js = self.race(during)
                t = env.task(sc.BASIC)
                row = t["outbox"][0]
                self.assertEqual((t["task_state"]["state"], t["lease_record"]["status"], row["void_reason"]), want)
                self.assertEqual((row["status"], row["sent_at"]), ("void", None))
                self.assertEqual(len(env.ports.sender.sent), 1)
                self.assertEqual(sc.se(js, "send_envelope"), [])
                self.assertEqual(self.marks(js), ["not_marked"])
                self.assertEqual(self.conflicts(js), [("void", want[2], "send")])

    def test_the_envelope_that_went_out_is_refused(self):
        """The void envelope did reach the builder; its lease is over, so nothing it reports moves the task."""
        for label, during, state in (("expired", self.expire, "queued"), ("revoked", self.cancel_and_restart, "cancelled")):
            with self.subTest(case=label):
                env, _ = self.race(during)
                m = sc.mark(env)
                env.run_builders()
                js = env.journal()[m:]
                self.assertEqual((sc.tr(js), sc.noops(js), env.state(sc.BASIC)), ([], [("late_envelope_rejected", "R-11")], state))

    def test_a_second_send_does_not_mark_the_row_again(self):
        """sender_retry sends and marks the row first; the first send's marking then finds it sent and keeps its sent_at."""
        from daemon.core import lease as lease_mod
        marked_at = []

        def retry(env, task_id):
            env.clock.advance(1)
            lease_mod.resend_outbox(env.core, task_id, "sender_retry")
            marked_at.append(env.clock.now())
            env.clock.advance(1)  # the first send's marking runs later
        env, js = self.race(retry)
        row = env.task(sc.BASIC)["outbox"][0]
        self.assertEqual((row["status"], row["sent_at"]), ("sent", marked_at[0]))
        self.assertLess(row["sent_at"], env.clock.now())
        self.assertEqual(len(env.ports.sender.sent), 2)
        self.assertEqual([r["args"]["trigger"] for r in js if r["kind"] == "side_effect_record" and r["id"] == "send_envelope"],
                         ["sender_retry"])
        self.assertEqual(self.marks(js), ["sent", "not_marked"])
        self.assertEqual(self.conflicts(js), [("sent", None, "send")])

    def test_an_undisturbed_send_is_marked(self):
        env, js = self.race(lambda env, task_id: None)
        row = env.task(sc.BASIC)["outbox"][0]
        self.assertEqual((row["status"], row["sent_at"], row["void_reason"]), ("sent", env.clock.now(), None))
        self.assertEqual((len(sc.se(js, "send_envelope")), self.marks(js), self.conflicts(js)), (1, ["sent"], []))

    def test_comparing_a_check_that_still_holds_reopens_the_finding(self):
        """Mutation: compare lease_match instead of pending (the lease id and generation do not change on expiry) and
        the void(expired) row becomes sent again."""
        raw = _mutated(lambda r: self.spec(r)["mark_sent"].update(compare_and_set="lease_match"))
        env, js = self.race(self.expire, raw)
        row = env.task(sc.BASIC)["outbox"][0]
        self.assertEqual((row["status"], row["void_reason"], self.marks(js)), ("sent", "expired", ["sent"]))

    def test_rules_that_break_the_mark_contract_are_refused(self):
        from daemon.core.ports import SpecGap
        breaks = {"unknown check": lambda m: m.update(compare_and_set="no_such_check"),
                  "no status write": lambda m: m["set"].pop("status"),
                  "conflict writes": lambda m: m["on_conflict"].update(writes=["status"]),
                  "no diagnostic": lambda m: m["on_conflict"].pop("diagnostic"),
                  "missing": lambda m: m.clear()}
        for label, fn in breaks.items():
            with self.subTest(case=label):
                with self.assertRaises(SpecGap):
                    MockEnv(_mutated(lambda r: fn(self.spec(r)["mark_sent"])), str(TASKS))


class GuardWaitRollsBack(unittest.TestCase):
    """audit2-daemon-guard-fail-partial-commit: when a lease guard failed on the retry row (building -> building,
    result_failed_tests), the transaction still committed the before_cond counter, the inbox_seen mark and an empty
    usage slot of the next generation; a redelivery was a duplicate and the task sat in building until the lease timed
    out. core_contract.operations.issue_lease.on_guard_wait now discards the whole transaction."""
    WAITS = ("conflict", "writer", "parallel", "lock", "slot", "builder")

    def spec(self, raw=None):
        return (raw or raw_rules())["core_contract"]["operations"]["issue_lease"]["on_guard_wait"]

    def rejected(self, kind, raw=None, **usage):
        """BASIC is building; `kind` makes a guard wait; the builder reports failed_tests."""
        env = MockEnv(raw or str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        res = env.builder_for(sc.BASIC).result_envelope(env.instr(sc.BASIC), "failed_tests", **usage)
        sc.inject(env, kind, sc.BASIC)
        before = sc.event_writes(env.snap())
        m = sc.mark(env)
        out = env.submit(sc.BASIC, "result", copy.deepcopy(res))
        return env, res, before, out, env.journal()[m:]

    def test_on_guard_wait_is_data(self):
        self.assertEqual({k: v for k, v in self.spec().items() if not k.startswith("_")},
                         {"transaction": "rollback", "keep_diagnostics": ["guard_failed", "cond_not_met"],
                          "diagnostic": "guard_wait_rolled_back", "result": "guard_wait"})

    def test_a_waiting_guard_keeps_nothing_of_the_result(self):
        for kind in self.WAITS:
            with self.subTest(kind=kind):
                env, res, before, out, js = self.rejected(kind, calls=3, wall_s=4, cost_units=5)
                self.assertEqual(sc.event_writes(env.snap()), before)
                t = env.task(sc.BASIC)
                self.assertEqual((t["task_state"]["consecutive_failed_tests"], len(t["inbox_seen"]), t["lease_generation"],
                                  t["lease_record"]["status"], t["task_state"]["state"]), (0, 1, 1, "active", "building"))
                self.assertEqual([(u["lease_generation"], u["calls"]) for u in sc.usage_rows(env, sc.BASIC)], [(1, None)])
                self.assertEqual((out["accepted"], out["applied"], out["transition"], out["reason"]),
                                 (False, False, None, "guard_wait"))
                self.assertEqual({r["kind"] for r in js}, {"diagnostic_record"})
                self.assertEqual([r["what"] for r in js], ["cond_not_met", "guard_wait_rolled_back"])
                want = sorted(sc.FAILS_WITH.get(kind, [sc.GUARD_FOR[kind]]))
                self.assertEqual(sc.failed_guard_ids(js), want)
                last = js[-1]
                self.assertEqual((last["event"], sorted(last["failed"]), last["envelope_id"]),
                                 ("result_failed_tests", want, res["envelope_id"]))

    def test_the_same_envelope_is_taken_once_the_guard_passes(self):
        env, res, _, _, _ = self.rejected("conflict", calls=3, wall_s=4, cost_units=5)
        sc.release(env, "conflict", sc.BASIC)
        m = sc.mark(env)
        out = env.submit(sc.BASIC, "result", copy.deepcopy(res))
        t = env.task(sc.BASIC)
        self.assertEqual((out["accepted"], out["transition"]), (True, ("building", "building", "result_failed_tests")))
        self.assertEqual((t["task_state"]["consecutive_failed_tests"], t["lease_generation"], len(sc.sent_ids(env))), (1, 2, 2))
        self.assertEqual([(u["lease_generation"], u["calls"]) for u in sc.usage_rows(env, sc.BASIC)], [(1, 3), (2, None)])
        self.assertEqual([r["args"]["reason"] for r in env.journal()[m:] if r["kind"] == "side_effect_record" and r["id"] == "issue_lease"],
                         ["retry_failed_tests"])
        again = env.submit(sc.BASIC, "result", copy.deepcopy(res))  # generation 2 now: late before duplicate (G40)
        self.assertEqual((again["noop"], again["return_code"]), ("late_envelope_rejected", "R-11"))

    def test_a_failed_usage_write_is_not_queued_for_a_result_not_taken(self):
        env = MockEnv(str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        res = env.builder_for(sc.BASIC).result_envelope(env.instr(sc.BASIC), "failed_tests", calls=3)
        sc.inject(env, "conflict", sc.BASIC)
        env.ports.faults.arm_fail("usage:record_result")
        env.submit(sc.BASIC, "result", copy.deepcopy(res))
        self.assertEqual(env.snap().get("usage_retry", []), [])
        self.assertNotIn("usage_record_failed_warning", [r["what"] for r in env.journal() if r["kind"] == "diagnostic_record"])

    def test_a_queued_lease_request_leaves_no_slot(self):
        env = MockEnv(str(RULES), str(TASKS))
        env.start_task(sc.BASIC)
        sc.inject(env, "conflict", sc.BASIC)
        before = sc.event_writes(env.snap())
        out = env.grant(sc.BASIC)
        self.assertEqual((sc.event_writes(env.snap()), out["reason"], sc.usage_rows(env, sc.BASIC)), (before, "guard_wait", []))
        self.assertIsNone(env.snap()["lease_lock"][sc.BASIC]["holder"])

    def test_an_invalid_envelope_is_a_transition_and_commits(self):
        """instruction_envelope_valid emits envelope_invalid (G48): the result is taken and the task returns."""
        env, res, _, out, js = self.rejected("envelope")
        t = env.task(sc.BASIC)
        self.assertEqual((t["task_state"]["state"], t["lease_record"]["status"], out["accepted"]), ("returned", "returned", True))
        self.assertEqual(len(t["inbox_seen"]), 2)
        self.assertNotIn("guard_wait_rolled_back", [r.get("what") for r in js])

    def test_keep_diagnostics_decides_what_stays(self):
        raw = _mutated(lambda r: self.spec(r).update(keep_diagnostics=[]))
        _, _, _, out, js = self.rejected("conflict", raw)
        self.assertEqual(([r["what"] for r in js], out["reason"]), (["guard_wait_rolled_back"], "guard_wait"))

    def test_rules_that_break_the_contract_are_refused(self):
        from daemon.core.ports import SpecGap
        breaks = {"commit": lambda s: s.update(transaction="commit"), "keep not a list": lambda s: s.update(keep_diagnostics="x"),
                  "no diagnostic": lambda s: s.pop("diagnostic"), "no result": lambda s: s.pop("result"),
                  "missing": lambda s: s.clear()}
        for label, fn in breaks.items():
            with self.subTest(case=label):
                with self.assertRaises(SpecGap):
                    MockEnv(_mutated(lambda r: fn(self.spec(r))), str(TASKS))


class ReportValues(unittest.TestCase):
    """The report shows the values as they were compared, not as the scenario left them afterwards."""

    def test_check_keeps_a_copy_of_a_list_changed_later(self):
        rep = sc.Report()
        writes = []
        rep.eq("원격 쓰기 0건", [], writes)
        rep.gap("공백", "note", expected=[], actual=writes)
        writes.append(("push", sc.BASIC, 2, "P-CUR"))
        self.assertEqual([c["actual"] for c in rep.checks], [[], []])
        self.assertEqual(rep.checks[0]["status"], sc.PASS)

    def test_every_pass_row_prints_equal_expected_and_actual(self):
        bad = [(mid, c["name"]) for mid, res in results().items() for c in res["checks"]
               if c["status"] == sc.PASS and dry_run.compact(c["expected"]) != dry_run.compact(c["actual"])]
        self.assertEqual(bad, [])

    def test_late_result_row_shows_no_remote_write(self):
        row = [c for c in results()["M28"]["checks"] if c["name"].startswith("현재 과제 전이 0건")][0]
        self.assertEqual(row["status"], sc.PASS)
        self.assertEqual(dry_run.compact(row["actual"]), dry_run.compact(([], False, [])))


class CoverageBothWays(unittest.TestCase):
    """audit2-daemon-coverage-reverse: the test ids run must equal the required list. A missing, an unlisted or a
    repeated id each fails the coverage test and `--require-all`; none of them is hidden by the other direction."""
    REQUIRED = ["a", "b", "c"]

    def test_coverage_names_each_direction(self):
        ok = [("M1", "-"), ("M2", "a"), ("M3", "b"), ("M4", "c"), ("STATIC", "static-checks")]
        self.assertEqual(dry_run.coverage(self.REQUIRED, ok), {"not_run": [], "unlisted": [], "repeated": []})
        cases = {
            "missing": (ok[:3] + ok[4:], self.REQUIRED, {"not_run": ["c"], "unlisted": [], "repeated": []}),
            "unlisted": (ok + [("M5", "z")], self.REQUIRED, {"not_run": [], "unlisted": ["z"], "repeated": []}),
            "run twice": (ok + [("M5", "a")], self.REQUIRED, {"not_run": [], "unlisted": [], "repeated": ["a"]}),
            "listed twice": (ok, self.REQUIRED + ["b"], {"not_run": [], "unlisted": [], "repeated": ["b"]}),
            "renamed to -": ([("M4", "-") if e[0] == "M4" else e for e in ok], self.REQUIRED,
                             {"not_run": ["c"], "unlisted": [], "repeated": []}),
        }
        for name, (ran, required, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(dry_run.coverage(required, ran), want)

    def test_dropping_any_one_required_scenario_is_caught(self):
        tasks = json.loads(TASKS.read_text(encoding="utf-8"))["t_op_00_required_test_ids"]
        ran = [(e[0], e[1]) for e in sc.SCENARIOS]
        for i, (mid, tid) in enumerate(ran):
            if mid == "STATIC" or tid == "-":
                continue
            with self.subTest(mid):
                self.assertEqual(dry_run.coverage(tasks, ran[:i] + ran[i + 1:])["not_run"], [tid])

    def run_cli(self, scenarios, required, *extra):
        cfg = json.loads(TASKS.read_text(encoding="utf-8"))
        cfg["t_op_00_required_test_ids"] = required
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(sc, "SCENARIOS", scenarios), \
                contextlib.redirect_stdout(buf):
            p = Path(tmp) / "tasks.json"
            p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            code = dry_run.main(["--rules", str(RULES), "--tasks", str(p), "--scenario", "all", "--quiet", *extra])
        return code, buf.getvalue()

    def test_require_all_fails_on_each_direction(self):
        m41, m44 = SCEN["M41"], SCEN["M44"]
        required = [m41[1], m44[1]]
        code, out = self.run_cli([m41, m44], required, "--require-all")
        self.assertEqual(code, 0, out[-1500:])
        self.assertIn("실행하지 않은 것 0개", out)
        self.assertIn("필수 목록에 없는 시험 ID 0개", out)
        self.assertIn("두 번 이상 나온 시험 ID 0개", out)
        cases = {
            "missing": ([m41], required, "실행하지 않은 시험 ID: " + m44[1]),
            "unlisted": ([m41, m44, ("M44x", "not-in-list", m44[2], m44[3])], required,
                         "필수 목록에 없는 시험 ID 1개, not-in-list"),
            "run twice": ([m41, m44, ("M44x", m44[1], m44[2], m44[3])], required, f"두 번 이상 나온 시험 ID 1개, {m44[1]}"),
            "listed twice": ([m41, m44], required + [m41[1]], f"두 번 이상 나온 시험 ID 1개, {m41[1]}"),
        }
        for name, (scen, req, line) in cases.items():
            with self.subTest(name):
                code, out = self.run_cli(scen, req, "--require-all")
                self.assertEqual(code, 1, out[-1500:])
                self.assertIn(line, out)
                self.assertIn("실패 0건", out)  # the scenarios themselves pass: only coverage fails
                code, _ = self.run_cli(scen, req)
                self.assertEqual(code, 0, "without --require-all coverage is reported, not enforced")

    def test_report_json_lists_both_directions(self):
        m41 = SCEN["M41"]
        with tempfile.TemporaryDirectory() as tmp:
            rep = Path(tmp) / "r.json"
            code, _ = self.run_cli([m41, ("M41x", "not-in-list", m41[2], m41[3])], [m41[1], "never-run"],
                                   "--report", str(rep))
            data = json.loads(rep.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual((data["not_run"], data["unlisted"], data["repeated"]), (["never-run"], ["not-in-list"], []))


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = dry_run.main(list(args))
        return code, buf.getvalue()

    def test_all_scenarios_exit_zero_and_print_expected_and_actual(self):
        code, out = self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "all")
        self.assertEqual(code, 0, out[-2000:])
        self.assertIn("기대:", out)
        self.assertIn("실제:", out)
        self.assertIn("실행하지 않은 시험 ID", out)

    def test_pass_rows_print_the_full_transition_columns(self):
        """The report is what the final audit (T-OP-08) reads: no column is shortened, PASS rows included."""
        for mid in ("M1", "M5", "M10", "M17"):
            code, out = self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", mid)
            self.assertEqual(code, 0)
            self.assertNotIn('..."', out)
            for c in results()[mid]["checks"]:
                self.assertIn(f"      기대: {dry_run.compact(c['expected'])}\n", out, (mid, c["name"]))
                self.assertIn(f"      실제: {dry_run.compact(c['actual'])}\n", out, (mid, c["name"]))
        row = [c for c in results()["M10"]["checks"] if "decision_pending" in c["name"]][0]
        self.assertIn('"review_approved", "merge_wait"', dry_run.compact(row["actual"]))

    def test_evidence_logs_name_the_parent_commit_and_source_hash(self):
        """The logs are made before the commit that holds them, so they name the parent commit and a content hash of
        the sources instead of a SHA they cannot match (README, "증거 기록")."""
        import hashlib
        files = sorted([str(p.relative_to(ROOT)) for p in (ROOT / "tools/daemon").rglob("*")
                        if p.is_file() and "__pycache__" not in p.parts and (ROOT / "tools/daemon/reports") not in p.parents
                        and (ROOT / "tools/daemon/runner_verify") not in p.parents]
                       + ["tools/tests/test_daemon_dry_run.py"], key=lambda x: x.encode())
        listing = "".join(f"{hashlib.sha256((ROOT / f).read_bytes()).hexdigest()}  {f}\n" for f in files)
        want = hashlib.sha256(listing.encode()).hexdigest()
        for name in ("dry_run.log", "unittest.log"):
            head = [ln for ln in (ROOT / "tools/daemon/reports" / name).read_text(encoding="utf-8").splitlines() if ln.startswith("#")]
            line = [ln for ln in head if "generated from parent commit" in ln]
            self.assertEqual(len(line), 1, (name, head))
            self.assertRegex(line[0], r"parent commit [0-9a-f]{40} \+ tree hash of tools/daemon sources sha256:[0-9a-f]{64}")
            self.assertIn("sha256:" + want, line[0], name)
            self.assertNotIn("working tree", "\n".join(head), name)
            self.assertNotIn("base commit", "\n".join(head), name)

    def test_single_scenario_by_number_and_by_test_id(self):
        for sel in ("M41", "restart-ttl-expired-no-resend"):
            code, out = self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", sel, "--quiet")
            self.assertEqual(code, 0)
            self.assertIn("== M41", out)

    def test_exit_code_is_one_when_one_check_differs(self):
        raw = raw_rules()
        raw["core_contract"]["operations"]["resend_outbox"]["checks"] = raw["core_contract"]["operations"]["resend_outbox"]["checks"][:1]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rules.json"
            p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            code, out = self.run_cli("--rules", str(p), "--tasks", str(TASKS), "--scenario", "M42", "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL]", out)

    def test_report_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "out" / "report.json"
            code, _ = self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "M44", "--report", str(p), "--quiet")
            data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(data["results"][0]["id"], "M44")
        self.assertIn("spec_gaps", data)

    def test_unknown_scenario_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "M99")


class InboxSeenPruning(unittest.TestCase):
    """audit1: inbox_seen keeps the idempotency keys of the ended lease and of the live one, not of every generation."""

    def generations(self, env, t):
        return sorted({v["lease_generation"] for v in env.task(t)["inbox_seen"].values()})

    def test_end_lease_drops_keys_of_older_generations_and_keeps_its_own(self):
        env = MockEnv(str(RULES), str(TASKS))
        t = sc.BASIC
        env.bring_to_building(t)
        old, ob = copy.deepcopy(env.instr(t)), env.builder_for(t)
        ob.send_result(old, "failed_tests")  # ends generation 1
        self.assertEqual(self.generations(env, t), [1])  # the ended generation's own keys stay (nothing older to drop)
        env.run_builders("first_heartbeat")  # re-lease: generation 2 starts
        self.assertEqual(self.generations(env, t), [1, 2])  # superseded, but not yet pruned
        instr2 = copy.deepcopy(env.instr(t))
        env.submit(t, "heartbeat", ob.heartbeat_envelope(instr2))
        env.builder_for(t).send_result(instr2, "failed_tests")  # ends generation 2
        self.assertEqual(self.generations(env, t), [2])  # generation 1 keys are gone, generation 2's stay

    def test_pruning_does_not_change_how_old_envelopes_are_classified(self):
        env = MockEnv(str(RULES), str(TASKS))
        t = sc.BASIC
        env.bring_to_building(t)
        old, ob = copy.deepcopy(env.instr(t)), env.builder_for(t)
        hb1 = ob.heartbeat_envelope(old)
        env.submit(t, "heartbeat", copy.deepcopy(hb1))
        ob.send_result(old, "failed_tests")
        env.run_builders("first_heartbeat")
        instr2 = copy.deepcopy(env.instr(t))
        env.builder_for(t).send_result(instr2, "failed_tests")
        self.assertEqual(self.generations(env, t), [2])
        late = env.submit(t, "heartbeat", copy.deepcopy(hb1))  # generation 1 key is gone: still late, not accepted
        self.assertEqual((late["accepted"], late["noop"], late["return_code"]), (False, "late_envelope_rejected", "R-11"))


if __name__ == "__main__":
    unittest.main()
