"""Audit 7: guard the adopted stage/gate/early-implementation contract.

These are document-contract regressions, not proof of service release gating.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = "ADR-0020-작업-단계와-V1-관문-정합화.md"
BUNDLE = "docs/blueprint/proposals/설계검토_결과/"
EXPECTED = {
    "S0": ["M0", "M1"], "S1": ["M2"], "S2": ["M2", "M4", "M6"],
    "S3": ["M3", "M4"], "S4": ["M3", "M4", "M5", "M6"], "S5": ["M6"],
}


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def mapping(text):
    rows = re.findall(r"^\| (S[0-5]) \| ([^|]+) \|", text, re.M)
    if len(rows) != 6 or len(dict(rows)) != 6:
        raise AssertionError("six unique stage rows required")
    return {stage: re.findall(r"M\d", milestones) for stage, milestones in rows}


def require(text, *phrases):
    for phrase in phrases:
        if phrase not in text:
            raise AssertionError(f"missing contract: {phrase}")


def v1_contract(text):
    require(text, "T-OP-02는 V1을 대체하지 않는다", "14/14", "실제 이종 계열 검수",
            "화면 S1·S6", "모의 경로만으로 S1·M2를 통과시키지 않는다")


def fixture_contract(text):
    require(text, "T-TW-02", "로컬 엔진·픽스처", "fixture_only", "서비스 상품군 적용",
            "M5·M6", "실제 사례", "검수·릴리스 증거")


class Audit7Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adr = read("docs/decisions/" + ADR)
        cls.bp = read("docs/BLUEPRINT.md")
        cls.tasks_doc = json.loads(read(BUNDLE + "tasks.json"))
        cls.tasks = {t["id"]: t for t in cls.tasks_doc["tasks"]}

    def test_mapping_matches_adopted_stages_and_milestones(self):
        self.assertEqual(mapping(self.adr), EXPECTED)
        self.assertEqual(mapping(self.bp), EXPECTED)
        self.assertEqual({t["stage"] for t in self.tasks.values()}, set(EXPECTED))
        stage_contract = self.tasks_doc["field_definitions"]["stage"]
        for stage, milestones in EXPECTED.items():
            self.assertIn(stage + "→" + "·".join(milestones), stage_contract)
        for text in (self.adr, self.bp, stage_contract):
            require(text, "단계 완료가 마일스톤 통과를 뜻하지 않는다")
        # Every mapped milestone must remain defined by the actual milestone table.
        milestone_section = self.bp.split("### 9.2 ")[1].split("### 9.3 ")[0]
        self.assertEqual(set(re.findall(r"^\| (M\d) \|", milestone_section, re.M)),
                         {m for ms in EXPECTED.values() for m in ms})

    def test_v1_stays_independent_in_adr_blueprint_and_task(self):
        task = self.tasks["T-OP-02"]
        for text in (self.adr, self.bp.split("### 9.2 ")[1].split("### 9.3 ")[0],
                     " ".join(task["done_criteria"])):
            v1_contract(text)
        self.assertEqual(task["decision_gates"]["real_data"], ["D-02"])
        require(task["done_criteria"][0], "(b) 없이 S1 관문을 통과로 적지 않는다")
        v1_row = next(l for l in self.bp.splitlines() if l.startswith("| V1 |"))
        require(v1_row, "관문 미통과")

    def test_fixture_exception_reaches_previous_ban_and_both_contracts(self):
        task = self.tasks["T-TW-02"]
        for text in (self.adr, self.bp.split("### 9.3 ")[1].split("### 9.4 ")[0],
                     read("docs/decisions/ADR-0014-V1-검증-결과의-설계-반영.md").split("후속 변경")[1],
                     task["notes"], read(BUNDLE + "09_제품목적_대응표.md")):
            fixture_contract(text)
        require(" ".join(task["done_criteria"]), "fixture_only", "관문 통과로 표시하지 않는다")
        require(self.adr, "자동 차단 기능이 아니다", "DEC-O12", "연산별 S6")
        self.assertNotIn("에서 사례와 함께 추가한다", self.bp)
        self.assertIn("docs/decisions/" + ADR, task["inputs"])

    def test_decision_is_propagated_and_release_evidence_preserved(self):
        for start, end in (("## 7. ", "## 8. "), ("## 9. ", "## 10. "),
                           ("## 11. ", "## 12. "), ("## 13. ", None)):
            section = self.bp.split(start)[1]
            if end:
                section = section.split(end)[0]
            require(section, "ADR-0020")
        require(read("docs/blueprint/DECISIONS.md"), "BP-D-21", ADR)
        require(read("README.md"), "0020 작업 단계와 V1 관문 정합화")
        require(self.adr, "ADR-0019", "P01~P19", "purpose-rows-all-closed")
        self.assertEqual(self.tasks_doc["_common_done_criteria_status"],
                         "non_binding_until_adopted")
        final = self.tasks["T-OP-08"]
        self.assertTrue(final["final_gate"])
        self.assertIn("purpose-rows-all-closed", final["required_test_ids"])
        require(read(BUNDLE + "09_제품목적_대응표.md"), "P08·P14 또는 T-OP-08을 완료 처리하지 않는다")

    def test_record_describes_saved_resolution_and_links_evidence(self):
        record = read("docs/decisions/audit7-adopt-task-bundle-adr.md")
        require(record, ADR, "문서 정합성 finding 해결")
        for stale in ("파일시스템이 읽기 전용이므로", "파일로 저장하거나 BLUEPRINT와 회귀검사를 갱신하지 못했다",
                      "finding 전체를 해결 완료로 표시하지 않는다"):
            self.assertNotIn(stale, record)
        for path, text in ((ROOT / "docs/decisions" / ADR, self.adr),
                           (ROOT / "docs/decisions/audit7-adopt-task-bundle-adr.md", record)):
            links = re.findall(r"\]\(([^)]+)\)", text)
            self.assertTrue(links)
            for link in links:
                self.assertTrue((path.parent / link).is_file(), link)

    def test_reported_contract_regressions_are_detected(self):
        with self.assertRaisesRegex(AssertionError, "six unique"):
            mapping(self.adr.replace("| S2 |", "| S1 |"))
        changed = mapping(self.adr.replace("| S5 | M6 |", "| S5 | M0 |"))
        self.assertNotEqual(changed, EXPECTED)
        for phrase in ("T-OP-02는 V1을 대체하지 않는다", "14/14", "실제 이종 계열 검수",
                       "화면 S1·S6", "모의 경로만으로 S1·M2를 통과시키지 않는다"):
            with self.subTest(removed=phrase), self.assertRaises(AssertionError):
                v1_contract(self.adr.replace(phrase, ""))
        for phrase in ("로컬 엔진·픽스처", "fixture_only", "M5·M6", "검수·릴리스 증거"):
            with self.subTest(removed=phrase), self.assertRaises(AssertionError):
                fixture_contract(self.adr.replace(phrase, ""))


if __name__ == "__main__":
    unittest.main()
