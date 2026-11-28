"""Registry integrity: live snapshot, disposable regressions and the real CI command."""
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_check as rc
from registry_normalize import HISTORICAL_TABLE

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/registry"


class RegistryCheck(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.reg = self.root / "data/registry"
        shutil.copytree(REG, self.reg)
        vocab = self.root / "packages/schemas/vocabulary.json"
        vocab.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "packages/schemas/vocabulary.json", vocab)

    def rows(self, name):
        with (self.reg / name).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def write(self, name, rows):
        with (self.reg / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def change(self, name, key, value, **changes):
        rows = self.rows(name)
        row = next(r for r in rows if r[key] == value)
        row.update(changes)
        self.write(name, rows)

    def assertFinding(self, expected):
        problems = rc.check(self.root)
        self.assertTrue(any(expected in p for p in problems), problems)

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.reg.glob("*.csv")}

    def test_repository_passes_without_writing_and_historical_scope_is_independent_of_membership(self):
        before = self.snapshot()
        self.assertEqual(rc.check(self.root), [])
        self.assertEqual(self.snapshot(), before)
        historical = self.rows(HISTORICAL_TABLE)
        self.assertNotIn("status", historical[0])
        self.assertEqual(Counter(r["entity_evidence"] for r in historical),
                         Counter(two_or_more_sources=2, one_source=47))
        self.assertTrue(all(r["in_current_assoc_list"] == "false" for r in historical))
        self.assertEqual(Counter(r["historical_product_scope"] for r in historical),
                         Counter(in_scope=6, review_required=37, out_of_scope=6))
        for field in ("disclosure_status", "product_list_status"):
            self.assertEqual(Counter(r[field] for r in historical), Counter(unqueried=49))

        expected_successors = {
            "hist-nonlife-mg": "nonlife-yebyeol", "hist-nonlife-carrot": "nonlife-hanwha",
            "dart-9027ec66": "life-miraeasset", "dart-d8d5621b": "life-shinhan",
            "dart-a3a75abb": "life-kb", "dart-6da11385": "nonlife-hanwha",
        }
        self.assertEqual({r["insurer_id"]: r["successor_insurer_id"] for r in historical
                          if r["historical_product_scope"] == "in_scope"}, expected_successors)
        self.assertTrue(all((r["historical_product_scope"] == "out_of_scope") ==
                            r["insurer_id"].startswith("kidi-public-") for r in historical))

    def test_historical_scope_rejects_invalid_disposition_reasons_and_progress(self):
        name = HISTORICAL_TABLE
        original = self.rows(name)
        cases = (
            ("hist-nonlife-mg", {"historical_product_scope": "excluded"}, "invalid historical_product_scope"),
            ("hist-nonlife-mg", {"in_current_assoc_list": "true"}, "requires in_current_assoc_list=false"),
            ("hist-nonlife-mg", {"historical_scope_reason": " "}, "missing historical_scope_reason"),
            ("hist-nonlife-mg", {"disclosure_gap_reason": ""}, "missing disclosure_gap_reason"),
            ("hist-nonlife-mg", {"product_list_reason": ""}, "missing product_list_reason"),
            ("hist-nonlife-carrot", {"product_list_reason_codes": ""}, "product_list_reason_codes must be"),
            ("kidi-public-5e3f7f", {"product_list_reason_codes": "awaiting_T-DT-04"}, "historical_out_of_scope"),
            ("dart-df7015d9", {"product_list_status": "archived"},
             "'review_required' requires product_list_status='unqueried'"),
        )
        for insurer, changes, expected in cases:
            with self.subTest(changes=changes):
                self.write(name, original)
                self.change(name, "insurer_id", insurer, **changes)
                self.assertFinding(expected)

    def test_historical_successor_requires_distinct_registered_insurer_and_evidence(self):
        name = HISTORICAL_TABLE
        original = self.rows(name)
        for successor in ("", "hist-nonlife-mg", "missing-insurer", "public-epost"):
            with self.subTest(successor=successor):
                self.write(name, original)
                self.change(name, "insurer_id", "hist-nonlife-mg", successor_insurer_id=successor)
                self.assertFinding("invalid successor_insurer_id")
        for url in ("", "http://example.invalid/notice", "https://", "https://[invalid",
                    "https://example.invalid/url with spaces"):
            with self.subTest(url=url):
                self.write(name, original)
                self.change(name, "insurer_id", "hist-nonlife-carrot", successor_evidence_url=url)
                self.assertFinding("successor_evidence_url must be a public HTTPS source")

    def test_hyundai_note_describes_initial_js_shell_and_failed_tls_followup(self):
        row = next(r for r in self.rows("insurers.csv") if r["insurer_id"] == "nonlife-hyundai")
        self.assertEqual(row["home_access"], "tls_error")
        self.assertIn("200_js_shell -> tls_handshake_fail", row["home_access_detail"])
        for phrase in ("초기", "200_js_shell", "후속", "tls_handshake_fail", "공시실 URL 미확인"):
            self.assertIn(phrase, row["notes"])
        self.assertNotIn("홈페이지는 응답했으나 정적 HTML에서 상품공시 링크를 찾지 못함", row["notes"])
        attempts = [r for r in self.rows("access_log.csv") if r["purpose"].endswith(":nonlife-hyundai")]
        self.assertEqual([r["host_access"] for r in attempts], ["js_shell", "tls_error"])

    def test_each_original_dangling_id_is_rejected(self):
        cases = [
            ("access_log.csv", "purpose", "homepage:public-epost", "homepage:other-epost", ":84:"),
            ("access_log.csv", "purpose", "homepage:nonlife-mitsuisumitomo-kr",
             "homepage:nonlife-mitsuisumitomo", ":77:"),
            ("sources.csv", "source_id", "homepage_nonlife-mitsuisumitomo-kr",
             "homepage_nonlife-mitsuisumitomo", ":49:"),
        ]
        for name, key, good, bad, line in cases:
            with self.subTest(name=name, bad=bad):
                self.change(name, key, good, **{key: bad})
                self.assertFinding(f"{name}{line}")
                self.assertFinding("unknown insurer_id")
                self.change(name, key, bad, **{key: good})

    def test_all_entity_purpose_and_source_prefixes_validate_ids(self):
        for prefix in rc.PREFIXES:
            with self.subTest(prefix=prefix):
                rows = self.rows("access_log.csv")
                original = rows[0]["purpose"]
                rows[0]["purpose"] = f"{prefix}:missing"
                self.write("access_log.csv", rows)
                self.assertFinding("purpose references unknown insurer_id 'missing'")
                rows[0]["purpose"] = original
                self.write("access_log.csv", rows)
                rows = self.rows("sources.csv")
                original = rows[0]["source_id"]
                rows[0]["source_id"] = f"{prefix}_missing"
                self.write("sources.csv", rows)
                self.assertFinding("source_id references unknown insurer_id 'missing'")
                rows[0]["source_id"] = original
                self.write("sources.csv", rows)

    def test_listed_in_references_are_checked_in_all_entity_tables(self):
        for name in rc.ENTITY_TABLES:
            rows = self.rows(name)
            original = rows[0]["listed_in"]
            rows[0]["listed_in"] += ";absent_source"
            self.write(name, rows)
            self.assertFinding("listed_in references unknown source_id 'absent_source'")
            rows[0]["listed_in"] = original
            self.write(name, rows)

    def test_seed_and_artifact_purposes_are_not_dangling_entity_references(self):
        self.assertTrue(any(not r["listed_in"] and r["entity_evidence"] == "seed"
                            for r in self.rows("cooperatives_and_others.csv")))
        rows = self.rows("access_log.csv")
        for purpose in ("source:artifact.html", "probe:artifact.html", "meta:artifact.json",
                        "discover:artifact.jsp", "wikipedia_search (tertiary source attempt)"):
            rows[0]["purpose"] = purpose
            self.write("access_log.csv", rows)
            self.assertEqual(rc.check(self.root), [])

    def test_empty_untrimmed_and_duplicate_ids_fail_in_each_namespace(self):
        for name, field in (("insurers.csv", "insurer_id"), ("sources.csv", "source_id")):
            rows = self.rows(name)
            original = rows[1][field]
            for bad in ("", " " + original, rows[0][field]):
                with self.subTest(name=name, bad=bad):
                    rows[1][field] = bad
                    self.write(name, rows)
                    self.assertFinding(field)
            rows[1][field] = original
            self.write(name, rows)

    def test_entity_ids_cannot_collide_across_tables(self):
        self.change("cooperatives_and_others.csv", "insurer_id", "coop-suhyup", insurer_id="life-hanwha")
        self.assertFinding("duplicate insurer_id: 'life-hanwha'")

    def test_legacy_status_column_and_values_fail_without_rewriting(self):
        name = "excluded_or_historical.csv"
        original = (self.reg / name).read_bytes()
        for field, value in (("status", "verified_2_sources"), ("entity_evidence", "verified_2_sources")):
            with self.subTest(field=field):
                rows = self.rows(name)
                for row in rows:
                    row[field] = row.pop("entity_evidence") if field == "status" else value
                self.write(name, rows)
                before = self.snapshot()
                self.assertFinding("deprecated field `status`" if field == "status" else "expected entity_evidence code")
                self.assertEqual(self.snapshot(), before)
                (self.reg / name).write_bytes(original)

    def test_log_classification_cannot_disagree_with_raw_result(self):
        self.change("access_log.csv", "purpose", "homepage:life-aia", host_access="tls_error")
        self.assertFinding("host_access='tls_error' disagrees with raw access evidence '200'")

    def test_reachable_disclosures_with_response_hashes_cannot_claim_archival(self):
        name = "insurers.csv"
        rows = self.rows(name)
        sources = {r["source_id"]: r for r in self.rows("sources.csv")}
        mislabelled = []
        for line, row in enumerate(rows, start=2):
            if row["disclosure_access"] != "reachable":
                continue
            insurer_id = row["insurer_id"]
            source = sources[f"disclosure_{insurer_id}"]
            self.assertEqual(source["http_status"], "200")
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            row.update(disclosure_status="archived", disclosure_gap_reason="")
            mislabelled.append((line, insurer_id))
        self.assertEqual(len(mislabelled), 8)
        self.write(name, rows)

        before = self.snapshot()
        self.assertEqual(rc.check(self.root), [
            f"data/registry/{name}:{line}: disclosure_status='archived' is unsupported "
            f"in the access registry for {insurer_id!r}"
            for line, insurer_id in mislabelled
        ])
        self.assertEqual(self.snapshot(), before)

    def test_disclosure_archive_check_is_independent_of_product_list_status(self):
        name = "cooperatives_and_others.csv"
        self.change(name, "insurer_id", "coop-suhyup", product_list_status="archived")
        self.assertEqual(rc.check(self.root), [])
        self.change(name, "insurer_id", "coop-suhyup", disclosure_status="archived")
        self.assertFinding("disclosure_status='archived' is unsupported in the access registry for 'coop-suhyup'")

    def test_unknown_raw_evidence_fails_cleanly(self):
        self.change("access_log.csv", "purpose", "homepage:life-aia", result="mystery")
        self.assertFinding("unmapped raw access evidence 'mystery'")

    def test_home_and_disclosure_summaries_use_final_observation_even_if_rows_are_reordered(self):
        attempts = self.rows("access_log.csv")
        self.write("access_log.csv", list(reversed(attempts)))
        self.assertEqual(rc.check(self.root), [])
        for key, changes, expected in (
            ("nonlife-hyundai", dict(home_access="js_shell", home_access_detail="200_js_shell"), "home_access"),
            ("life-aia", dict(disclosure_access="tls_error", disclosure_access_detail="tls_handshake_fail"),
             "disclosure_access"),
        ):
            with self.subTest(key=key):
                self.change("insurers.csv", "insurer_id", key, **changes)
                self.assertFinding(f"{expected}={changes[expected]!r} disagrees with latest access_log")

    def test_raw_detail_cannot_contradict_final_state(self):
        self.change("insurers.csv", "insurer_id", "nonlife-hyundai", home_access_detail="200_js_shell -> 200")
        self.assertFinding("home_access='tls_error' disagrees with raw access evidence")

    def test_entity_sources_must_trace_to_url_timestamp_result_and_purpose(self):
        name = "sources.csv"
        original = (self.reg / name).read_bytes()
        for column, bad in (("url", "https://example.invalid/"), ("retrieved_at", "2026-10-09T00:00:00Z"),
                            ("http_status", "403"), ("source_id", "disclosure_nonlife-mitsuisumitomo-kr-extra")):
            with self.subTest(column=column):
                self.change(name, "source_id", "homepage_nonlife-mitsuisumitomo-kr", **{column: bad})
                self.assertFinding("no matching access_log observation")
                (self.reg / name).write_bytes(original)

    def test_supervisory_coverage_rejects_missing_row_or_one_sided_match(self):
        snapshot = self.rows(rc.CROSSCHECK)
        for insurer in ("life-hanwha", "nonlife-mybrown"):
            with self.subTest(insurer=insurer):
                self.write(rc.CROSSCHECK, [r for r in snapshot if r["registry_id"] != insurer])
                self.assertFinding(f"no supervisory cross-check for {insurer!r}")
        for column, ref in (("fisis_id", "fisis_source_id"), ("fine_id", "fine_source_ids")):
            with self.subTest(column=column):
                self.write(rc.CROSSCHECK, snapshot)
                self.change(rc.CROSSCHECK, "registry_id", "life-hanwha", **{column: "", ref: ""})
                self.assertFinding("insurer 'life-hanwha' requires both FISIS and Fine IDs")

    def test_supervisory_rows_reject_broken_registry_joins_and_ids(self):
        snapshot = self.rows(rc.CROSSCHECK)
        cases = (
            (dict(registry_id="no-such-insurer"), "invalid registry reference"),
            (dict(registry_name="다른 기관"), "invalid registry reference"),
            (dict(registry_id="life-kyobo", registry_name="교보생명보험"), "duplicate registry_id"),
            (dict(comparison="excluded"), "invalid comparison"),
            (dict(category="unknown"), "unknown supervisory category"),
            (dict(fisis_id="0010619"), "duplicate fisis_id"),
            (dict(fine_id=" 18942"), "invalid or duplicate fine_id"),
        )
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.write(rc.CROSSCHECK, snapshot)
                self.change(rc.CROSSCHECK, "registry_id", "life-hanwha", **changes)
                self.assertFinding(expected)

    def test_supervisory_row_requires_the_right_lists_and_all_fine_pages(self):
        snapshot = self.rows(rc.CROSSCHECK)
        cases = (
            ("life-hanwha", "fisis_source_id", ""),
            ("life-hanwha", "fisis_source_id", "fisis_20261110_nonlife_list"),
            ("life-hanwha", "fine_source_ids", "fine_20261110_life_domestic_p1"),
            ("life-hanwha", "fine_source_ids", "fine_20261110_life_foreign_p1"),
            ("dart-df7015d9", "fisis_source_id", "fisis_20261110_nonlife_list"),
        )
        for insurer, column, value in cases:
            with self.subTest(insurer=insurer, column=column, value=value):
                self.write(rc.CROSSCHECK, snapshot)
                self.change(rc.CROSSCHECK, "registry_id", insurer, **{column: value})
                self.assertFinding(f"{column} disagrees with")

    def test_supervisory_provenance_requires_successful_sources_and_matching_requests(self):
        source_id = "fisis_20261110_life_list"
        sources = self.rows("sources.csv")
        requests = self.rows("access_log.csv")
        self.write("sources.csv", [r for r in sources if r["source_id"] != source_id])
        self.assertFinding(f"missing supervisory list source {source_id!r}")
        for column, value in (("url", "https://dart.fss.or.kr/"), ("sha256", "bad"),
                              ("http_status", "200_service_outage_notice"),
                              ("retrieved_at", "2026-10-09T04:23:09Z")):
            with self.subTest(source_column=column):
                self.write("sources.csv", sources)
                self.change("sources.csv", "source_id", source_id, **{column: value})
                self.assertFinding(f"invalid supervisory list source {source_id!r}")
        self.write("sources.csv", sources)
        for column, value in (("detail", "POST partDiv=I&baseMonth=202606"), ("http_code", "503"),
                              ("curl_exit", "56"), ("final_url", "https://fisis.fss.or.kr/"),
                              ("attempted_at", "2026-11-10T11:09:16Z"), ("result", "200_service_outage_notice")):
            with self.subTest(request_column=column):
                self.write("access_log.csv", requests)
                self.change("access_log.csv", "purpose", f"source:{source_id}.json", **{column: value})
                self.assertFinding(f"no matching successful access_log observation for {source_id!r}")

    def test_missing_files_columns_and_malformed_csv_fail_with_locations(self):
        name = "sources.csv"
        path = self.reg / name
        original = path.read_bytes()
        for contents, expected in (
            (None, "cannot read CSV"), (b"", "missing or duplicate CSV header"),
            (b"source_id,source_id\n", "missing or duplicate CSV header"),
            (b"source_id\n", "missing required columns"),
            (b"source_id,url,retrieved_at,http_status,sha256\na,b\n", ":2: expected 5 cells, got 2"),
            (b'source_id,url,retrieved_at,http_status,sha256\na,"unterminated\n', "invalid CSV"),
        ):
            with self.subTest(contents=contents):
                if contents is None:
                    path.unlink()
                else:
                    path.write_bytes(contents)
                self.assertFinding(expected)
                path.write_bytes(original)

    def test_multiline_cells_keep_physical_line_diagnostics(self):
        rows = self.rows("insurers.csv")
        rows[0]["notes"] += "\nextra evidence"
        rows[1]["listed_in"] = "absent_source"
        self.write("insurers.csv", rows)
        self.assertFinding("insurers.csv:4: listed_in references unknown source_id")

    def test_declared_ci_command_passes_and_rejects_original_findings_read_only(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        match = re.search(r"^      - name: Registry CSV references and access evidence\n"
                          r"        run: (.+)$", workflow, re.MULTILINE)
        self.assertIsNotNone(match)
        command = match[1]
        self.assertEqual(command, "python3 -I tools/registry_check.py")
        self.assertLess(match.start(), workflow.index("python3 -m pip install"))
        self.assertLess(match.start(), workflow.index("run: cargo build"))
        scripts = self.root / "tools"
        scripts.mkdir()
        for name in ("registry_check.py", "registry_normalize.py", "vocab_check.py"):
            shutil.copy2(ROOT / "tools" / name, scripts / name)
        baseline = self.snapshot()
        aia_row = next(row for row in baseline["insurers.csv"].splitlines() if row.startswith(b"life-aia,"))
        cases = (
            (None, None, None, "registry check passed"),
            ("insurers.csv", aia_row, aia_row.replace(b",unqueried,", b",archived,", 1),
             "disclosure_status='archived' is unsupported in the access registry for 'life-aia'"),
            ("access_log.csv", b"homepage:public-epost,", b"homepage:other-epost,",
             "purpose references unknown insurer_id 'other-epost'"),
            ("access_log.csv", b"homepage:nonlife-mitsuisumitomo-kr,", b"homepage:nonlife-mitsuisumitomo,",
             "purpose references unknown insurer_id 'nonlife-mitsuisumitomo'"),
            ("sources.csv", b"homepage_nonlife-mitsuisumitomo-kr,", b"homepage_nonlife-mitsuisumitomo,",
             "source_id references unknown insurer_id 'nonlife-mitsuisumitomo'"),
            ("excluded_or_historical.csv", b"entity_evidence,", b"status,", "deprecated field `status`"),
            ("excluded_or_historical.csv", b",historical_product_scope,", b",unknown_scope,",
             "missing required columns: historical_product_scope"),
            (rc.CROSSCHECK, b",life-hanwha,", b",unmatched-hanwha,",
             "no supervisory cross-check for 'life-hanwha'"),
        )
        for name, old, new, expected in cases:
            with self.subTest(name=name, expected=expected):
                for filename, contents in baseline.items():
                    (self.reg / filename).write_bytes(contents)
                if name:
                    self.assertEqual(baseline[name].count(old), 1)
                    (self.reg / name).write_bytes(baseline[name].replace(old, new))
                before = self.snapshot()
                result = subprocess.run(["bash", "-e", "-c", command], cwd=self.root,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, int(name is not None), result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertIn(expected, result.stdout)
                self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
