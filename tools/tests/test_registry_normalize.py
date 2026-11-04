"""Registry normalization on disposable CSVs; repository registries stay read-only."""
import csv
import io
import os
import re
import runpy
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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

    def test_reachable_disclosure_is_not_archived_without_preservation_evidence(self):
        status, reason = rn.disclosure(dict(disclosure_url=" https://example.invalid/terms ",
                                            disclosure_access="reachable", home_access="origin_denied"))
        self.assertEqual(status, "unqueried")
        self.assertIn("공시 URL 접근 확인", reason)
        self.assertIn("불변 보관 전", reason)
        for url, access in (("", "reachable"), ("   ", "reachable"),
                            ("https://example.invalid", "origin_denied")):
            with self.subTest(url=url, access=access):
                status, reason = rn.disclosure(dict(disclosure_url=url, disclosure_access=access,
                                                    home_access="reachable"))
                self.assertEqual(status, "failed")
                self.assertTrue(reason)

    def test_access_results_alone_never_prove_archival(self):
        for home in rn.HOST_CODES:
            for access in rn.HOST_CODES:
                with self.subTest(home=home, access=access):
                    status, _ = rn.disclosure(dict(disclosure_url="https://example.invalid",
                                                   disclosure_access=access, home_access=home))
                    self.assertNotEqual(status, "archived")

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
        self.assertEqual(row["disclosure_access"], "reachable")
        self.assertEqual(row["disclosure_status"], "unqueried")
        self.assertIn("불변 보관 전", row["disclosure_gap_reason"])
        self.assertEqual(row["product_list_status"], "unqueried")
        self.assertIn("상품·특약", row["product_list_reason"])
        self.assertEqual(row["product_list_reason_codes"], "awaiting_T-DT-04;awaiting_domestic_env")
        first = self.path.read_bytes()
        self.assertEqual(rn.normalize(self.path), 1)
        self.assertEqual(self.path.read_bytes(), first)

    def test_legacy_archived_claim_is_repaired_and_access_evidence_is_preserved(self):
        original = dict(entity_evidence="two_or_more_sources", home_access="reachable",
                        disclosure_access="reachable", disclosure_access_detail="200",
                        disclosure_url="https://example.invalid/terms", observed_at="2026-10-09T04:27:43Z",
                        disclosure_status="archived", disclosure_gap_reason="",
                        product_list_status="unqueried", product_list_reason="상품·특약 목록 열거 전",
                        product_list_reason_codes="awaiting_T-DT-04;awaiting_domestic_env")
        self.write([original])
        rn.normalize(self.path)
        row = self.read()[0]
        for field in original.keys() - {"disclosure_status", "disclosure_gap_reason"}:
            self.assertEqual(row[field], original[field], field)
        self.assertEqual(row["disclosure_status"], "unqueried")
        self.assertIn("불변 보관 전", row["disclosure_gap_reason"])
        first = self.path.read_bytes()
        rn.normalize(self.path)
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
                         product_list_reason="already enumerated", note="keep\r\nquoted, detail")])
        self.assertEqual(rn.normalize(self.path), 1)
        row = self.read()[0]
        self.assertEqual(row["home_access_detail"], "prior evidence")
        self.assertEqual(row["disclosure_access_detail"], "")
        self.assertEqual(row["product_list_status"], "archived")
        self.assertEqual(row["product_list_reason"], "already enumerated")
        self.assertEqual(row["note"], "keep\r\nquoted, detail")
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
        for contents in (b"", b"status,home_access\r\n"):
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                self.assertEqual(rn.normalize(self.path), 0)
                self.assertEqual(self.path.read_bytes(), contents)

    def test_missing_disclosure_access_does_not_claim_reachable_or_archived(self):
        for home, expected in ((None, "unqueried"), ("200", "failed"), ("403", "blocked")):
            with self.subTest(home=home):
                row = dict(entity_evidence="seed", disclosure_url="https://example.invalid/terms")
                if home is not None:
                    row["home_access"] = home
                self.write([row])
                self.assertEqual(rn.normalize(self.path), 1)
                normalized = self.read()[0]
                self.assertEqual(normalized["disclosure_status"], expected)
                self.assertTrue(normalized["disclosure_gap_reason"])
                self.assertIn("disclosure_entry_missing", normalized["product_list_reason_codes"])
                first = self.path.read_bytes()
                rn.normalize(self.path)
                self.assertEqual(self.path.read_bytes(), first)

    def test_empty_access_log_is_unchanged(self):
        for contents in (b"", b"url,result\r\n", b"url,result,host_access\n"):
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                self.assertEqual(rn.normalize_access_log(self.path), 0)
                self.assertEqual(self.path.read_bytes(), contents)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def normalization_cases(self):
        return ((rn.normalize, dict(entity_evidence="seed", home_access="200"), "home_access", "reachable"),
                (rn.normalize_access_log, dict(result="429"), "host_access", "rate_limited"))

    def test_atomic_replacement_keeps_original_until_complete_and_preserves_mode(self):
        replace = os.replace
        for normalize, row, column, expected in self.normalization_cases():
            with self.subTest(normalizer=normalize.__name__):
                self.write([row])
                self.path.chmod(0o640)
                before = self.path.read_bytes()

                def inspect_then_replace(source, destination):
                    source, destination = Path(source), Path(destination)
                    self.assertEqual(destination, self.path)
                    self.assertEqual(source.parent, self.path.parent)
                    self.assertNotEqual(source, self.path)
                    self.assertEqual(self.path.read_bytes(), before)
                    with source.open(encoding="utf-8", newline="") as f:
                        self.assertEqual(list(csv.DictReader(f))[0][column], expected)
                    replace(source, destination)

                with patch.object(rn.os, "replace", side_effect=inspect_then_replace) as swapped:
                    self.assertEqual(normalize(self.path), 1)
                swapped.assert_called_once()
                self.assertEqual(self.read()[0][column], expected)
                self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_partial_write_failure_preserves_original_and_cleans_temporary_file(self):
        for normalize, row, _, _ in self.normalization_cases():
            with self.subTest(normalizer=normalize.__name__):
                self.write([row, row])
                before = self.path.read_bytes()

                def partial_write(writer, rows):
                    writer.writerow(rows[0])
                    raise OSError("simulated disk full")

                with patch.object(csv.DictWriter, "writerows", partial_write):
                    with self.assertRaisesRegex(OSError, "simulated disk full"):
                        normalize(self.path)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_sync_or_replace_failure_preserves_original_and_cleans_temporary_file(self):
        for normalize, row, _, _ in self.normalization_cases():
            for operation in ("fsync", "replace"):
                with self.subTest(normalizer=normalize.__name__, operation=operation):
                    self.write([row])
                    before = self.path.read_bytes()
                    with patch.object(rn.os, operation, side_effect=OSError("simulated I/O error")):
                        with self.assertRaisesRegex(OSError, "simulated I/O error"):
                            normalize(self.path)
                    self.assertEqual(self.path.read_bytes(), before)
                    self.assertEqual(list(self.path.parent.iterdir()), [self.path])

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

    def test_script_normalizes_all_four_registries_in_isolated_tree(self):
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
        excluded = registry / "excluded_or_historical.csv"
        excluded.write_text(
            'insurer_id,name_ko,status,listed_in,observed_at,notes,in_current_assoc_list\n'
            'hist-a,과거기관,verified_2_sources,kidi;dart,2026-10-09T04:24:59Z,"미확인, 제외 사유",false\n'
            'hist-b,제외기관,verified_1_source,dart,2026-10-09T04:27:40Z,과거 기록,false\n',
            encoding="utf-8")
        with excluded.open(encoding="utf-8", newline="") as f:
            original_excluded = list(csv.DictReader(f))
        (registry / "access_log.csv").write_text("url,result\nhttps://example.invalid,429\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()) as out:
            runpy.run_path(str(script), run_name="__main__")
        self.assertEqual(out.getvalue().splitlines(), ["insurers 2", "cooperatives_and_others 2",
                                                       "excluded_or_historical 2", "access_log 1"])
        for name in ("insurers", "cooperatives_and_others"):
            with (registry / f"{name}.csv").open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["entity_evidence"] for r in rows], ["one_source", "seed"])
            self.assertEqual([r["disclosure_status"] for r in rows], ["blocked", "failed"])
        with (registry / "access_log.csv").open(encoding="utf-8") as f:
            self.assertEqual(next(csv.DictReader(f))["host_access"], "rate_limited")
        with excluded.open(encoding="utf-8", newline="") as f:
            excluded_rows = list(csv.DictReader(f))
        expected = [dict((k, v) for k, v in row.items() if k != "status") for row in original_excluded]
        for row, value in zip(expected, ("two_or_more_sources", "one_source")):
            row["entity_evidence"] = value
        self.assertEqual(excluded_rows, expected)
        before = {p.name: p.read_bytes() for p in registry.glob("*.csv")}
        with redirect_stdout(io.StringIO()):
            runpy.run_path(str(script), run_name="__main__")
        self.assertEqual({p.name: p.read_bytes() for p in registry.glob("*.csv")}, before)


class WorkflowWiring(unittest.TestCase):
    def test_ci_runs_registry_regressions_before_dependency_install_or_build(self):
        workflow = (rn.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        step = re.search(
            r"^      - name: Registry normalization regressions\n"
            # The step is gated off for PR edits; it still runs on code pushes and PR updates.
            r"(?:        if: github\.event\.action != 'edited'\n)?"
            r"        run: python3 -m unittest discover -s tools/tests -p test_registry_normalize.py -v$",
            workflow, re.MULTILINE)
        self.assertIsNotNone(step, "CI must explicitly run registry normalization regressions")
        self.assertLess(step.start(), workflow.index("python3 -m pip install"))
        self.assertLess(step.start(), workflow.index("run: cargo build"))


if __name__ == "__main__":
    unittest.main()
