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
        self.tasks_state = self.root / "tasks_state.json"
        self.data = {
            "tasks": [{"id": f"T-AA-{i:02}"} for i in range(1, 21)],
            "feature_registry": [{"id": "feature", "tasks": ["T-AA-01"],
                                  "acceptance_tests": ["screen flow", "data trace"],
                                  "excluded": False, "scope_decision": None}],
        }
        self.table = "| # | 구현 작업 |\n|---|---|\n" + "".join(
            f"| P{i:02} | T-AA-{i:02} |\n" for i in range(1, 21))
        self.manifest = {
            "version": 1,
            "rows": {f"P{i:02}": self.record(f"P{i:02}") for i in range(1, 21)},
            "features": {"feature": self.record("feature", ["screen flow", "data trace"])},
        }
        self.ledger = {"version": 1, "tasks": {}}
        for task in self.data["tasks"]:
            tid = task["id"]
            reference = f"{tid}/review.md"
            (self.evidence / tid).mkdir()
            (self.evidence / reference).write_text("Synthetic task evidence.\n")
            self.ledger["tasks"][tid] = {"state": "done", "merge_sha": "a" * 40,
                                         "evidence_path": reference}
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
        self.tasks_state.write_text(json.dumps(self.ledger))
        (self.evidence / "readiness.json").write_text(json.dumps(self.manifest))

    def cli(self, *extra):
        return subprocess.run([sys.executable, "-I", str(SCRIPT), "--registry", str(self.registry),
                               "--purpose", str(self.purpose), "--tasks-state", str(self.tasks_state),
                               "--evidence", str(self.evidence),
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
                self.ledger["tasks"]["T-AA-01"]["state"] = state
                report = self.report(0)
                self.assertEqual({"open": 0, "closed": 20, "excluded": 0}, report["rows_counts"])
                self.assertEqual(1, report["features_counts"]["closed"])

    def test_empty_evidence_or_missing_directory_reports_20_open(self):
        empty = self.root / "empty"
        for exists in (False, True):
            if exists:
                empty.mkdir()
            result = self.cli("--evidence", empty)
            self.assertEqual(1, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual({"open": 20, "closed": 0, "excluded": 0}, report["rows_counts"])
            self.assertEqual({f"P{i:02}" for i in range(1, 21)}, set(report["rows"]))

    def test_purpose_rows_all_closed_every_row_requires_evidence_and_logs(self):
        for i in range(1, 21):
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
        for i in range(1, 21):
            tid = f"T-AA-{i:02}"
            for state in (None, "building", "merge_wait", "merged_invalid_approval", "cancelled", "unknown"):
                with self.subTest(task=i, state=state):
                    self.ledger["tasks"][tid]["state"] = state
                    report = self.report(1)
                    self.assert_open(report, f"P{i:02}", f"{tid}: not post_merge")
                    if i == 1:
                        self.assert_open(report, "feature", f"{tid}: not post_merge")
            self.ledger["tasks"][tid]["state"] = "done"

    def test_legacy_states_and_contract_prose_cannot_supply_or_override_ledger_state(self):
        self.manifest["task_states"] = {"T-AA-01": "cancelled"}
        self.report(0)
        self.manifest["task_states"]["T-AA-01"] = "done"
        self.data["tasks"][0].update(state="done", merge_sha="a" * 40, evidence_path="P01.txt")
        del self.ledger["tasks"]["T-AA-01"]
        report = self.report(1)
        for key in ("P01", "feature"):
            self.assert_open(report, key, "T-AA-01: not post_merge (state=missing)")

    def test_post_merge_task_requires_both_sha_and_evidence(self):
        record = self.ledger["tasks"]["T-AA-01"]
        for field, reason in (("merge_sha", "missing merge SHA"),
                              ("evidence_path", "missing task evidence path")):
            with self.subTest(field=field):
                saved = record[field]
                record[field] = None
                report = self.report(1)
                for key in ("P01", "feature"):
                    self.assert_open(report, key, f"T-AA-01: {reason}")
                record[field] = saved

    def test_task_evidence_requires_a_nonempty_regular_file_inside_evidence(self):
        (self.evidence / "empty.log").write_text(" \n")
        (self.root / "outside.log").write_text("outside")
        (self.evidence / "escape.log").symlink_to(self.root / "outside.log")
        (self.evidence / "cycle").symlink_to("cycle")
        for reference in ("missing", "empty.log", "../outside.log", str(self.root / "outside.log"),
                          "escape.log", "cycle", "T-AA-01", "illegal\x00path"):
            with self.subTest(reference=reference):
                self.ledger["tasks"]["T-AA-01"]["evidence_path"] = reference
                report = self.report(1)
                for key in ("P01", "feature"):
                    self.assert_open(report, key, "T-AA-01: task evidence")
                self.assertEqual(1, report["rows_counts"]["open"])

    def test_missing_row_record_and_reference_lists(self):
        saved = self.manifest["rows"].pop("P20")
        self.assert_open(self.report(1), "P20", "missing")
        self.manifest["rows"]["P20"] = saved
        for field in ("evidence", "acceptance_tests"):
            saved = self.manifest["rows"]["P20"][field]
            self.manifest["rows"]["P20"][field] = []
            self.assert_open(self.report(1), "P20", "missing")
            self.manifest["rows"]["P20"][field] = saved

    def test_all_tasks_in_a_row_are_required_and_repeated_headers_work(self):
        self.table = self.table.replace("| P01 | T-AA-01 |", "| P01 | `T-AA-01`, `T-AA-02` |")
        self.table = self.table.replace("| P10 |", "\n| # | 구현 작업 |\n|---|---|\n| P10 |")
        self.report(0)
        del self.ledger["tasks"]["T-AA-02"]
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
                                 "--purpose", str(self.purpose), "--tasks-state", str(self.tasks_state),
                                 "--evidence", str(self.evidence)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("purpose-rows-all-closed: open=0, closed=20, excluded=0", result.stdout)
        self.assertIn("release-readiness-rejects-incomplete: open=0, closed=1, excluded=0", result.stdout)

    def test_unsupported_exclusions_including_partial_scope_and_pending_gates(self):
        for key in ("P01", "P02", "P18", "P20", "feature"):
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
        record = self.manifest["rows"]["P20"]
        record["environment"] = "fixture"
        self.assert_open(self.report(1), "P20", "fixture/test")
        record["environment"] = "release"
        for code in (1, False, "0", None):
            record["acceptance_tests"][0]["exit_code"] = code
            self.assert_open(self.report(1), "P20", "did not pass")
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
                    dict(original, rows={"P21": {}}), dict(original, features={"unknown": {}}),
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
        for table in ("", original.replace("P20", "P19"), original.replace("P20", "P21"),
                      original.replace("T-AA-19", "T-AA-99"), original.replace("구현 작업", "wrong")):
            self.table = table
            self.write()
            self.assertEqual(2, self.cli().returncode)
        self.table = original
        self.data["feature_registry"] = []
        self.write()
        self.assertEqual(2, self.cli().returncode)

    def test_empty_ledger_is_incomplete_and_missing_ledger_is_an_input_error(self):
        self.ledger["tasks"].clear()
        report = self.report(1)
        self.assertEqual(20, report["rows_counts"]["open"])
        self.assertEqual(1, report["features_counts"]["open"])
        self.tasks_state.unlink()
        result = self.cli()
        self.assertEqual(2, result.returncode)
        self.assertIn("tasks_state.json", result.stderr)
        self.assertEqual("", result.stdout)

    def test_invalid_ledger_never_returns_passing_counts(self):
        record = self.ledger["tasks"]["T-AA-01"]
        variants = (
            (["tasks"], "requires version and tasks"),
            (dict(self.ledger, version=True), "version must be 1"),
            (dict(self.ledger, tasks=[]), "must map task IDs"),
            (dict(self.ledger, tasks={"T-AA-99": record}), "unknown task T-AA-99"),
            (dict(self.ledger, tasks={"T-AA-01": {}}), "expected state, merge_sha and evidence_path"),
        )
        cases = [(json.dumps(value), reason) for value, reason in variants]
        for field, value in (("state", True), ("evidence_path", []), ("merge_sha", "abc"),
                             ("merge_sha", "0" * 40), ("merge_sha", 123), ("merge_sha", "Z" * 40)):
            ledger = dict(self.ledger, tasks={"T-AA-01": dict(record, **{field: value})})
            reason = "expected a full merge commit SHA" if field == "merge_sha" else f"{field} must be"
            cases.append((json.dumps(ledger), reason))
        cases += [('not JSON', 'Expecting value'),
                  ('{"version":1,"tasks":{"T-AA-01":{},"T-AA-01":{}}}', 'duplicate JSON key: T-AA-01')]
        for content, reason in cases:
            with self.subTest(reason=reason, content=content[:85]):
                self.tasks_state.write_text(content)
                result = self.cli()
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertEqual("", result.stdout)

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
            self.assertEqual({"open": 20, "closed": 0, "excluded": 0}, report["rows_counts"])
            for row, owners in {
                "P02": ("T-DT-04", "T-AP-04"),
                "P03": ("T-WB-01",),
                "P08": ("T-MB-04",),
                "P16": ("T-MB-04",),
                "P20": ("T-PS-03", "T-PS-04", "T-OP-05"),
            }.items():
                for owner in owners:
                    with self.subTest(row=row, owner=owner):
                        self.assert_open(report, row, f"{owner}: not post_merge")
            live = json.loads((C.BUNDLE / "tasks.json").read_text())
            self.assertEqual(len(live["feature_registry"]), report["features_counts"]["open"])


class RepositoryScaffoldTests(unittest.TestCase):
    def test_repository_scaffold_exists_and_starts_incomplete(self):
        evidence = ROOT / "docs/release-readiness/evidence"
        self.assertTrue((evidence / "README.md").is_file())
        self.assertEqual(
            {"version": 1, "task_states": {}, "rows": {}, "features": {}},
            json.loads((evidence / "readiness.json").read_text(encoding="utf-8")),
        )
        # Exercise the real files: missing input also returns open counts, so
        # counts alone cannot catch accidental removal of the scaffold.
        for explicit in (False, True):
            with self.subTest(explicit_purpose=explicit):
                args = [sys.executable, "-I", str(SCRIPT), "--registry",
                        str(C.BUNDLE / "tasks.json"), "--evidence", str(evidence)]
                if explicit:
                    args += ["--purpose", str(C.PURPOSE), "--json"]
                result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                if explicit:
                    report = json.loads(result.stdout)
                    self.assertEqual({"open": 20, "closed": 0, "excluded": 0},
                                     report["rows_counts"])
                    self.assertEqual({"open": 64, "closed": 0, "excluded": 0},
                                     report["features_counts"])
                    self.assertEqual(C.ROW_IDS, set(report["rows"]))
                else:
                    self.assertIn("purpose-rows-all-closed: open=20, closed=0, excluded=0",
                                  result.stdout)
                    self.assertIn("release-readiness-rejects-incomplete: open=64, closed=0, excluded=0",
                                  result.stdout)


if __name__ == "__main__":
    unittest.main()
