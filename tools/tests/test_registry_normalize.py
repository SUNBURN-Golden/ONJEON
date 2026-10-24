"""Registry normalization on disposable CSVs; repository registries stay read-only."""
import csv
import io
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import registry_normalize as rn


class AccessCodes(unittest.TestCase):
    def test_axis_lookup(self):
        self.assertEqual(rn.axis("host_access")["id"], "host_access")
        with self.assertRaises(StopIteration):
            rn.axis("missing_axis")

    def test_canonical_codes_and_all_deprecated_aliases(self):
        for value in rn.axis("host_access")["values"]:
            for raw in [value["code"], *value["deprecated_aliases"]]:
                with self.subTest(raw=raw):
                    self.assertEqual(rn.host_code(raw), value["code"])

    def test_raw_http_results_redirects_whitespace_and_empty_values(self):
        cases = [(None, "not_checked"), ("", "not_checked"), ("  ", "not_checked"),
                 ("200", "reachable"), ("301", "reachable"), ("302", "reachable"),
                 ("307", "reachable"), ("403", "origin_denied"), ("429", "rate_limited"),
                 ("502", "proxy_error"), ("503", "proxy_error"), ("504", "proxy_error"),
                 (" 200 -> 302 -> 403 (https://example.invalid) ", "origin_denied"),
                 ("302 -> 200_js_shell (redirect target)", "js_shell"),
                 ("302 -> reachable (target)", "reachable")]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(rn.host_code(raw), expected)

    def test_unknown_results_abort_instead_of_claiming_success(self):
        for raw in ("404", "mystery", "200 -> unknown (target)"):
            with self.subTest(raw=raw), self.assertRaisesRegex(SystemExit, "unmapped access result"):
                rn.host_code(raw)

    def test_reachable_disclosure_url_is_required_for_archived(self):
        status, reason = rn.disclosure(dict(disclosure_url=" https://example.invalid/terms ",
                                            disclosure_access="reachable", home_access="origin_denied"))
        self.assertEqual((status, reason), ("archived", ""))
        for url, access in (("", "reachable"), ("   ", "reachable"),
                            ("https://example.invalid", "origin_denied")):
            with self.subTest(url=url, access=access):
                status, reason = rn.disclosure(dict(disclosure_url=url, disclosure_access=access,
                                                    home_access="reachable"))
                self.assertEqual(status, "failed")
                self.assertTrue(reason)

    def test_home_access_mapping_keeps_unqueried_blocked_and_failed_distinct(self):
        for home, expected in (("not_checked", "unqueried"), ("reachable", "failed"),
                               ("js_shell", "failed"), ("geo_blocked", "blocked"),
                               ("origin_denied", "blocked"), ("rate_limited", "blocked"),
                               ("timeout", "failed"), ("proxy_error", "failed")):
            with self.subTest(home=home):
                status, reason = rn.disclosure(dict(home_access=home))
                self.assertEqual(status, expected)
                self.assertTrue(reason)
        self.assertEqual(rn.disclosure({})[0], "unqueried")


class RegistryCsv(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "registry.csv"

    def write(self, rows, fields=None):
        with self.path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    def read(self):
        with self.path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_normalizes_evidence_access_details_and_lower_denominator_idempotently(self):
        self.write([dict(name="보험사", status="verified_2_sources", home_access="200",
                         disclosure_access="302 -> 200 (target)", disclosure_url="https://example.invalid")])
        self.assertEqual(rn.normalize(self.path), 1)
        row = self.read()[0]
        self.assertNotIn("status", row)
        self.assertEqual(row["name"], "보험사")
        self.assertEqual(row["entity_evidence"], "two_or_more_sources")
        self.assertEqual(row["home_access"], "reachable")
        self.assertEqual(row["home_access_detail"], "200")
        self.assertEqual(row["disclosure_access_detail"], "302 -> 200 (target)")
        self.assertEqual(row["disclosure_status"], "archived")
        self.assertEqual(row["disclosure_gap_reason"], "")
        self.assertEqual(row["product_list_status"], "unqueried")
        self.assertIn("상품·특약", row["product_list_reason"])
        first = self.path.read_bytes()
        self.assertEqual(rn.normalize(self.path), 1)
        self.assertEqual(self.path.read_bytes(), first)

    def test_all_evidence_aliases_and_canonical_values(self):
        cases = [("verified_2_sources", "two_or_more_sources"), ("verified_1_source", "one_source"),
                 ("unverified_seed", "seed"), ("seed", "seed"),
                 ("one_source", "one_source"), ("two_or_more_sources", "two_or_more_sources")]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.write([dict(status=raw)])
                self.assertEqual(rn.normalize(self.path, has_disclosure=False), 1)
                self.assertEqual(self.read(), [dict(entity_evidence=expected)])

    def test_existing_details_product_progress_and_unrelated_fields_survive(self):
        self.write([dict(entity_evidence="seed", home_access="reachable", home_access_detail="prior evidence",
                         disclosure_access="not_checked", disclosure_url="", product_list_status="archived",
                         product_list_reason="already enumerated", note="keep")])
        self.assertEqual(rn.normalize(self.path), 1)
        row = self.read()[0]
        self.assertEqual(row["home_access_detail"], "prior evidence")
        self.assertEqual(row["disclosure_access_detail"], "")
        self.assertEqual(row["product_list_status"], "archived")
        self.assertEqual(row["product_list_reason"], "already enumerated")
        self.assertEqual(row["note"], "keep")
        self.assertEqual(row["disclosure_status"], "failed")

    def test_without_disclosure_does_not_add_disclosure_or_product_fields(self):
        self.write([dict(entity_evidence="seed", home_access="403_origin")])
        self.assertEqual(rn.normalize(self.path, has_disclosure=False), 1)
        self.assertEqual(self.read(), [dict(entity_evidence="seed", home_access="origin_denied",
                                          home_access_detail="403_origin")])

    def test_invalid_evidence_or_access_leaves_whole_input_untouched(self):
        for bad in (dict(entity_evidence="invalid", home_access="200"),
                    dict(entity_evidence="seed", home_access="unknown"), dict(home_access="200")):
            with self.subTest(bad=bad):
                good = dict(entity_evidence="seed", home_access="200")
                fields = list(dict.fromkeys([*good, *bad]))
                self.write([good, bad], fields)
                before = self.path.read_bytes()
                with self.assertRaises(SystemExit):
                    rn.normalize(self.path)
                self.assertEqual(self.path.read_bytes(), before)

    def test_empty_registry_is_unchanged(self):
        self.write([], ["status", "home_access"])
        before = self.path.read_bytes()
        self.assertEqual(rn.normalize(self.path), 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_access_log_retains_raw_result_and_is_idempotent(self):
        self.write([dict(url="https://example.invalid/a", result="200 -> 429 (target)"),
                    dict(url="https://example.invalid/b", result="")])
        self.assertEqual(rn.normalize_access_log(self.path), 2)
        self.assertEqual(self.read(), [dict(url="https://example.invalid/a", result="200 -> 429 (target)",
                                           host_access="rate_limited"),
                                      dict(url="https://example.invalid/b", result="", host_access="not_checked")])
        first = self.path.read_bytes()
        self.assertEqual(rn.normalize_access_log(self.path), 2)
        self.assertEqual(self.path.read_bytes(), first)

    def test_access_log_preserves_existing_code_and_handles_absent_result(self):
        self.write([dict(url="a", result="unmapped historical detail", host_access="timeout")])
        self.assertEqual(rn.normalize_access_log(self.path), 1)
        self.assertEqual(self.read()[0]["host_access"], "timeout")
        self.write([dict(url="b")])
        self.assertEqual(rn.normalize_access_log(self.path), 1)
        self.assertEqual(self.read()[0]["host_access"], "not_checked")

    def test_invalid_access_log_leaves_input_untouched(self):
        self.write([dict(result="200"), dict(result="unmapped")])
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SystemExit, "unmapped access result"):
            rn.normalize_access_log(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_script_normalizes_all_three_registries_in_isolated_tree(self):
        root = self.path.parent
        script = root / "tools/registry_normalize.py"
        script.parent.mkdir()
        script.write_bytes(Path(rn.__file__).read_bytes())
        vocab = root / "packages/schemas/vocabulary.json"
        vocab.parent.mkdir(parents=True)
        vocab.write_bytes((rn.ROOT / "packages/schemas/vocabulary.json").read_bytes())
        registry = root / "data/registry"
        registry.mkdir(parents=True)
        for name in ("insurers", "cooperatives_and_others"):
            (registry / f"{name}.csv").write_text(
                "name,status,home_access\n가,verified_1_source,403\n나,unverified_seed,200\n", encoding="utf-8")
        (registry / "access_log.csv").write_text("url,result\nhttps://example.invalid,429\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()) as out:
            runpy.run_path(str(script), run_name="__main__")
        self.assertEqual(out.getvalue().splitlines(), ["insurers 2", "cooperatives_and_others 2", "access_log 1"])
        for name in ("insurers", "cooperatives_and_others"):
            with (registry / f"{name}.csv").open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["entity_evidence"] for r in rows], ["one_source", "seed"])
            self.assertEqual([r["disclosure_status"] for r in rows], ["blocked", "failed"])
        with (registry / "access_log.csv").open(encoding="utf-8") as f:
            self.assertEqual(next(csv.DictReader(f))["host_access"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
