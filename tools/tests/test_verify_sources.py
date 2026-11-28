"""Regression tests for source verification and CLI dependencies in tools/verify_sources.py.

839ecdb review: a differing derived output was recorded but the sample stayed `reproduced` (exit 0).
Follow-up review: outputs were enumerated from the store, so a file listed in the manifest but
deleted from the store vanished from the comparison and the sample passed. Now the manifest to
verify is pinned by SHA-256 in samples.csv; its hash, raw link, every listed output's presence and
hash, and the absence of unlisted outputs are checked before any regeneration is compared.

The unit tests need no originals or extractors. The archive tests run only when
ONJEON_ARCHIVE_RAW and ONJEON_ARCHIVE_DERIVED point at local stores (the originals are not in
the public repository) and pdftotext is installed.
"""
import gc
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import source_archive as sa  # noqa: E402
import verify_sources as vs  # noqa: E402


OK = {"state": "byte_identical"}


def rec(outputs, errors=(), manifest="m" * 64):
    return {"manifest": manifest, "record_errors": list(errors), "outputs": outputs}


class Decide(unittest.TestCase):
    def test_matrix(self):
        cases = [
            ((False, rec([OK, OK])), "reproduced"),
            ((False, rec([OK, {"state": "differs"}])), "derived_mismatch"),
            ((False, rec([OK, {"state": "tool_version_differs"}])), "derived_unverified"),
            ((False, rec([OK, {"state": "no_regenerator"}])), "derived_unverified"),
            ((False, rec([OK, {"state": "not_rerun"}])), "derived_unverified"),
            ((False, rec([])), "derived_unverified"),
            ((False, rec([OK], errors=["listed output missing"])), "derived_record_invalid"),
            ((False, rec([], manifest=None)), "derived_unverified"),
            ((False, None), "derived_unverified"),
            ((True, rec([OK])), "quote_mismatch"),
        ]
        for (missing, derived), want in cases:
            with self.subTest(derived=derived, missing=missing):
                self.assertEqual(vs.decide(missing, derived), want)


class RowsFileHandling(unittest.TestCase):
    """rows() built its DictReader on an unmanaged open(), so samples.csv stayed
    open until garbage collection and the suite surfaced ResourceWarning noise."""

    def test_rows_returns_the_samples_without_leaking_the_handle(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            rows = vs.rows()
            gc.collect()
        self.assertTrue(rows)
        self.assertIn("sample_id", rows[0])
        self.assertIn("sha256", rows[0])
        leaked = [w for w in caught
                  if issubclass(w.category, ResourceWarning) and "samples.csv" in str(w.message)]
        self.assertEqual(leaked, [], f"rows() left samples.csv open: {leaked}")


class VerifyDerived(unittest.TestCase):
    """839ecdb follow-up: outputs were enumerated from the store, so a file listed in the manifest
    but deleted from the store simply disappeared from the comparison and the sample passed."""

    RAW = "d" * 64
    LAYOUT = f"derived/{'d' * 64}/text/poppler-pdftotext-layout@24.02.0/x.layout.txt"
    READING = f"derived/{'d' * 64}/text/poppler-pdftotext-reading-order@24.02.0/x.raw.txt"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = sa.LocalStore(self.root)
        sa.put_once(self.store, self.LAYOUT, b"layout", "text/plain")
        sa.put_once(self.store, self.READING, b"reading", "text/plain")
        self.pin = self.write_manifest({"raw_sha256": self.RAW, "sample_id": "s", "outputs": [
            {"key": self.LAYOUT, "sha256": sa.sha256_bytes(b"layout")},
            {"key": self.READING, "sha256": sa.sha256_bytes(b"reading")}]})

    def tearDown(self):
        self.tmp.cleanup()

    def write_manifest(self, m, raw=None):
        body = (json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        pin = sa.sha256_bytes(body)
        sa.put_once(self.store, vs.manifest_key(raw or self.RAW, pin), body, "application/json")
        return pin

    @staticmethod
    def regen(layout=b"layout", reading=b"reading"):
        def f(kind, tool, name):
            return layout if "layout" in tool else reading
        return f

    def status(self, pin, regen=None):
        d = vs.verify_derived(self.store, self.RAW, pin, "s", regen or self.regen())
        return vs.decide(False, d), d

    def path(self, key):
        return self.root / key

    def test_intact_record_and_identical_regeneration_is_reproduced(self):
        self.assertEqual(self.status(self.pin)[0], "reproduced")

    def test_listed_output_deleted_is_invalid(self):
        self.path(self.READING).unlink()  # the reviewer's reproduction: 2 listed, 1 deleted
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("listed output missing" in e for e in d["record_errors"]))

    def test_listed_output_bytes_changed_is_invalid(self):
        self.path(self.LAYOUT).write_bytes(b"other")
        st, d = self.status(self.pin, self.regen(layout=b"other"))  # even if regeneration agrees
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("hash differs from manifest" in e for e in d["record_errors"]))

    def test_manifest_tampered_is_invalid(self):
        mk = self.path(vs.manifest_key(self.RAW, self.pin))
        m = json.loads(mk.read_bytes())
        m["outputs"] = m["outputs"][:1]  # drop an entry to hide a deleted file
        mk.write_bytes((json.dumps(m) + "\n").encode())
        self.path(self.READING).unlink()
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("do not hash to the pin" in e for e in d["record_errors"]))

    def test_pinned_manifest_missing_is_invalid(self):
        self.path(vs.manifest_key(self.RAW, self.pin)).unlink()
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("pinned manifest missing" in e for e in d["record_errors"]))

    def test_no_pinned_manifest_is_not_success(self):
        self.assertEqual(self.status(None)[0], "derived_unverified")

    def test_manifest_for_another_raw_is_invalid(self):
        pin = self.write_manifest({"raw_sha256": "e" * 64, "sample_id": "s", "outputs": [
            {"key": self.LAYOUT, "sha256": sa.sha256_bytes(b"layout")}]})
        st, d = self.status(pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("manifest links raw" in e for e in d["record_errors"]))

    def test_unlisted_output_in_store_is_invalid(self):
        extra = f"derived/{self.RAW}/text/poppler-pdftotext-layout@24.02.0/extra.layout.txt"
        sa.put_once(self.store, extra, b"x", "text/plain")
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("not in the pinned manifest" in e for e in d["record_errors"]))

    def test_regeneration_differs_is_mismatch(self):
        self.assertEqual(self.status(self.pin, self.regen(layout=b"changed"))[0], "derived_mismatch")

    def test_unregenerable_output_is_unverified(self):
        def f(kind, tool, name):
            return b"layout" if "layout" in tool else "no_regenerator"
        self.assertEqual(self.status(self.pin, f)[0], "derived_unverified")


@unittest.skipUnless(os.environ.get("ONJEON_ARCHIVE_RAW") and os.environ.get("ONJEON_ARCHIVE_DERIVED")
                     and shutil.which("pdftotext"), "local archive and pdftotext required")
class ArchiveReproduce(unittest.TestCase):
    SAMPLE = "kyobo_cancer_summary"
    DIGEST = "11b72fb0f018d55f6f1c3c53d28660d5ecf6cecec47331634f4fc4a9e4a9d6f1"

    def run_reproduce(self, derived_root):
        with tempfile.TemporaryDirectory() as t:
            rep = Path(t) / "r.json"
            p = subprocess.run([sys.executable, "-I", str(TOOLS / "verify_sources.py"), "reproduce",
                                "--raw", f"file://{os.environ['ONJEON_ARCHIVE_RAW']}",
                                "--derived", f"file://{derived_root}", "--report", str(rep)],
                               capture_output=True, text=True)
            doc = json.loads(rep.read_text())
        return p.returncode, {x["sample_id"]: x for x in doc["results"]}

    def test_tampered_stored_output_fails_with_exit_1(self):
        with tempfile.TemporaryDirectory() as t:
            copy = Path(t) / "derived"
            shutil.copytree(os.environ["ONJEON_ARCHIVE_DERIVED"], copy)
            target = next((copy / "derived" / self.DIGEST / "text").glob("poppler-pdftotext-layout@*/*.txt"))
            target.write_bytes(target.read_bytes() + b"\ntampered\n")
            code, res = self.run_reproduce(copy)
        # caught by the record check (hash differs from the pinned manifest) before regeneration;
        # the regeneration-differs path (derived_mismatch) is covered by VerifyDerived
        self.assertEqual(res[self.SAMPLE]["status"], "derived_record_invalid")
        self.assertEqual(code, 1)

    def test_deleted_listed_output_fails_with_exit_1(self):
        with tempfile.TemporaryDirectory() as t:
            copy = Path(t) / "derived"
            shutil.copytree(os.environ["ONJEON_ARCHIVE_DERIVED"], copy)
            next((copy / "derived" / self.DIGEST / "text").glob("poppler-pdftotext-layout@*/*.txt")).unlink()
            code, res = self.run_reproduce(copy)
        self.assertEqual(res[self.SAMPLE]["status"], "derived_record_invalid")
        self.assertEqual(code, 1)

    def test_untampered_sample_is_reproduced(self):
        code, res = self.run_reproduce(os.environ["ONJEON_ARCHIVE_DERIVED"])
        self.assertEqual(res[self.SAMPLE]["status"], "reproduced")


class CliDependencies(unittest.TestCase):
    """Audit 1: detect must run without pdfplumber; reproduce still requires it."""

    def run_main(self, argv, pdfplumber=None):
        with mock.patch.object(sys, "argv", ["verify_sources.py", *argv]), \
                mock.patch.dict(sys.modules, {"pdfplumber": pdfplumber}), \
                mock.patch.object(vs.shutil, "which", return_value="/usr/bin/pdftotext"), \
                mock.patch.object(vs, "tool_version", return_value=None), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            code = vs.main()
        return code, stdout.getvalue()

    def test_detect_cli_reports_exact_audit5_download_filename_changes(self):
        import html_content_hash as hch
        for before in (b'<a href=x.pdf>terms</a>',
                       b'<a href="#" onclick="fileDown(\'x.pdf\')">terms</a>',
                       b'<button onclick="fileDown(\'x.pdf\')">terms</button>'):
            for change in (False, True):
                with self.subTest(before=before, change=change), tempfile.TemporaryDirectory() as d:
                    after = before.replace(b"x.pdf", b"y.pdf") if change else before
                    status = "changed" if change else "unchanged_bytes"
                    row = {"sample_id": "s1", "url": "https://www.kyobo.com/disclosure",
                           "format": "html", "cache_path": "s1/page.html",
                           "sha256": sa.sha256_bytes(before), "content_hash_rule": hch.RULE,
                           "content_sha256": hch.content_sha256(before, "www.kyobo.com")}
                    out, report = Path(d) / "out", Path(d) / "report.json"
                    with mock.patch.object(vs, "rows", return_value=[row]), \
                            mock.patch.object(vs, "fetch", return_value=(after, "text/html", row["url"], 200)):
                        code, _ = self.run_main(["detect", "--out", str(out), "--report", str(report)])
                    self.assertEqual(code, 0)
                    doc = json.loads(report.read_text())
                    self.assertEqual(doc["summary"], {status: 1})
                    result, = doc["results"]
                    self.assertEqual(result["status"], status)
                    self.assertEqual(result["baseline_sha256"], sa.sha256_bytes(before))
                    self.assertEqual(result["sha256_now"], sa.sha256_bytes(after))
                    if change:
                        self.assertEqual(result["content_hash_rule"], hch.RULE)
                    self.assertEqual((out / row["cache_path"]).read_bytes(), after)

    def test_detect_cli_reports_exact_audit6_link_extraction_changes(self):
        import html_content_hash as hch
        pages = (b'<a href=x.pdf>terms</a>',
                 b'<a href="#" onclick="fnDown(\'x.pdf\')">terms</a>',
                 b'<button onclick="fnDown(\'x.pdf\')">terms</button>',
                 b'<a data-href="decoy.pdf" href="x.pdf">terms</a>',
                 b'<a href="x.pdf" data-href="decoy.pdf">terms</a>',
                 b'<a data-href=decoy.pdf href=x.pdf>terms</a>')
        for before in pages:
            responses = [(before, "unchanged_bytes"),
                         (before.replace(b"x.pdf", b"y.pdf"), "changed")]
            if b"decoy.pdf" in before:
                responses.append((before.replace(b"decoy.pdf", b"other.pdf"),
                                  "bytes_changed_content_same"))
            for after, status in responses:
                with self.subTest(before=before, status=status), tempfile.TemporaryDirectory() as d:
                    row = {"sample_id": "s1", "url": "https://www.kyobo.com/disclosure",
                           "format": "html", "cache_path": "s1/page.html",
                           "sha256": sa.sha256_bytes(before), "content_hash_rule": hch.RULE,
                           "content_sha256": hch.content_sha256(before, "www.kyobo.com")}
                    out, report = Path(d) / "out", Path(d) / "report.json"
                    with mock.patch.object(vs, "rows", return_value=[row]), \
                            mock.patch.object(vs, "fetch", return_value=(after, "text/html", row["url"], 200)):
                        code, _ = self.run_main(["detect", "--out", str(out), "--report", str(report)])
                    self.assertEqual(code, 0)
                    doc = json.loads(report.read_text())
                    self.assertEqual(doc["summary"], {status: 1})
                    result, = doc["results"]
                    self.assertEqual(result["status"], status)
                    self.assertEqual(result["baseline_sha256"], sa.sha256_bytes(before))
                    self.assertEqual(result["sha256_now"], sa.sha256_bytes(after))
                    if after != before:
                        self.assertEqual(result["content_hash_rule"], hch.RULE)
                    self.assertEqual((out / row["cache_path"]).read_bytes(), after)

    def test_detect_without_pdfplumber_writes_report_and_preserves_exit_status(self):
        body = b"%PDF-1.4 sample bytes"
        row = {"sample_id": "s1", "url": "https://www.kyobo.com/source.pdf", "format": "pdf",
               "cache_path": "s1/source.pdf", "sha256": sa.sha256_bytes(body)}
        cases = [(body, "unchanged_bytes", 0), (b"new PDF bytes", "changed", 0),
                 (OSError("offline"), "fetch_failed", 1)]
        for response, status, expected_code in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as d:
                out = Path(d) / "downloads"
                report = Path(d) / "report.json"
                fetch = mock.Mock(side_effect=response) if isinstance(response, Exception) else \
                    mock.Mock(return_value=(response, "application/pdf", row["url"], 200))
                with mock.patch.object(vs, "rows", return_value=[row]), \
                        mock.patch.object(vs, "fetch", fetch):
                    code, _ = self.run_main(["detect", "--out", str(out), "--report", str(report)])
                self.assertEqual(code, expected_code)
                fetch.assert_called_once_with(row["url"], expected_format=row["format"],
                                              robots_deferrals={}, host_pacing={})
                doc = json.loads(report.read_text())
                self.assertEqual(doc["check"], "detect")
                self.assertEqual(doc["summary"], {status: 1})
                self.assertIsNone(doc["tools"]["pdfplumber"])
                downloaded = out / row["cache_path"]
                if status == "fetch_failed":
                    self.assertFalse(downloaded.exists())
                else:
                    self.assertEqual(downloaded.read_bytes(), response)
                    self.assertEqual(doc["results"][0]["sha256_now"], sa.sha256_bytes(response))

    def test_reproduce_without_pdfplumber_stops_before_processing(self):
        with mock.patch.object(vs, "cmd_reproduce") as reproduce, \
                mock.patch.object(sa, "with_budget") as budget:
            code, output = self.run_main(["reproduce", "--cache", "unused"])
        self.assertEqual(code, 2)
        self.assertIn("pdfplumber is required (pip install pdfplumber==0.11.10)", output)
        reproduce.assert_not_called()
        budget.assert_not_called()

    def test_detect_with_only_robots_disallowed_samples_fails_without_requests(self):
        blocked = [r for r in vs.rows() if vs.urllib.parse.urlsplit(r["url"]).hostname == "pub.insure.or.kr"]
        self.assertEqual(len(blocked), 2)
        with tempfile.TemporaryDirectory() as d:
            out, report = Path(d) / "out", Path(d) / "report.json"
            with mock.patch.object(vs, "rows", return_value=blocked), mock.patch.object(vs, "fetch") as fetch:
                code, output = self.run_main(["detect", "--out", str(out), "--report", str(report)])
            self.assertEqual(code, 1)
            self.assertIn("fetch_failed 2 (of 2)", output)
            self.assertEqual(json.loads(report.read_text())["summary"], {"fetch_failed": 2})
            fetch.assert_not_called()
            self.assertFalse(out.exists())

    def test_reproduce_with_pdfplumber_dispatches(self):
        with mock.patch.object(vs, "cmd_reproduce", return_value=0) as reproduce:
            code, _ = self.run_main(["reproduce", "--cache", "unused"], pdfplumber=mock.Mock())
        self.assertEqual(code, 0)
        reproduce.assert_called_once()
        self.assertEqual(reproduce.call_args.args[0].cache, "unused")


class DetectExit(unittest.TestCase):
    """A green detect run must mean every source was observed: a fetch failure exits 1."""

    def run_detect(self, fetch):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            import argparse
            args = argparse.Namespace(raw=None, out=d, archive_new=False, report=str(Path(d) / "r.json"),
                                      endpoint_url=None, cache=None, derived=None, ocr=False)
            with mock.patch.object(vs, "fetch", side_effect=fetch), \
                    mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
                code = vs.cmd_detect(args)
            return code, json.loads(Path(args.report).read_text())["summary"]

    def test_any_fetch_failure_fails_the_run(self):
        rows = [self.html_row("unused", b"x")]
        calls = {"n": 0}

        def fetch(url, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("blocked")
            return b"other bytes", "application/pdf", url, 200
        with mock.patch.object(vs, "rows", return_value=rows):
            code, summary = self.run_detect(fetch)
        self.assertEqual(code, 1)
        self.assertEqual(summary.get("fetch_failed"), 1)
        self.assertEqual(sum(summary.values()), len(rows))

    def test_changed_sources_are_a_successful_observation(self):
        with mock.patch.object(vs, "rows", return_value=[self.html_row("unused", b"x")]):
            code, summary = self.run_detect(lambda url, **kw: (b"other bytes", "text/html", url, 200))
        self.assertEqual(code, 0)
        self.assertNotIn("fetch_failed", summary)

    def test_traversing_cache_path_is_not_fetched_or_written(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "out"
            out.mkdir()
            row = self.html_row(__import__("html_content_hash").RULE, b"x")
            row["cache_path"] = "../escaped.html"
            args = __import__("argparse").Namespace(raw=None, out=str(out), archive_new=False,
                                                    report=str(Path(t) / "r.json"), endpoint_url=None,
                                                    cache=None, derived=None, ocr=False)
            fetch = mock.Mock(return_value=(b"y", "text/html"))
            with mock.patch.object(vs, "rows", return_value=[row]), mock.patch.object(vs, "fetch", fetch), \
                    mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
                code = vs.cmd_detect(args)
            summary = json.loads(Path(args.report).read_text())["summary"]
            self.assertEqual(code, 1)
            self.assertEqual(summary, {"unsafe_cache_path": 1})
            fetch.assert_not_called()
            self.assertFalse((Path(t) / "escaped.html").exists())

    def test_reproduce_ignores_cache_path_outside_cache(self):
        with tempfile.TemporaryDirectory() as t:
            cache = Path(t) / "cache"
            cache.mkdir()
            (Path(t) / "outside.pdf").write_bytes(b"x")
            args = __import__("argparse").Namespace(raw=None, cache=str(cache))
            with vs.materialize(args, [{"sample_id": "s", "cache_path": "../outside.pdf"}]) as paths:
                self.assertEqual(paths, {})

    def test_oversized_body_is_fetch_failed_too_large(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            import argparse
            args = argparse.Namespace(raw=None, out=d, archive_new=False, report=str(Path(d) / "r.json"),
                                      endpoint_url=None, cache=None, derived=None, ocr=False)
            with mock.patch.object(vs, "fetch", side_effect=vs.FetchRejected("too_large: body exceeds 5 bytes")), \
                    mock.patch.object(vs, "rows", return_value=[self.html_row("unused", b"x")]), \
                    mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
                code = vs.cmd_detect(args)
            doc = json.loads(Path(args.report).read_text())
            self.assertEqual(code, 1)
            self.assertEqual(doc["summary"], {"fetch_failed": len(doc["results"])})
            self.assertTrue(all(x["detail"].startswith("too_large:") for x in doc["results"]))
            self.assertFalse(any("sha256_now" in x for x in doc["results"]))
            self.assertEqual(list(Path(d).glob("*/")), [])  # nothing written for a refused body

    def html_row(self, rule, body):
        import html_content_hash as hch
        return {"sample_id": "s1", "url": "https://www.kyobo.com/p", "sha256": "0" * 64, "format": "html",
                "cache_path": "s1/page.html", "content_sha256": hch.content_sha256(body, "www.kyobo.com"),
                "content_hash_rule": rule}

    def detect_html(self, rule, before, after):
        from unittest import mock
        row = self.html_row(rule, before)
        with mock.patch.object(vs, "rows", return_value=[row]):
            return self.run_detect(lambda url, **kw: (after, "text/html", url, 200))[1]

    def test_current_rule_hash_reports_bytes_changed_content_same(self):
        import html_content_hash as hch
        a = b'<a href="/d?id=7&jsessionid=A">x</a>'
        b = b'<a href="/d?id=7&jsessionid=B">x</a>'
        self.assertEqual(self.detect_html(hch.RULE, a, b), {"bytes_changed_content_same": 1})

    def test_sid_document_id_change_is_changed_not_same(self):
        import html_content_hash as hch
        a = b'<a href="/d?sid=1001">x</a>'
        b = b'<a href="/d?sid=1002">x</a>'
        self.assertEqual(self.detect_html(hch.RULE, a, b), {"changed": 1})

    def test_baseline_under_an_older_rule_is_not_compared(self):
        a = b'<a href="/d?id=7&jsessionid=A">x</a>'
        b = b'<a href="/d?id=7&jsessionid=B">x</a>'
        for rule in ("html-visible-text-v1", "html-visible-text-v2"):
            with self.subTest(rule=rule):
                self.assertEqual(self.detect_html(rule, a, b), {"changed": 1})

    def test_download_target_changes_are_changed_not_content_same(self):
        import html_content_hash as hch
        for before in (b'<a href=/old.pdf>terms</a>',
                       b'<a href="#" onclick="download(\'old.pdf\')">terms</a>',
                       b'<button onclick=download(\'old.pdf\')>terms</button>'):
            with self.subTest(before=before):
                self.assertEqual(self.detect_html(hch.RULE, before, before.replace(b"old.pdf", b"new.pdf")),
                                 {"changed": 1})


class RecordedRobotsPolicy(unittest.TestCase):
    def test_real_samples_are_reported_without_fetching_writing_or_archiving(self):
        # Exercise the real denominator, including both KLIA pages, with no network or archive.
        import argparse
        rows = vs.rows()
        blocked = [r for r in rows if vs.urllib.parse.urlsplit(r["url"]).hostname == "pub.insure.or.kr"]
        self.assertEqual({r["sample_id"] for r in blocked},
                         {"klia_pub_cancer_compare", "klia_pub_cancer_criteria"})
        with tempfile.TemporaryDirectory() as d:
            args = argparse.Namespace(raw="file:///unused", out=str(Path(d) / "out"),
                                      archive_new=True, report=str(Path(d) / "report.json"),
                                      endpoint_url=None)
            store = mock.Mock()
            with mock.patch.object(vs.sa, "store", return_value=store), \
                    mock.patch.object(vs, "fetch", side_effect=lambda url, **kw: (b"changed", "text/html", url, 200)) as fetch, \
                    mock.patch.object(vs.sa, "put_raw", return_value=("key", "new")) as put_raw, \
                    mock.patch.object(vs.sa, "put_observation", return_value=("obs", "new")) as put_obs, \
                    mock.patch("sys.stdout", new_callable=io.StringIO):
                code = vs.cmd_detect(args)
            doc = json.loads(Path(args.report).read_text())
            self.assertEqual(code, 1)
            self.assertEqual(doc["summary"], {"changed": len(rows) - 2, "fetch_failed": 2})
            self.assertEqual(len(doc["results"]), len(rows))
            self.assertEqual([c.args[0] for c in fetch.call_args_list],
                             [r["url"] for r in rows if r not in blocked])
            self.assertEqual(put_raw.call_count, len(rows) - 2)
            self.assertEqual(put_obs.call_count, len(rows) - 2)
            for r in blocked:
                res = next(x for x in doc["results"] if x["sample_id"] == r["sample_id"])
                self.assertEqual(res["status"], "fetch_failed")
                self.assertTrue(res["detail"].startswith("robots_disallow:"))
                self.assertIn(vs.ROBOTS_POLICY_SOURCE, res["detail"])
                self.assertIsNone(res["http_status"])
                self.assertIsNone(res["final_url"])
                self.assertEqual(res["baseline_sha256"], r["sha256"])
                for key in ("sha256_now", "archived_object", "observation"):
                    self.assertNotIn(key, res)
                self.assertFalse((Path(args.out) / r["cache_path"]).exists())

    def test_policy_applies_to_host_regardless_of_path_case_port_or_scheme(self):
        for url in ("https://pub.insure.or.kr/", "http://PUB.INSURE.OR.KR:80/new/path?x=1",
                    "https://pub.insure.or.kr./download.pdf"):
            with self.subTest(url=url), mock.patch.object(vs.subprocess, "run") as run:
                with self.assertRaises(vs.RobotsDisallowed):
                    vs.fetch(url)
                run.assert_not_called()

    def test_policy_matches_hostname_not_url_substrings(self):
        for url in ("https://pub.insure.or.kr.www.kyobo.com/", "https://www.kyobo.com/pub.insure.or.kr",
                    "https://www.kyobo.com/?url=https://pub.insure.or.kr/", "https://www.klia.or.kr/"):
            with self.subTest(url=url):
                vs.check_recorded_robots_policy(url)


if __name__ == "__main__":
    unittest.main()
