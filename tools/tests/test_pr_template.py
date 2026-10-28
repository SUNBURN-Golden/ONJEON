"""허용 경로의 PR 템플릿 제안과 패치를 검사한다. 실제 적용 증거는 아니다."""
import difflib
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / ".github/pull_request_template.md"
EVIDENCE = ROOT / "tools/evidence/audit3-pr-template-task-fields"
PROPOSAL = EVIDENCE / "proposed_pull_request_template.md"
PATCH = EVIDENCE / "template.patch"
PURPOSE = "docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md"


class ProposedPrTemplate(unittest.TestCase):
    def setUp(self):
        self.template = PROPOSAL.read_text(encoding="utf-8")

    def test_patch_exactly_describes_proposal_and_preserves_current_template(self):
        current = TEMPLATE.read_text(encoding="utf-8")
        self.assertTrue(self.template.endswith(current))
        expected_patch = "".join(difflib.unified_diff(
            current.splitlines(keepends=True),
            self.template.splitlines(keepends=True),
            fromfile="a/.github/pull_request_template.md",
            tofile="b/.github/pull_request_template.md",
        ))
        self.assertTrue(expected_patch, "proposal must add the missing fields")
        self.assertEqual(expected_patch, PATCH.read_text(encoding="utf-8"))

    def test_patch_applies_cleanly_without_writing_live_template(self):
        before = TEMPLATE.read_bytes()
        result = subprocess.run(
            ["git", "apply", "--check", str(PATCH)], cwd=ROOT,
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, TEMPLATE.read_bytes())

    def field(self, label):
        # 설명 문장에 이름만 언급하는 것으로는 작성 필드를 대체하지 못한다.
        match = re.search(rf"^- {re.escape(label)}:[ \t]*([^\n]*)$",
                          self.template, re.MULTILINE)
        self.assertIsNotNone(match, f"missing PR field: {label}")
        return match.group(1)

    def test_task_and_author_fields_are_explicit(self):
        self.field("과제 ID (`task_id`)")
        authors = self.field("작성 모델 역할·실행 경로 (`authors`)")
        self.assertIn("모델 식별자 원문", authors)
        self.assertIn("제외", authors)

    def test_product_purpose_row_points_to_completion_criteria(self):
        self.field("제품 목적 P행")
        self.assertIn("P01~P19", self.template)
        self.assertIn(f"]({PURPOSE})", self.template)
        self.assertTrue((ROOT / PURPOSE).is_file())

    def test_target_sha_and_reproducible_test_log_have_separate_fields(self):
        sha = self.field("대상 SHA (`target_sha`)")
        self.assertIn("전체 커밋 SHA", sha)
        self.assertIn("미커밋 변경", sha)
        log = self.field("테스트 로그 (`test_log_ref`)")
        for required in ("명령", "종료 코드", "결과", "경로/링크"):
            with self.subTest(required=required):
                self.assertIn(required, log)

    def test_existing_design_traceability_and_validation_limits_remain(self):
        for label in (
            "정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M)",
            "해결하는 소비자 질문",
            "요구 ID (`docs/blueprint/REQUIREMENTS.md`)",
            "수락 사례와 기대 결과",
            "실제 수행한 검증 및 결과",
            "합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위",
            "미정 또는 지원하지 않는 동작",
        ):
            with self.subTest(field=label):
                self.field(label)
        self.assertIn("CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다",
                      self.template)


if __name__ == "__main__":
    unittest.main()
