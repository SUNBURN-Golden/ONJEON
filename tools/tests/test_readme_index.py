"""README.md 문서 표가 docs/ 디렉터리의 실제 내용과 어긋나지 않는지 대조한다."""
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
        ):
            row(cell)

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


if __name__ == "__main__":
    unittest.main()
