"""Audit 8 fix round 3: the live completion scope must be P01..P20 everywhere.

The finding that added P20 changed the completion denominator. This test keeps
the checker, the purpose table, the decision records and the CI documentation on
the same 20-row contract, and rejects a silent return to the 19-row denominator.
It is document/tool consistency evidence only.

The release evidence scaffold `docs/release-readiness/evidence/README.md` is
owned outside this node's allowed paths and is not edited here, so it is not
part of this test. Its P01–P19 wording must be synced by its owner; see
ADR-0022 and the node evidence README for the hand-off.
"""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
PURPOSE = BUNDLE / "09_제품목적_대응표.md"
CI_README = ROOT / "tools/ci/README.md"
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
DECISIONS_README = ROOT / "docs/decisions/README.md"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
SCOPE_ADR = ROOT / "docs/decisions/ADR-0022-제품-완료-범위-P20-확장.md"
SUPERSEDED = (
    ROOT / "docs/decisions/ADR-0019-제품-완료와-작업-계약-한정-채택.md",
    ROOT / "docs/decisions/ADR-0020-작업-단계와-V1-관문-정합화.md",
)
EXPECTED_ROWS = {f"P{i:02}" for i in range(1, 21)}
STALE_SCOPE = re.compile(r"P01\s*[~–-]\s*P19")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stale_scope(text):
    return STALE_SCOPE.findall(text)


class CompletionScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.check = load_module("release_readiness_check", ROOT / "tools/release_readiness/check.py")
        cls.product = load_module("check_product_purpose", ROOT / "tools/ci/check_product_purpose.py")

    def test_checkers_use_twenty_rows(self):
        self.assertEqual(self.check.ROW_IDS, EXPECTED_ROWS)
        self.assertEqual(self.product.EXPECTED_ROWS, EXPECTED_ROWS)

    def test_purpose_table_declares_every_twenty_row_once(self):
        rows = re.findall(r"^\| (P\d{2}) \|", PURPOSE.read_text(encoding="utf-8"), re.M)
        self.assertEqual(len(rows), len(set(rows)))
        self.assertEqual(set(rows), EXPECTED_ROWS)

    def test_p20_links_the_privacy_and_recovery_requirements(self):
        row = next(line for line in PURPOSE.read_text(encoding="utf-8").splitlines()
                   if line.startswith("| P20 |"))
        for phrase in ("T-CT-05", "T-CT-06", "T-PS-03", "T-PS-04", "T-AP-09",
                       "T-MB-04", "T-AP-06", "T-OP-05", "R19", "R20", "R22", "R23"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)

    def test_ci_readme_reports_the_registered_test_id_count(self):
        ci = CI_README.read_text(encoding="utf-8")
        self.assertEqual(len(self.product.REQUIRED_TEST_IDS), 11)
        self.assertIn("All eleven product-purpose test IDs", ci)
        self.assertNotIn("All nine product-purpose test IDs", ci)

    def test_scope_change_has_a_superseding_adr_and_ledger_entry(self):
        adr = SCOPE_ADR.read_text(encoding="utf-8")
        for phrase in ("P01~P20", "P20", "R19", "R20", "R22", "R23",
                       "T-PS-03", "T-PS-04", "T-OP-05", "purpose-rows-all-closed"):
            with self.subTest(adr_phrase=phrase):
                self.assertIn(phrase, adr)
        ledger = LEDGER.read_text(encoding="utf-8")
        self.assertEqual(1, ledger.count("| BP-D-23 |"))
        self.assertIn(SCOPE_ADR.name, ledger)
        self.assertIn("P01~P20", ledger)
        for path in SUPERSEDED:
            with self.subTest(document=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(SCOPE_ADR.name, text)
                self.assertIn("P01~P20", text)

    def test_live_documents_do_not_keep_the_nineteen_row_scope(self):
        for path in (*SUPERSEDED, DECISIONS_README, BLUEPRINT, LEDGER):
            with self.subTest(document=str(path.relative_to(ROOT))):
                self.assertEqual([], stale_scope(path.read_text(encoding="utf-8")))

    def test_regression_to_nineteen_rows_is_detected(self):
        live = DECISIONS_README.read_text(encoding="utf-8")
        self.assertEqual([], stale_scope(live))
        regressed = live.replace("P01~P20", "P01~P19")
        self.assertIn("P01~P19", stale_scope(regressed))
        # ADR-0019 and the blueprint are the two places the reviewer found stale.
        for path in (SUPERSEDED[0], BLUEPRINT):
            text = path.read_text(encoding="utf-8")
            self.assertNotEqual(text, text.replace("P01~P20", "P01~P19"))
            self.assertIn("P01~P19", stale_scope(text.replace("P01~P20", "P01~P19", 1)))


if __name__ == "__main__":
    unittest.main()
