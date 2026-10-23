import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docproc", ROOT / "docproc.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
sys.path.insert(0, str(ROOT / "tests"))
import shared_contract as sc  # noqa: E402

FIXTURE_DIGEST = hashlib.sha256(b"fixture_only").hexdigest()
LEGACY_LABELS = ("보통약관", "특약 약관", "별표", "요약서", "공시 목록", "안내 쪽")


def shared_schema(test):
    """packages/schemas regexes and doc_role enum; absent files skip on the host and fail in the pinned suite."""
    try:
        return sc.load_schema()
    except OSError:
        if os.environ.get("DOCPROC_REQUIRE_PINNED") == "1":
            raise AssertionError("Shared schema files required: set DOCPROC_SCHEMA_DIR")
        test.skipTest("packages/schemas/json unavailable; set DOCPROC_SCHEMA_DIR")


def synthetic_pdf(path, gap=1):
    bodies = [b"<< /Type /Catalog /Pages 2 0 R >>",
              b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>",
              b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
              b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for page in (1, 2):
        if page == 2:
            bodies.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>")
        stream = f"BT /F1 12 Tf 72 720 Td (Article {page} \\(synthetic fixture_only\\)) Tj 0 -24 Td (No{' ' * gap}automatic approval.) Tj ET".encode()
        bodies.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for i, body in enumerate(bodies, 1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    pdf += f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(pdf)


class DocprocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        version = d.tool_version()
        if not version.startswith("24.02."):
            if os.environ.get("DOCPROC_REQUIRE_PINNED") == "1":
                raise AssertionError("Native Poppler 24.02 required")
            raise unittest.SkipTest("Extraction suite requires native Poppler 24.02; run test_sandbox.sh")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf = Path(self.tmp.name) / "fixture_only.pdf"
        synthetic_pdf(self.pdf)
        self.specs = [{"page_from": 1, "page_to": 2, "doc_role": "terms", "seg_rule_ver": "explicit-0.1"}]

    def extract(self, **kwargs):
        return d.extract(self.pdf, self.specs, origin="fixture", **kwargs)

    def test_native_poppler_identity(self):
        output = self.extract()
        self.assertTrue(d.tool_version().startswith("24.02."))
        self.assertTrue(all(c["extractor"]["version"] == d.tool_version() for c in output["clauses"]))

    def test_exact_quote_coordinates_and_tamper(self):
        output = self.extract()
        self.assertTrue(d.verify(self.pdf, output))
        for key, value in (("quote", "wrong"), ("bbox", [0, 0, 1, 1]), ("page", 2), ("segment_id", "wrong")):
            bad = copy.deepcopy(output)
            bad["clauses"][0][key] = value
            with self.assertRaises(ValueError):
                d.verify(self.pdf, bad)
        self.assertEqual(output["clauses"][0]["quote"], "Article 1 (synthetic fixture_only)")
        self.assertGreater(output["clauses"][0]["bbox"][0], 0)

    def test_quote_preserves_region_spacing_and_rejects_systematic_error(self):
        synthetic_pdf(self.pdf, gap=11)
        output = self.extract()
        # Wide spacing becomes separate bbox lines. Independently crop their combined region.
        clause, following = output["clauses"][1:3]
        clause["bbox"][2] = following["bbox"][2]
        clause["words"] += following["words"]
        clause["quote"] = d.check_region(self.pdf, clause["page"], clause)
        self.assertIn("   ", clause["quote"])
        self.assertEqual(clause["quote"], d.region_text(self.pdf, clause["page"], clause["bbox"]))
        bad = copy.deepcopy(output)
        bad["clauses"][1]["quote"] = " ".join(clause["quote"].split())
        # Even if re-extraction repeats the same reconstruction bug, the crop must reject it.
        with patch.object(d, "extract", return_value=bad):
            with self.assertRaises(ValueError):
                d.verify(self.pdf, bad)

    def test_wrong_word_reconstruction_rejected_by_crop(self):
        clause = self.extract()["clauses"][0]
        clause["words"][0]["text"] = "incorrect"
        with self.assertRaises(ValueError):
            d.check_region(self.pdf, clause["page"], clause)

    def test_fingerprint_from_native_layout(self):
        output = self.extract()
        texts = [subprocess.check_output(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(self.pdf), "-"]).decode()
                 for page in (1, 2)]
        self.assertEqual(output["segments"][0]["fingerprint"], d.fingerprint(texts, d.tool_version()))

    def test_clause_id_reextract_new(self):
        first = self.extract()
        second = self.extract(edition="docproc-text@1.2")
        self.assertEqual(first["segments"], second["segments"])
        self.assertNotEqual(first["clauses"][0]["id"], second["clauses"][0]["id"])
        for c in first["clauses"]:
            self.assertRegex(c["id"], r"^clause:seg:[a-f0-9]{12}:p1-2:terms:explicit-0.1/[^/]+#p[12]:docproc-text@1.1$")
        self.assertEqual(len({c["id"] for c in first["clauses"]}), len(first["clauses"]))

    def test_segment_and_uncertainty(self):
        output = self.extract()
        segment = output["segments"][0]
        self.assertEqual((segment["page_from"], segment["page_to"]), (1, 2))
        self.assertEqual(segment["boundary"], "unconfirmed")
        self.assertEqual(segment["fingerprint"]["rule"], "fp-0.1")
        self.assertEqual([c["clause_path_basis"] for c in output["clauses"]], ["printed", "inferred"] * 2)
        self.assertTrue(all(c["review_status"] == "hold" and c["origin"] == "fixture" for c in output["clauses"]))

    def test_invalid_segments(self):
        for update in ({"page_from": 0}, {"page_to": 3}, {"doc_role": "unknown"}, {"doc_role": "보통약관"}, {"doc_role": "official_terms"},
                       {"seg_rule_ver": "bad/version"}, {"boundary": "accepted"}):
            self.specs[0].update(update)
            with self.assertRaises(ValueError):
                self.extract()
            self.specs = [{"page_from": 1, "page_to": 2, "doc_role": "terms", "seg_rule_ver": "explicit-0.1"}]
        self.specs *= 2
        with self.assertRaises(ValueError):
            self.extract()

    def test_fail_closed_on_wrong_poppler_and_invalid_pdf(self):
        with patch.object(d, "tool_version", return_value="25.03.0"):
            with self.assertRaises(ValueError):
                d.extract(self.pdf, self.specs)
        self.pdf.write_bytes(b"not a PDF")
        with self.assertRaises(ValueError):
            self.extract()

    def test_source_change_rejected(self):
        output = self.extract()
        self.pdf.write_bytes(self.pdf.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            d.verify(self.pdf, output)

    def test_cli_rejects_without_leaking_content(self):
        result = subprocess.run(["python3", str(ROOT / "docproc.py"), str(self.pdf), "--segments", str(self.pdf)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b"synthetic", result.stderr)

    def test_textless_page_needs_ocr(self):
        with patch.object(d, "page_lines", return_value=[]):
            with self.assertRaises(ValueError):
                self.extract()

    def test_extracted_ids_and_roles_pass_shared_contract(self):
        schema = shared_schema(self)
        output = self.extract()
        self.assertEqual(sc.check_output(output, schema), (1, 4))
        self.assertEqual(output["segments"][0]["doc_role"], "terms")
        for tamper in ({"id": output["segments"][0]["id"].replace(":terms:", ":보통약관:")},
                       {"doc_role": "보통약관"}, {"doc_role": "official_terms"}):
            bad = copy.deepcopy(output)
            bad["segments"][0].update(tamper)
            with self.assertRaises(ValueError):
                sc.check_output(bad, schema)

    def test_multiple_segments_and_determinism(self):
        self.specs = [{"page_from": page, "page_to": page, "doc_role": role,
                       "seg_rule_ver": "explicit-0.1", "boundary": "confirmed"}
                      for page, role in ((1, "terms"), (2, "annex"))]
        output = self.extract()
        self.assertEqual(output, self.extract())
        self.assertEqual(len(output["segments"]), 2)
        self.assertNotEqual(output["segments"][0]["fingerprint"], output["segments"][1]["fingerprint"])


class PureTests(unittest.TestCase):
    def test_fingerprint_nfc_whitespace_preserves_semantics(self):
        fp = d.fingerprint(["e\u0301 \n", "10 이상 아님"], "24.02.0")
        self.assertEqual(fp, {"rule": "fp-0.1", "sha256": hashlib.sha256("é10이상아님".encode()).hexdigest()})
        for text in ("é11이상아님", "é10초과아님", "é10이상"):
            self.assertNotEqual(fp, d.fingerprint([text], "24.02.0"))
        with self.assertRaises(ValueError):
            d.fingerprint(["text"], "25.03.0")

    def test_printed_heading_shape_and_inserted_articles(self):
        for quote, path, slug in (("제3조의2(합성 시험)", "제3조의2", "article-3-2"),
                                  ("제 3 조 의 12 (합성 시험)", "제 3 조 의 12", "article-3-12"),
                                  ("제3조", "제3조", "article-3"),
                                  ("Article 2 (fixture_only)", "Article 2", "article-2")):
            self.assertEqual(d.printed_path(quote), (path, slug))
        for quote in ("제5조에 따라 합성 시험", "제3조의2에 따라", "Article 2 applies to fixture_only", "제3조의", "제3조의2항"):
            self.assertIsNone(d.printed_path(quote))


class SharedContractTests(unittest.TestCase):
    """docproc ids and roles against packages/schemas (SegmentRef, ClauseRef, EvidenceRef, doc_role enum)."""

    def setUp(self):
        self.schema = shared_schema(self)

    def test_roles_are_vocabulary_doc_role_codes(self):
        self.assertEqual(len(d.ROLES), 6)
        self.assertEqual(len(set(d.ROLES)), 6)
        self.assertLessEqual(set(d.ROLES), set(self.schema["doc_role"]))
        for role in d.ROLES:
            self.assertRegex(role, r"^[a-z][a-z0-9_]*$")

    def test_specs_accept_codes_and_reject_labels_and_aliases(self):
        for role in d.ROLES:
            normalized = d.validate_specs([{"page_from": 1, "page_to": 2, "doc_role": role, "seg_rule_ver": "explicit-0.1"}])
            self.assertEqual(normalized, [{"page_from": 1, "page_to": 2, "doc_role": role,
                                           "seg_rule_ver": "explicit-0.1", "boundary": "unconfirmed"}])
        for role in (*LEGACY_LABELS, "official_terms", "price_example", "Terms", "terms ", "", None, ["terms"]):
            with self.assertRaises(ValueError, msg=repr(role)):
                d.validate_specs([{"page_from": 1, "page_to": 2, "doc_role": role, "seg_rule_ver": "explicit-0.1"}])
        for specs in (["terms"], [], {}, [{"page_from": 1, "page_to": 2, "doc_role": "terms", "seg_rule_ver": 1}]):
            with self.assertRaises(ValueError):
                d.validate_specs(specs)

    def test_every_role_id_matches_shared_grammar(self):
        for role in d.ROLES:
            sid = d.segment_id(FIXTURE_DIGEST, 3, 5, role, "explicit-0.1")
            self.assertTrue(self.schema["SegmentRef"].fullmatch(sid), sid)
            self.assertTrue(self.schema["EvidenceRef"].fullmatch(sid), sid)
            for slug, page in (("article-3-2-line-7", 4), ("line-1", 3)):
                cid = d.clause_id(sid, slug, page, d.EDITION)
                self.assertTrue(self.schema["ClauseRef"].fullmatch(cid), cid)
                self.assertTrue(self.schema["EvidenceRef"].fullmatch(cid), cid)
                self.assertIsNone(self.schema["SegmentRef"].fullmatch(cid))
        for label in LEGACY_LABELS:
            legacy = d.segment_id(FIXTURE_DIGEST, 1, 2, label, "explicit-0.1")
            self.assertIsNone(self.schema["SegmentRef"].fullmatch(legacy), legacy)
            self.assertIsNone(self.schema["ClauseRef"].fullmatch(d.clause_id(legacy, "line-1", 1, d.EDITION)))

    def test_check_output_rejects_ids_that_do_not_restate_fields(self):
        sid = d.segment_id(FIXTURE_DIGEST, 1, 2, "terms", "explicit-0.1")
        output = {"raw_sha256": FIXTURE_DIGEST,
                  "segments": [{"id": sid, "page_from": 1, "page_to": 2, "doc_role": "terms", "seg_rule_ver": "explicit-0.1"}],
                  "clauses": [{"id": d.clause_id(sid, "line-1", 2, d.EDITION), "segment_id": sid,
                               "page": 2, "extraction_edition": d.EDITION}]}
        self.assertEqual(sc.check_output(output, self.schema), (1, 1))
        for where, key, value in (("segments", "doc_role", "annex"), ("segments", "page_to", 3),
                                  ("clauses", "page", 1), ("clauses", "extraction_edition", "docproc-text@1.2"),
                                  ("clauses", "segment_id", sid + "0")):
            bad = copy.deepcopy(output)
            bad[where][0][key] = value
            with self.assertRaises(ValueError, msg=(where, key)):
                sc.check_output(bad, self.schema)
        bad = copy.deepcopy(output)
        bad["clauses"][0].update({"page": 3, "id": d.clause_id(sid, "line-1", 3, d.EDITION)})
        with self.assertRaises(ValueError):
            sc.check_output(bad, self.schema)


class RustParserTests(unittest.TestCase):
    """The shared Rust parser (onjeon_contracts::evidence_ref::validate) and DocRole enum judge docproc ids."""

    def setUp(self):
        if not shutil.which("cargo"):
            if os.environ.get("DOCPROC_REQUIRE_RUST_PARSER") == "1":
                raise AssertionError("cargo required for shared Rust parser conformance")
            self.skipTest("cargo unavailable; shared Rust parser conformance runs on the host")

    def test_rust_parser_accepts_every_role_id_and_rejects_legacy_labels(self):
        accepted, rejected = [], []
        for role in d.ROLES:
            sid = d.segment_id(FIXTURE_DIGEST, 1, 2, role, "explicit-0.1")
            accepted += [sid, d.clause_id(sid, "article-3-2-line-7", 2, d.EDITION), d.clause_id(sid, "line-1", 1, d.EDITION)]
            rejected.append(d.clause_id(sid, "line-1", 3, d.EDITION))  # page outside the segment range
        for label in LEGACY_LABELS:
            legacy = d.segment_id(FIXTURE_DIGEST, 1, 2, label, "explicit-0.1")
            rejected += [legacy, d.clause_id(legacy, "line-1", 1, d.EDITION)]
        bad_roles = [*LEGACY_LABELS, "official_terms", "price_example", "Terms", ""]
        verdicts = sc.rust_parser_verdicts(accepted + rejected, [*d.ROLES, *bad_roles])
        by_ref = {v["ref"]: v for v in verdicts if "ref" in v}
        by_role = {v["doc_role"]: v for v in verdicts if "doc_role" in v}
        self.assertEqual(len(by_ref), len(accepted) + len(rejected))
        for ref in accepted:
            self.assertTrue(by_ref[ref]["ok"] and by_ref[ref]["round_trip"], by_ref[ref])
            self.assertEqual(by_ref[ref]["kind"], "Segment" if ref.startswith("seg:") else "Clause")
        for ref in rejected:
            self.assertFalse(by_ref[ref]["ok"], ref)
        for role in d.ROLES:
            self.assertTrue(by_role[role]["ok"] and by_role[role]["code"] == role, by_role[role])
        for role in bad_roles:
            self.assertFalse(by_role[role]["ok"], role)


if __name__ == "__main__":
    unittest.main()
