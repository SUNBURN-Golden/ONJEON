"""README 인덱스의 경로·결정·구현 범위를 저장소 정본과 대조한다."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def row(path_cell):
    for line in README.splitlines():
        if line.startswith(f"| `{path_cell}`"):
            return line
    raise AssertionError(f"README has no table row for {path_cell}")


class DecisionsRow(unittest.TestCase):
    def test_every_adr_number_is_listed(self):
        text = row("docs/decisions/")
        listed = set(re.findall(r"(?<!\d)(\d{4}) ", text))
        on_disk = {
            m.group(1)
            for p in (ROOT / "docs/decisions").glob("ADR-*.md")
            if (m := re.match(r"ADR-(\d{4})-", p.name))
        }
        self.assertTrue(on_disk, "no ADR files found")
        self.assertEqual(on_disk - listed, set(), "ADRs missing from README")
        self.assertEqual(listed - on_disk, set(), "README lists ADRs that do not exist")

    def test_dec_records_exist_and_are_pointed_to(self):
        self.assertTrue(list((ROOT / "docs/decisions").glob("DEC-*.md")))
        self.assertIn("DEC-*", row("docs/decisions/"))


class IndexedPaths(unittest.TestCase):
    def test_required_rows_present(self):
        for cell in (
            "docs/blueprint/VOCABULARY.md",
            "docs/blueprint/validation/",
            "docs/blueprint/proposals/설계검토_결과/",
            "data/registry/",
            "infra/r2/",
            "infra/s3/",
            "tools/daemon/",
        ):
            with self.subTest(path=cell):
                row(cell)

    def test_registry_is_an_institution_inventory_not_product_completion(self):
        text = row("data/registry/")
        for required in ("기관", "상품·특약", "미완료", "ADR-0018",
                         "[README](data/registry/README.md)"):
            self.assertIn(required, text)

    def test_r2_is_current_and_s3_templates_are_unused_alternatives(self):
        current = row("infra/r2/")
        for required in ("현재", "Cloudflare R2", "ADR-0016", "ADR-0017",
                         "[README](infra/r2/README.md)"):
            self.assertIn(required, current)
        historical = row("infra/s3/")
        for required in ("*.cfn.yaml", "AWS", "대안", "미사용", "미배포", "ADR-0016",
                         "[README](infra/s3/README.md)"):
            self.assertIn(required, historical)

    def test_daemon_is_a_development_tool_with_limited_evidence(self):
        text = row("tools/daemon/")
        for required in ("개발 도구", "모의", "실행기 검증", "가동 승인",
                         "출시 완료", "[README](tools/daemon/README.md)"):
            self.assertIn(required, text)

    def test_every_path_in_the_docs_table_exists(self):
        table = [l for l in README.splitlines() if l.startswith("| `")]
        self.assertGreaterEqual(len(table), 13)
        for line in table:
            path = re.match(r"\| `([^`]+)`", line).group(1)
            self.assertTrue((ROOT / path).exists(), f"README row points to missing {path}")

    def test_review_results_row_names_every_file(self):
        text = row("docs/blueprint/proposals/설계검토_결과/")
        for p in sorted((ROOT / "docs/blueprint/proposals/설계검토_결과").glob("[0-9][0-9]_*.md")):
            self.assertRegex(text, rf"{p.name[:2]} ", f"{p.name} missing from README row")


class ProductScope(unittest.TestCase):
    def test_introduction_points_to_scope_and_product_completion_criteria(self):
        intro = README.split("## ", 1)[0]
        for path in (
            "docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md",
            "docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md",
        ):
            self.assertIn(f"]({path})", intro)
            self.assertTrue((ROOT / path).is_file())
        for required in ("내부 전용", "픽스처", "미완료"):
            self.assertIn(required, intro)
        self.assertNotIn("앱·크롤러·API는 아직 없다", intro)


if __name__ == "__main__":
    unittest.main()
