#!/usr/bin/env python3
"""fixture_only regression tests for the bootstrap integration runner."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prune", HERE / "prune.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


class BootstrapSampleTests(unittest.TestCase):
    def test_verification_records_all_commands_and_propagates_failures(self):
        spec = importlib.util.spec_from_file_location("verify", HERE / "verify.py")
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        for failing in (False, True):
            with self.subTest(failing=failing), tempfile.TemporaryDirectory(dir=HERE) as tmp:
                results = [subprocess.CompletedProcess(cmd, int(failing and i == 0), "fixture_only output\n")
                           for i, cmd in enumerate(verify.COMMANDS)]
                with mock.patch.object(verify, "HERE", Path(tmp)), \
                     mock.patch.object(verify.subprocess, "check_output", return_value="fixture-only-sha\n"), \
                     mock.patch.object(verify.subprocess, "run", side_effect=results) as run, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(verify.main(), int(failing))
                self.assertEqual(run.call_count, len(verify.COMMANDS))
                log = (Path(tmp) / "reports/verification.log").read_text()
                self.assertEqual(log.count("exit:"), len(verify.COMMANDS))
                self.assertIn("verification: " + ("FAIL" if failing else "PASS"), log)

    def test_existing_peel_and_single_drop(self):
        self.assertEqual(P.selftest(), 0)

    def test_followup_merge_is_peeled_with_its_task(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            tasks = {t["id"]: t for t in P.selftest_repo(repo)["tasks"]}
            P.merge_branch(repo, "T-AA-02b", {"shared.txt": "followup fixture_only\n"})
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            merges = P.mainline_merges(repo, ref)
            self.assertEqual(merges[0][1], "T-AA-02")
            P.prune(repo, ref, tasks, "T-BB-01")
            self.assertEqual((repo / "shared.txt").read_text(), "line0\nline1\nline2\nline3\nline4\n")
            self.assertFalse((repo / "pkg/b").exists())
        self.assertIsNone(P.MERGE_TASK.search("onjeon-T-AA-020"))
        self.assertIsNone(P.MERGE_TASK.search("onjeon-T-AA-02unknown"))

    def test_members_peel_preserves_later_members_and_other_settings(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            tasks = {t["id"]: t for t in P.selftest_repo(repo)["tasks"]}
            P.put(repo, "Cargo.toml", '[workspace]\nresolver = "2"\nmembers = ["pkg/a", "pkg/b", "pkg/c", "pkg/d"]\n')
            P.put(repo, "pkg/d/Cargo.toml", '[package]\nname = "fixture_only"\n')
            P.sgit(repo, "add", "-A")
            P.sgit(repo, "commit", "-qm", "fixture_only later workspace edit")
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            P.prune(repo, ref, tasks, "T-BB-01", only="T-AA-02")
            self.assertEqual(P.original_members(repo), ["pkg/a", "pkg/c", "pkg/d"])
            self.assertIn('resolver = "2"', (repo / "Cargo.toml").read_text())

    def test_conflicting_workspace_setting_still_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            tasks = {t["id"]: t for t in P.selftest_repo(repo)["tasks"]}
            P.merge_branch(repo, "T-AA-02b", {
                "Cargo.toml": '[workspace]\nresolver = "2"\nmembers = ["pkg/a", "pkg/b", "pkg/c"]\n'})
            P.put(repo, "Cargo.toml", '[workspace]\nresolver = "3"\nmembers = ["pkg/a", "pkg/b", "pkg/c"]\n')
            P.sgit(repo, "commit", "-qam", "fixture_only conflicting resolver")
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            with self.assertRaisesRegex(P.GraphError, "residual non-prerequisite"):
                P.prune(repo, ref, tasks, "T-BB-01")

    def test_consumes_edges_expand_the_keep_set(self):
        """A consumed crate means every task that produced a path inside its member dir."""
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            raw = P.selftest_repo(repo)
            for t in raw["tasks"]:
                if t["id"] == "T-BB-01":
                    t["consumes"] = ["crate:onjeon-bb"]
            tasks = {t["id"]: t for t in raw["tasks"]}
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            dirs = P.member_crates_at(repo, ref)
            self.assertEqual(dirs.get("onjeon-bb"), "pkg/b")
            self.assertEqual(dirs.get("onjeon-aa"), "pkg/a")
            keep = P.expanded_keep(tasks, "T-BB-01", dirs)
            self.assertEqual(keep, {"T-BB-01", "T-AA-01", "T-AA-02"})
            _, peeled, _, _ = P.prune(repo, ref, tasks, "T-BB-01")
            self.assertEqual(peeled, [])
            self.assertTrue((repo / "pkg/b/src.rs").exists())
            self.assertTrue((repo / "extra/note.txt").exists())

    def test_consumed_path_glob_keeps_its_producer(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            raw = P.selftest_repo(repo)
            for t in raw["tasks"]:
                if t["id"] == "T-BB-01":
                    t["consumes"] = ["path:extra/**"]
            tasks = {t["id"]: t for t in raw["tasks"]}
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            keep = P.expanded_keep(tasks, "T-BB-01", {})
            self.assertEqual(keep, {"T-BB-01", "T-AA-01", "T-AA-02"})

    def test_consumes_expansion_is_transitive(self):
        tasks = {
            "T-AA-01": {"prereq_tasks": [], "produces": ["path:vocab/x.json"], "consumes": []},
            "T-AA-02": {"prereq_tasks": [], "produces": ["crate:onjeon-aa"], "consumes": ["path:vocab/x.json"]},
            "T-BB-01": {"prereq_tasks": [], "produces": ["crate:onjeon-bb"],
                        "consumes": ["crate:onjeon-aa"]},
        }
        keep = P.expanded_keep(tasks, "T-BB-01", {})
        self.assertEqual(keep, {"T-BB-01", "T-AA-01", "T-AA-02"})

    def test_cycle_is_rejected(self):
        tasks = {"T-AA-01": {"prereq_tasks": ["T-AA-02"]},
                 "T-AA-02": {"prereq_tasks": ["T-AA-01"]}}
        with self.assertRaisesRegex(P.GraphError, "cycle"):
            P.keep_set(tasks, "T-AA-01")

    def test_invalid_target_is_rejected(self):
        for tasks in ({}, {"T-AA-01": {"produces": []}},
                      {"T-AA-01": {"produces": ["crate:a", "crate:b"]}},
                      {"T-AA-01": {"produces": ["crate:../escape"]}}):
            with self.subTest(tasks=tasks), self.assertRaises(P.GraphError):
                P.target_crate(tasks, "T-AA-01")

    def test_except_keeps_an_exempted_merge(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            tasks = {t["id"]: t for t in P.selftest_repo(repo)["tasks"]}
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            _, peeled, _, _ = P.prune(repo, ref, tasks, "T-BB-01", except_ids={"T-AA-02"})
            self.assertEqual(peeled, [])
            self.assertTrue((repo / "pkg/b/src.rs").exists())
            self.assertEqual((repo / "shared.txt").read_text(), "line0\nline1\nline-bb\nline3\nline4\n")

    def test_dep_dirs_and_suspects(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            tasks = {t["id"]: t for t in P.selftest_repo(repo)["tasks"]}
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(P.dep_dirs(repo, "onjeon-cc"), {"pkg/c"})
            self.assertEqual(P.suspect_merges(repo, ref, tasks, "T-BB-01", ["pkg/b", "extra"]), ["T-AA-02"])
            self.assertEqual(P.suspect_merges(repo, ref, tasks, "T-BB-01", ["pkg/c"]), [])

    def undeclared_fixture(self, repo):
        """Keep crate calls a symbol a non-prerequisite merge added to its dependency."""
        P.sgit(repo, "init", "-q", "-b", "main")
        P.put(repo, "Cargo.toml", '[workspace]\nresolver = "2"\nmembers = ["pkg/a", "pkg/c"]\n')
        P.put(repo, "pkg/a/Cargo.toml", '[package]\nname = "onjeon-aa"\nversion = "0.1.0"\n'
                                        'edition = "2021"\n[lib]\npath = "src.rs"\n')
        P.put(repo, "pkg/a/src.rs", 'pub fn fixture_base() {}\n')
        P.put(repo, "pkg/c/Cargo.toml", '[package]\nname = "onjeon-cc"\nversion = "0.1.0"\n'
                                        'edition = "2021"\n[lib]\npath = "src.rs"\n'
                                        '[dependencies]\nonjeon-aa = { path = "../a" }\n')
        P.put(repo, "pkg/c/src.rs", "#[test]\nfn fixture_base() { onjeon_aa::fixture_base(); }\n")
        P.sgit(repo, "add", "-A")
        P.sgit(repo, "commit", "-qm", "base")
        tasks = {"tasks": [
            {"id": "T-AA-01", "prereq_tasks": [], "produces": ["crate:onjeon-aa"]},
            {"id": "T-AA-02", "prereq_tasks": [], "produces": ["crate:onjeon-bb"]},
            {"id": "T-BB-01", "prereq_tasks": ["T-AA-01"], "produces": ["crate:onjeon-cc"]},
        ]}
        P.put(repo, "tasks.json", json.dumps(tasks))
        P.sgit(repo, "add", "tasks.json")
        P.sgit(repo, "commit", "-qm", "tasks")
        P.merge_branch(repo, "T-AA-01", {"pkg/a/src.rs": 'pub fn fixture_base() {}\npub fn aa() {}\n'})
        P.merge_branch(repo, "T-AA-02", {
            "Cargo.toml": '[workspace]\nresolver = "2"\nmembers = ["pkg/a", "pkg/b", "pkg/c"]\n',
            "pkg/b/Cargo.toml": '[package]\nname = "onjeon-bb"\nversion = "0.1.0"\n'
                                'edition = "2021"\n[lib]\npath = "src.rs"\n',
            "pkg/b/src.rs": "pub fn fixture_bb() {}\n",
            "pkg/a/src.rs": 'pub fn fixture_base() {}\npub fn aa() {}\n'
                            'pub fn fixture_marker() -> &\'static str { "m" }\n'})
        P.merge_branch(repo, "T-BB-01", {
            "pkg/c/src.rs": "#[test]\nfn fixture_only() { assert_eq!(onjeon_aa::fixture_marker(), \"m\"); }\n"})
        return {t["id"]: t for t in tasks["tasks"]}

    def test_diagnose_names_the_undeclared_dependency(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            tasks = self.undeclared_fixture(repo)
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            lines = []
            needed = P.diagnose(repo, ref, tasks, "T-BB-01", "onjeon-cc",
                                Path(tmp) / "diag", lines.append)
            self.assertEqual(needed, {"T-AA-02"}, lines)
            self.assertIn("T-AA-02", "\n".join(lines))

    def test_diagnose_reports_when_nothing_was_peeled_from_the_closure(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo, _ = self.fixture(tmp)
            tasks = {"tasks": [
                {"id": "T-AA-01", "prereq_tasks": [], "produces": ["crate:onjeon-aa"]},
                {"id": "T-AA-02", "prereq_tasks": ["T-AA-01"], "produces": ["crate:onjeon-bb", "path:extra/**"]},
                {"id": "T-BB-01", "prereq_tasks": ["T-AA-01"], "produces": ["crate:onjeon-cc"]},
            ]}
            tasks = {t["id"]: t for t in tasks["tasks"]}
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            lines = []
            needed = P.diagnose(repo, ref, tasks, "T-BB-01", "onjeon-cc",
                                Path(tmp) / "diag", lines.append)
            self.assertEqual(needed, [], lines)
            self.assertIn("not explained", "\n".join(lines))

    def test_conflicting_non_prerequisite_edit_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo = Path(tmp)
            tasks = {t["id"]: t for t in P.selftest_repo(repo)["tasks"]}
            ref = P.sgit(repo, "rev-parse", "HEAD").stdout.strip()
            with mock.patch.object(P, "unmerge", return_value=False):
                with self.assertRaisesRegex(P.GraphError, "residual non-prerequisite"):
                    P.prune(repo, ref, tasks, "T-BB-01")

    def test_usage_rejects_missing_values_and_unsafe_task_ids(self):
        for args in ([], ["--task"], ["--ref"], ["--repo"],
                     ["--task", "--ref"], ["--task", "../../escape"]):
            with self.subTest(args=args):
                result = subprocess.run(["bash", str(HERE / "run.sh"), *args],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)

    def fixture(self, tmp):
        root = Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        tasks = P.selftest_repo(repo)
        for name in ("a", "b", "c"):
            P.put(repo, f"pkg/{name}/Cargo.toml",
                  f'[package]\nname = "onjeon-{name}{name}"\nversion = "0.1.0"\n'
                  'edition = "2021"\n[lib]\npath = "src.rs"\n')
            P.put(repo, f"pkg/{name}/src.rs", '#[test]\nfn fixture_only() { assert_eq!(2 + 2, 4); }\n')
        P.put(repo, P.DEFAULT_TASKS.relative_to(P.ROOT), json.dumps(tasks))
        P.sgit(repo, "add", "-A")
        P.sgit(repo, "commit", "-qm", "fixture_only valid crates and pinned task graph")
        runner = root / "harness"
        runner.mkdir()
        for name in ("run.sh", "prune.py"):
            shutil.copyfile(HERE / name, runner / name)
        P.put(repo, P.DEFAULT_TASKS.relative_to(P.ROOT), '{"tasks": []}')
        return repo, runner

    def test_runner_builds_real_fixture_and_uses_committed_graph(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo, runner = self.fixture(tmp)
            result = subprocess.run(["bash", str(runner / "run.sh"), "--task", "T-BB-01",
                                     "--repo", str(repo), "--ref", "HEAD"],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("bootstrap-sample-build: PASS", result.stdout)
            self.assertEqual(result.stdout.count("+ cargo build -p onjeon-cc"), 2)
            self.assertEqual(result.stdout.count("+ cargo test -p onjeon-cc"), 2)
            self.assertIn("fixture_only ... ok", result.stdout)
            self.assertFalse(list(runner.glob(".run.*")))
            self.assertEqual(len(list((runner / "reports").glob("*.log"))), 1)

    def test_runner_propagates_real_build_failure(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            repo, runner = self.fixture(tmp)
            P.put(repo, "pkg/c/src.rs", "fixture_only invalid Rust\n")
            P.sgit(repo, "add", "pkg/c/src.rs")
            P.sgit(repo, "commit", "-qm", "fixture_only compile failure")
            result = subprocess.run(["bash", str(runner / "run.sh"), "--task", "T-BB-01",
                                     "--repo", str(repo), "--ref", "HEAD"],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("bootstrap-sample-build: FAIL", result.stdout)
            self.assertNotIn("+ cargo test", result.stdout)
            self.assertFalse(list(runner.glob(".run.*")))


if __name__ == "__main__":
    unittest.main()
