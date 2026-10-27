"""BLUEPRINT의 DEC 기록 지위와 결정 원장 §3의 상태·조건을 대조한다."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ("DEC-D-02", "DEC-D-04", "DEC-D-12", "DEC-CANON-T-CT-02")


class DecisionRecords(unittest.TestCase):
    def setUp(self):
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        self.blueprint = blueprint
        self.hierarchy = blueprint.split("### 0.1 ", 1)[1].split("### 0.2 ", 1)[0]
        self.open_decisions = blueprint.split("## 12. ", 1)[1].split("## 13. ", 1)[0]
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

    def test_blueprint_d02_rows_state_delegation_pending_user_confirmation(self):
        for decision, note in (
            ("AI 제공자 구성(서로 다른 모델 계열 2개 이상)", "ADR-0006 이행 조건"),
            ("정책 소유자 지정(AI 승인 임계값·사고 시 중단)", "사람의 유일한 역할"),
        ):
            with self.subTest(decision=decision):
                rows = [line for line in self.open_decisions.splitlines()
                        if line.startswith(f"| {decision} |")]
                self.assertEqual(len(rows), 1)
                cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
                self.assertEqual(len(cells), 3)
                self.assertEqual(cells[1], "M2")
                self.assertIn(note, cells[2])
                self.assertIn("위임 결정 DEC-D-02, 사용자 확정 대기", cells[2])

    def test_d02_provider_summary_records_composition_and_remaining_access(self):
        row = next(line for line in self.open_decisions.splitlines()
                   if line.startswith("| AI 제공자 구성("))
        for phrase in ("[DEC-D-02](decisions/DEC-D-02.md)", "작성=claude",
                       "승인=비-claude X", "레드팀=별도 비-claude Y",
                       "degraded", "업체·모델 ID는 미고정", "접근 확인",
                       "월 한도", "게이트 등록", "모의 시험·병합은 허용"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)

    def test_d02_owner_summary_and_ledger_do_not_call_every_owner_unassigned(self):
        row = next(line for line in self.open_decisions.splitlines()
                   if line.startswith("| 정책 소유자 지정("))
        scope = self.row("DEC-D-02")[2]
        for text in (row, scope):
            for phrase in ("정책 소유자=사용자 본인 1인", "재개는 소유자만",
                           "O06", "D-19", "T-OP-03"):
                with self.subTest(text=text, phrase=phrase):
                    self.assertIn(phrase, text)
        self.assertIn("[DEC-D-02](decisions/DEC-D-02.md)", row)
        self.assertIn("임계값 수치는 미정", row)
        self.assertNotIn("역할의 담당자 이름은 아직 지정되지 않았다", self.section)
        self.assertIn("위임 결정", self.section.split("| ID |", 1)[0])

    def test_o01_is_closed_by_adr0018_without_removing_the_stable_id(self):
        rows = [line for line in self.section.splitlines() if line.startswith("| O01 |")]
        self.assertEqual(1, len(rows))
        for phrase in ("해결", "ADR-0018", "우체국보험 포함", "기관 유형은 구분",
                       "공제 제외", "확보율 분모에서도 제외", "2026-10-10",
                       "목록 작성·분모 검증은 구현 작업"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rows[0])
        self.assertNotIn("포함 여부", rows[0])
        self.assertNotIn("M3 확장 전", rows[0])

    def test_d12_app_display_is_allowed_but_repo_redistribution_stays_pending(self):
        blueprint_row = next(line for line in self.open_decisions.splitlines()
                             if line.startswith("| 저장소 공개 범위"))
        ledger_row = next(line for line in self.section.splitlines() if line.startswith("| O16 |"))
        index = self.row("DEC-D-12")
        for row in (blueprint_row, ledger_row, " ".join(index)):
            for phrase in ("DEC-D-12", "소비자 앱의 원문 이미지·발췌 표시 허용",
                           "외부 검토 없음", "법적 위험은 소유자가 감수",
                           "새 원문 발췌 추가", "승인하지 않음"):
                with self.subTest(row=row, phrase=phrase):
                    self.assertIn(phrase, row)
        self.assertIn("소유자 직접 결정", index[1])
        for phrase in ("2026-10-14 07:23 KST", "기존 발췌·Git 이력 유지",
                       "표시 플래그 적용·게이트 등록은 별도"):
            self.assertIn(phrase, " ".join(index))
        self.assertIn("다음 원문 발췌 추가", blueprint_row)
        self.assertIn("재배포 결정 없이 원본 파일을 공개 저장소에 올리지 않음", ledger_row)

    def test_all_open_items_are_referenced_without_a_stale_upper_bound(self):
        section = self.blueprint.split("## 13. ", 1)[1]
        ids = re.findall(r"^\| (O\d+) \|", self.section, re.M)
        self.assertIn("O18", ids)
        self.assertIn("O19", ids)
        self.assertNotRegex(section, r"O01\s*[~～–-]\s*O\d+")
        self.assertIn("원장 §3의 전체 O 항목", section)
        self.assertIn("해결된 범위와 남은 차단 조건", section)

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
