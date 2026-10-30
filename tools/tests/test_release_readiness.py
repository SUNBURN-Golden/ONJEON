"""Executable acceptance for the readiness scaffold; all positive data is synthetic.

These tests verify gate mechanics, never supply product completion evidence.
"""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/release_readiness/check.py"
SPEC = importlib.util.spec_from_file_location("release_readiness_check", SCRIPT)
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        self.registry = self.root / "tasks.json"
        self.purpose = self.root / "purpose.md"
        self.data = {
            "tasks": [{"id": f"T-AA-{i:02}"} for i in range(1, 20)],
            "feature_registry": [{"id": "feature", "tasks": ["T-AA-01"],
                                  "acceptance_tests": ["screen flow", "data trace"],
                                  "excluded": False, "scope_decision": None}],
        }
        self.table = "| # | 구현 작업 |\n|---|---|\n" + "".join(
            f"| P{i:02} | T-AA-{i:02} |\n" for i in range(1, 20))
        self.manifest = {
            "version": 1,
            "task_states": {f"T-AA-{i:02}": "done" for i in range(1, 20)},
            "rows": {f"P{i:02}": self.record(f"P{i:02}") for i in range(1, 20)},
            "features": {"feature": self.record("feature", ["screen flow", "data trace"])},
        }
        self.write()

    def record(self, key, names=None):
        (self.evidence / f"{key}.txt").write_text("Synthetic test artifact, not product evidence.\n")
        (self.evidence / f"{key}.log").write_text("Synthetic successful execution.\n")
        return {"environment": "release", "evidence": [f"{key}.txt"],
                "acceptance_tests": [{"name": name, "log": f"{key}.log", "exit_code": 0}
                                     for name in (names or ["purpose acceptance"])]}

    def write(self):
        self.registry.write_text(json.dumps(self.data))
        self.purpose.write_text(self.table)
        (self.evidence / "readiness.json").write_text(json.dumps(self.manifest))

    def cli(self, *extra):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--registry", str(self.registry),
                               "--purpose", str(self.purpose), "--evidence", str(self.evidence),
                               "--json", *map(str, extra)], cwd=self.root, capture_output=True, text=True)

    def report(self, code):
        self.write()
        result = self.cli()
        self.assertEqual(code, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_open(self, report, key, reason):
        group = "rows" if key.startswith("P") else "features"
        self.assertEqual("open", report[group][key]["status"])
        self.assertIn(reason, " ".join(report[group][key]["reasons"]))

    def test_all_covered_and_all_post_merge_states(self):
        rules = json.loads((C.BUNDLE / "daemon_rules.json").read_text())
        self.assertEqual(set(rules["post_merge_states"]), C.POST_MERGE)
        for state in ("merged", "audit_queued", "done"):
            with self.subTest(state=state):
                self.manifest["task_states"]["T-AA-01"] = state
                report = self.report(0)
                self.assertEqual({"open": 0, "closed": 19, "excluded": 0}, report["rows_counts"])
                self.assertEqual(1, report["features_counts"]["closed"])

    def test_empty_evidence_or_missing_directory_reports_19_open(self):
        empty = self.root / "empty"
        for exists in (False, True):
            if exists:
                empty.mkdir()
            result = self.cli("--evidence", empty)
            self.assertEqual(1, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual({"open": 19, "closed": 0, "excluded": 0}, report["rows_counts"])
            self.assertEqual({f"P{i:02}" for i in range(1, 20)}, set(report["rows"]))

    def test_purpose_rows_all_closed_every_row_requires_evidence_and_logs(self):
        for i in range(1, 20):
            key = f"P{i:02}"
            for suffix in ("txt", "log"):
                with self.subTest(row=key, artifact=suffix):
                    path = self.evidence / f"{key}.{suffix}"
                    content = path.read_bytes()
                    path.unlink()
                    report = self.report(1)
                    self.assertEqual(1, report["rows_counts"]["open"])
                    self.assert_open(report, key, "missing/empty artifact")
                    path.write_bytes(content)

    def test_release_readiness_rejects_incomplete_feature(self):
        for field in ("evidence", "acceptance_tests"):
            with self.subTest(field=field):
                saved = self.manifest["features"]["feature"].pop(field)
                self.assert_open(self.report(1), "feature", "missing")
                self.manifest["features"]["feature"][field] = saved
        for suffix in ("txt", "log"):
            path = self.evidence / f"feature.{suffix}"
            content = path.read_bytes()
            path.unlink()
            self.assert_open(self.report(1), "feature", "missing/empty artifact")
            path.write_bytes(content)

    def test_every_linked_task_requires_post_merge(self):
        for i in range(1, 20):
            for state in (None, "building", "merge_wait", "merged_invalid_approval", "cancelled"):
                with self.subTest(task=i, state=state):
                    tid = f"T-AA-{i:02}"
                    if state is None:
                        self.manifest["task_states"].pop(tid)
                    else:
                        self.manifest["task_states"][tid] = state
                    report = self.report(1)
                    self.assert_open(report, f"P{i:02}", tid)
                    if i == 1:
                        self.assert_open(report, "feature", tid)
                    self.manifest["task_states"][tid] = "done"

    def test_missing_row_record_and_reference_lists(self):
        saved = self.manifest["rows"].pop("P19")
        self.assert_open(self.report(1), "P19", "missing")
        self.manifest["rows"]["P19"] = saved
        for field in ("evidence", "acceptance_tests"):
            saved = self.manifest["rows"]["P19"][field]
            self.manifest["rows"]["P19"][field] = []
            self.assert_open(self.report(1), "P19", "missing")
            self.manifest["rows"]["P19"][field] = saved

    def test_all_tasks_in_a_row_are_required_and_repeated_headers_work(self):
        self.table = self.table.replace("| P01 | T-AA-01 |", "| P01 | `T-AA-01`, `T-AA-02` |")
        self.table = self.table.replace("| P10 |", "\n| # | 구현 작업 |\n|---|---|\n| P10 |")
        self.report(0)
        del self.manifest["task_states"]["T-AA-02"]
        self.assert_open(self.report(1), "P01", "T-AA-02")

    def test_malformed_and_duplicate_execution_records_are_incomplete(self):
        record = self.manifest["rows"]["P01"]
        good = copy.deepcopy(record["acceptance_tests"])
        for logs in ("prose", [None], [{}], [{"name": "test", "log": "P01.log"}],
                     good + good, [{"name": "test", "log": None, "exit_code": 0}]):
            with self.subTest(logs=logs):
                record["acceptance_tests"] = logs
                self.assertEqual("open", self.report(1)["rows"]["P01"]["status"])

    def test_evidence_directory_cannot_be_a_file(self):
        self.assertEqual(2, self.cli("--evidence", self.registry).returncode)

    def test_text_output_reports_both_gate_counts(self):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--registry", str(self.registry),
                                 "--purpose", str(self.purpose), "--evidence", str(self.evidence)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("purpose-rows-all-closed: open=0, closed=19, excluded=0", result.stdout)
        self.assertIn("release-readiness-rejects-incomplete: open=0, closed=1, excluded=0", result.stdout)

    def test_unsupported_exclusions_including_partial_scope_and_pending_gates(self):
        for key in ("P01", "P02", "P18", "feature"):
            group = "features" if key == "feature" else "rows"
            for decision in (None, "invented", "ADR-0018", "DEC-D-18", "BLUEPRINT §1 A7"):
                with self.subTest(key=key, decision=decision):
                    record = self.manifest[group][key]
                    record.update(excluded=True, scope_decision=decision)
                    self.assert_open(self.report(1), key, "unsupported exclusion")
                    del record["excluded"], record["scope_decision"]
        self.data["feature_registry"][0].update(excluded=True, scope_decision="ADR-0018")
        self.assert_open(self.report(1), "feature", "unsupported exclusion")

    def test_fixture_evidence_failed_and_missing_named_tests(self):
        record = self.manifest["rows"]["P01"]
        record["environment"] = "fixture"
        self.assert_open(self.report(1), "P01", "fixture/test")
        record["environment"] = "release"
        for code in (1, False, "0", None):
            record["acceptance_tests"][0]["exit_code"] = code
            self.assert_open(self.report(1), "P01", "did not pass")
        record["acceptance_tests"][0]["exit_code"] = 0
        self.manifest["features"]["feature"]["acceptance_tests"].pop()
        self.assert_open(self.report(1), "feature", "missing acceptance test: data trace")

    def test_empty_escaping_absolute_and_directory_artifacts(self):
        (self.evidence / "empty.log").write_text(" \n")
        (self.root / "outside.log").write_text("outside")
        (self.evidence / "escape.log").symlink_to(self.root / "outside.log")
        for reference in ("empty.log", "../outside.log", str(self.root / "outside.log"), "escape.log", "."):
            with self.subTest(reference=reference):
                self.manifest["rows"]["P01"]["evidence"] = [reference]
                self.assertEqual("open", self.report(1)["rows"]["P01"]["status"])

    def test_invalid_inputs_exit_2_without_success_counts(self):
        original = copy.deepcopy(self.manifest)
        variants = [[], {}, dict(original, version=True), dict(original, task_states=[]),
                    dict(original, rows={"P20": {}}), dict(original, features={"unknown": {}}),
                    dict(original, task_states={"T-AA-99": "done"}),
                    dict(original, rows={"P01": None}), dict(original, typo={})]
        for value in variants:
            with self.subTest(value=str(value)[:60]):
                self.manifest = value
                self.write()
                result = self.cli()
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertEqual("", result.stdout)
        for content in ("not JSON", '{"version": 1, "version": 1}'):
            (self.evidence / "readiness.json").write_text(content)
            self.assertEqual(2, self.cli().returncode)

    def test_invalid_denominators_never_pass(self):
        original = self.table
        for table in ("", original.replace("P19", "P18"), original.replace("P19", "P20"),
                      original.replace("T-AA-19", "T-AA-99"), original.replace("구현 작업", "wrong")):
            self.table = table
            self.write()
            self.assertEqual(2, self.cli().returncode)
        self.table = original
        self.data["feature_registry"] = []
        self.write()
        self.assertEqual(2, self.cli().returncode)

    def test_live_contract_empty_evidence_and_default_purpose(self):
        empty = self.root / "empty"
        for explicit in (False, True):
            args = [sys.executable, "-I", str(SCRIPT), "--registry", str(C.BUNDLE / "tasks.json"),
                    "--evidence", str(empty), "--json"]
            if explicit:
                args += ["--purpose", str(C.PURPOSE)]
            result = subprocess.run(args, cwd=self.root, capture_output=True, text=True)
            self.assertEqual(1, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual({"open": 19, "closed": 0, "excluded": 0}, report["rows_counts"])
            live = json.loads((C.BUNDLE / "tasks.json").read_text())
            self.assertEqual(len(live["feature_registry"]), report["features_counts"]["open"])


if __name__ == "__main__":
    unittest.main()
