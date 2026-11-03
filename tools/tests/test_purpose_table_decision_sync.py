"""Audit 4: 09 scope cells must distinguish recorded decisions from open gates.

These are documentation contracts, discovered by the existing Python CI job.
They do not evaluate product completion or change decisions_recorded.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PURPOSE = ROOT / "docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md"


class PurposeTableDecisionSync(unittest.TestCase):
    def setUp(self):
        self.text = PURPOSE.read_text(encoding="utf-8")
        self.rows = {}
        for line in self.text.splitlines():
            if re.match(r"^\| P\d{2} \|", line):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                self.assertEqual(10, len(cells))
                self.assertNotIn(cells[0], self.rows)
                self.rows[cells[0]] = cells
        self.assertEqual({f"P{i:02}" for i in range(1, 20)}, self.rows.keys())

    def require_scope(self, row, *phrases):
        scope = self.rows[row][-1]
        for phrase in phrases:
            with self.subTest(row=row, phrase=phrase):
                self.assertIn(phrase, scope)
        return scope

    def test_p03_includes_the_full_inquiry_workflow_and_manual_send_boundary(self):
        self.require_scope("P03", "DEC-D-14", "위임 결정", "사용자 확정 아님",
                           "첫 출시", "공백 관리", "초안 생성",
                           "회신 보존", "주장별 평가", "온전 명의", "AI 작성 보조",
                           "사용자 승인", "사람이 수동 발송", "자동 발송 금지",
                           "게이트 등록", "구현", "별도", "범위 축소 아님")

    def test_p06_separates_ai_configuration_from_access_and_registration(self):
        self.require_scope("P06", "DEC-D-02", "위임 결정", "사용자 확정 아님",
                           "2계열", "작성=claude", "승인=비-claude X",
                           "레드팀=별도 비-claude Y", "degraded",
                           "정책 소유자=사용자 본인 1인", "접근 확인", "월 한도",
                           "접근 확인 뒤 게이트 등록", "별도 real_data 게이트",
                           "O06·D-19", "모의", "시험·병합", "범위 축소 아님")

    def test_p11_preserves_statement_only_inputs_and_guidance_only_claims(self):
        self.require_scope("P11", "DEC-D-06", "DEC-D-07", "위임 결정", "사용자 확정 아님",
                           "PDF만", "사진 없음", "사용자 진술", "질병 코드는 미확인",
                           "진단서 입력은 별도 ADR", "청구 서류·기한·보험사 공식 채널",
                           "조항 근거", "안내만", "대행·전송·연계 금지", "지급 보장 금지",
                           "게이트 등록", "구현 검증", "별도")

    def test_p14_records_owner_permission_without_enabling_the_flag_or_repo_redistribution(self):
        scope = self.require_scope("P14", "DEC-D-12", "소유자 직접 결정",
                                   "2026-10-14 07:23 KST", "선택 C", "소비자 앱",
                                   "원문 이미지·발췌 표시 허용", "플래그 적용", "게이트 등록",
                                   "별도", "공개 저장소의 새 원문 발췌 추가는 승인하지 않음",
                                   "조항 참조·출처 링크", "범위 축소 아님")
        self.assertNotIn("위임 결정", scope)

    def test_p17_keeps_defaults_off_and_criteria_conditional(self):
        self.require_scope("P17", "DEC-D-08", "위임 결정", "사용자 확정 아님",
                           "defaults_enabled=false", "defaults_basis_ref 없음", "user_assumption만",
                           "가정 누락은 hold", "임의 0·평균 금지", "출처·범위·동결 릴리스",
                           "비편집 기준", "금액·점수·순위·가입 추천 없이",
                           "기본값·편집 기준은 별도 소유자 결정", "O05 미해결",
                           "게이트 등록", "구현 검증", "별도")

    def test_p19_records_preregistered_thresholds_without_claiming_validation(self):
        self.require_scope("P19", "DEC-D-16", "위임 결정", "사용자 확정 아님",
                           "U1~U7", "탐색 8~12명", "새 참가자 확인 12명 이상",
                           "U1·U2·U3·U5 80%", "U4·U6·U7 90%",
                           "동일 오해 3명 이상 시 실패", "첫 세션 전 PREREG 고정",
                           "기준 변경 시 해당 회차 무효", "게이트 등록", "별도",
                           "실제 시험·확인 회차 통과는 미완료", "범위 축소 아님")

    def test_scope_decisions_link_to_existing_records_and_keep_task_gates(self):
        tasks = {task["id"]: task for task in json.loads(
            (PURPOSE.parent / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
        expected = {
            "P03": {"D-14": ("T-KN-11", "merge")},
            "P06": {"D-02": ("T-KN-06", "real_data")},
            "P11": {"D-06": ("T-AP-08", "merge"), "D-07": ("T-AP-08", "merge")},
            "P14": {"D-12": ("T-AP-02", "release")},
            "P17": {"D-08": ("T-KN-14", "release")},
            "P19": {"D-16": ("T-UX-01", "start")},
        }
        for row, gates in expected.items():
            scope = self.rows[row][-1]
            self.assertNotIn("결정 대기", scope, row)
            self.assertNotIn("초안만", scope, row)
            for gate, (task, phase) in gates.items():
                with self.subTest(row=row, gate=gate):
                    target = ROOT / f"docs/decisions/DEC-{gate}.md"
                    self.assertIn(f"[DEC-{gate}](../../../decisions/DEC-{gate}.md)", scope)
                    self.assertTrue(target.is_file())
                    self.assertIn(task, scope)
                    self.assertIn(phase, scope)
                    self.assertIn(gate, tasks[task]["decision_gates"][phase])

    def test_completion_evidence_still_requires_real_records_and_participant_tests(self):
        for row, required in {
            "P03": ("R2 관측", "변경 감지→영향 재처리 실행 기록"),
            "P06": ("실제 이종 계열 2개의 ReviewDecision 기록", "hold 경로 실행 기록"),
            "P11": ("진술 입력 → 조건부 계산 → 확인 주체 표시 기록",),
            "P14": ("화면 숫자 → 원문 좌표 기록", "I6 계약 시험"),
            "P17": ("no-composite-score", "네 결과", "실제 흐름"),
            "P19": ("상태 카탈로그 캡처 1:1", "실제 참가자 이해 시험 결과"),
        }.items():
            for phrase in required:
                with self.subTest(row=row, phrase=phrase):
                    self.assertIn(phrase, self.rows[row][7])
        note = next(line for line in self.text.splitlines() if "2026-11-03_purpose_table_sync.md" in line)
        self.assertIn("문서 정합성 finding의 완료 증거", note)
        self.assertIn("출시 완료 증거를 대신하지 않는다", note)


if __name__ == "__main__":
    unittest.main()
