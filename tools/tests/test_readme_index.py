"""README 인덱스의 경로·결정·구현 범위를 저장소 정본과 대조한다."""
import fnmatch
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")

# 결정 디렉터리의 DEC 기록 계열. README 행이 이 계열을 모두 안내해야 한다.
DEC_FAMILIES = (
    "DEC-D-*.md",
    "DEC-O*.md",
    "DEC-CANON-*.md",
    "DEC-BUNDLE-STATUS.md",
)


def row(path_cell, text=None):
    for line in (README if text is None else text).splitlines():
        if line.startswith(f"| `{path_cell}`"):
            return line
    raise AssertionError(f"README has no table row for {path_cell}")


def listed_adr_numbers(text):
    """ADR 행에서 `NNNN ` 형태로 나열된 번호를 문서 순서대로 돌려준다."""
    return re.findall(r"(?<!\d)(\d{4}) ", text)


class DecisionsRow(unittest.TestCase):
    def test_every_adr_number_is_listed(self):
        text = row("docs/decisions/")
        listed = set(listed_adr_numbers(text))
        on_disk = {
            m.group(1)
            for p in (ROOT / "docs/decisions").glob("ADR-*.md")
            if (m := re.match(r"ADR-(\d{4})-", p.name))
        }
        self.assertTrue(on_disk, "no ADR files found")
        self.assertEqual(on_disk - listed, set(), "ADRs missing from README")
        self.assertEqual(listed - on_disk, set(), "README lists ADRs that do not exist")

    def test_adr_numbers_are_listed_once_in_ascending_order(self):
        numbers = listed_adr_numbers(row("docs/decisions/"))
        self.assertEqual(numbers, sorted(set(numbers)),
                         "README ADR list has duplicates or is out of order")

    def test_dec_records_exist_and_are_pointed_to(self):
        self.assertTrue(list((ROOT / "docs/decisions").glob("DEC-*.md")))
        self.assertIn("DEC-*", row("docs/decisions/"))

    def test_dec_record_families_are_named_and_cover_every_record(self):
        text = row("docs/decisions/")
        for family in ("DEC-D-xx", "DEC-Oxx", "DEC-CANON-*", "DEC-BUNDLE-STATUS"):
            with self.subTest(family=family):
                self.assertIn(family, text)
        for pattern in DEC_FAMILIES:
            with self.subTest(pattern=pattern):
                self.assertTrue(list((ROOT / "docs/decisions").glob(pattern)),
                                f"no records match {pattern}")
        records = (ROOT / "docs/decisions").glob("DEC-*.md")
        unmatched = [
            p.name
            for p in records
            if not any(fnmatch.fnmatchcase(p.name, pattern) for pattern in DEC_FAMILIES)
        ]
        self.assertEqual(unmatched, [], "README DEC families do not cover these records")


class DocumentHierarchy(unittest.TestCase):
    def test_priority_points_to_blueprint_section_0_1(self):
        self.assertIn(
            "[BLUEPRINT §0.1 문서 위계](docs/BLUEPRINT.md#01-문서-위계)",
            README,
        )
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        self.assertIn("### 0.1 문서 위계", blueprint)

    def test_replaced_masterplan_priority_is_not_present(self):
        self.assertNotRegex(
            README, r"불변\s*원칙\s*→\s*제2부\s*→\s*제3부\s*→\s*제1부"
        )
        self.assertNotRegex(
            README, r"제3부\s*§56의\s*사용자\s*결정은\s*이\s*순서보다\s*우선"
        )


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
