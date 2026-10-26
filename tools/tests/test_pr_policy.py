"""검토용 공통 완료 기준을 현행 PR 의무로 오인하지 않도록 문서 지위를 대조한다."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"


class PrPolicy(unittest.TestCase):
    def setUp(self):
        self.tasks = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
        readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
        work_spec = (BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        self.assertIn("## 0.1 PR 완료 기준의 적용 상태", readme)
        self.readme_policy = readme.split("## 0.1 PR 완료 기준의 적용 상태", 1)[1].split("## 1.", 1)[0]
        self.spec_policy = work_spec.split("## 2.", 1)[1].split("## 3.", 1)[0]
        self.policies = {
            "tasks.json": self.tasks.get("_common_done_criteria_note", ""),
            "README §0.1": self.readme_policy,
            "03 §2": self.spec_policy,
        }

    def test_json_and_both_documents_explicitly_defer_common_pr_criteria(self):
        self.assertEqual("non_binding_until_adopted",
                         self.tasks.get("_common_done_criteria_status"))
        self.assertIn("채택된 정본이 아니다", self.tasks["_status"])
        for name, policy in self.policies.items():
            with self.subTest(document=name):
                self.assertIn("common_done_criteria", policy)
                self.assertIn("채택 전 모든 PR에 구속력을 갖지 않는다", policy)

    def test_documented_current_policy_links_resolve_to_real_policy_files(self):
        for name, policy in list(self.policies.items())[1:]:
            targets = {(BUNDLE / path).resolve()
                       for path in re.findall(r"\[[^]]+\]\(([^)]+)\)", policy)}
            with self.subTest(document=name):
                for path in (".github/pull_request_template.md", "docs/BLUEPRINT.md"):
                    target = ROOT / path
                    self.assertIn(target, targets)
                    self.assertTrue(target.is_file())

    def test_adoption_instructions_cover_each_missing_field(self):
        for name, policy in self.policies.items():
            with self.subTest(document=name):
                for text in ("채택 시", "과제 ID", "모델 역할·실행 경로", "대상 SHA", "테스트 로그"):
                    self.assertIn(text, policy)

    def test_proposed_traceability_and_test_evidence_requirements_are_retained(self):
        criteria = self.tasks["common_done_criteria"]
        self.assertIn("과제 ID, 작성에 참여한 모델 역할·실행 경로, 대상 SHA를 적었다", criteria)
        self.assertIn("tests의 명령을 실행하고 로그를 첨부했다('시험 추가 예정'은 통과가 아님)", criteria)


if __name__ == "__main__":
    unittest.main()
