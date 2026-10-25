"""BLUEPRINT의 DEC 기록 지위와 결정 원장 §3의 상태·조건을 대조한다."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ("DEC-D-02", "DEC-D-04", "DEC-CANON-T-CT-02")


class DecisionRecords(unittest.TestCase):
    def setUp(self):
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        self.hierarchy = blueprint.split("### 0.1 ", 1)[1].split("### 0.2 ", 1)[0]
        ledger = (ROOT / "docs/blueprint/DECISIONS.md").read_text(encoding="utf-8")
        self.section = ledger.split("## 3. ", 1)[1].split("## 4. ", 1)[0]

    def row(self, record_id):
        rows = [line for line in self.section.splitlines()
                if line.startswith(f"| [{record_id}](")]
        self.assertEqual(len(rows), 1, f"§3 must index {record_id} exactly once")
        return [cell.strip() for cell in rows[0].strip("|").split("|")]

    def test_hierarchy_defines_dec_records_and_preserves_adr_change_path(self):
        self.assertRegex(self.hierarchy, r"ADR.*이 문서를 바꾸는 유일한 경로")
        self.assertIn("DEC-*.md", self.hierarchy)
        self.assertIn("결정 게이트 기록", self.hierarchy)
        self.assertIn("ADR을 대신하지 않는다", self.hierarchy)
        self.assertIn("[결정 원장 §3](blueprint/DECISIONS.md#3-구현-전-미정-사항과-차단-범위)",
                      self.hierarchy)

    def test_each_record_has_a_working_link_and_status_in_section_three(self):
        for record_id in RECORDS:
            with self.subTest(record=record_id):
                cells = self.row(record_id)
                self.assertEqual(len(cells), 4)
                link = re.fullmatch(r"\[([^]]+)\]\(([^)]+)\)", cells[0])
                self.assertIsNotNone(link)
                target = (ROOT / "docs/blueprint" / link.group(2)).resolve()
                self.assertEqual(target, ROOT / f"docs/decisions/{record_id}.md")
                self.assertTrue(target.is_file())
                self.assertTrue(cells[1], "status is required")
                self.assertTrue(cells[2], "decision scope is required")
                self.assertTrue(cells[3], "remaining gate conditions are required")

    def test_hierarchy_and_ledger_explicitly_describe_a_partial_index(self):
        dec_paragraph = next(paragraph for paragraph in self.hierarchy.split("\n\n")
                             if "DEC-*.md" in paragraph)
        self.assertRegex(dec_paragraph, r"§3\.1.*일부 기록.*색인")
        index_intro = self.section.split("### 3.1 ", 1)[1].split("| 기록 |", 1)[0]
        self.assertIn("일부", index_intro)
        self.assertIn("전체 DEC 기록 목록은 아니다", index_intro)
        self.assertIn("docs/decisions/DEC-*.md", index_intro)

    def test_index_registration_does_not_open_operational_gates(self):
        self.assertIn("이 표의 등록은 문서 색인", self.section)
        self.assertIn("`decisions_recorded` 등록", self.section)
        self.assertIn("관문 통과의 증거가 아니다", self.section)

    def test_d02_keeps_delegation_and_access_conditions(self):
        cells = self.row("DEC-D-02")
        self.assertIn("위임 결정", cells[1])
        self.assertIn("사용자 확정 아님", cells[1])
        for phrase in ("접근 확인", "등록", "별도 게이트", "T-OP-03"):
            self.assertIn(phrase, cells[3])

    def test_d04_records_owner_ruling_without_reuse_approval(self):
        cells = self.row("DEC-D-04")
        self.assertIn("소유자 직접 결정", cells[1])
        self.assertIn("폐기하지 않는다", cells[2])
        self.assertIn("O13", cells[2])
        for phrase in ("재사용", "승인하지 않음", "D16~D18", "접근 자격"):
            self.assertIn(phrase, cells[3])

    def test_canon_record_preserves_conditional_scope_and_merge_gate(self):
        cells = self.row("DEC-CANON-T-CT-02")
        self.assertIn("위임", cells[1])
        self.assertIn("조건부 승인", cells[1])
        for path in ("packages/schemas/vocabulary.json", "docs/blueprint/VOCABULARY.md"):
            self.assertIn(path, cells[2])
        for phrase in ("병합 미승인", "독립 리뷰", "사용자 병합 지시", "canon_change_approval"):
            self.assertIn(phrase, cells[3])


if __name__ == "__main__":
    unittest.main()
