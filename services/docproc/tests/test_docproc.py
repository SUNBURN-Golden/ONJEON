import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docproc", ROOT / "docproc.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def synthetic_pdf(path):
    bodies = [b"<< /Type /Catalog /Pages 2 0 R >>",
              b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>",
              b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
              b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for page in (1, 2):
        if page == 2:
            bodies.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>")
        stream = f"BT /F1 12 Tf 72 720 Td (Article {page} synthetic fixture_only) Tj 0 -24 Td (No automatic approval.) Tj ET".encode()
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
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf = Path(self.tmp.name) / "fixture_only.pdf"
        synthetic_pdf(self.pdf)
        self.specs = [{"page_from": 1, "page_to": 2, "doc_role": "보통약관", "seg_rule_ver": "explicit-0.1"}]

    def extract(self, **kwargs):
        with patch.object(d, "tool_version", return_value="24.02.0"):
            return d.extract(self.pdf, self.specs, origin="fixture", **kwargs)

    def test_exact_quote_coordinates_and_tamper(self):
        output = self.extract()
        with patch.object(d, "tool_version", return_value="24.02.0"):
            self.assertTrue(d.verify(self.pdf, output))
            for key, value in (("quote", "wrong"), ("bbox", [0, 0, 1, 1]), ("page", 2), ("segment_id", "wrong")):
                bad = copy.deepcopy(output)
                bad["clauses"][0][key] = value
                with self.assertRaises(ValueError):
                    d.verify(self.pdf, bad)
        self.assertEqual(output["clauses"][0]["quote"], "Article 1 synthetic fixture_only")
        self.assertGreater(output["clauses"][0]["bbox"][0], 0)

    def test_clause_id_reextract_new(self):
        first = self.extract()
        second = self.extract(edition="docproc-text@1.1")
        self.assertEqual(first["segments"], second["segments"])
        self.assertNotEqual(first["clauses"][0]["id"], second["clauses"][0]["id"])
        for c in first["clauses"]:
            self.assertRegex(c["id"], r"^clause:seg:[a-f0-9]{12}:p1-2:보통약관:explicit-0.1/[^/]+#p[12]:docproc-text@1.0$")
        self.assertEqual(len({c["id"] for c in first["clauses"]}), len(first["clauses"]))

    def test_segment_and_uncertainty(self):
        output = self.extract()
        segment = output["segments"][0]
        self.assertEqual((segment["page_from"], segment["page_to"]), (1, 2))
        self.assertEqual(segment["boundary"], "unconfirmed")
        self.assertEqual(segment["fingerprint"]["rule"], "fp-0.1")
        self.assertEqual([c["clause_path_basis"] for c in output["clauses"]], ["printed", "inferred"] * 2)
        self.assertTrue(all(c["review_status"] == "hold" and c["origin"] == "fixture" for c in output["clauses"]))

    def test_fingerprint_nfc_whitespace_preserves_semantics(self):
        fp = d.fingerprint(["e\u0301 \n", "10 이상 아님"], "24.02.0")
        self.assertEqual(fp, {"rule": "fp-0.1", "sha256": hashlib.sha256("é10이상아님".encode()).hexdigest()})
        for text in ("é11이상아님", "é10초과아님", "é10이상"):
            self.assertNotEqual(fp, d.fingerprint([text], "24.02.0"))
        with self.assertRaises(ValueError):
            d.fingerprint(["text"], "25.03.0")

    def test_invalid_segments(self):
        for update in ({"page_from": 0}, {"page_to": 3}, {"doc_role": "unknown"}, {"seg_rule_ver": "bad/version"}, {"boundary": "accepted"}):
            self.specs[0].update(update)
            with self.assertRaises(ValueError):
                self.extract()
            self.specs = [{"page_from": 1, "page_to": 2, "doc_role": "보통약관", "seg_rule_ver": "explicit-0.1"}]
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
        with patch.object(d, "tool_version", return_value="24.02.0"):
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

    def test_multiple_segments_and_determinism(self):
        self.specs = [{"page_from": page, "page_to": page, "doc_role": role,
                       "seg_rule_ver": "explicit-0.1", "boundary": "confirmed"}
                      for page, role in ((1, "보통약관"), (2, "별표"))]
        output = self.extract()
        self.assertEqual(output, self.extract())
        self.assertEqual(len(output["segments"]), 2)
        self.assertNotEqual(output["segments"][0]["fingerprint"], output["segments"][1]["fingerprint"])

    def test_container_configuration(self):
        config = (ROOT / "compose.yaml").read_text()
        for setting in ("network_mode: none", "read_only: true", "cap_drop: [ALL]", "no-new-privileges:true", ":/input:ro"):
            self.assertIn(setting, config)


if __name__ == "__main__":
    unittest.main()
