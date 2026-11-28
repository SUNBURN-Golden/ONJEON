"""Registry integrity: live snapshot, disposable regressions and the real CI command."""
import csv
import hashlib
import json
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
        self.manifest = self.root / rc.SUPERVISORY_REQUESTS
        self.manifest.parent.mkdir(parents=True)
        shutil.copy2(ROOT / rc.SUPERVISORY_REQUESTS, self.manifest)

    def rows(self, name, delimiter=","):
        with (self.reg / name).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f, delimiter=delimiter))

    def write(self, name, rows, delimiter=","):
        with (self.reg / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=delimiter)
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

    def copy_scripts(self):
        scripts = self.root / "tools"
        scripts.mkdir(exist_ok=True)
        for name in ("registry_check.py", "registry_normalize.py", "vocab_check.py"):
            shutil.copy2(ROOT / "tools" / name, scripts / name)

    def test_repository_passes_without_writing_and_historical_rows_stay_excluded(self):
        before = self.snapshot()
        self.assertEqual(rc.check(self.root), [])
        self.assertEqual(self.snapshot(), before)
        excluded = self.rows("excluded_or_historical.csv")
        self.assertNotIn("status", excluded[0])
        self.assertNotIn("product_list_status", excluded[0])
        self.assertEqual(Counter(r["entity_evidence"] for r in excluded),
                         Counter(two_or_more_sources=2, one_source=47))
        self.assertTrue(all(r["in_current_assoc_list"] == "false" for r in excluded))

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

    def test_listed_in_cannot_be_cleared_for_a_non_seed(self):
        self.change("insurers.csv", "insurer_id", "life-hanwha", listed_in="")
        self.assertFinding("insurers.csv:2: listed_in is empty for non-seed 'life-hanwha'")

    def test_snapshot_row_counts_reject_a_missing_record_in_each_table_and_survey(self):
        for name, column, date, expected in (
            ("insurers.csv", None, None, 53),
            ("cooperatives_and_others.csv", None, None, 16),
            ("excluded_or_historical.csv", None, None, 49),
            ("sources.csv", "retrieved_at", "2026-10-09", 66),
            ("access_log.csv", "attempted_at", "2026-10-09", 98),
            ("sources.csv", "retrieved_at", "2026-11-10", 9),
            ("access_log.csv", "attempted_at", "2026-11-10", 14),
        ):
            with self.subTest(name=name, date=date):
                original = (self.reg / name).read_bytes()
                rows = self.rows(name)
                i = next(i for i, row in enumerate(rows) if date is None or row[column].startswith(date))
                del rows[i]
                self.write(name, rows)
                date_label = f"{date!r}: " if date else ""
                self.assertFinding(f"{name}:1: {date_label}expected {expected} data rows, got {expected - 1}")
                (self.reg / name).write_bytes(original)

    def test_snapshot_count_rejects_date_drift_even_with_the_same_total(self):
        self.change("access_log.csv", "purpose", "source:klia_home.html", attempted_at="2026-10-10T04:21:35Z")
        self.assertFinding("'2026-10-09': expected 98 data rows, got 97")
        self.assertFinding("'2026-10-10': expected 0 data rows, got 1")

    def test_access_digest_cli_maps_each_reachable_200_to_its_exact_evidence(self):
        self.copy_scripts()
        command = [sys.executable, "-I", "tools/registry_check.py", "--access-digests"]
        before = self.snapshot()
        manifest_before = self.manifest.read_bytes()
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        report = list(csv.DictReader(result.stdout.splitlines()))
        access = {str(i): r for i, r in enumerate(self.rows("access_log.csv"), 2)
                  if r["http_code"] == "200" and r["host_access"] == "reachable"}
        sources = {r["source_id"]: r for r in self.rows("sources.csv")}
        requests = {str(i): r for i, r in enumerate(self.rows(self.manifest, delimiter="\t"), 2)}
        self.assertEqual([r["line"] for r in report], list(access))
        self.assertEqual(Counter(r["digest_kind"] for r in report),
                         Counter(response_body=63, access_record_only=5))
        self.assertEqual([r["line"] for r in report if r["digest_kind"] == "access_record_only"],
                         ["10", "14", "15", "20", "27"])
        self.assertEqual(sum(r["evidence"].startswith(rc.SUPERVISORY_REQUESTS) for r in report), 14)
        for record in report:
            with self.subTest(line=record["line"], purpose=record["purpose"]):
                row = access[record["line"]]
                for field in ("attempted_at", "purpose", "url", "final_url"):
                    self.assertEqual(record[field], row[field])
                evidence = record["evidence"]
                self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")
                if record["digest_kind"] == "access_record_only":
                    self.assertEqual(evidence, f"data/registry/access_log.csv:{record['line']}")
                    payload = json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8")
                    self.assertEqual(record["sha256"], hashlib.sha256(payload).hexdigest())
                elif evidence.startswith("data/registry/sources.csv#"):
                    source = sources[evidence.split("#", 1)[1]]
                    self.assertEqual((row["attempted_at"], row["url"]), (source["retrieved_at"], source["url"]))
                    self.assertEqual(source["sha256"], record["sha256"])
                else:
                    request = requests[evidence.rsplit(":", 1)[1]]
                    self.assertEqual((row["attempted_at"], row["url"]), (request["started_at"], request["url"]))
                    self.assertEqual(request["sha256"], record["sha256"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manifest.read_bytes(), manifest_before)

        self.change("sources.csv", "source_id", "klia_home", retrieved_at="2026-10-09T04:21:36Z")
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("access_log.csv:2: no matching response SHA-256", result.stderr)

    def test_access_digest_check_rejects_invalid_source_hashes_and_ambiguous_observations(self):
        original = (self.reg / "sources.csv").read_bytes()
        for bad in ("", "a" * 63, "g" * 64):
            with self.subTest(hash=bad):
                self.change("sources.csv", "source_id", "klia_member", sha256=bad)
                self.assertFinding("sources.csv:2: invalid SHA-256 for source_id 'klia_member'")
                (self.reg / "sources.csv").write_bytes(original)

        sources = self.rows("sources.csv")
        source = dict(sources[0], source_id="conflicting_klia_member", sha256="a" * 64)
        self.write("sources.csv", [source, *sources[:-1]])
        self.assertFinding("duplicate HTTP 200 source observation")
        (self.reg / "sources.csv").write_bytes(original)
        attempts = self.rows("access_log.csv")
        attempts[1] = dict(attempts[0])
        self.write("access_log.csv", attempts)
        self.assertFinding("access_log.csv:3: duplicate access observation")

    def test_access_record_digest_applies_only_to_the_original_probes(self):
        self.change("access_log.csv", "purpose", "source:dart_dsae001.html",
                    detail="changed historical request evidence")
        self.assertFinding("access_log.csv:27: no matching response SHA-256 for 'source:dart_dsae001.html'")

    def test_success_cannot_be_hidden_by_changing_http_code_or_curl_result(self):
        original = (self.reg / "access_log.csv").read_bytes()
        for changes in (dict(http_code="302"), dict(curl_exit="28"), dict(result="302")):
            with self.subTest(changes=changes):
                self.change("access_log.csv", "purpose", "source:klia_home.html", **changes)
                self.assertFinding("access_log.csv:2: inconsistent reachable HTTP 200 observation")
                (self.reg / "access_log.csv").write_bytes(original)

    def test_supervisory_digests_require_the_original_request_and_agreement_with_sources(self):
        manifest = self.rows(self.manifest, delimiter="\t")
        self.write(self.manifest, manifest[1:], delimiter="\t")
        self.assertFinding("no matching supervisory request for 'probe:fisis_home.html'")
        for index, changes, expected in (
            (0, dict(final_url="https://fisis.fss.or.kr/"), "no matching supervisory request"),
            (0, dict(sha256="g" * 64), "invalid response SHA-256"),
            (2, dict(method="GET"), "no matching supervisory request"),
            (4, dict(post_data="partDiv=I&baseMonth=202606"), "no matching supervisory request"),
            (4, dict(sha256="a" * 64), "conflicting response SHA-256"),
            (1, manifest[0], "duplicate request"),
        ):
            with self.subTest(index=index, changes=changes):
                modified = list(manifest)
                modified[index] = dict(manifest[index], **changes)
                self.write(self.manifest, modified, delimiter="\t")
                self.assertFinding(expected)
        self.manifest.unlink()
        self.assertFinding(f"{rc.SUPERVISORY_REQUESTS}:1: cannot read TSV")

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

    def test_scope_columns_are_required_in_both_denominator_inputs(self):
        for name in ("insurers.csv", "cooperatives_and_others.csv"):
            original = self.rows(name)
            for column in ("in_denominator", "scope_adr"):
                with self.subTest(name=name, column=column):
                    self.write(name, [{k: v for k, v in row.items() if k != column} for row in original])
                    self.assertFinding(f"{name}:1: missing required columns: {column}")
            self.write(name, original)

    def test_scope_values_must_follow_adr_0018(self):
        cases = (
            ("insurers.csv", "life-hanwha", "in_denominator", "false"),
            ("cooperatives_and_others.csv", "public-epost", "in_denominator", "false"),
            ("cooperatives_and_others.csv", "public-epost", "in_denominator", "True"),
            ("cooperatives_and_others.csv", "public-epost", "in_denominator", ""),
            ("cooperatives_and_others.csv", "coop-suhyup", "in_denominator", "true"),
            ("cooperatives_and_others.csv", "seed-coop-nh", "in_denominator", "true"),
            ("cooperatives_and_others.csv", "public-ksure", "in_denominator", "true"),
            ("cooperatives_and_others.csv", "public-epost", "scope_adr", ""),
            ("insurers.csv", "life-hanwha", "scope_adr", "ADR-0004"),
        )
        for name, entity, column, bad in cases:
            with self.subTest(entity=entity, column=column, value=bad):
                original = (self.reg / name).read_bytes()
                self.change(name, "insurer_id", entity, **{column: bad})
                self.assertFinding(f"{column}={bad!r} for {entity!r}")
                (self.reg / name).write_bytes(original)

    def test_epost_is_required_in_the_separate_institution_table(self):
        name = "cooperatives_and_others.csv"
        self.write(name, [row for row in self.rows(name) if row["insurer_id"] != "public-epost"])
        self.assertFinding(f"{name}:1: ADR-0018 requires 'public-epost'")

    def test_denominator_cli_selects_all_53_insurers_and_epost_and_rejects_drift(self):
        self.copy_scripts()
        command = [sys.executable, "-I", "tools/registry_check.py", "--denominator"]
        snapshot = self.snapshot()
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        insurers = [r["insurer_id"] for r in self.rows("insurers.csv")]
        self.assertEqual(len(insurers), 53)
        self.assertEqual(len(set(insurers)), 53)
        self.assertNotIn("public-epost", insurers)
        self.assertEqual(result.stdout.splitlines(), insurers + ["public-epost"])
        self.assertEqual(self.snapshot(), snapshot)

        self.change("cooperatives_and_others.csv", "insurer_id", "public-epost", in_denominator="false")
        snapshot = self.snapshot()
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("in_denominator='false' for 'public-epost'", result.stderr)
        self.assertEqual(self.snapshot(), snapshot)

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
            (b"source_id,url,retrieved_at,http_status,sha256\na,b,c,d,e,f\n", ":2: expected 5 cells, got 6"),
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
        match = re.search(r"^      - name: Registry CSV integrity and access digests\n"
                          r"        run: (.+)$", workflow, re.MULTILINE)
        self.assertIsNotNone(match)
        command = match[1]
        self.assertEqual(command, "python3 -I tools/registry_check.py")
        self.assertLess(match.start(), workflow.index("python3 -m pip install"))
        self.assertLess(match.start(), workflow.index("run: cargo build"))
        self.copy_scripts()
        baseline = self.snapshot()
        aia_row = next(row for row in baseline["insurers.csv"].splitlines() if row.startswith(b"life-aia,"))
        hanwha_row = baseline["insurers.csv"].splitlines()[1]
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
            ("access_log.csv", b"source:klia_home.html,200,0,200,,,reachable", b"source:klia_home.html,200,0,200,,,reachable,",
             "expected 10 cells, got 11"),
            ("sources.csv", b"\nklia_pub_mngtdis,", b"\nklia_member,", "duplicate source_id"),
            ("insurers.csv", aia_row + b"\r\n", b"", "expected 53 data rows, got 52"),
            ("insurers.csv", hanwha_row, hanwha_row.replace(b"klia_member;", b"absent_source;", 1),
             "listed_in references unknown source_id 'absent_source'"),
            ("insurers.csv", aia_row, aia_row.replace(b",unqueried,", b",invented_code,", 1),
             "expected acquisition_status code"),
            ("sources.csv", b"2026-10-09T04:21:35Z,dc950", b"2026-10-09T04:21:36Z,dc950",
             "no matching response SHA-256"),
            ("excluded_or_historical.csv", b"entity_evidence,", b"status,", "deprecated field `status`"),
            ("cooperatives_and_others.csv", b",in_denominator,scope_adr\r\n", b",scope_adr\r\n",
             "missing required columns: in_denominator"),
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
