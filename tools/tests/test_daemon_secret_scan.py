"""Real-format, synthetic-only corpus; no provider calls, commits or pushes.

Values are assembled at runtime so fixture source cannot be confused with a credential.
The Git integration exercises only a temporary index and tree, never a commit or remote.
"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from daemon import scenarios as sc
from daemon.core import Rules, secret_scan
from daemon.mock_env import MockEnv
from daemon.runner_verify import cli, secret_scan_preflight
from daemon.runner_verify.secret_scan_preflight import CASES, corpus, non_secret
from daemon.runner_verify.adapters import RealGit
from daemon.runner_verify.common import Layout

RULES = ROOT / "docs/blueprint/proposals/설계검토_결과/daemon_rules.json"
TASKS = ROOT / "tools/daemon/mock_tasks.json"

EXCLUDED = (
    ".env", ".env.local", ".ENV.LOCAL", "nested/.Env.production",
    "nested/cert.PEM", "private.KEY", "Credentials.JSON", "nested/SeCrEt.txt",
    "TARGET/keep.txt", "nested/Node_Modules/keep.txt",
)
KEPT = ("src/app.py", "nested/settings.json", "environment.txt", ".envoy", "keynote.md")


class SecretCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(json.loads(RULES.read_text(encoding="utf-8")))
        cls.pats = secret_scan.patterns(cls.rules)

    def test_corpus_labels_are_pinned(self):
        # Removing a format from corpus() must not silently remove it from the preflight too.
        self.assertEqual(set(corpus()), set(CASES))
        self.assertEqual(len(corpus()), 28)

    def test_real_format_corpus_is_detected_and_recursively_redacted(self):
        for label, value in corpus().items():
            with self.subTest(case=label):
                self.assertGreater(secret_scan.count(self.pats, value), 0)
                nested = {"details": ["safe", (value,)]}
                clean, hits = secret_scan.redact(self.pats, nested)
                self.assertGreater(hits, 0)
                self.assertEqual(clean, {"details": ["safe", (secret_scan.REDACTED,)]})
                self.assertEqual(secret_scan.count_in(self.pats, nested), hits)

    def test_nonsecret_boundaries_and_ordinary_digests_are_preserved(self):
        for label, value in non_secret().items():
            with self.subTest(case=label):
                self.assertEqual(secret_scan.redact(self.pats, value), (value, 0))

    def test_bare_32_and_64_hex_keys_are_detected_not_exempted(self):
        # The acceptance scope includes bare R2 keys. They are positive cases; only a digest
        # label on the same line may suppress detection.
        hex32, hex64 = "a1" * 16, "b2" * 32
        for label, value in (("bare-32", hex32), ("bare-64", hex64),
                             ("json-bare-64", json.dumps({"value": hex64}))):
            with self.subTest(case=label):
                self.assertGreater(secret_scan.count(self.pats, value), 0)
                self.assertEqual(secret_scan.redact(self.pats, value), (secret_scan.REDACTED, 1))
        for label, value in (("checksum", 'checksum = "' + hex64 + '"'),
                             ("sha256", '"sha256": "' + hex64 + '"'),
                             ("sha256-line", "sha256:" + hex64),
                             ("tree-hash", 'tree_hash = "' + hex32 + '"'),
                             ("content-hash", '"content_hash": "' + hex64 + '"')):
            with self.subTest(case=label):
                self.assertEqual(secret_scan.count(self.pats, value), 0)

    def test_corpus_stops_handoff_before_commit_or_push(self):
        for label, value in corpus().items():
            with self.subTest(case=label):
                env, path = sc.handoff_bench(str(RULES), str(TASKS))
                env.ports.worktree.write(path, "src/config.txt", value)
                env.clock.advance(1)
                sc.switch(env)
                self.assertEqual((env.state(sc.HANDOFF), env.task(sc.HANDOFF)["task_state"]["return_code"],
                                  env.lease(sc.HANDOFF)["status"]), ("returned", "R-10", "revoked"))
                self.assertEqual((env.ports.git.commit_count, env.ports.git.push_count), (0, 0))
                self.assertEqual(secret_scan.count_in(self.pats, env.journal()), 0)

    def test_digest_bearing_files_do_not_stop_handoff(self):
        # Lock-file checksums and log hashes share the 32/64-hex shape but are not credentials.
        env, path = sc.handoff_bench(str(RULES), str(TASKS))
        hex32, hex64 = "a1" * 16, "b2" * 32
        env.ports.worktree.write(path, "Cargo.lock", 'checksum = "' + hex64 + '"\n')
        env.ports.worktree.write(path, "checksums.json",
                                 json.dumps({"sha256": hex64, "content_hash": hex32}) + "\n")
        env.ports.worktree.write(path, "build.log", "sha256:" + hex64 + "\n")
        env.clock.advance(1)
        sc.switch(env)
        self.assertEqual(env.state(sc.HANDOFF), "leased")
        self.assertGreaterEqual(env.ports.git.commit_count, 1)
        self.assertEqual(env.ports.git.push_count, 1)

    def test_corpus_rejects_result_signal_and_heartbeat_without_storing_values(self):
        for label, value in corpus().items():
            for kind in ("result", "switch_signal", "heartbeat"):
                with self.subTest(case=label, kind=kind):
                    env = MockEnv(str(RULES), str(TASKS))
                    env.bring_to_building(sc.BASIC)
                    builder, instr = env.builder_for(sc.BASIC), env.instr(sc.BASIC)
                    if kind == "result":
                        envelope = builder.result_envelope(instr, "pr_opened")
                    elif kind == "switch_signal":
                        envelope = builder.signal_envelope(instr)
                    else:
                        envelope = builder.heartbeat_envelope(instr)
                    envelope["details"] = {"items": [value]}
                    seen = env.task(sc.BASIC)["inbox_seen"]
                    out = env.submit(sc.BASIC, kind, envelope)
                    self.assertFalse(out["accepted"])
                    self.assertGreater(out["secret_detected"], 0)
                    self.assertEqual(env.task(sc.BASIC)["task_state"]["return_code"], "R-10")
                    self.assertEqual(env.lease(sc.BASIC)["status"], "revoked")
                    self.assertEqual(env.task(sc.BASIC)["inbox_seen"], seen)
                    self.assertEqual(secret_scan.count_in(self.pats, env.core.snapshot()), 0)

    def test_corpus_is_redacted_before_journal_append(self):
        for label, value in corpus().items():
            with self.subTest(case=label):
                env = MockEnv(str(RULES), str(TASKS))
                with env.ports.store.transaction() as data:
                    env.core.rec.diagnostic(data, sc.BASIC, "synthetic-corpus", details=[value])
                snapshot = env.core.snapshot()
                self.assertEqual(snapshot["journal"][-1]["details"], [secret_scan.REDACTED])
                self.assertGreater(snapshot["secret_hits"][-1]["match_count"], 0)
                self.assertEqual(secret_scan.count_in(self.pats, snapshot), 0)


class ManifestExcludes(unittest.TestCase):
    def test_mock_manifest_excludes_env_variants_and_case_variants(self):
        env, path = sc.handoff_bench(str(RULES), str(TASKS))
        for rel in EXCLUDED + KEPT:
            env.ports.worktree.write(path, rel, "ordinary text")
        files = env.ports.git.included_files(path)
        for rel in EXCLUDED:
            with self.subTest(excluded=rel):
                self.assertNotIn(rel, files)
        for rel in KEPT:
            self.assertIn(rel, files)

    def test_real_git_manifest_matches_mock_without_commits_or_pushes(self):
        # No remote is provisioned. Every subprocess is checked before it can run.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            layout = Layout(tmp).make()
            layout.clone.mkdir()
            rules = Rules(json.loads(RULES.read_text(encoding="utf-8")))
            git = RealGit(layout, "unused", rules.get("preserve_manifest.excludes"), None)
            run = subprocess.run

            def local_git_only(args, **kwargs):
                self.assertEqual(args[0], "git")
                self.assertIn(args[1], {"init", "add", "write-tree", "ls-files"})
                return run(args, **kwargs)

            with mock.patch("subprocess.run", side_effect=local_git_only):
                git._git(["init", "-q"], cwd=layout.clone)
                for rel in EXCLUDED + KEPT:
                    target = layout.clone / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("ordinary text", encoding="utf-8")
                digest = "b2" * 32
                digest_files = {
                    "Cargo.lock": 'checksum = "' + digest + '"\n',
                    "manifest.json": json.dumps({"sha256": digest}) + "\n",
                }
                for rel, content in digest_files.items():
                    (layout.clone / rel).write_text(content, encoding="utf-8")
                expected = set(KEPT) | set(digest_files)
                files = git.included_files(layout.clone)
                self.assertEqual(set(files), expected)
                # A digest-bearing file is preserved but is not a secret; a bare 64-hex value
                # without a credential name must not stop the handoff.
                pats = secret_scan.patterns(rules)
                for rel, _content in digest_files.items():
                    self.assertEqual(secret_scan.count(pats, files[rel]), 0, rel)
                # included_files uses a throwaway index, so the default index never affects the
                # manifest and is never changed by it. Stage everything, then compare both sides.
                git._git(["add", "-A"], cwd=layout.clone)
                staged_before = git._git(["ls-files", "-s", "-z"], cwd=layout.clone).stdout
                self.assertEqual(set(git.included_files(layout.clone)), expected)
                staged_after = git._git(["ls-files", "-s", "-z"], cwd=layout.clone).stdout
                self.assertEqual(staged_after, staged_before)


class RunnerPreflight(unittest.TestCase):
    def test_current_rules_cover_every_preflight_case(self):
        self.assertEqual(secret_scan_preflight.missing_cases(RULES), [])

    def test_preflight_rejects_rules_that_omit_bare_key_detection(self):
        # No exception in the corpus: removing the bare-key pattern must fail the preflight.
        original = json.loads(RULES.read_text(encoding="utf-8"))
        patterns = original["preserve_manifest"]["secret_patterns"]["patterns"]
        kept = [p for p in patterns if "content[_-]?hash" not in p]
        self.assertEqual(len(kept), len(patterns) - 1)
        original["preserve_manifest"]["secret_patterns"]["patterns"] = kept
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "rules.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            failures = secret_scan_preflight.missing_cases(path)
        for label in ("bare-r2-key-32", "bare-r2-key-64", "bare-r2-key-json"):
            self.assertIn(f"missing-format:{label}", failures)

    def test_empty_and_all_matching_patterns_are_rejected(self):
        original = json.loads(RULES.read_text(encoding="utf-8"))
        for patterns, expected in (([""], lambda f: f == "empty-pattern"),
                                   (["."], lambda f: f.startswith("non-secret:")),
                                   ([".*"], lambda f: f.startswith("non-secret:"))):
            with self.subTest(patterns=patterns), tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                original["preserve_manifest"]["secret_patterns"]["patterns"] = patterns
                rules_path = Path(tmp) / "rules.json"
                rules_path.write_text(json.dumps(original), encoding="utf-8")
                failures = secret_scan_preflight.missing_cases(rules_path)
                self.assertTrue(any(expected(f) for f in failures), failures)

    def test_missing_or_invalid_patterns_stop_cli_before_any_scenario(self):
        original = json.loads(RULES.read_text(encoding="utf-8"))
        for patterns in ([], ["never-matches"], ["["], [""], ["."], [".*"]):
            with self.subTest(patterns=patterns), tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                original["preserve_manifest"]["secret_patterns"]["patterns"] = patterns
                rules_path = Path(tmp) / "rules.json"
                rules_path.write_text(json.dumps(original), encoding="utf-8")
                report = Path(tmp) / "output" / "report.json"
                err = io.StringIO()
                with mock.patch.object(cli, "Ctx") as ctx, \
                     mock.patch.object(cli.reporting, "run_scenario") as scenario, \
                     contextlib.redirect_stderr(err):
                    code = cli.main(["--rules", str(rules_path), "--report", str(report), "--no-cli"])
                self.assertEqual(code, 1)
                self.assertIn("secret scan preflight failed", err.getvalue())
                ctx.assert_not_called()
                scenario.assert_not_called()
                self.assertFalse(report.parent.exists())

    def test_unreadable_and_malformed_rules_stop_cli(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "rules.json"
            for content in (None, "{", "{}"):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_text(content, encoding="utf-8")
                    with mock.patch.object(cli, "Ctx") as ctx, \
                         contextlib.redirect_stderr(io.StringIO()) as err:
                        code = cli.main(["--rules", str(path), "--report", str(Path(tmp) / "r.json")])
                    self.assertEqual(code, 1)
                    self.assertIn("unreadable or invalid rules", err.getvalue())
                    ctx.assert_not_called()


if __name__ == "__main__":
    unittest.main()
