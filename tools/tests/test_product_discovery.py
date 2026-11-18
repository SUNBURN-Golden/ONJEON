"""First-source L0 discovery, from permission checks to ExpectedDocument rows."""
import copy
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import enumerate_products as ep
from crawler import product_lists as pl
from crawler.adapters._html import ParseError
from crawler.config import CrawlerConfig
from crawler.transport import Response, TransportError


HTML = "text/html; charset=utf-8"
VERSION_HEADER = "<tr><th>상품명</th><th>판매기간</th><th>약관</th></tr>"
AIA_URL = "https://mypage.aia.co.kr/list"
ACE_URL = "https://ec.aceinsurance.co.kr/list"
QUERY = ep.Query("nonlife-heungkuk", "on_sale-long-term",
                 "https://www.heungkukfire.co.kr/FRW/announce/insGoodsGongsiSale.do",
                 "heungkuk", "on_sale", (("mode", "go"), ("type", "1"), ("searchvalue", "")))


def heungkuk(selected, last, name="건강보험"):
    return f"""
    <form id="frm"><input name="mode" value="go"><input name="type" value="1">
      <table><tr><th>구분</th><th>판매년도</th><th>상품명</th><th>판매일</th><th>첨부파일</th></tr>
        <tr><td>건강</td><td>2026</td><td>{name}</td><td>2026-01-01</td>
          <td><a onclick="fn_filedownX('/Upload/gongsi/goods/','name.pdf', 'FILE.pdf'); return false;">상품약관</a></td>
        </tr></table>
      <div class="paginate"><a class="on">{selected}</a><a class="go_end" href="javascript:goPage({last});"></a></div>
    </form>
    """.encode()


def fetched(query, page, body, content_type=HTML):
    return {
        "page": page, "url": query.request(page)[0], "content_type": content_type,
        "sha256": ep.digest(body), "bytes": len(body), "http_status": 200,
    }, body, None, None


class Parsers(unittest.TestCase):
    def test_aia_rowspan_legacy_locator_and_missing_reference(self):
        body = f"""
        <h3>제도성특약</h3><table class="default-table2">{VERSION_HEADER}
        <tr><td rowspan="2">암특약</td><td>20260101 ~ 현재</td><td>
        <a href="javascript:downLoad('OK.pdf', '형1.pdf')"></a>
        <a href="javascript:downLoad('OK2.pdf', '형2.pdf')"></a>
        </td></tr>
        <tr><td>20250101 ~ 20251231</td><td>
        <a href="javascript:downLoad('192.0.2.1_old.pdf', '특약.pdf')"></a></td></tr>
        <tr><td>다른 특약</td><td>알 수 없음</td><td></td></tr>
        </table>""".encode("cp949")
        result = pl.parse_version_tables(body, "text/html;charset=EUC-KR", AIA_URL, "aia")
        self.assertEqual(result.termination, "inline_version_tables")
        a, b, c = result.products
        self.assertEqual((a.name, b.name, b.period), ("암특약", "암특약", "20250101 ~ 20251231"))
        self.assertTrue(all(row.rider for row in result.products))
        self.assertEqual(a.documents, (pl.Document("rider_terms", "OK.pdf"), pl.Document("rider_terms", "OK2.pdf")))
        self.assertEqual(b.documents, c.documents)
        self.assertEqual(c.documents, (pl.Document("rider_terms"),))
        with self.assertRaisesRegex(ParseError, "invalid_version_column_count"):
            pl.parse_version_tables(body.replace(b'rowspan="2"', b'rowspan="3"'),
                                    "text/html;charset=EUC-KR", AIA_URL, "aia")

    def test_ace_preserves_versions_and_rejects_foreign_download_url(self):
        link = "/jsp/file/WebProductFiledown.jsp?fileType=2&amp;fileName=ok.pdf"
        body = f"""
        <table>{VERSION_HEADER}
        <tr><td rowspan=2'>건강보험</td><td>2026-01-01</td><td><a href="{link}">다운로드</a></td></tr>
        <tr><td>2025-01-01</td><td></td></tr>
        <tr><td>자동차보험</td><td>2024-01-01</td><td></td></tr>
        </table>""".encode()
        result = pl.parse_version_tables(body, HTML, ACE_URL, "ace")
        self.assertEqual(result.excluded, 1)
        self.assertEqual([product.period for product in result.products], ["2026-01-01", "2025-01-01"])
        self.assertEqual(result.products[0].documents[0].url,
                         "https://ec.aceinsurance.co.kr/jsp/file/WebProductFiledown.jsp?fileType=2&fileName=ok.pdf")
        with self.assertRaisesRegex(ParseError, "unknown_ace_download_reference"):
            pl.parse_version_tables(body.replace(b'/jsp/file/', b'https://example.invalid/jsp/file/'),
                                    HTML, ACE_URL, "ace")

    def test_empty_needs_an_explicit_source_row(self):
        page = f'<table class="default-table2">{VERSION_HEADER}<tr><td>해당 데이터가 없습니다.</td></tr></table>'
        result = pl.parse_version_tables(page.encode(), HTML, AIA_URL, "aia")
        self.assertEqual(result.products, ())
        with self.assertRaisesRegex(ParseError, "missing_version_rows"):
            pl.parse_version_tables(f'<table class="default-table2">{VERSION_HEADER}</table>'.encode(),
                                    HTML, AIA_URL, "aia")

    def test_cardif_keeps_source_ids_and_leaves_versions_unresolved(self):
        filters = {"saleYn": "1", "productTypeId": "2"}
        row = {"productid": "0123", "productname": "건강보험", "sellable": "1",
               "producttypeid": "2", "unused": "mock session must not be emitted"}
        body = {"resultCode": 1, "data": {"result": {"productList": [row, dict(row, productname="단체신용보험")]}}}
        result = pl.parse_cardif(json.dumps(body).encode(), filters)
        self.assertEqual(result.excluded, 1)
        self.assertEqual(result.products[0].source_ref, "0123")
        self.assertIsNone(result.products[0].period)
        self.assertEqual(len(result.products[0].documents), 3)
        self.assertTrue(all(doc.source_ref is None and doc.url is None for doc in result.products[0].documents))
        with self.assertRaisesRegex(ParseError, "cardif_filter_mismatch"):
            pl.parse_cardif(json.dumps(body).encode(), dict(filters, saleYn="0"))

    def test_lifeplanet_uses_embedded_sale_period_and_source_file(self):
        payload = {"outData": {"prdList": [{"prdNm": "건강보험", "prdCd": "1001", "intyCd": "x",
                                           "saleStYmd": "20260101", "saleEdYmd": "99991231",
                                           "insTxtPat": "20260101_1001_03.pdf"}]}}
        body = f"<script>var result = {json.dumps(payload)}; function render() {{}}</script>".encode()
        result = pl.parse_lifeplanet(body, HTML)
        self.assertEqual(result.products[0].period, "20260101 ~ 99991231")
        self.assertEqual(result.products[0].documents[0], pl.Document("terms", "20260101_1001_03.pdf"))
        with self.assertRaisesRegex(ParseError, "missing_lifeplanet_product_list"):
            pl.parse_lifeplanet(b"<script>var result = {};</script>", HTML)

    def test_association_sources_keep_company_identity_and_distinct_codes(self):
        url = "https://kpub.knia.or.kr/popup/disclosureList.do"
        literal = """{list:[
        {P_CODE_NM:'흥국화재', TP_NAME:'암\n보험 \\'형\\'', TP_CODE:'N32PB14A', SUMMARY_SEQ:'12'},
        {P_CODE_NM:'흥국화재', TP_NAME:'암 보험 \\'형\\'', TP_CODE:'N32PB14B', SUMMARY_SEQ:''}
        ]}""".encode()
        result = pl.parse_knia(literal, url)
        self.assertEqual([p.name for p in result.products], ["암 보험 '형'", "암 보험 '형'"])
        self.assertEqual([p.source_ref for p in result.products], ["N32PB14A", "N32PB14B"])
        self.assertEqual(result.products[0].documents[1].url, "https://kpub.knia.or.kr/file/download/12.do")
        with self.assertRaises(ParseError):
            pl.parse_knia(b"{list:loadProducts()}", url)
        table = "<table><tr><th>보험회사</th><th>보험상품명</th></tr><tr><td>AIA생명</td><td>암보험</td></tr></table>"
        result = pl.parse_klia(table.encode(), HTML)
        self.assertIsNone(result.termination)
        self.assertEqual(result.products[0].company, "AIA생명")

    def test_generic_entry_requires_a_version_table_with_document_roles(self):
        with self.assertRaisesRegex(ParseError, "company_listing_structure_unverified"):
            pl.parse_company_table(b"<html><title>Public disclosures</title></html>", HTML)
        body = f"<table>{VERSION_HEADER}<tr><td>보험</td><td>2026</td><td></td></tr></table>"
        result = pl.parse_company_table(body.encode(), HTML)
        self.assertEqual(result.products[0].documents, (pl.Document("terms"),))
        self.assertIsNone(result.termination)


class Manifest(unittest.TestCase):
    def test_pagination_cap_failure_and_success_have_distinct_evidence(self):
        def fetch(query, number):
            return fetched(query, number, heungkuk(number, 2, name=f"보험 {number}"))

        partial, products, docs = ep.crawl_query(QUERY, fetch, {}, 1)
        self.assertEqual((partial["state"], partial["reason"], partial["last_page"]),
                         ("partial", "page_limit_reached", 2))
        full, all_products, all_docs = ep.crawl_query(QUERY, fetch, {}, 2)
        self.assertEqual((full["state"], full["reason"], full["expected_document_rows"]),
                         ("complete", "pagination_last_page", 2))
        self.assertTrue(products.keys() <= all_products.keys())
        self.assertTrue(docs.keys() <= all_docs.keys())
        self.assertTrue(all(row["acquisition_status"] == "unqueried" for row in all_docs.values()))

        def repeated(query, number):
            return fetched(query, number, heungkuk(number, 2))

        manifest, products, _ = ep.crawl_query(QUERY, repeated, {}, 2)
        self.assertEqual((manifest["state"], manifest["reason"], len(products)),
                         ("partial", "listing_page_repeated", 1))

        def blocked(query, page):
            if page == 1:
                return fetch(query, page)
            return {"page": page}, None, "blocked", "rate_limited"

        manifest, products, _ = ep.crawl_query(QUERY, blocked, {}, 2)
        self.assertEqual((manifest["state"], manifest["reason"], len(products)), ("partial", "rate_limited", 1))

    def test_company_mismatch_is_a_gap_and_keeps_known_products(self):
        query = ep.Query("knia", "PB15", "https://kpub.knia.or.kr/popup/disclosureList.do", "knia")
        raw = """{list:[
        {P_CODE_NM:'흥국화재', TP_NAME:'암보험', TP_CODE:'N32PB14A'},
        {P_CODE_NM:'미등록 보험사', TP_NAME:'건강보험', TP_CODE:'N99PB14B'}
        ]}""".encode()
        result, products, docs = ep.crawl_query(
            query, lambda q, n: fetched(q, n, raw, "text/plain"), {"흥국화재": "nonlife-heungkuk"}, 1,
        )
        self.assertEqual(result["unmatched_companies"], {"미등록 보험사": 1})
        self.assertEqual(result["state"], "partial")
        self.assertEqual(next(iter(products.values()))["company_as_listed"], "흥국화재")
        self.assertEqual(next(iter(docs.values()))["discovery_status"], "reference_unresolved")


class TransportBoundaries(unittest.TestCase):
    def setUp(self):
        self.transport = Mock(user_agent="ONJEON-SourceArchiver/0.1 (+https://example.invalid/)")
        self.config = CrawlerConfig(contact="https://example.invalid/", per_host_min_interval_s=1, max_attempts=1)
        self.query = next(q for q in ep.queries(ep.insurer_rows()) if q.source == "knia")
        self.session = ep.ListingSession(self.config, self.transport, {"kpub.knia.or.kr"})
        # Use the normal limiter with a deterministic clock.
        seconds = [0.]
        self.session.fetcher._limiter._clock = lambda: seconds[0]
        self.session.fetcher._limiter._sleep = lambda delay: seconds.__setitem__(0, seconds[0] + delay)

    def test_robots_denial_and_transport_error_prevent_listing_post(self):
        self.transport.request.return_value = Response(403, {}, iter(()))
        first, body, state, reason = self.session.fetch(self.query, 1)
        self.assertEqual((body, state, reason), (None, "blocked", "robots_forbidden"))
        self.assertEqual(first["wire"][0]["http_status"], 403)
        self.session.fetch(self.query, 1)
        self.transport.request.assert_called_once()
        self.transport.request_listing.assert_not_called()

        self.transport.reset_mock()
        self.transport.request.side_effect = TransportError("request failed: URLError(SSLEOFError)")
        session = ep.ListingSession(self.config, self.transport, {"kpub.knia.or.kr"})
        record, body, state, reason = session.fetch(self.query, 1)
        self.assertEqual((body, state, reason), (None, "failed", "robots_unreachable"))
        self.assertIn("SSLEOFError", record["wire"][0]["error"])
        self.transport.request_listing.assert_not_called()

    def test_allowed_knia_uses_fixed_post_and_keeps_http_evidence(self):
        self.transport.request.return_value = Response(404, {}, iter(()))
        body = b"{list:[]}"
        self.transport.request_listing.return_value = Response(200, {"content-type": "text/plain"}, iter((body,)))
        record, result, state, reason = self.session.fetch(self.query, 1)
        self.assertEqual((result, state, reason), (body, None, None))
        self.assertEqual(record["sha256"], ep.digest(body))
        self.assertEqual([event["method"] for event in record["wire"]], ["GET", "POST"])
        self.assertIn(b"tabType=1&tptyCode=PB11", self.transport.request_listing.call_args.kwargs["data"])
        self.assertEqual(ep.parse(self.query, 1, record, body).products, ())

    def test_cross_origin_and_http_requests_are_refused_before_wire(self):
        for url in ("http://kpub.knia.or.kr/list", "https://evil.invalid/list", "https://kpub.knia.or.kr:444/list"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.session.fetch(ep.Query("knia", "other", url, "knia"), 1)
        self.transport.request.assert_not_called()
        self.transport.request_listing.assert_not_called()

    def test_read_failure_cannot_emit_rows(self):
        self.transport.request.return_value = Response(404, {}, iter(()))
        self.transport.request_listing.return_value = Response(
            200, {"content-type": "text/plain", "content-length": "20"}, iter((b"{list:[]}",)),
        )
        record, body, state, reason = self.session.fetch(self.query, 1)
        self.assertEqual((body, state, reason), (None, "failed", "listing_content_length_mismatch"))
        self.assertNotIn("sha256", record)


class CommittedEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(ep.SNAPSHOT.read_text(encoding="utf-8"))
        cls.insurers = ep.insurer_rows()

    def test_snapshot_validates_and_has_real_rows_and_recorded_gaps(self):
        ep.validate(self.snapshot, self.insurers)
        self.assertEqual(ep.refresh_registry(self.snapshot, [r.copy() for r in self.insurers]), self.insurers)
        self.assertEqual(len(self.snapshot["source_products"]), 5213)
        self.assertEqual(len(self.snapshot["expected_documents"]), 11938)
        manifests = self.snapshot["manifests"]
        self.assertEqual({m["source_id"] for m in manifests if m["product_rows"]},
                         {"life-aia", "life-bnpcardif", "nonlife-ace-chubb", "nonlife-heungkuk"})
        self.assertEqual(Counter(m["state"] for m in manifests), Counter(blocked=37, complete=10, failed=6, partial=1))
        for assoc, reason in (("klia", "robots_disallow"), ("knia", "robots_forbidden")):
            runs = [m for m in manifests if m["source_id"] == assoc]
            self.assertTrue(runs)
            for manifest in runs:
                self.assertEqual(manifest["reason"], reason)
                self.assertTrue(all(event["url"].endswith("/robots.txt")
                                    for page in manifest["pages"] for event in page["wire"]))

    def test_snapshot_refuses_missing_source_evidence_or_archive_claim(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["manifests"].pop(0)
        with self.assertRaisesRegex(ValueError, "planned source scopes"):
            ep.validate(snapshot, self.insurers)

        snapshot = copy.deepcopy(self.snapshot)
        snapshot["expected_documents"][0]["acquisition_status"] = "archived"
        with self.assertRaisesRegex(ValueError, "invalid expected document evidence"):
            ep.validate(snapshot, self.insurers)


if __name__ == "__main__":
    unittest.main()
