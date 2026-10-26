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
        self.assertIn("과제 실행·완료 기준으로 채택", self.tasks["_status"])
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


class BundleStatus(unittest.TestCase):
    """DEC-BUNDLE-STATUS: 실행·완료 기준 채택과 정본 미채택을 모든 지위 문장이 함께 적는다."""

    EXECUTION = "과제 실행·완료 기준으로 채택"
    CANON = "채택된 정본이 아니다"
    RECORD = ROOT / "docs/decisions/DEC-BUNDLE-STATUS.md"

    def setUp(self):
        readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
        self.status_line = next(line for line in readme.splitlines() if line.startswith("작성 2026-10-12 |"))
        self.readme = readme
        self.handoff = (BUNDLE / "그록봇_인계/README.md").read_text(encoding="utf-8").splitlines()[2]
        self.json_status = {name: json.loads((BUNDLE / name).read_text(encoding="utf-8"))["_status"]
                            for name in ("tasks.json", "daemon_rules.json")}

    def statements(self):
        return {"README 상태": self.status_line, "그록봇 README": self.handoff, **self.json_status}

    def test_record_exists_and_states_both_halves(self):
        record = self.RECORD.read_text(encoding="utf-8")
        for phrase in ("Execution and completion basis: adopted", "Canon: not adopted",
                       "D-21", "09_제품목적_대응표", "2026-10-13", "NOT personally decide"):
            self.assertIn(phrase, record)

    def test_every_status_statement_carries_both_halves_and_the_record(self):
        for name, text in self.statements().items():
            with self.subTest(document=name):
                self.assertIn(self.EXECUTION, text)
                self.assertIn(self.CANON, text)
                self.assertIn("D-21", text)
                self.assertIn("DEC-BUNDLE-STATUS", text)

    def test_markdown_links_to_the_record_resolve(self):
        for name, base, text in (("README 상태", BUNDLE, self.status_line),
                                 ("그록봇 README", BUNDLE / "그록봇_인계", self.handoff)):
            with self.subTest(document=name):
                targets = {(base / path).resolve() for path in re.findall(r"\]\(([^)]+)\)", text)}
                self.assertIn(self.RECORD, targets)

    def test_completion_criterion_is_09_in_bundle_handoff_and_blueprint(self):
        self.assertIn("09가 최상위 완료 기준", self.status_line)
        self.assertIn("09가 최상위 완료 기준", self.handoff)
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        self.assertIn("첫 출시 완료는 [09_제품목적_대응표]", blueprint)

    def test_superseded_wording_is_gone(self):
        for stale in ("수정 완료 판정은 독립 재검토 뒤", "채택 전 검토용 초안",
                      "자동 개발 가동은 그 검토 뒤"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.readme)
        for name, text in self.json_status.items():
            with self.subTest(document=name):
                self.assertNotIn("초안", text)


if __name__ == "__main__":
    unittest.main()
