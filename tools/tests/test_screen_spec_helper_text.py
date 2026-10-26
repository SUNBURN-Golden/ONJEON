"""Audit 1: effective helper copy follows CONSUMER_FLOW_SPEC, without a P0 gate.

The design appendix is read-only for this node. BLUEPRINT explicitly supersedes
its conflicting copy and open item; the editable screen binding uses that copy.
Discovered by the existing tools/tests CI step. No release UX result is claimed.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def section(text, number):
    match = re.search(rf"^## {number}\. .*?(?=^## |\Z)", text, re.M | re.S)
    if match is None:
        raise AssertionError(f"Missing section {number}")
    return match.group()


def table_row(text, label):
    rows = [line for line in text.splitlines() if line.startswith(f"| {label} |")]
    if len(rows) != 1:
        raise AssertionError(f"Expected one {label} row, got {len(rows)}")
    return [cell.strip() for cell in rows[0].strip("|").split("|")]


class ScreenSpecHelperTextTests(unittest.TestCase):
    def setUp(self):
        self.blueprint = read("docs/BLUEPRINT.md")
        source = section(read("docs/design/CONSUMER_FLOW_SPEC.md"), 2)
        title_row = table_row(source, "제목")
        self.canonical = title_row[2].removeprefix("보조 문구: ")
        self.assertEqual(self.canonical, "예산 안에서 보장과 조건을 비교하세요")

    def test_blueprint_adopts_exact_upstream_copy_and_supersedes_both_appendix_items(self):
        consumer = section(self.blueprint, 3)
        row = table_row(consumer, "내 설계 보조문")
        self.assertEqual(row[1], self.canonical)
        self.assertIn("CONSUMER_FLOW_SPEC §2", row[2])
        for reference in ("화면_조작_설계서.md", "§10", "§13", "대체", "확정"):
            self.assertIn(reference, consumer)

    def test_helper_is_no_longer_an_open_decision_and_other_design_items_remain(self):
        decisions = section(self.blueprint, 12)
        self.assertNotIn("보조문", decisions)
        self.assertIn("색 토큰", decisions)
        self.assertIn("C2~C4·C7", decisions)

    def test_screen_binding_shows_canonical_helper_under_title(self):
        binding = section(read("docs/blueprint/validation/SCREEN_BINDING.md"), 1)
        self.assertIn(f"나에게 필요한 만큼\n{self.canonical}\n", binding)
        self.assertNotIn("예산을 움직여 보장을 비교하세요", binding)

    def test_conflict_register_closes_helper_only(self):
        conflicts = section(read("docs/blueprint/DECISIONS.md"), 2)
        row = table_row(conflicts, "내 설계 보조문을 P0 미정으로 남긴 부록 §10·§13")
        self.assertIn(self.canonical, row[1])
        self.assertIn("CONSUMER_FLOW_SPEC §2", row[1])
        self.assertIn("해결", row[2])
        self.assertIn("BLUEPRINT §3", row[2])


if __name__ == "__main__":
    unittest.main()
