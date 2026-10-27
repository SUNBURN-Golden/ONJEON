"""§4 must describe the implemented scope without claiming a finished service."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class BlueprintLayerStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        cls.section = cls.text.split("## 4. 시스템 계층", 1)[1].split("## 5.", 1)[0]
        cls.rows = {}
        for line in cls.section.splitlines():
            if re.match(r"\| L\d+ \|", line):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                cls.rows[cells[0]] = cells

    def test_implemented_layers_have_scoped_partial_status(self):
        for layer in ("L0", "L1", "L6"):
            with self.subTest(layer=layer):
                self.assertEqual(len(self.rows[layer]), 5)
                self.assertTrue(self.rows[layer][-1].startswith("부분 구현("))

    def test_l0_distinguishes_v0_from_product_and_rider_denominators(self):
        status = self.rows["L0"][-1]
        for phrase in ("V0", "기관 목록", "접근·공백", "어휘 정규화", "상품·특약 분모 미열거"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, status)
        self.assert_references_exist(status, ("data/registry/", "tools/registry_normalize.py"))

    def test_l1_distinguishes_archive_tooling_from_daily_full_collection(self):
        status = self.rows["L1"][-1]
        for phrase in ("수집·불변 보존 도구", "V1 표본 보존 기록", "전 상품 일일 수집 미완료"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, status)
        self.assert_references_exist(status, ("tools/crawler/", "tools/source_archive.py", "services/collect/"))

    def test_l6_includes_real_clauses_and_keeps_fixture_and_service_limits(self):
        status = self.rows["L6"][-1]
        for phrase in ("DSL 로더·평가기", "합성·실제 조항", "fixture_only", "승인 데이터→규칙→서비스 연결 미완료"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, status)
        self.assert_references_exist(status, ("packages/rules-engine/",))

    def test_scope_note_keeps_historical_observation_and_release_evidence_boundary(self):
        for phrase in ("2026-10-09 관측 기록", "§11", "09_제품목적_대응표", "완료 증거", "T-OP-08"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.section)
        link = "blueprint/audits/2026-10-27_blueprint_layer_status.md"
        self.assertIn(f"]({link})", self.section)
        self.assertTrue((ROOT / "docs" / link).is_file())

    def assert_references_exist(self, status, paths):
        for path in paths:
            with self.subTest(path=path):
                self.assertIn(f"`{path}`", status)
                self.assertTrue((ROOT / path).exists())


if __name__ == "__main__":
    unittest.main()
