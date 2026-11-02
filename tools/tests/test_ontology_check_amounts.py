"""I1: ontology explanations and comparisons preserve all engine amount states."""
import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "docs/blueprint/proposals/온톨로지/검증"))
import ontology_check as check  # noqa: E402


class AmountPresentation(unittest.TestCase):
    def setUp(self):
        self.view = check.view(check.ABOX, check.CURRENT)
        self.question = copy.deepcopy(check.QUESTIONS[0])

    def evaluation(self, kind, amount):
        field = "amount" if kind == "payable" else "conditional_amount"
        return {
            "payout": {"kind": kind, field: amount},
            "missing_inputs": ["insured_amount_krw"],
            "rule_id": "test-rule", "rule_version": "v1",
            "rule_content_hash": "a" * 64, "publication_state": "fixture_only",
            "engine_version": "test-engine", "input_snapshot_hash": "b" * 64,
            "evidence_refs": ["hana_2601_3d#c_2_1_art1_1"],
        }

    def test_exact_zero_range_and_unknown_for_both_payout_kinds(self):
        cases = [
            ({"kind": "exact", "krw": 5000000}, "5,000,000원"),
            ({"kind": "exact", "krw": 0}, "0원"),
            ({"kind": "range", "min_krw": 5000000, "max_krw": 5000001},
             "5,000,000~5,000,001원 (범위)"),
            ({"kind": "unknown"}, "금액 미확정"),
        ]
        for kind in ("payable", "undetermined"):
            for amount, text in cases:
                with self.subTest(payout=kind, amount=amount["kind"], text=text):
                    ev = self.evaluation(kind, amount)
                    before = copy.deepcopy(ev)
                    self.assertEqual(check.outcome({}, ev), ev["payout"])
                    lines = check.explain(self.view, self.question, {}, ev)
                    self.assertIn(text, lines[0])
                    if kind == "undetermined":
                        self.assertIn("판단 불가 · 대상이라면 " + text, lines[0])
                        self.assertIn("insured_amount_krw", lines[0])
                    if amount["kind"] == "unknown":
                        self.assertNotIn("0원", lines[0])
                    self.assertIn("test-rule v1", lines[1])
                    self.assertTrue(any("근거 hana_2601_3d#c_2_1_art1_1" in s for s in lines))
                    self.assertEqual(ev, before)

    def test_range_and_unknown_never_compare_equal(self):
        for kind in ("payable", "undetermined"):
            with self.subTest(payout=kind):
                amounts = [
                    {"kind": "range", "min_krw": 0, "max_krw": 1},
                    {"kind": "range", "min_krw": 0, "max_krw": 2},
                    {"kind": "unknown"},
                    {"kind": "exact", "krw": 0},
                ]
                results = [check.outcome({}, self.evaluation(kind, a)) for a in amounts]
                for i, first in enumerate(results):
                    for other in results[i + 1:]:
                        self.assertNotEqual(first, other)

    def test_unsupported_amount_kind_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "지원하지 않는 금액 종류: invalid"):
            check.amount_text({"kind": "invalid"})

    def test_blocked_and_not_payable_keep_their_meaning(self):
        res = {"blocked": ["판매본 미확인"]}
        self.assertEqual(check.outcome(res, None), {"kind": "blocked"})
        self.assertIn("계산하지 않음", check.explain(self.view, self.question, res, None)[0])
        ev = self.evaluation("payable", {"kind": "unknown"})
        ev["payout"] = {"kind": "not_payable"}
        self.assertEqual(check.outcome({}, ev), {"kind": "not_payable"})
        self.assertEqual(check.explain(self.view, self.question, {}, ev)[0],
                         "결과: 이 담보에서는 지급 대상이 아님")


if __name__ == "__main__":
    unittest.main()
