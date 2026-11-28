"""Audits 2/3: bounded source admission and redirect handling before permanent writes.

Only loopback sockets and temporary local archives are used; no insurer or R2 access.
"""
import csv
import functools
import io
import json
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import verify_sources as vs


PDF = b"%PDF-1.7\nnew disclosure bytes\n%%EOF"
HTML = b"<html><title>Disclosure</title><a href='/login'>Login</a><table><tr><td>123</td></tr></table></html>"
WAF = b"<html><title>Access Denied</title><p>Your IP has been blocked</p></html>"
GEO_BLOCK = "<html><title>공지</title><p>해외&nbsp;<b>IP</b>에서의 접속이 제한됩니다.</p></html>".encode("euc-kr")
RECORDED_NOTICE = "<html><title>안내</title><p>고객센터에 문의해 주세요.</p></html>".encode()


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
                    mock.patch.object(vs.urllib.request, "build_opener", side_effect=AssertionError("opener built")), \
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
    def __init__(self, body, mime="application/pdf", url="https://www.kyobo.com/final", status=200, length=None):
        super().__init__(body)
        self.headers = Message()
        if mime is not None:
            self.headers["Content-Type"] = mime
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self.url, self.status = url, status
        self.read_sizes = []

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class RedirectPolicy(unittest.TestCase):
    def test_redirect_bodies_are_closed_unread_for_every_code_and_length(self):
        for code in (301, 302, 303, 307, 308):
            for length in (None, "invalid", 1, vs.MAX_FETCH_BYTES + 1):
                with self.subTest(code=code, length=length):
                    req = urllib.request.Request("https://www.kyobo.com/start")
                    req.timeout = 120
                    response = Response(b"untrusted redirect body", length=length)
                    headers = Message()
                    headers["Location"] = "/document"
                    handler = vs.PolicyRedirectHandler()
                    handler.parent = mock.Mock()
                    handler.parent.open.return_value = sentinel = object()
                    result = getattr(handler, f"http_error_{code}")(req, response, code, "redirect", headers)
                    self.assertIs(result, sentinel)
                    self.assertTrue(response.closed)
                    self.assertEqual(response.read_sizes, [])
                    redirected = handler.parent.open.call_args.args[0]
                    self.assertEqual(redirected.full_url, "https://www.kyobo.com/document")
                    self.assertEqual(redirected.redirect_dict, {redirected.full_url: 1})

    def test_redirect_bodies_close_on_rejection_without_opening_target(self):
        for code in (301, 302, 303, 307, 308):
            for target in ("//other.org/document", "http://www.kyobo.com/document", "file:///tmp/document"):
                with self.subTest(code=code, target=target):
                    req = urllib.request.Request("https://www.kyobo.com/start")
                    response = Response(b"untrusted redirect body")
                    headers = Message()
                    headers["Location"] = target
                    handler = vs.PolicyRedirectHandler()
                    handler.parent = mock.Mock()
                    with self.assertRaises((vs.FetchRejected, urllib.error.HTTPError)):
                        getattr(handler, f"http_error_{code}")(req, response, code, "redirect", headers)
                    handler.parent.open.assert_not_called()
                    self.assertTrue(response.closed)
                    self.assertEqual(response.read_sizes, [])

    def test_every_redirect_code_refuses_cross_origin_before_standard_handler(self):
        source = urllib.request.Request("https://www.kyobo.com/source")
        targets = (
            "https://other.org/file", "https://sub.www.kyobo.com/file", "https://www.kyobo.com.evil.org/file",
            "https://www.kbinsure.co.kr/file",  # Registered, but a different origin is still refused.
            "http://www.kyobo.com/file", "https://www.kyobo.com:444/file", "ftp://www.kyobo.com/file",
            "file:///tmp/document", "https://user@www.kyobo.com/file", "https://www.kyobo.com:bad/file",
        )
        for code in (301, 302, 303, 307, 308):
            for target in targets:
                with self.subTest(code=code, target=target), mock.patch.object(
                        urllib.request.HTTPRedirectHandler, "redirect_request") as follow:
                    fp = mock.Mock()
                    with self.assertRaises(vs.FetchRejected):
                        vs.PolicyRedirectHandler().redirect_request(source, fp, code, "redirect", {}, target)
                    follow.assert_not_called()
                    fp.close.assert_called_once()

    def test_same_origin_and_default_port_are_allowed(self):
        for code in (301, 302, 303, 307, 308):
            for target in ("https://www.kyobo.com/new?version=2", "https://WWW.KYOBO.com:443/new"):
                with self.subTest(code=code, target=target):
                    req = urllib.request.Request("https://www.kyobo.com/start")
                    new = vs.PolicyRedirectHandler().redirect_request(req, None, code, "redirect", {}, target)
                    self.assertEqual(new.full_url, target)

    def test_same_origin_redirect_still_requires_registered_host(self):
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code), mock.patch.object(
                    urllib.request.HTTPRedirectHandler, "redirect_request") as follow:
                req = urllib.request.Request("https://example.org/start")
                response = Response(b"untrusted redirect body")
                with self.assertRaisesRegex(vs.FetchRejected, "url_disallowed: host"):
                    vs.PolicyRedirectHandler().redirect_request(
                        req, response, code, "redirect", {}, "https://example.org/document")
                follow.assert_not_called()
                self.assertTrue(response.closed)
                self.assertEqual(response.read_sizes, [])

    def test_non_https_and_credentialed_initial_urls_never_open(self):
        for url in ("http://www.kyobo.com/file", "file:///tmp/document", "ftp://www.kyobo.com/file",
                    "https://user:pass@www.kyobo.com/file", "https:///file", "https://www.kyobo.com:0/file",
                    " https://www.kyobo.com/file", "https://www.kyobo.com/\nfile", "data:text/plain,body"):
            with self.subTest(url=url), \
                    mock.patch.object(vs.subprocess, "run", side_effect=AssertionError("worker started")) as run, \
                    mock.patch.object(vs.urllib.request, "build_opener", side_effect=AssertionError("opener built")):
                with self.assertRaises(vs.FetchRejected):
                    vs.fetch(url)
                run.assert_not_called()

    def test_worker_entry_point_revalidates_source_url(self):
        command = [sys.executable, "-I", str(Path(vs.__file__).resolve()), "--fetch-worker"]
        for url in ("file:///must-not-read", "data:text/plain,body", "https://localhost/"):
            with self.subTest(url=url):
                proc = subprocess.run(command, input=json.dumps([url, 1, 1024, "html"]).encode(),
                                      capture_output=True, check=True, timeout=5)
                metadata = json.loads(proc.stdout)
                self.assertEqual(metadata["error"], "FetchRejected")
                self.assertTrue(metadata["detail"].startswith("url_disallowed:"))


class ResponseAdmission(unittest.TestCase):
    def fetch_with(self, response, **kwargs):
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(vs.urllib.request, "build_opener", return_value=opener), \
                mock.patch.object(vs.time, "sleep") as sleep:
            try:
                return vs._fetch_https("https://www.kyobo.com/start", **kwargs)
            finally:
                opener.open.assert_called_once()
                sleep.assert_not_called()
                self.assertTrue(response.closed)

    def test_pdf_aliases_and_generic_download_mimes_require_pdf_signature(self):
        for fmt in ("pdf", "text_pdf", "scanned_pdf"):
            for mime in ("application/pdf", "application/octet-stream", "binary/octet-stream",
                         "Application/PDF; charset=binary"):
                with self.subTest(fmt=fmt, mime=mime):
                    result = self.fetch_with(Response(PDF, mime), expected_format=fmt)
                    self.assertEqual(result, (PDF, mime.split(";")[0].lower(), "https://www.kyobo.com/final"))

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

    def test_html_mime_requires_recognizable_markup(self):
        for body in (b"<", b"<html ", b"<html-like>text</html-like>", b"<error>Not available</error>",
                     b'<?xml version="1.0"?><error><html></html></error>',
                     b"<!-- <html>some text</html> -->"):
            with self.subTest(body=body), self.assertRaisesRegex(vs.FetchRejected, "wrong_signature"):
                self.fetch_with(Response(body, "text/html"), expected_format="html")

    def test_html_signature_accepts_bom_comments_doctype_fragments_and_xhtml(self):
        for body, mime in ((b"\xef\xbb\xbf \n<!-- note -->\n<!DOCTYPE HTML><html></html>", "text/html"),
                           (b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"/>',
                            "application/xhtml+xml"),
                           (b"<table><tr><td>Disclosure</td></tr></table>", "text/html")):
            with self.subTest(body=body, mime=mime):
                self.assertEqual(self.fetch_with(Response(body, mime), expected_format="html")[0], body)

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
            self.assertEqual(raised.exception.final_url, "https://www.kyobo.com/final")

    def test_geographic_denial_and_outage_notices_are_rejected(self):
        for body in (GEO_BLOCK, "<html><p>국외에서 접속할 수 없습니다.</p></html>".encode(),
                     "<title>해외 IP 차단 안내</title>".encode(),
                     "<title>해외 IP 접속 차단</title>".encode(),
                     "<html><p>서비스 중단 안내</p></html>".encode(),
                     b"<html><p>This site is not available in your region.</p></html>",
                     b"<html><p>Access from outside Korea is blocked.</p></html>"):
            with self.subTest(body=body), self.assertRaisesRegex(vs.FetchRejected, "block_page"):
                self.fetch_with(Response(body, "text/html"), expected_format="html")

    def test_recorded_notice_registry_is_required_for_html(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sources.csv"
            for content in (None, "unexpected,columns\nfoo,bar\n"):
                with self.subTest(content=content), mock.patch.object(vs, "SOURCE_RESPONSE_REGISTRY", path):
                    if content is not None:
                        path.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(vs.FetchRejected, "notice_registry_unavailable") as raised:
                        self.fetch_with(Response(HTML, "text/html"), expected_format="html")
                    self.assertEqual(raised.exception.final_url, "https://www.kyobo.com/final")

    def test_public_html_navigation_and_binary_pdf_words_are_not_block_pages(self):
        for mime in ("text/html; charset=utf-8", "application/xhtml+xml"):
            with self.subTest(mime=mime):
                self.assertEqual(self.fetch_with(Response(HTML, mime), expected_format="html")[0], HTML)
        pdf = PDF + b" captcha access denied login required"
        self.assertEqual(self.fetch_with(Response(pdf))[0], pdf)
        disclosure = "<html><p>해외 IP 차단 서비스 가입 안내</p><p>해외 접속 시 유의사항</p></html>".encode()
        self.assertEqual(self.fetch_with(Response(disclosure, "text/html"), expected_format="html")[0], disclosure)

    def test_unexpected_success_status_and_final_origin_are_refused_unread(self):
        for status, url, reason in ((204, "https://www.kyobo.com/final", "unexpected_status"),
                                    (206, "https://www.kyobo.com/final", "unexpected_status"),
                                    (200, "https://example.org/final", "redirect_disallowed"),
                                    (200, "https://www.kbinsure.co.kr/final", "redirect_disallowed"),
                                    (200, "http://www.kyobo.com/final", "redirect_disallowed")):
            with self.subTest(status=status, url=url):
                response = Response(PDF, url=url, status=status)
                with self.assertRaisesRegex(vs.FetchRejected, reason):
                    self.fetch_with(response)
                self.assertEqual(response.read_sizes, [])

    def test_size_limit_is_bounded_with_missing_false_or_malformed_length(self):
        for length in (None, 1, "invalid"):
            with self.subTest(length=length):
                response = Response(PDF * 20, length=length)
                with self.assertRaises(vs.FetchTooLarge):
                    self.fetch_with(response, max_bytes=10)
                self.assertEqual(sum(response.read_sizes), 11)

    def test_size_limit_cannot_be_disabled_or_raised(self):
        for cap in (0, -1, True, vs.MAX_FETCH_BYTES + 1):
            with self.subTest(cap=cap), mock.patch.object(vs.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    vs.fetch("https://www.kyobo.com/start", max_bytes=cap)
                run.assert_not_called()

    def test_default_cap_rejects_declared_oversize_without_reading(self):
        self.assertEqual(vs.MAX_FETCH_BYTES, 256 * 1024 * 1024)
        response = Response(PDF, length=vs.MAX_FETCH_BYTES + 1)
        with self.assertRaises(vs.FetchTooLarge):
            self.fetch_with(response)
        self.assertEqual(response.read_sizes, [])

    def test_streaming_cap_applies_across_multiple_chunks(self):
        cap = 1024 * 1024 + len(PDF)
        response = Response(PDF + b"x" * (cap + 100))
        with self.assertRaises(vs.FetchTooLarge):
            self.fetch_with(response, max_bytes=cap)
        self.assertEqual(response.read_sizes, [1024 * 1024, len(PDF) + 1])
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

    def test_network_failures_are_retried_but_http_errors_are_not(self):
        opener = mock.Mock()
        opener.open.side_effect = [urllib.error.URLError("offline"), Response(PDF)]
        with mock.patch.object(vs.urllib.request, "build_opener", return_value=opener), \
                mock.patch.object(vs.time, "sleep") as sleep:
            self.assertEqual(vs._fetch_https("https://www.kyobo.com/start")[0], PDF)
        self.assertEqual(opener.open.call_count, 2)
        self.assertTrue(all(c.kwargs["timeout"] == vs.FETCH_SOCKET_TIMEOUT_SECONDS
                            for c in opener.open.call_args_list))
        sleep.assert_called_once_with(2)
        opener.reset_mock()
        opener.open.side_effect = urllib.error.HTTPError("https://www.kyobo.com/start", 403, "denied", {}, None)
        with mock.patch.object(vs.urllib.request, "build_opener", return_value=opener), \
                mock.patch.object(vs.time, "sleep") as sleep:
            with self.assertRaises(urllib.error.HTTPError):
                vs._fetch_https("https://www.kyobo.com/start")
        opener.open.assert_called_once()
        sleep.assert_not_called()


class DetectLocalHTTPS(unittest.TestCase):
    def setUp(self):
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

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                cls.requests.append(self.path)
                if self.path == "/disconnect":
                    self.close_connection = True
                    return
                if self.path in ("/slow-redirect", "/slow-redirect-then-pdf"):
                    time.sleep(0.65)
                if self.path == "/slow-pdf":
                    time.sleep(1.2)
                targets = {"/start": "/middle", "/middle": "/document?edition=2",
                           "/slow-redirect": "/drip",
                           "/slow-redirect-then-pdf": "/slow-pdf",
                           "/redirect-body": "/document", "/chain-external": "/external",
                           "/relative-external": f"//localhost:{self.server.server_port}/must-not-fetch",
                           "/robots-redirect": "https://pub.insure.or.kr/must-not-fetch",
                           "/denied-start": "/denied",
                           "/downgrade": f"http://127.0.0.1:{self.server.server_port}/must-not-fetch",
                           "/external": f"http://localhost:{self.server.server_port}/must-not-fetch",
                           "/loop": "/loop"}
                if self.path in targets:
                    self.send_response(302)
                    self.send_header("Location", targets[self.path])
                    if self.path == "/redirect-body":
                        # Never send this body: following the redirect must not wait
                        # for or buffer its declared bytes, even at the default cap.
                        self.send_header("Content-Length", str(vs.MAX_FETCH_BYTES + 1))
                    self.end_headers()
                    return
                mime, body = {
                    "/waf": ("text/html", WAF),
                    "/geo-block": ("text/html", GEO_BLOCK),
                    "/notice": ("text/html", RECORDED_NOTICE),
                    "/public": ("text/html", HTML),
                    "/missing-mime": (None, HTML),
                    "/duplicate-mime": ("text/html", HTML),
                    "/fake-html": ("text/html", b"<error>Temporary response</error>"),
                    "/fake-pdf": ("application/pdf", WAF),
                }.get(self.path, ("application/pdf", PDF))
                if self.path == "/drip":
                    body = PDF + b" " * 100
                self.send_response(403 if self.path == "/denied" else 200)
                if mime is not None:
                    self.send_header("Content-Type", mime)
                if self.path == "/duplicate-mime":
                    self.send_header("Content-Type", "application/xml")
                if self.path == "/declared-large":
                    self.send_header("Content-Length", "100000")
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
        report = root / "report.json"
        argv = ["verify_sources.py", "detect", "--raw", (root / "archive").as_uri(),
                "--out", str(root / "downloads"), "--archive-new", "--report", str(report)]
        row = {"sample_id": "source", "url": self.origin + path, "format": fmt,
               "cache_path": "source/document", "sha256": baseline}
        bounded_fetch = functools.partial(vs.fetch, max_bytes=cap)
        run = subprocess.run

        def run_worker(command, **kwargs):
            self.assertEqual(command, [sys.executable, "-I", str(Path(vs.__file__).resolve()), "--fetch-worker"])
            # Start the real worker code with a test-only registry and TLS trust root.
            script = ("import sys; from pathlib import Path; "
                      "sys.path.insert(0, sys.argv[1]); import verify_sources as vs; "
                      "vs.SOURCE_HOST_REGISTRY = Path(sys.argv[2]); "
                      "vs.SOURCE_RESPONSE_REGISTRY = Path(sys.argv[3]); "
                      "vs._fetch_worker(sys.stdin.buffer, sys.stdout.buffer)")
            return run([sys.executable, "-I", "-c", script, str(vs.ROOT / "tools"), str(self.policy),
                        str(vs.SOURCE_RESPONSE_REGISTRY)], **kwargs)

        with mock.patch.object(vs, "rows", return_value=[row]), \
                mock.patch.object(vs, "fetch", bounded_fetch), \
                mock.patch.object(vs.subprocess, "run", side_effect=run_worker), \
                mock.patch.object(vs, "tool_version", return_value=None), \
                mock.patch.object(vs.shutil, "which", return_value="pdftotext"), \
                mock.patch.dict("os.environ", {"SSL_CERT_FILE": str(self.cert), "no_proxy": "127.0.0.1,localhost"}), \
                mock.patch.object(sys, "argv", argv), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            code = vs.main()
        return code, json.loads(report.read_text())["results"][0]

    def test_deadline_covers_redirect_then_continuously_streamed_body(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vs, "FETCH_DEADLINE_SECONDS", 1.5):
            root = Path(d)
            start = time.monotonic()
            before = len(self.requests)
            code, result = self.run_detect(root, "/slow-redirect")
            self.assertLess(time.monotonic() - start, 3.5)
            self.assertEqual(self.requests[before:], ["/slow-redirect", "/drip"])
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertTrue(result["detail"].startswith("deadline_exceeded:"), result)
            self.assertFalse((root / "downloads").exists())
            self.assertFalse((root / "archive").exists())

    def test_deadline_includes_retry_backoff(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vs, "FETCH_DEADLINE_SECONDS", 1.5):
            before = len(self.requests)
            code, result = self.run_detect(Path(d), "/disconnect")
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertTrue(result["detail"].startswith("deadline_exceeded:"), result)
            self.assertEqual(self.requests[before:], ["/disconnect"])

    def test_redirect_does_not_reset_deadline_for_final_response_headers(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vs, "FETCH_DEADLINE_SECONDS", 1.5):
            before = len(self.requests)
            code, result = self.run_detect(Path(d), "/slow-redirect-then-pdf")
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertTrue(result["detail"].startswith("deadline_exceeded:"), result)
            self.assertEqual(self.requests[before:], ["/slow-redirect-then-pdf", "/slow-pdf"])

    def test_redirect_chain_records_final_url_in_report_and_actual_archive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            code, result = self.run_detect(root, "/start")
            self.assertEqual((code, result["status"]), (0, "changed"))
            self.assertEqual(result["requested_url"], self.origin + "/start")
            self.assertEqual(result["url"], self.origin + "/document?edition=2")
            self.assertEqual(result["final_url"], result["url"])
            self.assertEqual((root / "downloads/source/document").read_bytes(), PDF)
            observation = json.loads((root / "archive" / result["observation"]).read_text())
            self.assertEqual(observation["url"], result["final_url"])
            self.assertEqual(observation["final_url"], result["final_url"])
            self.assertEqual(observation["requested_url"], result["requested_url"])
            self.assertEqual((root / "archive" / observation["object_key"]).read_bytes(), PDF)

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

    def test_redirected_http_error_records_final_url_without_archiving(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            code, result = self.run_detect(root, "/denied-start")
            self.assertEqual((code, result["status"]), (1, "fetch_failed"))
            self.assertEqual(result["requested_url"], self.origin + "/denied-start")
            self.assertEqual(result["url"], self.origin + "/denied")
            self.assertEqual(result["final_url"], result["url"])
            self.assertFalse((root / "downloads").exists())
            self.assertEqual(list((root / "archive").rglob("*")), [])

    def test_redirect_body_is_ignored_and_only_final_document_is_archived(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            code, result = self.run_detect(root, "/redirect-body", cap=len(PDF))
            self.assertEqual((code, result["status"]), (0, "changed"))
            self.assertEqual(result["final_url"], self.origin + "/document")
            self.assertEqual((root / "downloads/source/document").read_bytes(), PDF)
            observation = json.loads((root / "archive" / result["observation"]).read_text())
            self.assertEqual(observation["bytes"], len(PDF))
            self.assertEqual((root / "archive" / observation["object_key"]).read_bytes(), PDF)

    def test_rejected_fetch_never_changes_cache_or_permanent_archive(self):
        for path, fmt, cap, reason in (
            ("/external", "text_pdf", vs.MAX_FETCH_BYTES, "redirect_disallowed"),
            ("/chain-external", "text_pdf", vs.MAX_FETCH_BYTES, "redirect_disallowed"),
            ("/relative-external", "text_pdf", vs.MAX_FETCH_BYTES, "redirect_disallowed"),
            ("/robots-redirect", "text_pdf", vs.MAX_FETCH_BYTES, "robots_disallow"),
            ("/downgrade", "text_pdf", vs.MAX_FETCH_BYTES, "redirect_disallowed"),
            ("/loop", "text_pdf", vs.MAX_FETCH_BYTES, "HTTPError"),
            ("/waf", "text_pdf", vs.MAX_FETCH_BYTES, "content_type_mismatch"),
            ("/waf", "html", vs.MAX_FETCH_BYTES, "block_page"),
            ("/geo-block", "html", vs.MAX_FETCH_BYTES, "block_page"),
            ("/missing-mime", "html", vs.MAX_FETCH_BYTES, "content_type_mismatch"),
            ("/duplicate-mime", "html", vs.MAX_FETCH_BYTES, "content_type_mismatch"),
            ("/fake-html", "html", vs.MAX_FETCH_BYTES, "wrong_signature"),
            ("/fake-pdf", "scanned_pdf", vs.MAX_FETCH_BYTES, "wrong_signature"),
            ("/declared-large", "text_pdf", 10, "too_large"),
            ("/streamed-large", "text_pdf", 10, "too_large"),
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
                if reason in ("content_type_mismatch", "block_page", "wrong_signature", "too_large"):
                    self.assertEqual(result["final_url"], self.origin + path)
                if path in ("/geo-block", "/missing-mime", "/duplicate-mime", "/fake-html"):
                    self.assertEqual(self.requests.count(path), 1)
                for key in ("sha256_now", "archived_object", "observation"):
                    self.assertNotIn(key, result)
                after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
                         if p.is_file() and p.name != "report.json"}
                self.assertEqual(before, after)
        self.assertNotIn("/must-not-fetch", self.requests)

    def test_recorded_200_notices_are_rejected_even_when_baseline_matches(self):
        good_digest, notice_digest = map(vs.sa.sha256_bytes, (HTML, RECORDED_NOTICE))
        for status in ("200_geoblock_notice", "200_service_outage_notice"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                registry = root / "sources.csv"
                with registry.open("w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["http_status", "sha256"])
                    writer.writerow([status, notice_digest])
                    writer.writerow(["200", good_digest])
                with mock.patch.object(vs, "SOURCE_RESPONSE_REGISTRY", registry):
                    code, good = self.run_detect(root, "/public", "html")
                    self.assertEqual((code, good["status"]), (0, "changed"))
                    observation = json.loads((root / "archive" / good["observation"]).read_text())
                    self.assertEqual(observation["sha256"], good_digest)
                    self.assertEqual((root / "archive" / observation["object_key"]).read_bytes(), HTML)
                    before = {p: p.read_bytes() for p in (root / "archive").rglob("*") if p.is_file()}

                    code, rejected = self.run_detect(root, "/notice", "html", baseline=notice_digest)
                    self.assertEqual((code, rejected["status"]), (1, "fetch_failed"))
                    self.assertEqual(rejected["detail"], "block_page: matches a recorded HTTP 200 notice")
                    self.assertEqual(rejected["baseline_sha256"], notice_digest)
                    self.assertEqual(rejected["final_url"], self.origin + "/notice")
                    self.assertNotIn("sha256_now", rejected)
                    self.assertNotIn("observation", rejected)
                    self.assertEqual((root / "downloads/source/document").read_bytes(), HTML)
                    after = {p: p.read_bytes() for p in (root / "archive").rglob("*") if p.is_file()}
                    self.assertEqual(after, before)

    def test_admitted_pdf_unchanged_and_public_html_still_archive(self):
        for path, fmt, body in (("/document", "text_pdf", PDF), ("/public", "html", HTML)):
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                code, result = self.run_detect(root, path, fmt, baseline=vs.sa.sha256_bytes(body))
                self.assertEqual((code, result["status"]), (0, "unchanged_bytes"))
                self.assertEqual((root / "downloads/source/document").read_bytes(), body)
                self.assertIn("observation", result)


if __name__ == "__main__":
    unittest.main()
