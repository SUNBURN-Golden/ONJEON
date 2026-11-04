"""PR 템플릿이 작업 계약에서 제품 완료 증거까지 연결할 입력란을 제공한다."""
import json
import re
import unittest
from pathlib import Path

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / ".git").exists())
TEMPLATE = ROOT / ".github/pull_request_template.md"
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"


class PrTemplateTraceability(unittest.TestCase):
    def setUp(self):
        self.template = TEMPLATE.read_text(encoding="utf-8")

    def field(self, label):
        matches = [line for line in self.template.splitlines()
                   if line.startswith("- ") and label in line]
        self.assertEqual(1, len(matches), f"expected one fillable field: {label}")
        return matches[0]

    def test_task_field_links_to_the_adopted_task_source(self):
        line = self.field("[tasks.json]")
        target = re.search(r"\]\(([^)]+)\)", line).group(1)
        self.assertEqual(BUNDLE / "tasks.json", ROOT / target)
        tasks = json.loads((ROOT / target).read_text(encoding="utf-8"))["tasks"]
        self.assertTrue(tasks)
        self.assertTrue(all(re.fullmatch(r"T-[A-Z]{2}-\d{2}", t["id"]) for t in tasks))
        for text in ("과제 ID", "T-XX-NN", "복수 가능", "목록 외 작업은 노드 ID와 사유"):
            self.assertIn(text, line)
        self.assertTrue(line.endswith(":"))

    def test_purpose_field_links_to_the_completion_standard(self):
        line = self.field("[09_제품목적_대응표]")
        target = re.search(r"\]\(([^)]+)\)", line).group(1)
        self.assertEqual(BUNDLE / "09_제품목적_대응표.md", ROOT / target)
        purpose = (ROOT / target).read_text(encoding="utf-8")
        self.assertEqual({f"P{i:02}" for i in range(1, 20)},
                         set(re.findall(r"^\| (P\d{2}) \|", purpose, re.M)))
        for text in ("P행", "P01", "P19", "복수 가능", "해당 없음이면 사유"):
            self.assertIn(text, line)
        self.assertTrue(line.endswith(":"))

    def test_acceptance_field_connects_task_requirements_to_this_pr(self):
        line = self.field("`done_criteria`")
        self.assertIn("`required_test_ids`", line)
        self.assertIn("이번 PR의 수락 기준", line)
        self.assertTrue(line.endswith(":"))

    def test_evidence_field_requires_contribution_gaps_and_log_locations(self):
        line = self.field("P행의 완료 증거")
        for text in ("기여", "남은 공백", "증거·테스트 로그 경로"):
            self.assertIn(text, line)
        self.assertTrue(line.endswith(":"))

    def test_tool_and_synthetic_evidence_do_not_close_product_rows(self):
        for text in ("개발 도구는 09 §5의 T-OP-08 축 5 운영 기록",
                     "개별 과제·합성 시험 통과는 P행 전체나 첫 출시 완료를 뜻하지 않는다",
                     "BLUEPRINT §9.5", "ADR-0019"):
            self.assertIn(text, self.template)

    def test_traceability_does_not_adopt_the_deferred_common_policy(self):
        self.assertIn("`common_done_criteria` 전체의 채택 여부는 기존 "
                      "`non_binding_until_adopted`를 유지한다", self.template)
        tasks = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
        self.assertEqual("non_binding_until_adopted",
                         tasks["_common_done_criteria_status"])


if __name__ == "__main__":
    unittest.main()
