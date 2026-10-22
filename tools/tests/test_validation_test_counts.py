"""검증 기록이 Rust 시험 수를 말할 때 단위·통합 테스트와 문서 시험(doctest)을 나눠 적는지 대조한다.

`cargo test`는 두 종류를 따로 센다. 합친 숫자만 적으면 한쪽만 세는 사람과 어긋난다
(Audit 1: "Rust 테스트 42개" = 테스트 39 + 문서 시험 3).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVERIFY = ROOT / "docs/blueprint/validation/REVERIFY_87a19c5.md"


class RustTestCountWording(unittest.TestCase):
    def setUp(self):
        self.text = REVERIFY.read_text(encoding="utf-8")

    def test_no_bare_combined_count(self):
        self.assertNotRegex(self.text, r"Rust 테스트 \d+개")

    def test_breakdown_is_stated(self):
        m = re.search(r"테스트 (\d+)개 \+ 문서 시험\(doctest\) (\d+)개 = (\d+)건", self.text)
        self.assertIsNotNone(m, "CI row must split tests from doctests")
        tests, docs, total = map(int, m.groups())
        self.assertEqual(tests + docs, total)
        self.assertEqual((tests, docs), (39, 3))

    def test_rerun_is_not_passed_off_as_ci_log(self):
        self.assertIn("재실행 값", self.text)


if __name__ == "__main__":
    unittest.main()
