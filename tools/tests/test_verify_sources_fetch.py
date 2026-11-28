"""Detect source admission through the shared crawler transport.

Only loopback sockets and temporary local archives are used; no insurer or R2 access.
"""
import argparse
import csv
import functools
import gzip
import io
import json
import os
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from email.message import Message
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import verify_sources as vs
from crawler import transport
from crawler.useragent import build_user_agent


PDF = b"%PDF-1.7\nnew disclosure bytes\n%%EOF"
HTML = b"<html><title>Disclosure</title><a href='/login'>Login</a><table><tr><td>123</td></tr></table></html>"
CONTACT = "archive@example.org"
SOURCE_URL = "https://www.kyobo.com/start"
WAF = b"<html><title>Access Denied</title><p>Your IP has been blocked</p></html>"


class SourceHostRegistry(unittest.TestCase):
    def test_registry_is_explicit_and_covers_recorded_sources_and_samples(self):
        hosts = vs.registered_source_hosts()
        self.assertNotIn("example.org", hosts)
        for host in hosts:
            with self.subTest(host=host):
                self.assertEqual(vs.source_origin(f"https://{host}/"), ("https", host, 443))
        for row in vs.rows():
            # Registration does not override the separate robots hold.
            self.assertIn(vs.source_origin(row["url"])[1], hosts)
        registry = vs.ROOT / "data/registry"
        for name, columns in (("sources.csv", ("url",)),
                              ("insurers.csv", ("home_url", "disclosure_url"))):
            with (registry / name).open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    for column in columns:
                        if row[column]:
                            self.assertIn(vs.urllib.parse.urlsplit(row[column]).hostname, hosts)

    def test_unregistered_initial_hosts_never_open_or_retry(self):
        for host in ("example.org", "127.0.0.1", "localhost", "169.254.169.254", "[::1]",
                     "sub.www.kyobo.com", "www.kyobo.com.evil.org", "www.kyobo.com.",
                     "www%2ekyobo.com", "www.kyobo.com%00.evil.org"):
            url = f"https://{host}/www.kyobo.com?next=https://www.kyobo.com/"
            with self.subTest(host=host), \
                    mock.patch.object(vs.subprocess, "run", side_effect=AssertionError("worker started")) as run, \
                    mock.patch.object(transport, "_build_opener", side_effect=AssertionError("opener built")), \
                    mock.patch.object(vs.time, "sleep") as sleep:
                with self.assertRaisesRegex(vs.FetchRejected, "url_disallowed: host"):
                    vs.fetch(url)
                run.assert_not_called()
                sleep.assert_not_called()

    def test_missing_or_invalid_registry_fails_before_network(self):
        bad = ("not JSON", "null", "[]", "{}", '{"hosts": "www.kyobo.com"}',
               '{"hosts": []}', '{"hosts": [null]}', '{"hosts": [[]]}',
               '{"hosts": ["www.kyobo.com", "www.kyobo.com"]}',
               '{"hosts": ["*.kyobo.com"]}', '{"hosts": ["https://www.kyobo.com"]}',
               '{"hosts": ["www.kyobo.com:443"]}', '{"hosts": ["WWW.KYOBO.COM"]}',
               '{"hosts": ["www.kyobo.com."]}', '{"hosts": ["-bad.com"]}',
               '{"hosts": ["a..com"]}', json.dumps({"hosts": ["a" * 64 + ".com"]}),
               json.dumps({"hosts": ["a." * 127 + "com"]}))
        with tempfile.TemporaryDirectory() as d:
            policy = Path(d) / "hosts.json"
            for contents in (None, *bad):
                with self.subTest(contents=contents), \
                        mock.patch.object(vs, "SOURCE_HOST_REGISTRY", policy), \
                        mock.patch.object(vs.subprocess, "run") as run:
                    if contents is not None:
                        policy.write_text(contents)
                    with self.assertRaisesRegex(vs.FetchRejected, "registry unavailable or invalid"):
                        vs.fetch("https://www.kyobo.com/file")
                    run.assert_not_called()

    def test_adding_a_sample_url_does_not_register_its_host(self):
        with mock.patch.object(vs, "rows", return_value=[{"url": "https://example.org/file"}]):
            with self.assertRaisesRegex(vs.FetchRejected, "url_disallowed: host"):
                vs.source_origin("https://example.org/file")


class Response(io.BytesIO):
    def __init__(self, body, mime="application/pdf", status=200, length=None):
        super().__init__(body)
        self.headers = Message()
        if mime is not None:
            self.headers["Content-Type"] = mime
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self.status = status
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class URLAdmission(unittest.TestCase):
    def test_non_https_and_credentialed_initial_urls_never_open(self):
        for url in ("http://www.kyobo.com/file", "file:///tmp/document", "ftp://www.kyobo.com/file",
                    "https://user:pass@www.kyobo.com/file", "https:///file", "https://www.kyobo.com:0/file",
                    " https://www.kyobo.com/file", "https://www.kyobo.com/\nfile", "data:text/plain,body",
                    "https://[broken/"):
            with self.subTest(url=url), \
                    mock.patch.object(vs.subprocess, "run", side_effect=AssertionError("worker started")) as run, \
                    mock.patch.object(transport, "_build_opener", side_effect=AssertionError("opener built")):
                with self.assertRaises(vs.FetchRejected):
                    vs.fetch(url)
                run.assert_not_called()

    def test_worker_entry_point_revalidates_source_url(self):
        command = [sys.executable, "-I", str(Path(vs.__file__).resolve()), "--fetch-worker"]
        for url in ("file:///must-not-read", "ftp://www.kyobo.com/file", "data:text/plain,body", "https://localhost/"):
            with self.subTest(url=url):
                proc = subprocess.run(command, input=json.dumps([url, 1, 1024, "html", [0, 0]]).encode(),
                                      capture_output=True, check=True, timeout=5)
                metadata = json.loads(proc.stdout)
                self.assertEqual(metadata["error"], "FetchRejected")
                self.assertTrue(metadata["detail"].startswith("url_disallowed:"))


class ResponseAdmission(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(os.environ, {vs.CONTACT_ENV: CONTACT, transport.ENV_ALLOW_NETWORK: "1"})
        patch.start()
        self.addCleanup(patch.stop)

    def fetch_with(self, response, **kwargs):
        robots = Response(b"", status=404)
        opener = mock.Mock()
        opener.open.side_effect = [robots, response]
        with mock.patch.object(transport, "_build_opener", return_value=opener), \
                mock.patch.object(vs.time, "sleep") as sleep:
            try:
                return vs._fetch_https(SOURCE_URL, **kwargs)
            finally:
                self.assertEqual([c.args[0].full_url for c in opener.open.call_args_list],
                                 ["https://www.kyobo.com/robots.txt", SOURCE_URL])
                sleep.assert_not_called()
                self.assertTrue(robots.closed)
                self.assertTrue(response.closed)

    def test_invalid_contact_never_opens_a_connection(self):
        for contact in ("", "Mozilla/5.0", "not a public contact", "a" * 201):
            with self.subTest(contact=contact), mock.patch.dict(os.environ, {vs.CONTACT_ENV: contact}), \
                    mock.patch.object(transport, "_build_opener") as build:
                with self.assertRaisesRegex(vs.FetchRejected, "crawler_contact"):
                    vs._fetch_https(SOURCE_URL)
                build.assert_not_called()

    def test_non_loopback_needs_explicit_network_opt_in(self):
        with mock.patch.dict(os.environ, {transport.ENV_ALLOW_NETWORK: ""}), \
                mock.patch.object(transport, "_build_opener") as build:
            with self.assertRaisesRegex(vs.FetchRejected, transport.ENV_ALLOW_NETWORK):
                vs._fetch_https(SOURCE_URL)
            build.return_value.open.assert_not_called()

    def test_redirect_bodies_close_unread_and_targets_are_never_opened(self):
        for code in (301, 302, 303, 304, 307, 308):
            for target in (None, "/document", "https://www.kbinsure.co.kr/file",
                           "https://pub.insure.or.kr/file", "http://www.kyobo.com/file",
                           "ftp://www.kyobo.com/file", "file:///must-not-read"):
                with self.subTest(code=code, target=target):
                    response = Response(b"redirect body", status=code, length=vs.MAX_FETCH_BYTES + 1)
                    if target is not None:
                        response.headers["Location"] = target
                    with self.assertRaisesRegex(vs.FetchRejected, "redirect_disallowed") as error:
                        self.fetch_with(response)
                    self.assertEqual((error.exception.final_url, error.exception.http_status), (SOURCE_URL, code))
                    self.assertEqual(response.read_sizes, [])

    def test_pdf_aliases_and_generic_download_mimes_require_pdf_signature(self):
        for fmt in ("pdf", "text_pdf", "scanned_pdf"):
            for mime in ("application/pdf", "application/octet-stream", "binary/octet-stream",
                         "Application/PDF; charset=binary"):
                with self.subTest(fmt=fmt, mime=mime):
                    result = self.fetch_with(Response(PDF, mime), expected_format=fmt)
                    self.assertEqual(result, (PDF, mime.split(";")[0].lower(), SOURCE_URL, 200))

    def test_mismatched_or_missing_mime_is_rejected_unread(self):
        for fmt, mime in (("pdf", "text/html"), ("pdf", "text/plain"), ("pdf", None),
                          ("html", "application/pdf"), ("html", "application/json"),
                          ("html", "application/octet-stream"), ("html", None)):
            with self.subTest(fmt=fmt, mime=mime):
                response = Response(WAF, mime)
                with self.assertRaisesRegex(vs.FetchRejected, "content_type_mismatch"):
                    self.fetch_with(response, expected_format=fmt)
                self.assertEqual(response.read_sizes, [])

    def test_empty_wrong_signature_and_truncated_bodies_are_rejected(self):
        for body, mime, fmt, length, reason in (
            (b"", "application/pdf", "pdf", None, "empty_body"),
            (WAF, "application/pdf", "pdf", None, "wrong_signature"),
            (WAF, "application/octet-stream", "pdf", None, "wrong_signature"),
            (PDF, "text/html", "html", None, "wrong_signature"),
            (PDF, "application/pdf", "pdf", len(PDF) + 1, "length_mismatch"),
        ):
            with self.subTest(reason=reason, mime=mime), self.assertRaisesRegex(vs.FetchRejected, reason):
                self.fetch_with(Response(body, mime, length=length), expected_format=fmt)

    def test_known_200_waf_challenge_and_login_html_are_rejected(self):
        pages = [WAF, b"<html><title>Just a moment...</title></html>",
                 b"<html><title>Attention Required! | Cloudflare</title></html>",
                 b"<html><title>Request Rejected</title><p>Please consult your administrator.</p></html>",
                 b"<html><p>Sorry, you have been blocked</p></html>",
                 b"<html><p>Please complete the CAPTCHA</p></html>",
                 b"<html><script src='/cdn-cgi/challenge-platform/x'></script></html>",
                 b"<html><p>Verify you are human</p></html>",
                 b"<html><p>Access <b>denied</b></p></html>",
                 b"<html><form><input type='password'></form></html>",
                 b"<html><div class='g-recaptcha'></div></html>",
                 "<html><meta charset='euc-kr'><p>접근이 차단되었습니다</p></html>".encode("euc-kr"),
                 "<html><p>로그인이 필요합니다</p></html>".encode()]
        for page in pages:
            with self.subTest(page=page), self.assertRaisesRegex(vs.FetchRejected, "block_page") as raised:
                self.fetch_with(Response(page, "text/html"), expected_format="html")
            self.assertEqual((raised.exception.final_url, raised.exception.http_status), (SOURCE_URL, 200))

    def test_public_html_navigation_and_binary_pdf_words_are_not_block_pages(self):
        for mime in ("text/html; charset=utf-8", "application/xhtml+xml"):
            with self.subTest(mime=mime):
                self.assertEqual(self.fetch_with(Response(HTML, mime), expected_format="html")[0], HTML)
        pdf = PDF + b" captcha access denied login required"
        self.assertEqual(self.fetch_with(Response(pdf))[0], pdf)

    def test_non_200_responses_are_not_read_or_retried(self):
        for status in (204, 206, 403, 404, 503):
            with self.subTest(status=status):
                response = Response(PDF, status=status)
                with self.assertRaisesRegex(vs.FetchRejected, "unexpected_status") as error:
                    self.fetch_with(response)
                self.assertEqual((error.exception.final_url, error.exception.http_status), (SOURCE_URL, status))
                self.assertIsNone(error.exception.deferred_until)
                self.assertEqual(response.read_sizes, [])

    def test_document_rate_limit_honors_retry_after_without_reading_or_retrying(self):
        for status, header, until in (
            (429, "600", 86_900),
            (503, formatdate(86_900, usegmt=True), 86_900),
            (429, None, 86_400),
            (429, "invalid", 86_400),
            (429, "0", 86_400),
            (429, formatdate(86_299, usegmt=True), 86_400),
        ):
            with self.subTest(status=status, header=header), mock.patch.object(vs.time, "time", return_value=86_300):
                response = Response(PDF, status=status)
                if header is not None:
                    response.headers["Retry-After"] = header
                with self.assertRaisesRegex(vs.FetchRejected, f"^rate_limited: {status}$") as error:
                    self.fetch_with(response)
                self.assertEqual((error.exception.final_url, error.exception.http_status), (SOURCE_URL, status))
                self.assertEqual(error.exception.deferred_until, until)
                self.assertEqual(response.read_sizes, [])

    def test_body_at_the_cap_is_returned(self):
        self.assertEqual(self.fetch_with(Response(PDF), max_bytes=len(PDF))[0], PDF)

    def test_size_limit_is_bounded_with_missing_or_understated_length(self):
        for length in (None, 1):
            with self.subTest(length=length):
                response = Response(PDF * 20, length=length)
                with self.assertRaisesRegex(vs.FetchRejected, "too_large"):
                    self.fetch_with(response, max_bytes=10)
                self.assertEqual(sum(response.read_sizes), 11)

    def test_size_limit_cannot_be_disabled_or_raised(self):
        for cap in (0, -1, True, vs.MAX_FETCH_BYTES + 1):
            with self.subTest(cap=cap), mock.patch.object(vs.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    vs.fetch("https://www.kyobo.com/start", max_bytes=cap)
                run.assert_not_called()

    def test_default_cap_rejects_declared_oversize_without_reading(self):
        self.assertEqual(vs.MAX_FETCH_BYTES, 64 * 1024 * 1024)
        response = Response(PDF, length=vs.MAX_FETCH_BYTES + 1)
        with self.assertRaisesRegex(vs.FetchRejected, "too_large"):
            self.fetch_with(response)
        self.assertEqual(response.read_sizes, [])

    def test_streaming_cap_applies_across_multiple_chunks(self):
        cap = transport.CHUNK_BYTES + len(PDF)
        response = Response(PDF + b"x" * (cap + 100))
        with self.assertRaisesRegex(vs.FetchRejected, "too_large"):
            self.fetch_with(response, max_bytes=cap)
        self.assertEqual(response.read_sizes, [transport.CHUNK_BYTES, len(PDF) + 1])
        self.assertEqual(sum(response.read_sizes), cap + 1)

    def test_unsupported_expectation_never_opens(self):
        with mock.patch.object(vs.subprocess, "run") as run:
            with self.assertRaisesRegex(vs.FetchRejected, "unsupported_format"):
                vs.fetch("https://www.kyobo.com/start", expected_format="unknown")
            run.assert_not_called()

    def test_invalid_attempt_count_never_opens(self):
        for attempts in (0, -1, True):
            with self.subTest(attempts=attempts), mock.patch.object(vs.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    vs.fetch("https://www.kyobo.com/start", attempts=attempts)
                run.assert_not_called()

    def test_only_document_connection_errors_retry_after_robots_and_its_crawl_delay(self):
        robots = Response(b"User-agent: *\nCrawl-delay: 5\n", "text/plain")
        opener = mock.Mock()
        opener.open.side_effect = [robots, urllib.error.URLError("offline"), Response(PDF)]
        with mock.patch.object(transport, "_build_opener", return_value=opener), \
                mock.patch.object(vs.time, "sleep") as sleep:
            self.assertEqual(vs._fetch_https(SOURCE_URL)[0], PDF)
        self.assertEqual([c.args[0].full_url for c in opener.open.call_args_list],
                         ["https://www.kyobo.com/robots.txt", SOURCE_URL, SOURCE_URL])
        self.assertTrue(all(c.kwargs["timeout"] == vs.FETCH_SOCKET_TIMEOUT_SECONDS
                            for c in opener.open.call_args_list[1:]))
        self.assertEqual(sleep.call_args_list, [mock.call(5), mock.call(5)])

    def test_previous_crawl_delay_is_used_even_when_another_origin_has_no_policy(self):
        opener = mock.Mock()
        opener.open.side_effect = [Response(b"", status=404), Response(PDF)]
        url = "https://www.kyobo.com:8443/document"
        calls = mock.Mock()
        calls.attach_mock(opener.open, "open")
        with mock.patch.object(transport, "_build_opener", return_value=opener), \
                mock.patch.object(vs.time, "monotonic", return_value=10), \
                mock.patch.object(vs.time, "sleep", calls.sleep):
            self.assertEqual(vs._fetch_https(url, pacing=(5, 12))[0], PDF)
        self.assertEqual([call[0] for call in calls.mock_calls], ["sleep", "open", "sleep", "open"])
        self.assertEqual(calls.sleep.call_args_list, [mock.call(2), mock.call(5)])


class HostDeferrals(unittest.TestCase):
    def test_deferral_is_host_scoped_and_expires_at_the_recorded_time(self):
        deferrals = {"www.kyobo.com": (86400, "robots_rate_limited")}

        def worker(command, *, input, stdout, **kwargs):
            url = json.loads(input)[0]
            result = {"content_type": "application/pdf", "final_url": url, "http_status": 200}
            stdout.write(json.dumps(result).encode() + b"\n" + PDF)

        with mock.patch.object(vs.subprocess, "run", side_effect=worker) as run, \
                mock.patch.object(vs.time, "time", return_value=86399) as clock:
            with self.assertRaisesRegex(vs.FetchRejected, "robots_rate_limited"):
                vs.fetch(SOURCE_URL, robots_deferrals=deferrals)
            run.assert_not_called()
            self.assertEqual(vs.fetch("https://www.kbinsure.co.kr/document", robots_deferrals=deferrals)[0], PDF)
            clock.return_value = 86400
            self.assertEqual(vs.fetch(SOURCE_URL, robots_deferrals=deferrals)[0], PDF)
            self.assertEqual(run.call_count, 2)

    def test_document_deferral_survives_worker_deadline_after_response_headers(self):
        def worker(command, *, stdout, timeout, **kwargs):
            metadata = {"response": {"final_url": SOURCE_URL, "http_status": 429},
                        "deferral": [86_900, "rate_limited: 429"]}
            stdout.write(json.dumps(metadata).encode() + b"\n")
            raise subprocess.TimeoutExpired(command, timeout)

        deferrals = {}
        with mock.patch.object(vs.subprocess, "run", side_effect=worker) as run, \
                mock.patch.object(vs.time, "time", return_value=86_401):
            with self.assertRaisesRegex(vs.FetchRejected, "deadline_exceeded") as error:
                vs.fetch(SOURCE_URL, robots_deferrals=deferrals)
            self.assertEqual((error.exception.final_url, error.exception.http_status), (SOURCE_URL, 429))
            with self.assertRaisesRegex(vs.FetchRejected, "rate_limited: 429") as suppressed:
                vs.fetch("https://www.kyobo.com:8443/later", robots_deferrals=deferrals)
            self.assertIsNone(suppressed.exception.final_url)
            self.assertIsNone(suppressed.exception.http_status)
            run.assert_called_once()

    def test_robots_retry_after_survives_in_the_parent_across_utc_midnight(self):
        def worker(command, *, input, stdout, **kwargs):
            vs._fetch_worker(io.BytesIO(input), stdout)

        robots_cache = functools.partial(vs.RobotsCache, clock=lambda: vs.time.time())
        for status, value, reason in (
            (429, "600", "robots_rate_limited"),
            (503, formatdate(86_900, usegmt=True), "robots_server_error"),
        ):
            robots = Response(b"wait", "text/plain", status)
            robots.headers["Retry-After"] = value
            opener = mock.Mock()
            opener.open.side_effect = [robots, Response(b"", status=404), Response(PDF)]
            deferrals = {}
            with self.subTest(status=status), mock.patch.object(vs.subprocess, "run", side_effect=worker) as run, \
                    mock.patch.object(vs.time, "time", return_value=86_300) as clock, \
                    mock.patch.object(vs, "RobotsCache", robots_cache), \
                    mock.patch.object(transport, "_build_opener", return_value=opener), \
                    mock.patch.dict(os.environ, {vs.CONTACT_ENV: CONTACT, transport.ENV_ALLOW_NETWORK: "1"}):
                with self.assertRaisesRegex(vs.FetchRejected, reason) as error:
                    vs.fetch(SOURCE_URL, robots_deferrals=deferrals)
                self.assertEqual(error.exception.deferred_until, 86_900)
                self.assertEqual(robots.read_sizes, [])

                clock.return_value = 86_401
                with self.assertRaisesRegex(vs.FetchRejected, reason):
                    vs.fetch("https://www.kyobo.com:8443/later", robots_deferrals=deferrals)
                run.assert_called_once()
                opener.open.assert_called_once()

                clock.return_value = 86_900
                self.assertEqual(vs.fetch(SOURCE_URL, robots_deferrals=deferrals)[0], PDF)
                self.assertEqual(run.call_count, 2)

    def test_crawl_delay_survives_worker_timeout_and_only_applies_to_that_host(self):
        url_other = "https://www.kbinsure.co.kr/document"
        url_same = "https://www.kyobo.com:8443/later"

        def worker(command, *, input, stdout, timeout, **kwargs):
            url, _, _, _, pacing = json.loads(input)
            self.assertEqual(pacing, [5, 105] if url == url_same else [0, 0])
            if url == SOURCE_URL:
                stdout.write(b'{"crawl_delay": 5}\n')
            elif url == url_other:
                result = {"content_type": "application/pdf", "final_url": url, "http_status": 200}
                stdout.write(json.dumps(result).encode() + b"\n" + PDF)
                return
            raise subprocess.TimeoutExpired(command, timeout)

        host_pacing = {}
        with mock.patch.object(vs.subprocess, "run", side_effect=worker), \
                mock.patch.object(vs.time, "monotonic", return_value=100) as clock:
            with self.assertRaisesRegex(vs.FetchRejected, "deadline_exceeded"):
                vs.fetch(SOURCE_URL, host_pacing=host_pacing)
            clock.return_value = 102
            self.assertEqual(vs.fetch(url_other, host_pacing=host_pacing)[0], PDF)
            with self.assertRaisesRegex(vs.FetchRejected, "deadline_exceeded"):
                vs.fetch(url_same, host_pacing=host_pacing)
            self.assertEqual(host_pacing, {"www.kyobo.com": (5, 105)})


class DetectLocalHTTPS(unittest.TestCase):
    def setUp(self):
        self.robots_status = 200
        self.robots_body = b"User-agent: *\nDisallow:\n"
        self.robots_length = None
        self.robots_range = None
        self.robots_raw_response = None
        self.server.test = self
        # Loopback hosts are admitted only in this isolated test registry.
        policy_dir = tempfile.TemporaryDirectory()
        self.addCleanup(policy_dir.cleanup)
        self.policy = Path(policy_dir.name) / "hosts.json"
        self.policy.write_text(json.dumps({"hosts": ["127.0.0.1", "localhost"]}))
        patch = mock.patch.object(vs, "SOURCE_HOST_REGISTRY", self.policy)
        patch.start()
        self.addCleanup(patch.stop)

    @classmethod
    def setUpClass(cls):
        cls.requests = []
        cls.request_headers = []
        cls.request_times = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                cls.request_times.append(time.monotonic())
                cls.requests.append(self.path)
                cls.request_headers.append(self.headers)
                if self.path == "/robots.txt":
                    raw_response = self.server.test.robots_raw_response
                    if raw_response is not None:
                        self.wfile.write(raw_response)
                        self.close_connection = True
                        return
                    status = self.server.test.robots_status
                    if not status:
                        self.close_connection = True
                        return
                    body = self.server.test.robots_body
                    length = self.server.test.robots_length
                    self.send_response(status)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body) if length is None else length))
                    if status == 302:
                        self.send_header("Location", "/must-not-fetch")
                    if self.server.test.robots_range is not None:
                        self.send_header("Content-Range", self.server.test.robots_range)
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/rate-limit":
                    self.send_response(429)
                    self.send_header("Retry-After", "600")
                    self.end_headers()
                    return
                if self.path == "/disconnect":
                    self.close_connection = True
                    return
                if self.path == "/slow-pdf":
                    time.sleep(2.0)
                targets = {"/start": "/must-not-fetch",
                           "/redirect-body": "/must-not-fetch",
                           "/relative-external": f"//localhost:{self.server.server_port}/must-not-fetch",
                           "/robots-redirect": "https://pub.insure.or.kr/must-not-fetch",
                           "/downgrade": f"http://127.0.0.1:{self.server.server_port}/must-not-fetch"}
                if self.path in targets:
                    self.send_response(302)
                    self.send_header("Location", targets[self.path])
                    if self.path == "/redirect-body":
                        self.send_header("Content-Length", str(vs.MAX_FETCH_BYTES + 1))
                    self.end_headers()
                    return
                mime = "text/html" if self.path in ("/waf", "/public") else "application/pdf"
                body = WAF if self.path in ("/waf", "/fake-pdf") else HTML if self.path == "/public" else PDF
                if self.path == "/drip":
                    body = PDF + b" " * 100
                self.send_response(403 if self.path == "/denied" else 200)
                self.send_header("Content-Type", mime)
                if self.path == "/declared-large":
                    self.send_header("Content-Length", "100000")
                elif self.path in ("/repeated-length", "/truncated-repeated-length"):
                    length = str(len(body) + (self.path == "/truncated-repeated-length"))
                    self.send_header("Content-Length", length)
                    self.send_header("Content-Length", length)
                elif self.path in ("/chunked", "/truncated-chunked"):
                    self.send_header("Transfer-Encoding", "chunked")
                    body = f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n"
                    if self.path == "/chunked":
                        body += b"\r\n"
                elif self.path != "/streamed-large":
                    self.send_header("Content-Length", str(len(body)))
                try:
                    self.end_headers()
                    if self.path == "/drip":
                        for value in body:
                            self.wfile.write(bytes([value]))
                            time.sleep(0.04)
                    else:
                        self.wfile.write(body)
                except (ConnectionError, ssl.SSLError):
                    if self.path not in ("/drip", "/slow-pdf"):
                        raise

        # Ephemeral test certificate, trusted only by this test's HTTPS client.
        # Production fetch keeps urllib's normal certificate verification enabled.
        cert_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cert_dir.cleanup)
        cert = cls.cert = Path(cert_dir.name) / "cert.pem"
        key = Path(cert_dir.name) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"],
                       check=True, capture_output=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.origin = f"https://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def run_detect(self, root, path, fmt="text_pdf", cap=vs.MAX_FETCH_BYTES, baseline="0" * 64):
        code, results = self.run_detect_rows(root, [
            {"sample_id": "source", "url": self.origin + path, "format": fmt,
             "cache_path": "source/document", "sha256": baseline},
        ], cap)
        return code, results[0]

    def run_detect_rows(self, root, rows, cap=vs.MAX_FETCH_BYTES):
        args = argparse.Namespace(raw=(root / "archive").as_uri(), out=str(root / "downloads"),
                                  archive_new=True, endpoint_url=None, report=str(root / "report.json"))
        bounded_fetch = functools.partial(vs.fetch, max_bytes=cap)
        run = subprocess.run

        def run_worker(command, **kwargs):
            self.assertEqual(command, [sys.executable, "-I", str(Path(vs.__file__).resolve()), "--fetch-worker"])
            # Start the real worker code with a test-only registry and TLS trust root.
            script = ("import sys; from pathlib import Path; "
                      "sys.path.insert(0, sys.argv[1]); import verify_sources as vs; "
                      "vs.SOURCE_HOST_REGISTRY = Path(sys.argv[2]); "
                      "vs._fetch_worker(sys.stdin.buffer, sys.stdout.buffer)")
            return run([sys.executable, "-I", "-c", script, str(vs.ROOT / "tools"), str(self.policy)], **kwargs)

        with mock.patch.object(vs, "rows", return_value=rows), \
                mock.patch.object(vs, "fetch", bounded_fetch), \
                mock.patch.object(vs.subprocess, "run", side_effect=run_worker), \
                mock.patch.object(vs, "tool_version", return_value=None), \
                mock.patch.dict("os.environ", {"SSL_CERT_FILE": str(self.cert), vs.CONTACT_ENV: CONTACT,
                                               "https_proxy": "http://127.0.0.1:1", "no_proxy": ""}), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            code = vs.cmd_detect(args)
        return code, json.loads(Path(args.report).read_text())["results"]

    def test_deadline_covers_continuously_streamed_body(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vs, "FETCH_DEADLINE_SECONDS", 1.5):
            root = Path(d)
            start = time.monotonic()
            before = len(self.requests)
            code, result = self.run_detect(root, "/drip")
            self.assertLess(time.monotonic() - start, 3.5)
            self.assertEqual(self.requests[before:], ["/robots.txt", "/drip"])
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertTrue(result["detail"].startswith("deadline_exceeded:"), result)
            self.assertEqual((result["final_url"], result["http_status"]), (self.origin + "/drip", 200))
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def test_deadline_includes_retry_backoff(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vs, "FETCH_DEADLINE_SECONDS", 1.5):
            before = len(self.requests)
            code, result = self.run_detect(Path(d), "/disconnect")
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertTrue(result["detail"].startswith("deadline_exceeded:"), result)
            self.assertEqual(self.requests[before:], ["/robots.txt", "/disconnect"])
            self.assertIsNone(result["final_url"])
            self.assertIsNone(result["http_status"])

    def test_deadline_applies_while_waiting_for_document_headers(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vs, "FETCH_DEADLINE_SECONDS", 1.5):
            before = len(self.requests)
            code, result = self.run_detect(Path(d), "/slow-pdf")
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertTrue(result["detail"].startswith("deadline_exceeded:"), result)
            self.assertEqual(self.requests[before:], ["/robots.txt", "/slow-pdf"])

    def test_live_robots_precedes_document_and_both_send_honest_ua_without_proxy(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = len(self.requests)
            code, result = self.run_detect(root, "/document?edition=2#page=1")
            self.assertEqual(self.requests[before:], ["/robots.txt", "/document?edition=2"])
            robots_headers, document_headers = self.request_headers[before:]
            for headers in (robots_headers, document_headers):
                self.assertEqual(headers["User-Agent"], build_user_agent(CONTACT))
            self.assertEqual(robots_headers["Accept"], "text/plain")
            self.assertEqual((code, result["status"], result["http_status"]), (0, "changed", 200))
            self.assertEqual(result["requested_url"], self.origin + "/document?edition=2#page=1")
            self.assertEqual(result["url"], self.origin + "/document?edition=2")
            self.assertEqual(result["final_url"], result["url"])
            self.assertEqual((root / "downloads/source/document").read_bytes(), PDF)
            observation = json.loads((root / "archive" / result["observation"]).read_text())
            for key in ("url", "final_url", "requested_url", "http_status"):
                self.assertEqual(observation[key], result[key])
            self.assertEqual((root / "archive" / observation["object_key"]).read_bytes(), PDF)

    def test_robots_disallow_redirect_forbidden_and_unreachable_only_request_robots(self):
        for status, body, reason in (
            (200, b"User-agent: *\nAllow: /\n\nUser-agent: ONJEON-SourceArchiver\nDisallow: /*.pdf$\n",
             "robots_disallow"),
            (302, b"redirect", "robots_redirect_refused"),
            (401, b"denied", "robots_forbidden"),
            (403, b"denied", "robots_forbidden"),
            (429, b"wait", "robots_rate_limited"),
            (503, b"outage", "robots_server_error"),
            (0, b"", "robots_unreachable"),
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                self.robots_status, self.robots_body = status, body
                before = len(self.requests)
                code, result = self.run_detect(root, "/document.pdf")
                self.assertEqual((code, result["status"], result["detail"]), (1, "fetch_failed", reason))
                self.assertEqual(self.requests[before:], ["/robots.txt"])
                self.assertIsNone(result["final_url"])
                self.assertIsNone(result["http_status"])
                self.assertFalse((root / "downloads").exists())
                self.assertFalse((root / "archive").exists())

    def test_missing_robots_permits_document_request(self):
        self.robots_status = 404
        with tempfile.TemporaryDirectory() as d:
            before = len(self.requests)
            code, result = self.run_detect(Path(d), "/document")
            self.assertEqual((code, result["http_status"]), (0, 200))
            self.assertEqual(self.requests[before:], ["/robots.txt", "/document"])

    def test_crawl_delay_spaces_all_requests_across_same_host_samples(self):
        self.robots_body = b"User-agent: *\nCrawl-delay: 1\n"
        rows = [{"sample_id": f"source_{i}", "url": f"{self.origin}/document-{i}", "format": "text_pdf",
                 "cache_path": f"source/document-{i}", "sha256": "0" * 64}
                for i in range(2)]
        with tempfile.TemporaryDirectory() as d:
            before = len(self.requests)
            code, results = self.run_detect_rows(Path(d), rows)
            self.assertEqual((code, [r["http_status"] for r in results]), (0, [200, 200]))
            self.assertEqual(self.requests[before:], ["/robots.txt", "/document-0", "/robots.txt", "/document-1"])
            times = self.request_times[before:]
            for previous, current in zip(times, times[1:]):
                self.assertGreaterEqual(current - previous, 1)

    def test_robots_rate_limit_defers_all_later_samples_on_the_host(self):
        self.robots_status = 429
        origins = (self.origin, self.origin, "https://127.0.0.1:1")
        rows = [{"sample_id": f"source-{i}", "url": f"{origin}/document-{i}", "format": "text_pdf",
                 "cache_path": f"source/document-{i}", "sha256": "0" * 64}
                for i, origin in enumerate(origins)]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = len(self.requests)
            code, results = self.run_detect_rows(root, rows)
            self.assertEqual(self.requests[before:], ["/robots.txt"])
            self.assertEqual(code, 1)
            self.assertEqual(len(results), len(rows))
            for result in results:
                self.assertEqual((result["status"], result["detail"]), ("fetch_failed", "robots_rate_limited"))
                self.assertIsNone(result["http_status"])
                self.assertIsNone(result["final_url"])
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def test_document_rate_limit_stops_later_robots_and_document_requests_on_host(self):
        urls = (self.origin + "/rate-limit", self.origin + "/document", "https://127.0.0.1:1/document")
        rows = [{"sample_id": f"source-{i}", "url": url, "format": "text_pdf",
                 "cache_path": f"source/document-{i}", "sha256": "0" * 64}
                for i, url in enumerate(urls)]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = len(self.requests)
            code, results = self.run_detect_rows(root, rows)
            self.assertEqual(self.requests[before:], ["/robots.txt", "/rate-limit"])
            self.assertEqual(code, 1)
            self.assertEqual([(r["status"], r["detail"]) for r in results], [("fetch_failed", "rate_limited: 429")] * 3)
            self.assertEqual((results[0]["final_url"], results[0]["http_status"]), (urls[0], 429))
            for result in results[1:]:
                self.assertIsNone(result["http_status"])
                self.assertIsNone(result["final_url"])
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def test_incomplete_robots_response_never_authorizes_document_request(self):
        self.robots_length = len(self.robots_body) + len(b"Disallow: /document\n")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = len(self.requests)
            code, result = self.run_detect(root, "/document")
            self.assertEqual(self.requests[before:], ["/robots.txt"])
            self.assertEqual((code, result["status"], result["detail"]), (1, "fetch_failed", "robots_unreachable"))
            self.assertIsNone(result["final_url"])
            self.assertIsNone(result["http_status"])
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def test_partial_robots_response_with_correct_message_length_never_authorizes_document(self):
        self.robots_status = 206
        length = len(self.robots_body)
        self.robots_range = f"bytes 0-{length - 1}/{length + len(b'Disallow: /document') + 1}"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = len(self.requests)
            code, result = self.run_detect(root, "/document")
            self.assertEqual(self.requests[before:], ["/robots.txt"])
            self.assertEqual((code, result["status"], result["detail"]), (1, "fetch_failed", "robots_unreachable"))
            self.assertIsNone(result["final_url"])
            self.assertIsNone(result["http_status"])
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def assert_robots_response_defers_host(self, raw_response):
        self.robots_raw_response = raw_response
        rows = [{"sample_id": f"source_{i}", "url": f"{self.origin}/document-{i}", "format": "text_pdf",
                 "cache_path": f"source/document-{i}", "sha256": "0" * 64} for i in range(2)]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = len(self.requests)
            code, results = self.run_detect_rows(root, rows)
            self.assertEqual(self.requests[before:], ["/robots.txt"])
            self.assertEqual(code, 1)
            self.assertEqual(len(results), len(rows))
            for result in results:
                self.assertEqual((result["status"], result["detail"]), ("fetch_failed", "robots_unreachable"))
                self.assertIsNone(result["final_url"])
                self.assertIsNone(result["http_status"])
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def test_unusable_robots_response_never_authorizes_document_request(self):
        compressed_policy = gzip.compress(b"User-agent: *\nDisallow: /document\n", mtime=0)
        disguised_html = b"\xef\xbb\xbf  \n<!DOCTYPE html><html><h1>Verify you are human</h1></html>"
        for name, headers, body in (
            ("HTML challenge", b"Content-Type: text/html; charset=utf-8\r\n", WAF),
            ("HTML declared plain text", b"Content-Type: text/plain\r\n", disguised_html),
            ("HTML without content type", b"", disguised_html),
            ("gzip policy", b"Content-Type: text/plain\r\nContent-Encoding: gzip\r\n", compressed_policy),
        ):
            with self.subTest(name=name):
                self.assert_robots_response_defers_host(
                    b"HTTP/1.1 200 OK\r\n" + headers + f"Content-Length: {len(body)}\r\n\r\n".encode() + body
                )

    def test_interrupted_robots_headers_never_authorize_document_request(self):
        for headers in (b"", b"Content-Type: text/plain\r\n", b"Content-Length: 0\r\n\r"):
            with self.subTest(headers=headers):
                self.assert_robots_response_defers_host(b"HTTP/1.1 200 OK\r\n" + headers)

    def test_interrupted_chunked_robots_response_never_authorizes_document_request(self):
        policy = b"User-agent: *\nAllow: /\n"
        prefix = (b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n"
                  + f"{len(policy):x}\r\n".encode() + policy + b"\r\n")
        for ending in (b"", b"0\r\n", b"0\r\nX-Test: example\r\n", b"0\r\n\r"):
            with self.subTest(ending=ending):
                self.assert_robots_response_defers_host(prefix + ending)

    def test_complete_chunked_robots_policy_is_honored(self):
        policy = b"\xef\xbb\xbf# comment\nUser-agent: *\nDisallow: /document\n"
        self.robots_raw_response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: Text/Plain; charset=utf-8\r\n"
            b"Content-Encoding: identity\r\nTransfer-Encoding: chunked\r\n\r\n"
            + f"{len(policy):x}\r\n".encode() + policy + b"\r\n0\r\nX-Test: example\r\n\r\n"
        )
        with tempfile.TemporaryDirectory() as d:
            before = len(self.requests)
            code, result = self.run_detect(Path(d), "/document")
            self.assertEqual(self.requests[before:], ["/robots.txt"])
            self.assertEqual((code, result["status"], result["detail"]), (1, "fetch_failed", "robots_disallow"))

    def test_robots_rules_disallow_document_request(self):
        for path, body in (
            ("/document", b"User-agent: ONJEON-SourceArchiver\nAllow: /\n\n"
             b"User-agent: onjeon-sourcearchiver\nDisallow: /document\n"),
            ("/parts%2fmanual", b"User-agent: *\nDisallow: /parts%2Fmanual\nAllow: /parts/manual\n"),
            ("/file-with-a-*.pdf", b"User-agent: *\nDisallow: /file-with-a-%2A.pdf\n"),
            ("/document?price=$", b"User-agent: *\nDisallow: /document?price=%24$\n"),
            ("/document", b"User-agent: ONJEON-SourceArchiver\nCrawl-delay: 0\n"
             b"User-agent: OtherBot\nDisallow: /document\n"),
        ):
            with self.subTest(path=path, robots=body), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                self.robots_body = body
                before = len(self.requests)
                code, result = self.run_detect(root, path)
                self.assertEqual(self.requests[before:], ["/robots.txt"])
                self.assertEqual((code, result["status"], result["detail"]), (1, "fetch_failed", "robots_disallow"))
                self.assertFalse((root / "downloads").exists())
                self.assertFalse((root / "archive").exists())

    def test_initial_http_url_fails_without_request_cache_or_archive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            before = list(self.requests)
            with mock.patch.object(self, "origin", self.origin.replace("https:", "http:")):
                code, result = self.run_detect(root, "/document")
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertTrue(result["detail"].startswith("url_disallowed"), result)
            self.assertEqual(self.requests, before)
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def test_unregistered_initial_url_and_file_fail_without_request_or_writes(self):
        for origin in (self.origin, "file:///must-not-read", "ftp://127.0.0.1"):
            with self.subTest(origin=origin), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                before = list(self.requests)
                with mock.patch.object(self, "origin", origin), mock.patch.object(
                        vs, "SOURCE_HOST_REGISTRY", vs.ROOT / "data/registry/source_fetch_hosts.json"):
                    code, result = self.run_detect(root, "/document")
                self.assertEqual((code, result["status"]), (1, "fetch_failed"))
                self.assertTrue(result["detail"].startswith("url_disallowed"), result)
                self.assertEqual(self.requests, before)
                self.assertFalse((root / "downloads").exists())
                self.assertFalse((root / "archive").exists())
                self.assertNotIn("sha256_now", result)

    def test_redirect_and_http_error_record_responding_url_without_following_or_writing(self):
        for path, status in (("/start", 302), ("/redirect-body", 302), ("/denied", 403)):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                before = len(self.requests)
                code, result = self.run_detect(root, path, cap=len(PDF))
                self.assertEqual(self.requests[before:], ["/robots.txt", path])
                self.assertEqual((code, result["status"], result["http_status"]), (1, "fetch_failed", status))
                self.assertEqual(result["requested_url"], self.origin + path)
                self.assertEqual(result["url"], self.origin + path)
                self.assertEqual(result["final_url"], result["url"])
                self.assertFalse((root / "downloads").exists())
                self.assertFalse((root / "archive").exists())

    def test_rejected_fetch_never_changes_cache_or_permanent_archive(self):
        for path, fmt, cap, reason in (
            ("/relative-external", "text_pdf", vs.MAX_FETCH_BYTES, "redirect_disallowed"),
            ("/robots-redirect", "text_pdf", vs.MAX_FETCH_BYTES, "redirect_disallowed"),
            ("/downgrade", "text_pdf", vs.MAX_FETCH_BYTES, "redirect_disallowed"),
            ("/waf", "text_pdf", vs.MAX_FETCH_BYTES, "content_type_mismatch"),
            ("/waf", "html", vs.MAX_FETCH_BYTES, "block_page"),
            ("/fake-pdf", "scanned_pdf", vs.MAX_FETCH_BYTES, "wrong_signature"),
            ("/declared-large", "text_pdf", 10, "too_large"),
            ("/streamed-large", "text_pdf", 10, "too_large"),
            ("/truncated-repeated-length", "text_pdf", vs.MAX_FETCH_BYTES, "length_mismatch"),
            ("/truncated-chunked", "text_pdf", vs.MAX_FETCH_BYTES, "length_mismatch"),
        ):
            with self.subTest(path=path, fmt=fmt), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                dest = root / "downloads/source/document"
                dest.parent.mkdir(parents=True)
                dest.write_bytes(b"prior cached document")
                marker = root / "archive/untouched"
                marker.parent.mkdir()
                marker.write_bytes(b"prior archive")
                before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
                code, result = self.run_detect(root, path, fmt, cap)
                self.assertEqual((code, result["status"]), (1, "fetch_failed"))
                self.assertTrue(result["detail"].startswith(reason), result)
                self.assertEqual(result["final_url"], self.origin + path)
                self.assertEqual(result["http_status"], 302 if reason == "redirect_disallowed" else 200)
                for key in ("sha256_now", "archived_object", "observation"):
                    self.assertNotIn(key, result)
                after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
                         if p.is_file() and p.name != "report.json"}
                self.assertEqual(before, after)
        self.assertNotIn("/must-not-fetch", self.requests)

    def test_admitted_pdf_unchanged_and_public_html_still_archive(self):
        for path, fmt, body in (("/document", "text_pdf", PDF), ("/public", "html", HTML),
                                ("/repeated-length", "text_pdf", PDF), ("/chunked", "text_pdf", PDF)):
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                code, result = self.run_detect(root, path, fmt, baseline=vs.sa.sha256_bytes(body))
                self.assertEqual((code, result["status"]), (0, "unchanged_bytes"))
                self.assertEqual((root / "downloads/source/document").read_bytes(), body)
                self.assertIn("observation", result)


if __name__ == "__main__":
    unittest.main()
