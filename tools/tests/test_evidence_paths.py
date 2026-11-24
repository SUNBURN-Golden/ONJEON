"""Task evidence outputs can be published under the real daemon policy.

All generated artifacts are synthetic, temporary gate tests, never release evidence.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from daemon.core.gate_evaluator import paths_within_scope, patterns_overlap  # noqa: E402
from release_readiness import check as readiness  # noqa: E402

EVIDENCE = "docs/release-readiness/evidence"
TOOL_EVIDENCE = "tools/evidence"
DEVELOPER_TOOLS = {"T-OP-00", "T-OP-09"}  # 09 §0 keeps these outside release evidence.
FINAL = "T-OP-08"


def evidence_grant(task_id):
    root = TOOL_EVIDENCE if task_id in DEVELOPER_TOOLS else EVIDENCE
    return f"{root}/{task_id}/**"


class EvidencePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = readiness.BUNDLE / "tasks.json"
        cls.data = json.loads(cls.registry.read_text(encoding="utf-8"))
        cls.tasks = {t["id"]: t for t in cls.data["tasks"]}
        cls.product = cls.tasks.keys() - DEVELOPER_TOOLS

    def test_every_task_declares_its_effective_evidence_output(self):
        self.assertTrue(self.product)
        self.assertLessEqual(DEVELOPER_TOOLS | {FINAL}, self.tasks.keys())
        for tid, task in self.tasks.items():
            with self.subTest(task=tid):
                grant = evidence_grant(tid)
                self.assertIn(grant, task["allowed_paths"])
                self.assertIn(f"path:{grant}", task["produces"])
                self.assertIn(grant, task["conflict_paths"])

                directory = grant.removesuffix("/**")
                paths = [f"{directory}/report.md", f"{directory}/acceptance/run.log"]
                self.assertTrue(paths_within_scope(paths, task))
                if tid != FINAL:
                    without_grant = copy.deepcopy(task)
                    without_grant["allowed_paths"].remove(grant)
                    self.assertFalse(paths_within_scope(paths, without_grant))

                denied = copy.deepcopy(task)
                denied["forbidden_paths"].append(grant)
                self.assertFalse(paths_within_scope(paths, denied))

    def test_only_final_auditor_can_aggregate_or_edit_another_tasks_evidence(self):
        manifest = f"{EVIDENCE}/readiness.json"
        for tid, task in self.tasks.items():
            with self.subTest(task=tid):
                self.assertEqual(tid == FINAL, paths_within_scope([manifest], task))
                for owner in sorted(self.product - {tid}):
                    self.assertEqual(tid == FINAL, paths_within_scope(
                        [f"{EVIDENCE}/{owner}/acceptance/run.log"], task), owner)
                for owner in sorted(DEVELOPER_TOOLS):
                    self.assertEqual(tid == owner, paths_within_scope(
                        [f"{TOOL_EVIDENCE}/{owner}/acceptance/run.log"], task), owner)
                    self.assertEqual(tid == FINAL, paths_within_scope(
                        [f"{EVIDENCE}/{owner}/acceptance/run.log"], task), owner)
                if tid != FINAL:
                    self.assertFalse(paths_within_scope([f"{EVIDENCE}/unowned.md"], task))

    def test_final_auditor_reads_the_supervisor_ledger_without_task_write_grants(self):
        path = readiness.TASKS_STATE.relative_to(ROOT).as_posix()
        self.assertIn(f"path:{path}", self.tasks[FINAL]["consumes"])
        for tid, task in self.tasks.items():
            with self.subTest(task=tid):
                self.assertFalse(paths_within_scope([path], task))

    def test_evidence_locks_preserve_parallel_task_isolation_and_final_audit_lock(self):
        final_locks = self.tasks[FINAL]["conflict_paths"]
        grants = []
        for tid in self.tasks:
            grant = evidence_grant(tid)
            self.assertEqual(tid in self.product,
                             any(patterns_overlap(grant, lock) for lock in final_locks))
            self.assertFalse(any(patterns_overlap(grant, other) for other in grants))
            grants.append(grant)

    def test_work_spec_lists_every_evidence_permission_and_output(self):
        text = (readiness.BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        for section, column, prefix in (("## 6.", 8, ""), ("## 7.", 1, "path:")):
            table = text.split(section, 1)[1].split("\n## ", 1)[0]
            rows = {cells[0]: cells for line in table.splitlines() if line.startswith("| T-")
                    for cells in [[c.strip() for c in line.strip("|").split("|")]]}
            for tid in self.tasks:
                with self.subTest(section=section, task=tid):
                    self.assertIn(f"{prefix}{evidence_grant(tid)}", rows[tid][column].split(", "))

    def test_live_denominators_can_reference_task_owned_artifacts_and_fail_if_removed(self):
        # Exercise real P01..P19 + every feature and the existing readiness checker.
        # Synthetic content is confined to a temporary directory; no live manifest changes.
        _, rows, features = readiness.read_contract(self.registry, readiness.PURPOSE)
        self.assertTrue(set().union(*(set(item["tasks"]) for item in rows.values())) <= self.product)
        self.assertTrue(set().union(*(set(item["tasks"]) for item in features.values())) <= self.product)
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            tasks_state = Path(temporary) / "tasks_state.json"
            manifest = {"version": 1, "rows": {}, "features": {}}
            linked = {tid for item in (*rows.values(), *features.values()) for tid in item["tasks"]}
            records = {}
            for tid in linked:
                reference = f"{tid}/merge-review.md"
                path = evidence / reference
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Synthetic task evidence.\n")
                records[tid] = {"state": "done", "merge_sha": "a" * 40, "evidence_path": reference}
            tasks_state.write_text(json.dumps({"version": 1, "tasks": records}))
            for group, items in (("rows", rows), ("features", features)):
                for key, item in items.items():
                    owner = item["tasks"][0]
                    report = f"{owner}/{group}/{key}/report.md"
                    log = f"{owner}/{group}/{key}/acceptance.log"
                    self.assertTrue(paths_within_scope(
                        [f"{EVIDENCE}/{report}", f"{EVIDENCE}/{log}"], self.tasks[owner]))
                    for ref in (report, log):
                        path = evidence / ref
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("Synthetic gate mechanics only; not product evidence.\n")
                    manifest[group][key] = {
                        "environment": "release", "evidence": [report],
                        "acceptance_tests": [{"name": name, "log": log, "exit_code": 0}
                                             for name in item.get("acceptance_tests", ["row acceptance"])],
                    }
            (evidence / "readiness.json").write_text(json.dumps(manifest))
            result = readiness.check(self.registry, readiness.PURPOSE, evidence, tasks_state)
            self.assertEqual({"open": 0, "closed": 19, "excluded": 0}, result["rows_counts"])
            self.assertEqual(len(features), result["features_counts"]["closed"])
            removed = evidence / manifest["rows"]["P01"]["evidence"][0]
            removed.unlink()
            result = readiness.check(self.registry, readiness.PURPOSE, evidence, tasks_state)
            self.assertEqual("open", result["rows"]["P01"]["status"])
            self.assertEqual(1, result["rows_counts"]["open"])


if __name__ == "__main__":
    unittest.main()
