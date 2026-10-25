"""CRAWL-05: synthetic origin=fixture bytes via FakeTransport, with sockets forbidden.

No HTTP implementation is added or used here. Time, sleep and randomness are
absent from the pure adapters, so every test is deterministic and offline.
"""
import ast
import dataclasses
import re
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crawler.adapter import AdapterRegistry, DuplicateAdapterError, UnknownAdapterError  # noqa: E402
from crawler.adapters import (DirectDocumentAdapter, LinkListAdapter, LinkListConfig,  # noqa: E402
                              MemberTableAdapter, MemberTableConfig, MemberRow,
                              builtin_registry, register_adapters, registry)
from crawler.adapters import _html  # noqa: E402
from crawler.config import CrawlerConfig  # noqa: E402
from crawler.transport import BodyTooLargeError, Response, Transport  # noqa: E402
from crawler.validate import BodyStreamInfo, validate_document  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "crawler"
BASE = "https://fixture.example/disclosure/list"


class FakeTransport(Transport):
    """Only explicit routes backed by local fixtures; unknown routes fail closed."""

    def __init__(self, routes):
        self.routes = dict(routes)
        self.requests = []

    def request(self, url, headers, timeout, max_bytes):
        self.requests.append((url, dict(headers or {})))
        if url not in self.routes:
            raise AssertionError(f"unscripted fixture request: {url}")
        status, headers, body = self.routes[url]
        if isinstance(body, Path):
            body = body.read_bytes()

        def stream():
            if len(body) > max_bytes:
                raise BodyTooLargeError("fixture cap exceeded")
            for offset in range(0, len(body), 37):
                yield body[offset:offset + 37]

        return Response(status, headers, stream())


def html(body):
    return ("<!doctype html><!-- origin=fixture -->" + body).encode("utf-8")


class OfflineCase(unittest.TestCase):
    def setUp(self):
        for name in ("socket", "create_connection", "getaddrinfo"):
            patcher = mock.patch.object(socket, name, side_effect=AssertionError("sockets forbidden"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def discover(self, adapter, fixture, *, url=BASE, **kwargs):
        body = FIXTURES / fixture if isinstance(fixture, str) else fixture
        transport = FakeTransport({url: (200, {}, body)})
        with transport.request(url, {}, 1, _html.MAX_HTML_BYTES) as response:
            self.assertEqual(adapter.classify(response).kind, "ok")
            # Only tiny, capped listing fixtures are materialised by this harness.
            result = adapter.discover(b"".join(response.body_iter), url, **kwargs)
        self.assertEqual(transport.requests, [(url, {})])
        return result


class RegistryTest(OfflineCase):
    def test_three_exact_versions_and_fresh_registries(self):
        for name, cls in (("link_list", LinkListAdapter), ("member_table", MemberTableAdapter),
                          ("direct_document", DirectDocumentAdapter)):
            with self.subTest(name=name):
                self.assertIs(registry.resolve(name, cls.VERSION), cls)
                adapter = registry.resolve(name, cls.VERSION)("fixture-source")
                self.assertEqual(adapter.version, cls.VERSION)
                with self.assertRaises(UnknownAdapterError):
                    registry.resolve(name, "latest")
        first, second = builtin_registry(), builtin_registry()
        self.assertIsNot(first, second)
        self.assertIs(register_adapters(AdapterRegistry()).resolve("link_list", "1.0.0"), LinkListAdapter)
        with self.assertRaises(DuplicateAdapterError):
            register_adapters(first)

    def test_status_gaps_have_reasons_do_not_consume_or_retry(self):
        def unread():
            raise AssertionError("classification consumed body")
            yield b""

        for cls in (LinkListAdapter, MemberTableAdapter, DirectDocumentAdapter):
            adapter = cls("fixture-source")
            for status in (200, 206, 301, 401, 403, 404, 429, 500):
                with self.subTest(adapter=cls.__name__, status=status):
                    out = adapter.classify(Response(status, {}, unread()))
                    self.assertEqual(out.kind, "ok" if 200 <= status < 300 else "gap")
                    if out.kind == "gap":
                        self.assertEqual(out.reason, f"http_{status}")
            transport = FakeTransport({BASE: (403, {}, FIXTURES / "adapter_blocked.html")})
            with transport.request(BASE, {}, 1, _html.MAX_HTML_BYTES) as response:
                self.assertEqual(adapter.classify(response).reason, "http_403")
            self.assertEqual(transport.requests, [(BASE, {})])


class LinkListTest(OfflineCase):
    def test_relative_links_kinds_titles_dedup_and_host_restriction(self):
        out = self.discover(LinkListAdapter("listing"), "adapter_links.html")
        self.assertEqual(out.completeness, "complete")
        self.assertEqual([(d.url, d.kind, d.title) for d in out.documents], [
            ("https://fixture.example/files/policy.PDF", "pdf", "Fixture policy"),
            ("https://fixture.example/files/rider.hwp?edition=1&lang=ko", "hwp", "Fixture rider"),
            ("https://fixture.example/files/bundle.zip", "zip", "Fixture archive"),
            (BASE + "?page=2", "next_page", "Next"),
        ])

    def test_configured_hosts_pattern_and_suffixes(self):
        cfg = LinkListConfig(suffixes=(".pdf",), allowed_hosts=("downloads.example",),
                             href_pattern=r"/download\?id=\d+$", pattern_kind="zip")
        out = self.discover(LinkListAdapter("listing", cfg), "adapter_links.html")
        self.assertEqual([d.kind for d in out.documents], ["pdf", "pdf", "zip", "next_page"])
        self.assertIn("https://downloads.example/extra.pdf", [d.url for d in out.documents])
        self.assertIn("https://fixture.example/download?id=42", [d.url for d in out.documents])
        suffix_only = LinkListConfig(suffixes=(), href_pattern=r"/download\?id=42$", pattern_kind="hwp")
        out = self.discover(LinkListAdapter("listing", suffix_only), "adapter_links.html")
        self.assertEqual([d.kind for d in out.documents], ["hwp", "next_page"])

    def test_verified_empty_and_structure_changed_are_distinct(self):
        adapter = LinkListAdapter("listing")
        out = self.discover(adapter, "adapter_links_empty.html")
        self.assertEqual(out.completeness, "empty_ok")
        self.assertFalse(out.documents)
        for fixture in ("adapter_links_changed.html", html('<div id="documents"></div>'),
                        html('<div id="documents"><a href="a.pdf">Unclosed'),
                        html('<div id="documents"></div><div id="documents"></div>'),
                        html('<div id="documents"><a href="x.pdf" href="y.pdf">Invalid</a></div>')):
            with self.subTest(fixture=fixture):
                out = self.discover(adapter, fixture)
                self.assertEqual(out.completeness, "structure_changed")
                self.assertFalse(out.is_success)
                self.assertTrue(out.reason)

    def test_pagination_is_bounded_across_local_fixture_traversal(self):
        for max_pages, expected in ((1, "structure_changed"), (2, "complete")):
            with self.subTest(max_pages=max_pages):
                adapter = LinkListAdapter("listing", LinkListConfig(max_pages=max_pages))
                routes = {BASE: (200, {}, FIXTURES / "adapter_links.html"),
                          BASE + "?page=2": (200, {}, FIXTURES / "adapter_links_last.html")}
                transport = FakeTransport(routes)
                page, number = BASE, 1
                while page:
                    with transport.request(page, {}, 1, _html.MAX_HTML_BYTES) as response:
                        out = adapter.discover(b"".join(response.body_iter), page, page_number=number)
                    successors = [doc.url for doc in out.documents if doc.kind == "next_page"]
                    page = successors[0] if successors else None
                    number += 1
                self.assertEqual(out.completeness, expected)
                self.assertEqual(len(transport.requests), max_pages)
                if max_pages == 1:
                    self.assertEqual(out.reason, "pagination_limit")
                    self.assertEqual(len(out.documents), 3)  # retained partial evidence
        with self.assertRaises(ValueError):
            self.discover(adapter, "adapter_links_last.html", page_number=3)

    def test_next_link_by_text_and_pagination_only_page(self):
        body = html('<div id="documents"></div><a href="?page=2">다음</a>')
        out = self.discover(LinkListAdapter("listing"), body)
        self.assertEqual([(d.url, d.kind) for d in out.documents], [(BASE + "?page=2", "next_page")])

    def test_unsafe_self_or_ambiguous_successors_cannot_mark_complete(self):
        for links in ('<a rel="next" href="https://unlisted.example/list">Next</a>',
                      '<a rel="next" href="#top">Next</a>',
                      '<a rel="next" href="javascript:next()">Next</a>',
                      '<a rel="next" href="?page=2">Next</a><a rel="next" href="?page=3">Next</a>'):
            with self.subTest(links=links):
                out = self.discover(LinkListAdapter("listing"), html('<div id="documents"></div>' + links))
                self.assertEqual(out.completeness, "structure_changed")
                self.assertFalse(any(d.kind == "next_page" for d in out.documents))

    def test_configured_container_encoding_and_empty_marker(self):
        cfg = LinkListConfig(container_id="custom", empty_markers=("자료 없음",), encoding="cp949")
        body = '<!-- origin=fixture --><div id="custom">자료 없음</div>'.encode("cp949")
        self.assertEqual(self.discover(LinkListAdapter("listing", cfg), body).completeness, "empty_ok")

    def test_inline_text_entities_and_chunk_boundaries_preserve_titles(self):
        # The long title crosses the parser's 16 KiB feed boundary, without spaces.
        title = "a" * 4000
        body = html('<!--' + 'x' * 14000 + '--><div id="documents">'
                    '<a rel href="a.pdf"><span>A</span>&amp;B' + title + '</a></div>')
        out = self.discover(LinkListAdapter("listing"), body)
        self.assertEqual(out.documents[0].title, "A&B" + title)

    def test_exact_host_allowlist_never_allows_subdomains_or_credentials(self):
        cfg = LinkListConfig(allowed_hosts=("DOWNLOADS.EXAMPLE",))
        body = html('<div id="documents"><a href="https://downloads.example/a.pdf">Allowed</a>'
                    '<a href="https://sub.downloads.example/b.pdf">Unlisted</a>'
                    '<a href="https://user:pass@downloads.example/c.pdf">Credentials</a>'
                    '<a href="https://downloads.example:bad/d.pdf">Invalid port</a>'
                    '<a href="https://downloads.example/e\\file.pdf">Backslash</a></div>')
        out = self.discover(LinkListAdapter("listing", cfg), body)
        self.assertEqual([d.url for d in out.documents], ["https://downloads.example/a.pdf"])

    def test_invalid_configuration_rejected(self):
        for kwargs in ({"max_pages": 0}, {"max_pages": True}, {"max_pages": 1001},
                       {"suffixes": (".exe",)}, {"suffixes": ()}, {"href_pattern": "["},
                       {"allowed_hosts": ("https://downloads.example",)},
                       {"allowed_hosts": ("downloads.example/path",)},
                       {"allowed_hosts": ("downloads.example:443",)},
                       {"suffixes": ".pdf"}, {"empty_markers": ("",)}, {"pattern_kind": "exe"}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, re.error)):
                LinkListConfig(**kwargs)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            LinkListConfig().max_pages = 100


class MemberTableTest(OfflineCase):
    def test_rows_headers_in_source_order_and_optional_address(self):
        adapter = MemberTableAdapter("members")
        out = self.discover(adapter, "adapter_members.html")
        self.assertEqual(out.completeness, "complete")
        self.assertEqual(out.rows, (MemberRow("가상 보험", "https://company-a.example/", "합성시 예제로 1 2층"),
                                    MemberRow("테스트 보험", "https://fixture.example/company-b/")))
        self.assertEqual([(d.url, d.kind, d.title) for d in out.documents],
                         [(r.homepage, "member_homepage", r.name) for r in out.rows])
        out = self.discover(adapter, "adapter_members_no_address.html")
        self.assertEqual(out.rows, (MemberRow("가상 보험", "https://company-a.example/"),))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            out.rows[0].name = "changed"

    def test_verified_empty_and_missing_structure(self):
        adapter = MemberTableAdapter("members")
        out = self.discover(adapter, "adapter_members_empty.html")
        self.assertEqual((out.completeness, out.rows, out.documents), ("empty_ok", (), ()))
        header = '<tr><th>회사명</th><th>홈페이지</th></tr>'
        cases = ("adapter_members_changed.html", html('<p>No results</p>'),
                 html('<table id="members">' + header + '</table>'),
                 html('<div id="members">No results</div>'),
                 html('<table id="members">' + header),
                 html('<table id="members"><tr><td>No results</td></tr></table>'),
                 html('<table id="members"><tr><th colspan="2">회사명</th><th>홈페이지</th></tr>'
                      '<tr><td>X</td><td><a href="/">Home</a></td></tr></table>'),
                 html('<table id="members"><tr><th>회사명</th><th>홈페이지</th><td>Extra</td></tr>'
                      '<tr><td>X</td><td><a href="/">Home</a></td></tr></table>'))
        for body in cases:
            with self.subTest(body=body):
                out = self.discover(adapter, body)
                self.assertEqual(out.completeness, "structure_changed")
                self.assertFalse(out.is_success)
                self.assertTrue(out.reason)

    def test_bad_rows_never_make_partial_table_successful(self):
        prefix = '<table id="members"><tr><th>회사명</th><th>홈페이지</th></tr>'
        valid = '<tr><td>가상 보험</td><td><a href="/member">Home</a></td></tr>'
        for invalid in ('<tr><td>Missing homepage</td><td></td></tr>',
                        '<tr><td></td><td><a href="/member">Home</a></td></tr>',
                        '<tr><td>Bad scheme</td><td><a href="javascript:go()">Home</a></td></tr>',
                        '<tr><td>Short row</td></tr>',
                        '<tr><td colspan="2">No results</td></tr>',
                        '<tr><td rowspan="2">Merged</td><td><a href="/">Home</a></td></tr>',
                        '<tr><td>Many</td><td><a href="/a">A</a><a href="/b">B</a></td></tr>',
                        '<tr><td>Name</td><td><a href="/">Home</a></td><th>Unexpected</th></tr>',
                        '<tr><td><table><tr><td>Nested</td></tr></table></td><td>X</td></tr>'):
            with self.subTest(invalid=invalid):
                out = self.discover(MemberTableAdapter("members"), html(prefix + valid + invalid + '</table>'))
                self.assertEqual(out.completeness, "structure_changed")
                self.assertTrue(out.reason)

    def test_configured_labels_and_marker(self):
        cfg = MemberTableConfig(table_id="companies", name_header="Name", homepage_header="Site",
                                address_header="Address", empty_markers=("None found",))
        body = html('<table id="companies"><tr><th>Name</th><th>Site</th></tr>'
                    '<tr><td colspan="2">None found</td></tr></table>')
        self.assertEqual(self.discover(MemberTableAdapter("members", cfg), body).completeness, "empty_ok")
        for kwargs in ({"table_id": ""}, {"name_header": "홈페이지"}, {"empty_markers": "No results"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                MemberTableConfig(**kwargs)


class DirectDocumentTest(OfflineCase):
    def test_document_url_is_its_own_ref_and_still_requires_validation(self):
        url = "https://fixture.example/policy.PDF?edition=1#page=3"
        out = self.discover(DirectDocumentAdapter("direct"), "adapter_document.pdf", url=url)
        self.assertEqual(out.completeness, "complete")
        self.assertEqual([(d.url, d.kind) for d in out.documents], [(url.split("#")[0], "pdf")])
        transport = FakeTransport({url: (200, {"Content-Type": "application/pdf"}, FIXTURES / "adapter_document.pdf")})
        with transport.request(url, {}, 1, 4096) as response:
            self.assertTrue(validate_document(BodyStreamInfo(response.body_iter,
                            response.headers["content-type"]), out.documents[0].kind).ok)

    def test_explicit_kind_for_opaque_url_and_hwp_zip_signatures(self):
        self.assertEqual(self.discover(DirectDocumentAdapter("direct", document_kind="pdf"), "adapter_document.pdf",
                                     url=BASE + "?id=1").documents[0].kind, "pdf")
        for kind, body in (("hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 origin=fixture"),
                           ("zip", b"PK\x03\x04 origin=fixture"), ("zip", b"PK\x05\x06 origin=fixture")):
            with self.subTest(kind=kind):
                out = self.discover(DirectDocumentAdapter("direct"), body, url=BASE + "." + kind)
                self.assertEqual(out.documents[0].kind, kind)

    def test_empty_wrong_format_html_and_invalid_url_are_structure_changed(self):
        for body, url in ((b"", BASE + ".pdf"), (b"origin=fixture: wrong signature", BASE + ".pdf"),
                          (FIXTURES / "adapter_blocked.html", BASE + ".pdf"),
                          (FIXTURES / "adapter_document.pdf", BASE + ".zip"),
                          (FIXTURES / "adapter_document.pdf", BASE),
                          (FIXTURES / "adapter_document.pdf", "file:///fixture.pdf"),
                          (FIXTURES / "adapter_document.pdf", "https://fixture.example:bad/file.pdf"),
                          (FIXTURES / "adapter_document.pdf", "https://user:pass@fixture.example/file.pdf")):
            with self.subTest(url=url, body=body):
                out = self.discover(DirectDocumentAdapter("direct"), body, url=url)
                self.assertEqual(out.completeness, "structure_changed")
                self.assertFalse(out.documents)
                self.assertTrue(out.reason)
        with self.assertRaises(ValueError):
            DirectDocumentAdapter("direct", document_kind="exe")


class ParserSafetyTest(OfflineCase):
    def test_blocked_html_stops_discovery(self):
        for adapter in (LinkListAdapter("listing"), MemberTableAdapter("members")):
            out = self.discover(adapter, "adapter_blocked.html")
            self.assertEqual(out.completeness, "blocked")
            self.assertTrue(out.reason)
            self.assertFalse(out.documents)
        for cls in (LinkListAdapter, MemberTableAdapter):
            out = self.discover(cls("fixture"), html('<form><input type="password"></form>'))
            self.assertEqual(out.reason, "login_required")
            # Valueless attributes are legal HTML and must not crash discovery.
            out = self.discover(cls("fixture"), html('<input type>'))
            self.assertEqual(out.completeness, "structure_changed")

    def test_encoding_depth_node_and_text_limits_fail_closed(self):
        cases = (b"<!-- origin=fixture -->\xff", html('<![invalid[abc]]>'), html('<div>' * _html.MAX_DEPTH),
                 html('<br>' * _html.MAX_NODES),
                 html('<div id="documents"><a href="a.pdf">' + 'x' * (_html.MAX_TEXT + 1) + '</a></div>'))
        for adapter in (LinkListAdapter("listing"), MemberTableAdapter("members")):
            for body in cases:
                with self.subTest(adapter=type(adapter).__name__, size=len(body)):
                    self.assertEqual(self.discover(adapter, body).completeness, "structure_changed")

    def test_size_limit_is_checked_before_html_parsing(self):
        # A small patched cap exercises the guard without allocating huge test objects.
        with mock.patch.object(_html, "MAX_HTML_BYTES", 64), mock.patch.object(_html, "_Parser") as parser:
            for adapter in (LinkListAdapter("listing"), MemberTableAdapter("members")):
                transport = FakeTransport({BASE: (200, {}, html('x' * 64))})
                with transport.request(BASE, {}, 1, 1024) as response:
                    out = adapter.discover(b"".join(response.body_iter), BASE)
                self.assertEqual(out.reason, "html_size_limit")
            parser.assert_not_called()

    def test_direct_hard_cap_is_checked_without_copying(self):
        with mock.patch("crawler.adapters.direct_document.HARD_OBJECT_CAP_BYTES", 16):
            out = self.discover(DirectDocumentAdapter("direct"), b"%PDF- origin=fixture", url=BASE + ".pdf")
        self.assertEqual(out.reason, "document_size_limit")

    def test_invalid_source_urls_and_types(self):
        for adapter, fixture in ((LinkListAdapter("listing"), "adapter_links_last.html"),
                                 (MemberTableAdapter("members"), "adapter_members.html")):
            self.assertEqual(self.discover(adapter, fixture, url="javascript:invalid").reason, "invalid_source_url")
        for cls in (LinkListAdapter, MemberTableAdapter):
            with self.assertRaises(TypeError):
                cls("fixture", config={})
        for cls in (LinkListAdapter, MemberTableAdapter, DirectDocumentAdapter):
            with self.assertRaises(TypeError):
                cls("fixture").discover("text", BASE)

    def test_fake_transport_never_has_a_network_fallback_and_enforces_cap(self):
        transport = FakeTransport({BASE: (200, {}, FIXTURES / "adapter_document.pdf")})
        with self.assertRaises(AssertionError):
            transport.request("https://unlisted.example/", {}, 1, 1024)
        with transport.request(BASE, {}, 1, 10) as response, self.assertRaises(BodyTooLargeError):
            next(response.body_iter)


class StaticSafetyTest(unittest.TestCase):
    def test_fixture_origins_are_marked(self):
        files = list(FIXTURES.glob("adapter_*")) + [FIXTURES / "adapter_document.pdf"]
        self.assertGreaterEqual(len(files), 10)
        for path in files:
            self.assertIn(b"origin=fixture", path.read_bytes(), path.name)

    def test_adapters_are_pure_stdlib_parsers_with_no_fetch_or_identity_changes(self):
        allowed = {"codecs", "dataclasses", "html.parser", "re", "typing", "urllib.parse"}
        forbidden_calls = {"open", "read_bytes", "read_text", "write_bytes", "write_text", "request",
                           "fetch", "connect", "urlopen", "getenv", "sleep", "system", "popen"}
        root = Path(__file__).resolve().parent.parent / "crawler" / "adapters"
        for path in root.glob("*.py"):
            text = path.read_text()
            self.assertNotRegex(text, re.compile(r"proxy|proxies|vpn|rotat\w*|spoof\w*|x-forwarded|"
                                                 r"user.?agent|robots.*(?:ignore|skip)|selenium|playwright", re.I))
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Import):
                    self.assertLessEqual({a.name for a in node.names}, allowed)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module, allowed)
                elif isinstance(node, ast.Call):
                    called = getattr(node.func, "attr", getattr(node.func, "id", ""))
                    self.assertNotIn(called, forbidden_calls, f"{path.name}:{node.lineno}")
                elif isinstance(node, ast.Attribute):
                    self.assertNotEqual(node.attr, "environ")
        self.assertFalse(CrawlerConfig().network_enabled)


if __name__ == "__main__":
    unittest.main()
