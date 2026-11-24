"""Verify the advisory purpose report with synthetic task and evidence inputs."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path("tools/release_readiness")
BUNDLE = Path("docs/blueprint/proposals/설계검토_결과")
EVIDENCE = Path("docs/release-readiness/evidence")
TASKS_STATE = Path("docs/blueprint/progress/tasks_state.json")


class PurposeProgress(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.tool = self.root / TOOL
        self.tool.mkdir(parents=True)
        for name in ("progress.py", "check.py"):
            shutil.copyfile(ROOT / TOOL / name, self.tool / name)
        bundle = self.root / BUNDLE
        bundle.mkdir(parents=True)
        self.evidence = self.root / EVIDENCE
        self.evidence.mkdir(parents=True)
        self.registry = bundle / "tasks.json"
        self.purpose = bundle / "09_제품목적_대응표.md"
        self.tasks_state = self.root / TASKS_STATE
        self.tasks_state.parent.mkdir(parents=True)
        self.manifest = self.evidence / "readiness.json"
        self.write_json(self.registry, {
            "tasks": [{"id": task} for task in ("T-AA-01", "T-AA-02", "T-AA-03")],
            "feature_registry": [{"id": "one", "tasks": ["T-AA-01"],
                                  "acceptance_tests": ["test"], "excluded": False}],
        })
        self.purpose.write_text(
            "| # | 구현 작업 |\n|---|---|\n"
            "| P01 | T-AA-01, T-AA-02 |\n"
            + "".join(f"| P{i:02} | T-AA-03 |\n" for i in range(2, 20)),
            encoding="utf-8",
        )
        self.write_states({"T-AA-01": {"merge_sha": "a" * 40, "state": None, "evidence_path": None}})

    def write_json(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def write_states(self, records):
        self.write_json(self.tasks_state, {"version": 1, "tasks": records})

    def run_report(self):
        return subprocess.run([sys.executable, "-I", str(self.tool / "progress.py")],
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def output(self):
        result = self.run_report()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def write_release_record(self):
        states = {}
        for tid, state, sha in (("T-AA-01", "merged", "a" * 40), ("T-AA-02", "done", "b" * 40)):
            reference = f"{tid}/review.md"
            (self.evidence / tid).mkdir()
            (self.evidence / reference).write_text("synthetic task evidence")
            states[tid] = {"state": state, "merge_sha": sha, "evidence_path": reference}
        self.write_states(states)
        (self.evidence / "artifact.md").write_text("synthetic evidence")
        (self.evidence / "test.log").write_text("synthetic execution")
        data = {
            "version": 1,
            "rows": {"P01": {
                "environment": "release",
                "evidence": ["artifact.md"],
                "acceptance_tests": [{"name": "acceptance", "log": "test.log", "exit_code": 0}],
            }},
            "features": {},
        }
        self.write_json(self.manifest, data)
        return data

    def test_complete_denominators_partial_merges_and_no_manifest(self):
        output = self.output()
        self.assertIn("Closed purpose rows **0/19** · Merged tasks **1/3**", output)
        self.assertEqual([f"P{i:02}" for i in range(1, 20)],
                         re.findall(r"^\| (P\d+) \|", output, re.MULTILINE))
        self.assertIn("| P01 | 1/2 | T-AA-02 | 0/2 | 0/0 | Open |", output)
        self.assertIn("| P19 | 0/1 | T-AA-03 | 0/1 | 0/0 | Open |", output)
        self.evidence.rmdir()
        self.assertEqual(output, self.output())
        self.write_states({})
        self.assertIn("Closed purpose rows **0/19** · Merged tasks **0/3**", self.output())

    def test_paths_can_be_supplied_from_another_working_directory(self):
        result = subprocess.run(
            [sys.executable, "-I", str(ROOT / TOOL / "progress.py"),
             "--registry", str(self.registry), "--purpose", str(self.purpose),
             "--tasks-state", str(self.tasks_state), "--evidence", str(self.evidence)],
            cwd=self.tool, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(self.output(), result.stdout)

    def test_task_artifacts_are_visible_before_row_evidence_registration(self):
        task_dir = self.evidence / "T-AA-02"
        task_dir.mkdir()
        (task_dir / "empty").touch()
        (task_dir / "directory").mkdir()
        (self.root / "outside").write_text("outside")
        (task_dir / "symlink").symlink_to(self.root / "outside")
        (self.evidence / "T-AA-01").symlink_to(self.root, target_is_directory=True)
        self.assertIn("| P01 | 1/2 | T-AA-02 | 0/2 | 0/0 | Open |", self.output())
        (task_dir / "directory/artifact").write_text("tentative artifact")
        self.assertIn("| P01 | 1/2 | T-AA-02 | 1/2 | 0/0 | Open |", self.output())
        self.assertIn("| P19 | 0/1 | T-AA-03 | 0/1 | 0/0 | Open |", self.output())

    def test_verified_row_closes_with_all_merges_and_successful_release_logs(self):
        self.write_release_record()
        output = self.output()
        self.assertIn("Closed purpose rows **1/19** · Merged tasks **2/3**", output)
        self.assertIn("| P01 | 2/2 | — | 2/2 | 1/1 | Closed |", output)
        states = json.loads(self.tasks_state.read_text())["tasks"]
        states["T-AA-01"]["merge_sha"] = None
        self.write_states(states)
        self.assertIn("| P01 | 1/2 | T-AA-01 | 2/2 | 1/1 | Open |", self.output())
        states["T-AA-01"].update(merge_sha="a" * 40, state="merged_invalid_approval")
        self.write_states(states)
        self.assertIn("| P01 | 2/2 | — | 2/2 | 1/1 | Open |", self.output())
        states["T-AA-01"]["state"] = "merged"
        self.write_states(states)
        (self.evidence / states["T-AA-01"]["evidence_path"]).unlink()
        self.assertIn("| P01 | 2/2 | — | 1/2 | 1/1 | Open |", self.output())

    def test_judge_and_report_share_the_default_ledger(self):
        self.write_release_record()
        states = json.loads(self.tasks_state.read_text())["tasks"]
        for state, expected in (("audit_queued", "Closed"), ("merge_wait", "Open")):
            with self.subTest(state=state):
                states["T-AA-02"]["state"] = state
                self.write_states(states)
                self.assertIn(f"| P01 | 2/2 | — | 2/2 | 1/1 | {expected} |", self.output())
                result = subprocess.run([sys.executable, "-I", str(self.tool / "check.py"), "--json"],
                                        cwd=self.tool, capture_output=True, text=True, timeout=10)
                self.assertEqual(1, result.returncode, result.stderr)  # The other rows stay open.
                self.assertEqual(expected.lower(), json.loads(result.stdout)["rows"]["P01"]["status"])

    def test_row_evidence_presence_does_not_close_row_without_release_execution(self):
        data = self.write_release_record()
        record = data["rows"]["P01"]
        record["acceptance_tests"][0]["exit_code"] = 1
        self.write_json(self.manifest, data)
        self.assertIn("| P01 | 2/2 | — | 2/2 | 1/1 | Open |", self.output())
        record["acceptance_tests"][0]["exit_code"] = 0
        (self.evidence / "test.log").unlink()
        self.write_json(self.manifest, data)
        self.assertIn("| P01 | 2/2 | — | 2/2 | 1/1 | Open |", self.output())
        (self.evidence / "test.log").write_text("synthetic execution")
        record["environment"] = "fixture"
        self.write_json(self.manifest, data)
        self.assertIn("| P01 | 2/2 | — | 2/2 | 1/1 | Open |", self.output())

    def test_missing_empty_or_outside_row_evidence_is_not_counted(self):
        data = self.write_release_record()
        (self.evidence / "empty").write_text(" \n")
        (self.root / "outside.md").write_text("outside")
        (self.evidence / "escape").symlink_to(self.root / "outside.md")
        data["rows"]["P01"]["evidence"] += ["missing", "empty", "../outside.md", "escape"]
        self.write_json(self.manifest, data)
        self.assertIn("| P01 | 2/2 | — | 2/2 | 1/5 | Open |", self.output())

    def test_invalid_inputs_emit_diagnostic_instead_of_counts(self):
        for content, diagnostic in (
            ("[]", "requires version and tasks"),
            ('{"version":1,"tasks":{"T-XX-99":{}}}', "unknown task"),
            ('{"version":1,"tasks":{"T-AA-01":{"state":null,"merge_sha":"abc","evidence_path":null}}}',
             "expected a full merge commit SHA"),
            ('{"version":1,"tasks":{"T-AA-01":{},"T-AA-01":{}}}', "duplicate JSON key"),
            ("{", "Expecting"),
        ):
            with self.subTest(content=content):
                self.tasks_state.write_text(content)
                result = self.run_report()
                self.assertEqual(2, result.returncode)
                self.assertIn(diagnostic, result.stderr)
                self.assertEqual("", result.stdout)
        self.write_states({})
        self.purpose.write_text("| # | 구현 작업 |\n| P01 | T-AA-01 |\n", encoding="utf-8")
        result = self.run_report()
        self.assertEqual(2, result.returncode)
        self.assertIn("missing purpose rows", result.stderr)

    def test_workflow_writes_summary_and_marks_report_as_advisory(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        steps = re.findall(
            r"^      - name: Product purpose progress\n((?:^        [^\n]+\n)+)",
            workflow, re.MULTILINE,
        )
        self.assertEqual(1, len(steps))
        self.assertIn("        continue-on-error: true\n", steps[0])
        self.assertIn("        shell: bash\n", steps[0])
        command = re.search(r"^        run: (.+)$", steps[0], re.MULTILINE)[1]
        summary = self.root / "job summary.md"
        for root, code, message in (
            (ROOT, 0, "| P19 |"),
            (self.root, 0, "Merged tasks **1/3**"),
            (self.root, 2, "Cannot report product purpose progress"),
        ):
            with self.subTest(root=root, code=code):
                if code:
                    self.tasks_state.unlink()
                summary.write_text("Previous step\n")
                result = subprocess.run(
                    ["bash", "-eo", "pipefail", "-c", command], cwd=root,
                    env=dict(os.environ, GITHUB_STEP_SUMMARY=str(summary)),
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(code, result.returncode, result.stdout + result.stderr)
                self.assertIn(message, result.stdout)
                self.assertEqual("Previous step\n" + result.stdout, summary.read_text())
