"""Pending review gates must reach the daemon; O03 remains a service obligation.

All approvals and readiness artifacts below are synthetic. No decision is registered
in the repository and these tests do not supply label or product completion evidence.
"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from tools.daemon.mock_env import MockEnv
from tools.release_readiness.check import inspect_item


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
SPEC = importlib.util.spec_from_file_location("missing_gates_spec", BUNDLE / "검증/spec_check.py")
SC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SC)
REGISTRY = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
TASKS = {t["id"]: t for t in REGISTRY["tasks"]}
MERGES = {"T-CT-05": ["D-09", "D-10"], "T-CT-03": ["D-15"],
          "T-CT-08": ["D-15"], "T-MB-01": ["D-15"]}


class MissingGateContracts(unittest.TestCase):
    def test_live_scope_and_index_pass(self):
        self.assertEqual(SC.decision_scope_problems(REGISTRY), [])

    def test_deleting_each_gate_even_from_both_copies_fails(self):
        for tid, task in TASKS.items():
            for stage, gates in task["decision_gates"].items():
                for gate in set(gates) & {"D-09", "D-10", "D-15", "O03"}:
                    for delete_index in (False, True):
                        with self.subTest(task=tid, stage=stage, gate=gate, index=delete_index):
                            data = copy.deepcopy(REGISTRY)
                            target = next(t for t in data["tasks"] if t["id"] == tid)
                            target["decision_gates"][stage].remove(gate)
                            if delete_index:
                                data["decision_index"][gate][stage].remove(tid)
                            self.assertTrue(SC.decision_scope_problems(data))

    def test_missing_index_or_broadened_start_gate_fails(self):
        for gate in ("D-09", "D-10", "D-15", "O03"):
            with self.subTest(gate=gate):
                data = copy.deepcopy(REGISTRY)
                del data["decision_index"][gate]
                self.assertTrue(SC.decision_scope_problems(data))
                data = copy.deepcopy(REGISTRY)
                data["tasks"][0]["decision_gates"]["start"].append(gate)
                self.assertTrue(SC.decision_scope_problems(data))

    def env(self, tid, state, approvals=()):
        env = MockEnv(str(BUNDLE / "daemon_rules.json"), str(ROOT / "tools/daemon/mock_tasks.json"))
        # Exercise the actual task's gates with the real shared transition core.
        task = copy.deepcopy(TASKS[tid])
        task["task_id"] = tid
        env.ports.catalog.add(task)
        env.core.register_task(tid, state, decisions=approvals)
        return env

    def test_unapproved_partial_and_unrelated_decisions_cannot_open_merge(self):
        for tid, gates in MERGES.items():
            for approvals in ([], ["O03"], *[[g] for g in gates if len(gates) > 1]):
                for state, event in (("review_approved", "audit_not_required"),
                                     ("audit_pending", "audit_pass"),
                                     ("merge_wait", "decision_recorded")):
                    with self.subTest(task=tid, approvals=approvals, event=event):
                        env = self.env(tid, state, approvals)
                        self.assertFalse(env.event(event, tid).get("applied"))
                        self.assertEqual(env.state(tid), state)

    def test_only_matching_merge_approvals_open_the_transition(self):
        for tid, gates in MERGES.items():
            for state, event in (("review_approved", "audit_not_required"),
                                 ("audit_pending", "audit_pass"),
                                 ("merge_wait", "decision_recorded")):
                with self.subTest(task=tid, event=event):
                    env = self.env(tid, state, gates)
                    self.assertTrue(env.event(event, tid).get("applied"))

    def test_o03_does_not_block_candidate_code_merge(self):
        for tid in ("T-KN-05", "T-KN-08"):
            with self.subTest(task=tid):
                self.assertEqual(TASKS[tid]["decision_gates"]["release"], ["O03"])
                self.assertEqual(TASKS[tid]["decision_gates"]["start"], [])
                self.assertEqual(TASKS[tid]["decision_gates"]["real_data"], [])
                env = self.env(tid, "review_approved")
                self.assertTrue(env.event("audit_not_required", tid).get("applied"))

    def test_dictionary_has_pre_m1_owner_and_p04_keeps_its_test(self):
        owner = TASKS["T-KN-05"]
        self.assertEqual(owner["stage"], "S1")
        self.assertIn("data/label-dictionary/**", owner["allowed_paths"])
        self.assertIn("path:data/label-dictionary/**", owner["produces"])
        self.assertIn("M1 완료 전", " ".join(owner["done_criteria"]))
        self.assertIn("미등록 O03", " ".join(owner["tests"]))
        consumer = TASKS["T-KN-08"]
        self.assertIn("T-KN-05", consumer["prereq_tasks"])
        self.assertIn("path:data/label-dictionary/**", consumer["consumes"])
        self.assertIn("label-kinds-complete", consumer["required_test_ids"])
        self.assertIn("종류 하나를 지우면 시험이 실패한다", " ".join(consumer["tests"]))

    def test_p04_failed_or_missing_completeness_result_cannot_close(self):
        # The future label test must fail on missing kinds. Feed that failure to
        # the existing readiness checker, without pretending to have real labels.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "sample.log").write_text("synthetic completeness result\n")
            item = {"tasks": ["T-KN-08"], "acceptance_tests": ["label-kinds-complete"]}
            record = {"environment": "release", "evidence": ["sample.log"],
                      "acceptance_tests": [{"name": "label-kinds-complete",
                                            "log": "sample.log", "exit_code": 0}]}
            self.assertEqual(inspect_item(item, record, {"T-KN-08": "done"}, directory)["status"], "closed")
            record["acceptance_tests"][0]["exit_code"] = 1
            failed = inspect_item(item, record, {"T-KN-08": "done"}, directory)
            self.assertEqual(failed["status"], "open")
            self.assertIn("acceptance test did not pass: label-kinds-complete", failed["reasons"])
            record["acceptance_tests"] = []
            missing = inspect_item(item, record, {"T-KN-08": "done"}, directory)
            self.assertIn("missing acceptance test: label-kinds-complete", missing["reasons"])

    def test_records_are_pending_and_documented_tables_match(self):
        for gate in ("D-09", "D-10", "D-15", "O03"):
            record = (ROOT / f"docs/decisions/DEC-{gate}.md").read_text(encoding="utf-8")
            self.assertIn("미승인", record)
            self.assertIn("사용자 확정 아님", record)
        design = (ROOT / "docs/decisions/DEC-D-15.md").read_text(encoding="utf-8")
        self.assertIn("T-CT-03 병합 전에 수행할 수 있으며", design)
        self.assertIn("후행 T-CT-08·T-MB-01 구현 완료를 선행 조건으로 요구하지 않는다", design)
        self.assertIn("세 PR의 구현 승인이나 병합 지시가 아니다", design)
        spec = (BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        for tid in (*MERGES, "T-KN-05", "T-KN-08"):
            rows = [line for line in spec.splitlines() if line.startswith(f"| {tid} |")]
            task_row = next(line for line in rows if len(line.strip("|").split("|")) == 12)
            cells = [c.strip() for c in task_row.strip("|").split("|")]
            expected = " / ".join(", ".join(TASKS[tid]["decision_gates"][s]) or "—"
                                  for s in ("start", "real_data", "merge", "release"))
            self.assertEqual(cells[7], expected)
