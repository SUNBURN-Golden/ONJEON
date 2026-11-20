"""Offline reproduction and extractor tests with LocalStore and mocked subprocess.run."""
import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as sa
import verify_sources as vs


class ReproduceOne(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "extracts").mkdir()
        patcher = mock.patch.object(vs, "VAL", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.pdf = self.root / "original.pdf"
        self.pdf.write_bytes(b"synthetic public PDF")
        self.row = dict(sample_id="sample", sha256=sa.sha256_bytes(self.pdf.read_bytes()), format="pdf")
        self.args = argparse.Namespace(ocr=False)
        self.paths = {"sample": self.pdf}
        self.store = sa.LocalStore(self.root / "derived")
        self.extract("[PDF p.2]\nquoted benefit")

    def extract(self, text, sample="sample"):
        (self.root / "extracts" / f"{sample}.md").write_text(f"```text\n{text}\n```\n", encoding="utf-8")

    def reproduce(self, derived=None):
        return vs.reproduce_one(self.row, self.paths, self.args, derived)

    def pin(self, body=b"regenerated", tool="poppler-pdftotext-layout@24.02.0"):
        digest = self.row["sha256"]
        key = f"derived/{digest}/text/{tool}/sample.layout.txt"
        sa.put_once(self.store, key, body, "text/plain")
        manifest = json.dumps(dict(raw_sha256=digest, sample_id="sample",
                                   outputs=[dict(key=key, sha256=sa.sha256_bytes(body))])).encode()
        pin = sa.sha256_bytes(manifest)
        sa.put_once(self.store, vs.manifest_key(digest, pin), manifest, "application/json")
        self.row["derived_manifest_sha256"] = pin
        return key

    def test_missing_original_returns_before_reading_extract_or_running_tools(self):
        self.paths.clear()
        with mock.patch.object(vs.subprocess, "run") as run:
            self.assertEqual(self.reproduce(), dict(sample_id="sample", sha256_recorded=self.row["sha256"],
                                                    status="missing"))
        run.assert_not_called()

    def test_hash_mismatch_returns_before_reading_extract_or_running_tools(self):
        self.pdf.write_bytes(b"tampered")
        (self.root / "extracts/sample.md").unlink()
        with mock.patch.object(vs.subprocess, "run") as run:
            result = self.reproduce()
        self.assertEqual(result["status"], "hash_mismatch")
        self.assertEqual(result["sha256_archived_bytes"], sa.sha256_bytes(b"tampered"))
        run.assert_not_called()

    def test_pdf_quotes_accept_any_extractor_and_normalize_whitespace(self):
        self.extract("[PDF p.2]\nquoted benefit\nsecond line")
        with mock.patch.object(vs, "pdf_page_texts", return_value=["unrelated", "quotedbenefitsecondline"]) as texts:
            result = self.reproduce()
        self.assertEqual((result["quoted_units"], result["not_found"], result["examples"]), (2, 0, []))
        self.assertEqual(result["status"], "derived_unverified")
        self.assertIsNone(result["derived"])
        self.assertEqual(texts.call_args_list[0].args[:2], (self.pdf, 2))
        self.assertIs(texts.call_args_list[0].args[2], texts.call_args_list[1].args[2])

    def test_pdf_quote_without_page_and_absent_text_are_mismatches(self):
        self.extract("no page\n[PDF p.3]\nabsent text")
        with mock.patch.object(vs, "pdf_page_texts", return_value=["different"]) as texts:
            result = self.reproduce()
        self.assertEqual(result["status"], "quote_mismatch")
        self.assertEqual((result["quoted_units"], result["not_found"]), (2, 2))
        self.assertEqual(result["examples"], ["pNone: no page", "p3: absent text"])
        texts.assert_called_once_with(self.pdf, 3, {})

    def test_html_checks_decoded_table_cells_and_caps_missing_examples(self):
        self.pdf.write_bytes(b"<html>benefit &amp; amount<script>hidden</script></html>")
        self.row.update(format="html", sha256=sa.sha256_bytes(self.pdf.read_bytes()))
        self.extract("[caption] benefit\nth:benefit | td[colspan=2]:& amount\n" +
                     "\n".join(f"td:missing {i}" for i in range(7)))
        result = self.reproduce()
        self.assertEqual(result["status"], "quote_mismatch")
        self.assertEqual((result["quoted_units"], result["not_found"]), (10, 7))
        self.assertEqual(result["examples"], [f"missing {i}" for i in range(5)])

    def test_paired_html_uses_shared_extract_and_sibling_only_when_present(self):
        sid = "klia_pub_cancer_criteria"
        self.row.update(sample_id=sid, format="html")
        sibling = self.root / "paired.html"
        sibling.write_bytes(b"<html>paired quote</html>")
        self.paths = {sid: self.pdf, "klia_pub_cancer_compare": sibling}
        self.extract("td:paired quote", "klia_pub_cancer_compare")
        result = self.reproduce()
        self.assertEqual(result["not_found"], 0)
        self.assertIn("klia_pub_cancer_compare", result["note"])
        self.paths.pop("klia_pub_cancer_compare")
        result = self.reproduce()
        self.assertEqual(result["status"], "quote_mismatch")
        self.assertNotIn("note", result)

    def test_scanned_pdf_requires_explicit_ocr(self):
        self.row["format"] = "scanned_pdf"
        with mock.patch.object(vs, "ocr_page") as ocr:
            self.assertEqual(self.reproduce()["status"], "ocr_not_rerun")
        ocr.assert_not_called()

    def test_scanned_quotes_reuse_each_page_and_do_not_leak_internal_cache(self):
        self.row["format"] = "scanned_pdf"
        self.args.ocr = True
        self.extract("[PDF p.2]\nquoted benefit\nsecond line\n[PDF p.3]\nmissing quote")
        with mock.patch.object(vs, "ocr_page", return_value="quoted benefit\nsecond line") as ocr:
            result = self.reproduce()
        self.assertEqual([call.args[1] for call in ocr.call_args_list], [2, 3])
        self.assertEqual((result["quoted_units"], result["not_found"]), (3, 1))
        self.assertEqual(result["examples"], ["p3: missing quote"])
        self.assertEqual(result["status"], "quote_mismatch")
        self.assertNotIn("_ocr_pages", result)

    def test_real_manifest_and_mocked_extractor_reproduce_byte_identically(self):
        self.pin()
        responses = [subprocess.CompletedProcess([], 0, "", "pdftotext version 24.02.0"),
                     subprocess.CompletedProcess([], 0, b"regenerated", b"")]
        with mock.patch.object(vs, "pdf_page_texts", return_value=["quotedbenefit"]), \
                mock.patch.object(vs.subprocess, "run", side_effect=responses) as run:
            result = self.reproduce(self.store)
        self.assertEqual(result["status"], "reproduced")
        self.assertEqual(result["derived"]["outputs"][0]["state"], "byte_identical")
        self.assertEqual(run.call_args_list[-1], mock.call(
            ["pdftotext", "-layout", str(self.pdf), "-"], capture_output=True, timeout=vs.EXTRACT_TIMEOUT_SECONDS))

    def test_derived_failure_states_propagate_from_local_store(self):
        key = self.pin()
        with mock.patch.object(vs, "pdf_page_texts", return_value=["quotedbenefit"]):
            for generated, expected in ((b"changed", "derived_mismatch"),
                                        ("tool_version_differs", "derived_unverified")):
                with self.subTest(generated=generated), mock.patch.object(vs.Regenerator, "__call__", return_value=generated):
                    self.assertEqual(self.reproduce(self.store)["status"], expected)
            (self.store.root / key).write_bytes(b"corrupt")
            with mock.patch.object(vs.Regenerator, "__call__") as regen:
                self.assertEqual(self.reproduce(self.store)["status"], "derived_record_invalid")
            regen.assert_not_called()

    def test_derived_without_pin_remains_unverified(self):
        with mock.patch.object(vs, "pdf_page_texts", return_value=["quotedbenefit"]):
            result = self.reproduce(self.store)
        self.assertEqual(result["status"], "derived_unverified")
        self.assertIsNone(result["derived"]["manifest"])

    def test_scan_quote_cache_is_passed_to_regenerator(self):
        self.row["format"] = "scanned_pdf"
        self.args.ocr = True
        digest = self.row["sha256"]
        key = f"derived/{digest}/ocr/tesseract@5.3.4-kor-psm3-300dpi-gray/ocr__p-2.txt"
        body = b"quoted benefit"
        sa.put_once(self.store, key, body, "text/plain")
        manifest = json.dumps(dict(raw_sha256=digest, outputs=[dict(key=key, sha256=sa.sha256_bytes(body))])).encode()
        pin = sa.sha256_bytes(manifest)
        sa.put_once(self.store, vs.manifest_key(digest, pin), manifest, "application/json")
        self.row["derived_manifest_sha256"] = pin
        with mock.patch.object(vs, "ocr_page", return_value=body.decode()) as ocr, \
                mock.patch.object(vs.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "tesseract 5.3.4", "")):
            result = self.reproduce(self.store)
        self.assertEqual(result["status"], "reproduced")
        ocr.assert_called_once()
        self.assertNotIn("_ocr_pages", result)

    def test_page_text_extraction_bounds_both_poppler_modes(self):
        doc = mock.MagicMock()
        doc.__enter__.return_value.pages = [None, mock.Mock()]
        doc.__enter__.return_value.pages[1].extract_text.return_value = "third source"
        pdfplumber = mock.Mock()
        pdfplumber.open.return_value = doc
        with mock.patch.dict(sys.modules, {"pdfplumber": pdfplumber}), \
                mock.patch.object(vs.subprocess, "run", return_value=mock.Mock(stdout="first source")) as run:
            self.assertEqual(vs.pdf_page_texts(self.pdf, 2, {}), ["firstsource", "firstsource", "thirdsource"])
        self.assertEqual(run.call_args_list, [mock.call(
            ["pdftotext", *mode, "-f", "2", "-l", "2", str(self.pdf), "-"],
            capture_output=True, text=True, timeout=vs.EXTRACT_TIMEOUT_SECONDS) for mode in (["-layout"], [])])

    def test_reproduce_timeout_fails_and_removes_materialized_archive_even_if_unverified_allowed(self):
        archive = sa.LocalStore(self.root / "archive")
        sa.put_raw(archive, self.pdf.read_bytes(), "application/pdf")
        args = argparse.Namespace(raw=archive.root.as_uri(), endpoint_url=None, ocr=False,
                                  derived=None, allow_unverified=True, report=None)

        def run(cmd, *, timeout, **kwargs):
            self.assertEqual(timeout, vs.EXTRACT_TIMEOUT_SECONDS)
            self.assertTrue(Path(cmd[-2]).is_file())  # materialized before starting the extractor
            raise subprocess.TimeoutExpired(cmd, timeout)

        with mock.patch.object(vs, "rows", return_value=[self.row]), \
                mock.patch.object(vs.tempfile, "tempdir", str(self.root)), \
                mock.patch.object(vs.subprocess, "run", side_effect=run), \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(vs.cmd_reproduce(args), 1)
        self.assertIn("tool_timeout: sample: pdftotext", stderr.getvalue())
        self.assertEqual(list(self.root.glob("onjeon-reproduce-*")), [])

    def test_materialized_archive_lifetime_and_cleanup_on_partial_download(self):
        archive = sa.LocalStore(self.root / "archive")
        body = self.pdf.read_bytes()
        sa.put_raw(archive, body, "application/pdf")
        second = b"second sample"
        sa.put_raw(archive, second, "application/pdf")
        second_row = {"sample_id": "other", "sha256": sa.sha256_bytes(second)}
        args = argparse.Namespace(raw=archive.root.as_uri(), endpoint_url=None)
        with mock.patch.object(vs.tempfile, "tempdir", str(self.root)):
            with vs.materialize(args, [self.row]) as paths:
                work = paths["sample"].parent
                self.assertEqual(paths["sample"].read_bytes(), body)
            self.assertFalse(work.exists())
            with mock.patch.object(sa, "store", return_value=archive), \
                    mock.patch.object(archive, "get", side_effect=[body, OSError("archive read failed")]), \
                    self.assertRaisesRegex(OSError, "archive read failed"), \
                    vs.materialize(args, [self.row, second_row]):
                self.fail("partial archive download reached reproduction")
            self.assertEqual(list(self.root.glob("onjeon-reproduce-*")), [])


class Regenerator(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.pdf = self.root / "source.pdf"
        self.regen = vs.Regenerator(self.pdf, {}, True)

    def test_poppler_modes_generate_distinct_bytes_and_cache_each_mode(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            if cmd == ["pdftotext", "-v"]:
                return subprocess.CompletedProcess(cmd, 0, "", "pdftotext version 24.02.0")
            return subprocess.CompletedProcess(cmd, 0, b"layout\n" if "-layout" in cmd else b"reading\n", b"")

        with mock.patch.object(vs.subprocess, "run", side_effect=run):
            for tool, expected in (("poppler-pdftotext-layout", b"layout\n"),
                                    ("poppler-pdftotext-reading-order", b"reading\n")):
                for name in ("first.txt", "second.txt"):
                    self.assertEqual(self.regen("text", f"{tool}@24.02.0", name), expected)
        extractions = [c for c in calls if "-v" not in c[0]]
        self.assertEqual(extractions, [
            (["pdftotext", "-layout", str(self.pdf), "-"], dict(capture_output=True, timeout=vs.EXTRACT_TIMEOUT_SECONDS)),
            (["pdftotext", str(self.pdf), "-"], dict(capture_output=True, timeout=vs.EXTRACT_TIMEOUT_SECONDS)),
        ])

    def test_missing_unknown_or_different_tool_version_prevents_extraction(self):
        for tool, response in (("poppler-pdftotext-layout@24.02.0", FileNotFoundError()),
                               ("poppler-pdftotext-layout@24.02.0", "no version"),
                               ("poppler-pdftotext-layout@24.02.0", "version 25.01.0"),
                               ("tesseract@5.3.4-kor-psm3-300dpi-gray", FileNotFoundError()),
                               ("tesseract@5.3.4-kor-psm3-300dpi-gray", "tesseract 4.1.1")):
            kind = "ocr" if tool.startswith("tesseract") else "text"
            with self.subTest(tool=tool, response=response):
                kwargs = dict(side_effect=response) if isinstance(response, Exception) else dict(
                    return_value=subprocess.CompletedProcess([], 0, response, ""))
                with mock.patch.object(vs.subprocess, "run", **kwargs) as run:
                    self.assertEqual(self.regen(kind, tool, "ocr__p-2.txt"), "tool_version_differs")
                run.assert_called_once()

    def test_ocr_disabled_does_not_rasterize(self):
        self.regen.ocr_enabled = False
        with mock.patch.object(vs.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "tesseract 5.3.4", "")) as run:
            self.assertEqual(self.regen("ocr", "tesseract@5.3.4-kor-psm3-300dpi-gray", "ocr__p-2.txt"), "not_rerun")
        run.assert_called_once_with(["tesseract", "--version"], capture_output=True, text=True,
                                    timeout=vs.TOOL_VERSION_TIMEOUT_SECONDS)

    def test_ocr_rasterizes_requested_page_with_fixed_options_and_caches_utf8(self):
        commands = []

        def run(cmd, **kwargs):
            commands.append((cmd, kwargs))
            if cmd == ["tesseract", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, "tesseract 5.3.4", "")
            if cmd[0] == "pdftoppm":
                Path(cmd[-1] + "-02.png").write_bytes(b"synthetic PNG")
                return subprocess.CompletedProcess(cmd, 0, b"", b"")
            self.assertTrue(Path(cmd[1]).is_file())
            return subprocess.CompletedProcess(cmd, 0, "보험금\n", "")

        with mock.patch.object(vs.tempfile, "tempdir", str(self.root)), \
                mock.patch.object(vs.subprocess, "run", side_effect=run):
            for _ in range(2):
                self.assertEqual(self.regen("ocr", "tesseract@5.3.4-kor-psm3-300dpi-gray", "ocr__p-2.txt"), "보험금\n".encode())
        extraction = [c for c in commands if "--version" not in c[0]]
        work = Path(extraction[0][0][-1]).parent
        self.assertEqual(extraction, [
            (["pdftoppm", "-r", "300", "-gray", "-f", "2", "-l", "2", "-png", str(self.pdf), str(work / "p2")],
             dict(check=True, capture_output=True, timeout=vs.EXTRACT_TIMEOUT_SECONDS)),
            (["tesseract", str(work / "p2-02.png"), "-", "-l", "kor", "--psm", "3"],
             dict(capture_output=True, text=True, timeout=vs.EXTRACT_TIMEOUT_SECONDS)),
        ])
        self.assertEqual(work.parent, self.root)
        self.assertFalse(work.exists())

    def test_existing_ocr_page_cache_is_used(self):
        regen = vs.Regenerator(self.pdf, {2: "cached 한글"}, True)
        with mock.patch.object(vs.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "5.3.4", "")) as run:
            self.assertEqual(regen("ocr", "tesseract@5.3.4-kor-psm3-300dpi-gray", "ocr__p-2.txt"), "cached 한글".encode())
        run.assert_called_once()

    def test_unknown_kind_tool_or_ocr_filename_is_unregenerable(self):
        cases = [("text", "pdfplumber@0.11.10", "sample.txt"),
                 ("ocr", "tesseract@5.3.4", "ocr_all.txt"),
                 ("ocr", "tesseract@5.3.4", "ocr__p-two.txt"),
                 ("text", "tesseract@5.3.4", "ocr__p-2.txt"),
                 ("ocr", "poppler-pdftotext-layout@24.02.0", "sample.txt")]
        with mock.patch.object(vs.subprocess, "run") as run:
            for args in cases:
                with self.subTest(args=args):
                    self.assertEqual(self.regen(*args), "no_regenerator")
        run.assert_not_called()

    def test_rasterization_failure_propagates_without_caching_page(self):
        responses = [subprocess.CompletedProcess([], 0, "5.3.4", ""),
                     subprocess.CalledProcessError(1, ["pdftoppm"])]
        with mock.patch.object(vs.tempfile, "tempdir", str(self.root)), \
                mock.patch.object(vs.subprocess, "run", side_effect=responses):
            with self.assertRaises(subprocess.CalledProcessError):
                self.regen("ocr", "tesseract@5.3.4-kor-psm3-300dpi-gray", "ocr__p-2.txt")
        self.assertNotIn(2, self.regen.ocr_pages)
        self.assertEqual(list(self.root.glob("onjeon-ocr-*")), [])

    def test_ocr_removes_partial_raster_on_either_tool_timeout(self):
        for slow_tool in ("pdftoppm", "tesseract"):
            with self.subTest(slow_tool=slow_tool):
                def run(cmd, *, timeout, **kwargs):
                    if cmd[0] == "pdftoppm":
                        Path(cmd[-1] + "-02.png").write_bytes(b"partial raster")
                    self.assertEqual(timeout, vs.EXTRACT_TIMEOUT_SECONDS)
                    if cmd[0] == slow_tool:
                        raise subprocess.TimeoutExpired(cmd, timeout)

                with mock.patch.object(vs.tempfile, "tempdir", str(self.root)), \
                        mock.patch.object(vs.subprocess, "run", side_effect=run), \
                        self.assertRaises(subprocess.TimeoutExpired):
                    vs.ocr_page(self.pdf, 2)
                self.assertEqual(list(self.root.glob("onjeon-ocr-*")), [])

    def test_tool_version_probes_can_time_out_without_blocking_a_completed_report(self):
        args = argparse.Namespace(raw=None, report=str(self.root / "report.json"))
        with mock.patch.object(vs, "TOOL_VERSION_TIMEOUT_SECONDS", 0.15):
            with self.assertRaises(subprocess.TimeoutExpired):
                vs.tool_version([sys.executable, "-c", "import time; time.sleep(5)"])
        with mock.patch.object(vs, "tool_version", side_effect=subprocess.TimeoutExpired(["pdftotext"], 10)):
            self.assertEqual(vs.report("detect", args, [], ok=set()), 0)
        tools = json.loads(Path(args.report).read_text())["tools"]
        self.assertIsNone(tools["pdftotext"])
        self.assertIsNone(tools["tesseract"])


if __name__ == "__main__":
    unittest.main()
