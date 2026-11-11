"""Audit 5: residual daemon work does not gate product tasks, but V1 gates M1.

Finding: bot cycles were treating the daemon (T-OP-00/T-OP-09) or the
stage-2/3 handoff sentence as the product start gate, while the first draft of
the decision record read the empty ``tasks.json`` prerequisites as
authorization to start M1 before V1 passed.

This test pins both halves of the resolved policy:

1. Only the final release audit T-OP-08 depends on daemon tasks; the remaining
   daemon follow-ups do not gate product tasks.
2. The V1 milestone gate, not the daemon, blocks the remaining unmerged M1 and
   downstream product tasks (BLUEPRINT §9.2/§9.5/§10 rule 6, ADR-0013 §5 and
   audit4-v1-gate-closure).

The first draft of the record failed the second half; these assertions fail if
an edit ever re-authorizes an M1 start while V1 is still unpassed.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
RECORD = ROOT / "docs/decisions/audit5-product-freeze-vs-daemon-gate.md"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
ADR0013 = ROOT / "docs/decisions/ADR-0013-전체-대상-목록-우선과-설계-확정.md"
V1_CLOSURE = ROOT / "docs/decisions/audit4-v1-gate-closure.md"
HANDOFF = BUNDLE / "그록봇_인계/README.md"

DAEMON = {"T-OP-00", "T-OP-09"}
FINAL_AUDIT = "T-OP-08"
MERGED_TASKS = (("T-CT-01", "#102"), ("T-CT-02", "#118"),
                ("T-DT-01", "#139"), ("T-DT-02", "#172"))


def read(path):
    return path.read_text(encoding="utf-8")


class DaemonDoesNotGateProductTasks(unittest.TestCase):
    def setUp(self):
        self.tasks = json.loads(read(BUNDLE / "tasks.json"))["tasks"]
        self.handoff = read(HANDOFF)

    def test_only_the_final_audit_depends_on_daemon_tasks(self):
        dependants = {task["id"] for task in self.tasks
                      if task["id"] not in DAEMON
                      and DAEMON & set(task["prereq_tasks"])}
        self.assertEqual({FINAL_AUDIT}, dependants)

    def test_daemon_tasks_are_not_start_gates_for_any_product_task(self):
        for task in self.tasks:
            start = task.get("decision_gates", {}).get("start", [])
            with self.subTest(task=task["id"]):
                self.assertFalse(DAEMON & set(start))

    def test_final_audit_dependency_is_release_reporting_only(self):
        audit = next(task for task in self.tasks if task["id"] == FINAL_AUDIT)
        self.assertIs(True, audit["final_gate"])
        self.assertTrue(any("자동 개발 운영 기록" in item and "축 5" in item
                            for item in audit["done_criteria"]))

    def test_handoff_stage_sentence_is_superseded_by_the_dated_note(self):
        stages = self.handoff.split("## 3. ", 1)[1].split("## 4. ", 1)[0]
        self.assertIn("제품 과제(T-CT-01 등)는 임대하지 않는다", stages)
        note = stages.split("[상태 기록 2026-10-26]", 1)[1]
        for phrase in ("직렬 제한 해제", "남은 데몬 후속 과제는 제품 과제를 막지 않는다",
                       "병행한다", "T-OP-08"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, note)


class V1GateBlocksM1(unittest.TestCase):
    def setUp(self):
        self.record = read(RECORD)
        self.blueprint = read(BLUEPRINT)
        self.adr = read(ADR0013)
        self.closure = read(V1_CLOSURE)

    def test_governing_documents_still_record_v1_as_unpassed(self):
        v1_row = next(line for line in self.blueprint.splitlines()
                      if line.startswith("| V1 |"))
        for phrase in ("관문 미통과", "완전 재현 8/14"):
            with self.subTest(document="BLUEPRINT §9.2", phrase=phrase):
                self.assertIn(phrase, v1_row)
        gate = self.blueprint.split("### 9.5 ", 1)[1].split("## 10.", 1)[0]
        self.assertIn("§9.2 마일스톤 관문을 생략하지 않는다", gate)
        rules = self.blueprint.split("## 10. ", 1)[1].split("## 11.", 1)[0]
        self.assertIn("마일스톤 관문을 건너뛰지 않는다", rules)
        self.assertIn("M1은 V1의 관문을 통과한 뒤 시작한다", self.adr)
        self.assertIn("V1 미통과와 M1 진입 차단", self.closure)

    def test_record_does_not_authorize_starting_m1_before_v1(self):
        for stale in ("should be leased and worked",
                      "Reaffirm parallel start",
                      "T-CT-02 still needs canon_change_approval",
                      "Product tasks remain unleased despite having no daemon gate"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.record)
        for phrase in ("Do not lease or start",
                       "V1 milestone",
                       "관문 미통과",
                       "until V1 is judged passed"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_treats_tasks_json_as_a_subordinate_contract(self):
        for phrase in ("ADR-0019", "하위 계약", "상위 계약을 우선한다",
                       "cannot waive the V1 gate"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_reconciles_with_the_concurrent_v1_decision(self):
        self.assertIn("audit5-v1-gate-before-m1", self.record)
        self.assertIn("do not lease/start T-CT-* until V1 is judged passed", self.record)

    def test_record_separates_merged_tasks_from_remaining_unmerged_work(self):
        for task, pr in MERGED_TASKS:
            with self.subTest(task=task):
                self.assertIn(f"{task} ({pr})", self.record)
        self.assertIn("not re-leased", self.record)
        self.assertIn("remaining unmerged", self.record)

    def test_record_links_resolve(self):
        for link in re.findall(r"\]\(([^)]+)\)", self.record):
            if "://" in link or link.startswith("#"):
                continue
            with self.subTest(link=link):
                target = (RECORD.parent / link.split("#", 1)[0]).resolve()
                self.assertTrue(target.is_relative_to(ROOT))
                self.assertTrue(target.is_file(), f"missing target: {link}")


if __name__ == "__main__":
    unittest.main()
