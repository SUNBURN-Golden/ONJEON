"""Rust 시험 수를 말하는 문서가 단위·통합 테스트와 문서 시험(doctest)을 나눠 적는지 대조한다.

`cargo test`는 두 종류를 따로 센다. 합친 숫자만 적으면 한쪽만 세는 사람과 어긋난다
(Audit 1: `docs/BLUEPRINT.md` §11 "Rust 테스트 42개" = 테스트 39 + 문서 시험 3).
근거 행은 docs/blueprint/validation/REVERIFY_87a19c5.md, 교체안과 재실행 기록은
docs/review/2026-10-22_audit1_blueprint_test_count.md.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVERIFY = ROOT / "docs/blueprint/validation/REVERIFY_87a19c5.md"
VALIDATION_README = ROOT / "docs/blueprint/validation/README.md"
REVIEW_NOTE = ROOT / "docs/review/2026-10-22_audit1_blueprint_test_count.md"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"

BARE = re.compile(r"Rust 테스트 (\d+)개")
SPLIT = re.compile(r"테스트 (\d+)개 \+ 문서 시험\(doctest\) (\d+)개")


def read(path):
    return path.read_text(encoding="utf-8")


def reverify_split():
    """(tests, doctests, total) as written in the CI row of the re-verification record."""
    m = re.search(SPLIT.pattern + r" = (\d+)건", read(REVERIFY))
    assert m, "REVERIFY CI row must split tests from doctests"
    return tuple(map(int, m.groups()))


def section(text, number):
    start = text.index(f"\n## {number}. ")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else None]


class ReverifyRecord(unittest.TestCase):
    def setUp(self):
        self.text = read(REVERIFY)

    def test_no_bare_combined_count(self):
        self.assertNotRegex(self.text, BARE)

    def test_breakdown_adds_up(self):
        tests, docs, total = reverify_split()
        self.assertEqual(tests + docs, total)

    def test_rerun_is_not_passed_off_as_ci_log(self):
        self.assertIn("재실행 값", self.text)
        self.assertIn("CI 로그 자체는 이 저장소에 없다", self.text)


class ReviewNote(unittest.TestCase):
    def setUp(self):
        self.text = read(REVIEW_NOTE)

    def test_replacement_wording_matches_reverify(self):
        tests, docs, _ = reverify_split()
        quoted = " ".join(l for l in self.text.splitlines() if l.startswith("> "))
        self.assertTrue(quoted, "review note must quote the replacement wording")
        m = SPLIT.search(quoted)
        self.assertIsNotNone(m, "replacement wording must split tests from doctests")
        self.assertEqual(tuple(map(int, m.groups())), (tests, docs))
        self.assertNotRegex(quoted, BARE)

    def test_per_binary_table_sums_to_test_count(self):
        tests, docs, _ = reverify_split()
        rows = re.findall(r"^\| `(?:src|tests)/[^`]+`[^|]*\| (\d+) \|$", self.text, re.M)
        self.assertGreaterEqual(len(rows), 2, "re-run table must list the test binaries")
        self.assertEqual(sum(map(int, rows)), tests)
        self.assertRegex(self.text, rf"문서 시험\(doctest\) {docs}개")

    def test_points_at_sources(self):
        for needle in ("REVERIFY_87a19c5.md", "docs/BLUEPRINT.md", "318행", "test_validation_test_counts.py"):
            self.assertIn(needle, self.text)


class ValidationReadme(unittest.TestCase):
    def test_follow_up_points_at_review_note(self):
        self.assertIn(REVIEW_NOTE.name, read(VALIDATION_README))


class Blueprint(unittest.TestCase):
    """docs/BLUEPRINT.md is protected: the round that found this could not edit it.

    expectedFailure turns into an "unexpected success" (a failing run) as soon as the §11 code row is
    corrected, which is the cue to delete the decorator. The replacement wording is in
    docs/review/2026-10-22_audit1_blueprint_test_count.md.
    """

    def setUp(self):
        rows = [l for l in section(read(BLUEPRINT), 11).splitlines() if l.startswith("| 코드 |")]
        self.assertEqual(len(rows), 1, "§11 must have exactly one 코드 row")
        self.code_row = rows[0]

    @unittest.expectedFailure
    def test_no_bare_combined_count(self):
        self.assertNotRegex(self.code_row, BARE)

    def test_count_agrees_with_split_evidence(self):
        tests, docs, total = reverify_split()
        bare = BARE.search(self.code_row)
        if bare:
            self.assertEqual(int(bare.group(1)), total, "bare count must equal tests + doctests in REVERIFY")
        else:
            m = SPLIT.search(self.code_row)
            self.assertIsNotNone(m, "corrected row must state tests + doctests")
            self.assertEqual(tuple(map(int, m.groups())), (tests, docs))


if __name__ == "__main__":
    unittest.main()
