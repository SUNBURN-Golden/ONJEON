#!/usr/bin/env python3
"""Discover public product-list metadata and emit an L0 snapshot. No archive I/O."""
import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from crawler import __version__ as crawler_version
from crawler import product_lists as lists
from crawler.adapters._html import ParseError
from crawler.config import CrawlerConfig, load_config
from crawler.hostlimit import HostRateLimiter
from crawler.polite import PoliteFetcher
from crawler.robots import RobotsCache, RobotsDecision
from crawler.transport import ENV_ALLOW_NETWORK, RefusedRequestError, TransportError, UrllibTransport
from registry_normalize import REG, atomic_write_csv, axis, disclosure_entry_reachable
from source_metadata import check_sha256, https_origin


SNAPSHOT = REG / "product_discovery.json"
VERSION = 1
EXTRA_HOSTS = {"mypage.aia.co.kr", "ec.aceinsurance.co.kr"}
RECORDED_HOLDS = {"pub.insure.or.kr", "www.idbins.com"}
# Exact aliases. Keep ambiguous association names in the manifest until reviewed.
ALIASES = {
    "한화생명": "life-hanwha", "삼성생명": "life-samsung", "교보생명": "life-kyobo",
    "흥국화재": "nonlife-heungkuk", "DB손보": "nonlife-db",
    "라이나손해보험": "nonlife-ace-chubb", "라이나손보": "nonlife-ace-chubb",
    "현대해상": "nonlife-hyundai", "삼성화재": "nonlife-samsung", "메리츠화재": "nonlife-meritz",
    "ABL생명": "life-abl", "AIA생명": "life-aia", "BNP파리바카디프생명": "life-bnpcardif",
    "교보라이프플래닛": "life-kyobo-lifeplanet", "교보라이프플래닛생명": "life-kyobo-lifeplanet",
    "iM라이프": "life-im", "미래에셋생명": "life-miraeasset", "KDB생명": "life-kdb",
    "DB생명": "life-db", "동양생명": "life-tongyang", "메트라이프생명": "life-metlife",
    "KB라이프생명": "life-kb", "신한라이프": "life-shinhan", "처브라이프생명": "life-chubb",
    "하나생명": "life-hana", "푸본현대생명": "life-fubonhyundai", "라이나생명": "life-lina",
    "NH농협생명": "life-nh", "흥국생명": "life-heungkuk",
}


@dataclass(frozen=True)
class Query:
    source: str
    scope: str
    url: str
    adapter: str
    sale_status: str = "unknown"
    params: tuple[tuple[str, str], ...] = ()
    content_type: str | None = None

    def request(self, page):
        params = dict(self.params)
        if self.adapter == "heungkuk":
            params["page"] = str(page)
        if self.content_type == "application/json":
            return self.url, json.dumps(params, separators=(",", ":")).encode("ascii")
        if self.content_type:
            return self.url, urlencode(params).encode("ascii")
        return self.url + ("?" + urlencode(params) if params else ""), None


def insurer_rows(path=REG / "insurers.csv"):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def queries(insurers):
    for family, path, group, count in (
        ("assurance", "assurance/listNew", "02440001", 11),
        ("saving", "saving/list", "02440002", 4),
    ):
        for index in range(1, count + 1):
            code = f"{group}{index:04}"
            yield Query("klia", f"{family}-{code}",
                        f"https://pub.insure.or.kr/compareDis/prodCompare/{path}.do", "klia",
                        params=(("search_prodGroup", code),))
    for path in ("assurance/listNew", "saving/list"):
        yield Query("klia", "variable-" + path.split("/")[0],
                    f"https://pub.insure.or.kr/compareDis/variableInsrn/prodCompare/{path}.do", "klia")

    for tab, codes in (
        ("1", "PB11 PB12 PB13 PB14 PB15 PB16 PB17 PB18 PB22 PB24 PB25 PB27 ELDERLY"),
        ("2", "PC11 PC12"), ("3", "PB28 PB21 PB23"), ("4", "PC99"),
    ):
        for code in codes.split():
            params = (("tabType", tab), ("tptyCode", code), ("refreshYn", ""), ("detailYn", ""),
                      ("pCode", ""), ("channel", ""), ("prdNm", ""), ("payNm", ""),
                      ("payReason", ""), ("__sort__", "1 asc"))
            yield Query("knia", code, "https://kpub.knia.or.kr/popup/disclosureList.do", "knia",
                        params=params, content_type="application/x-www-form-urlencoded")

    for row in insurers:
        if not disclosure_entry_reachable(row):
            continue
        source, entry = row["insurer_id"], row["disclosure_url"]
        if source == "life-aia":
            base = "https://mypage.aia.co.kr/AIAHomepage/disclosure/our-products"
            for scope, path, sale in (
                ("individual-on-sale", "selling/individual.do", "on_sale"),
                ("individual-discontinued", "stop-selling/individual.do", "discontinued"),
                ("rider-discontinued", "stop-selling/rider.do", "discontinued"),
            ):
                yield Query(source, scope, f"{base}/{path}", "aia", sale)
        elif source == "life-bnpcardif":
            for sale, endpoint, flag in (("on_sale", "101", "1"), ("discontinued", "201", "0")):
                for product_type in ("1", "2"):
                    yield Query(source, f"{sale}-{product_type}",
                                f"https://www.cardif.co.kr/pa/pag/rest/selectProductList{endpoint}.do",
                                "cardif", sale, (("saleYn", flag), ("productTypeId", product_type)),
                                "application/json")
        elif source == "life-kyobo-lifeplanet":
            for sale, number in (("on_sale", "11"), ("discontinued", "21")):
                yield Query(source, sale, f"https://www.lifeplanet.co.kr/disclosure/good/HPDA{number}S0.dev",
                            "lifeplanet", sale)
        elif source == "nonlife-ace-chubb":
            url = "https://ec.aceinsurance.co.kr/jsp/acelimited/notice/productNoticeV2.jsp"
            for sale, flag in (("on_sale", "Y"), ("discontinued", "N")):
                yield Query(source, sale, url, "ace", sale, (("status", flag),))
        elif source == "nonlife-heungkuk":
            for sale, mode in (("on_sale", "go"), ("discontinued", "stop")):
                for label, product_type in (("long-term", "1"), ("general", "2")):
                    yield Query(source, f"{sale}-{label}", entry, "heungkuk", sale,
                                (("mode", mode), ("type", product_type), ("searchvalue", "")))
        else:
            yield Query(source, "registered-entry", entry, "unverified")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stable_id(prefix, *parts):
    return prefix + "_" + digest(json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode("ascii"))


class ListingRobots(RobotsCache):
    """Expose the robots result while keeping the crawler's normal fetch control."""

    def check(self, url, *args, **kwargs):
        decision = super().check(url, *args, **kwargs)
        # DB publishes an unscoped Disallow: / that a standards parser ignores.
        # Retain both recorded holds even if a subsequent policy is ambiguous.
        if decision.allowed and urlsplit(url).hostname in RECORDED_HOLDS:
            decision = RobotsDecision(False, "robots_recorded_disallow")
        self.last_decision = decision
        return decision


class ListingSession:
    """Bind the transport to each planned URL and its HTTPS robots endpoint."""

    def __init__(self, config, transport, hosts):
        self.transport = transport
        self.hosts = hosts
        self.max_bytes = min(lists.MAX_LIST_BYTES, config.object_cap_bytes)
        self.robots = ListingRobots(self, transport.user_agent, ttl_s=config.robots_cache_ttl_s, timeout_s=10)
        self.fetcher = PoliteFetcher(self, self.robots, HostRateLimiter(config), config)

    def request(self, url, headers, timeout, max_bytes):
        if url not in (self.url, self.robots_url):
            raise RefusedRequestError("request outside planned listing scope")
        event = {"url": url, "method": "GET"}
        self.wire.append(event)
        try:
            if url == self.url and self.data is not None:
                event["method"] = "POST"
                response = self.transport.request_listing(
                    url, headers, timeout, max_bytes, data=self.data, content_type=self.content_type,
                )
            else:
                response = self.transport.request(url, headers, timeout, max_bytes)
        except TransportError as exc:
            event["error"] = str(exc)
            raise
        event["http_status"] = response.status
        return response

    def fetch(self, query, page):
        self.url, self.data = query.request(page)
        scheme, host, port = https_origin(self.url)
        if host not in self.hosts or port != 443 or urlsplit(self.url).fragment:
            raise ValueError(f"unregistered disclosure URL for {query.source}")
        self.robots_url = f"{scheme}://{host}/robots.txt"
        self.content_type = query.content_type
        self.wire = []
        self.robots.last_decision = None
        outcome = self.fetcher.fetch(self.url, query.source, timeout=15, max_bytes=self.max_bytes)
        decision = self.robots.last_decision
        record = {
            "page": page, "url": self.url, "observed_at": now(), "http_status": outcome.status,
            "robots": decision.reason if decision else None, "wire": self.wire,
        }
        try:
            if outcome.kind == "success":
                if outcome.status != 200:
                    return record, None, "failed", "unexpected_http_status"
                try:
                    body = b"".join(outcome.body_iter)
                except TransportError:
                    return record, None, "failed", "listing_body_read_failed"
                length = outcome.headers.get("content-length", "")
                if re.fullmatch(r"[0-9]{1,12}", length) and int(length) != len(body):
                    return record, None, "failed", "listing_content_length_mismatch"
                record.update(sha256=digest(body), bytes=len(body), content_type=outcome.headers.get("content-type", ""))
                return record, body, None, None
            if decision and not decision.allowed:
                blocked = decision.reason in {"robots_disallow", "robots_recorded_disallow", "robots_forbidden",
                                              "robots_rate_limited"}
                return record, None, "blocked" if blocked else "failed", decision.reason
            blocked = outcome.reason in {"origin_denied", "geo_blocked", "rate_limited"}
            return record, None, "blocked" if blocked else "failed", outcome.reason
        finally:
            outcome.close()


def parse(query, page, record, body):
    ct, url = record["content_type"], record["url"]
    adapter = query.adapter
    if adapter in ("cardif", "knia"):
        allowed_types = ("application/json",) if adapter == "cardif" else (
            "application/json", "text/plain", "text/html", "application/javascript",
        )
    else:
        allowed_types = ("text/html", "application/xhtml+xml")
    if ct.split(";", 1)[0].strip().lower() not in allowed_types:
        raise ParseError("unexpected_listing_media_type")
    match adapter:
        case "aia" | "ace":
            return lists.parse_version_tables(body, ct, url, adapter,
                                              rider_list=query.scope == "rider-discontinued")
        case "heungkuk":
            filters = dict(query.params)
            return lists.parse_heungkuk(body, ct, page, filters["mode"], filters["type"])
        case "cardif":
            return lists.parse_cardif(body, dict(query.params))
        case "lifeplanet":
            return lists.parse_lifeplanet(body, ct)
        case "knia":
            return lists.parse_knia(body, url)
        case "klia":
            return lists.parse_klia(body, ct)
        case "unverified":
            return lists.parse_company_table(body, ct)
        case _:
            raise ParseError("listing_adapter_unverified")


def company_index(insurers):
    allowed = {row["insurer_id"] for row in insurers if row["sector"] in ("life", "non_life")}
    names = {}
    for row in insurers:
        if row["insurer_id"] in allowed:
            name = row["name_ko"]
            if name in names:
                raise ValueError("ambiguous insurer name in registry")
            names[name] = row["insurer_id"]
    for name, company in ALIASES.items():
        if company in allowed:
            if name in names and names[name] != company:
                raise ValueError("insurer alias conflicts with registry")
            names[name] = company
    return names


def crawl_query(query, fetch, companies, max_pages):
    manifest_id = f"{query.source}/{query.scope}"
    manifest = {
        "id": manifest_id, "source_id": query.source, "scope": query.scope, "url": query.url,
        "adapter": query.adapter, "listing_sale_status": query.sale_status,
        "method": "POST" if query.content_type else "GET", "params": dict(query.params),
        "pages": [], "unmatched_companies": {}, "excluded_rows": 0, "last_page": None,
    }
    products, documents = {}, {}
    unknown = Counter()
    fingerprint_set = set()
    for page in range(1, max_pages + 1):
        record, body, state, reason = fetch(query, page)
        manifest["pages"].append(record)
        if state:
            break
        try:
            result = parse(query, page, record, body)
            if manifest["last_page"] not in (None, result.last_page):
                raise ParseError("listing_page_count_changed")
            manifest["last_page"] = result.last_page
            fingerprint = frozenset(result.products)
            if fingerprint in fingerprint_set:
                raise ParseError("listing_page_repeated")
            fingerprint_set.add(fingerprint)
        except ParseError as exc:
            state, reason = "failed", str(exc)
            break
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
            state, reason = "failed", "invalid_listing_payload"
            break

        record["source_rows"] = len(result.products) + result.excluded
        manifest["excluded_rows"] += result.excluded
        for product in result.products:
            insurer = companies.get(product.company) if product.company else query.source
            if insurer is None:
                unknown[product.company] += 1
                continue
            append_product(products, documents, manifest_id, page, insurer, product)
        if result.termination:
            state = "complete" if products else "empty_ok"
            reason = result.termination
            if unknown:
                state, reason = "partial", "unmatched_association_companies"
            break
        if result.last_page is None:
            state, reason = "partial", "listing_termination_unverified"
            break
    else:
        state, reason = "partial", "page_limit_reached"

    if (products or unknown) and state in ("blocked", "failed"):
        state = "partial"
    manifest.update(state=state, reason=reason, unmatched_companies=dict(sorted(unknown.items())),
                    product_rows=len(products), expected_document_rows=len(documents))
    return manifest, products, documents


def append_product(products, documents, manifest_id, page, insurer, product):
    product_id = stable_id("source_product", manifest_id, insurer, product.source_ref, product.name,
                           product.period, product.category, product.rider)
    if product_id not in products:
        products[product_id] = {
            "id": product_id, "manifest_id": manifest_id, "pages": [], "insurer_id": insurer,
            "name": product.name, "sale_period_as_listed": product.period, "source_ref": product.source_ref,
            "category_as_listed": product.category, "kind": "rider" if product.rider else "product",
        }
        if product.company:
            products[product_id]["company_as_listed"] = product.company
    if page not in products[product_id]["pages"]:
        products[product_id]["pages"].append(page)
    for doc in product.documents:
        doc_id = stable_id("expected_document", product_id, doc.role, doc.source_ref, doc.url)
        row = documents.setdefault(doc_id, {
            "id": doc_id, "source_product_id": product_id, "doc_role": doc.role, "pages": [],
            "source_ref": doc.source_ref, "source_url": doc.url, "acquisition_status": "unqueried",
            "discovery_status": "reference_listed" if doc.url or doc.source_ref else "reference_unresolved",
        })
        if page not in row["pages"]:
            row["pages"].append(page)


def discover(insurers, fetch, max_pages):
    companies = company_index(insurers)
    snapshot = {"version": VERSION, "crawler_version": crawler_version, "max_pages_per_scope": max_pages,
                "manifests": [], "source_products": [], "expected_documents": []}
    for query in queries(insurers):
        manifest, products, documents = crawl_query(query, fetch, companies, max_pages)
        snapshot["manifests"].append(manifest)
        snapshot["source_products"].extend(products.values())
        snapshot["expected_documents"].extend(documents.values())
    return snapshot


def refresh_registry(snapshot, insurers):
    for row in insurers:
        manifests = [m for m in snapshot["manifests"] if m["source_id"] == row["insurer_id"]]
        if not manifests:
            continue
        n = sum(m["product_rows"] for m in manifests)
        # This read-only pass establishes no complete company-wide inventory or
        # archive. Record whether the whole-list attempt is incomplete or blocked.
        if n:
            status, code = "failed", "initial_discovery_partial"
        elif all(m["state"] == "blocked" for m in manifests):
            status, code = "blocked", "initial_discovery_blocked"
        else:
            status, code = "failed", "initial_discovery_failed"
        refs = ", ".join(sorted({m["reason"] for m in manifests}))
        row.update(product_list_status=status, product_list_reason_codes=code,
                   product_list_reason=f"초기 공시 목록 관측 후보 {n}행. 전체 목록 미확정 ({refs}). product_discovery.json")
    return insurers


def validate(snapshot, insurers):
    if snapshot["version"] != VERSION or not 1 <= snapshot["max_pages_per_scope"] <= 20:
        raise ValueError("unsupported snapshot version or page limit")
    plan = {f"{q.source}/{q.scope}": q for q in queries(insurers)}
    manifests = {row["id"]: row for row in snapshot["manifests"]}
    products = {row["id"]: row for row in snapshot["source_products"]}
    documents = {row["id"]: row for row in snapshot["expected_documents"]}
    for key, index in (("manifests", manifests), ("source_products", products), ("expected_documents", documents)):
        if len(index) != len(snapshot[key]):
            raise ValueError(f"duplicate {key} ID")
    if plan.keys() != manifests.keys():
        raise ValueError("snapshot does not cover exactly the planned source scopes")
    companies = company_index(insurers)
    ids = set(companies.values())
    roles = {row["code"] for row in axis("doc_role")["values"]}
    product_counts, doc_counts = Counter(), Counter()
    products_with_docs = set()
    observed_pages = {}
    for key, manifest in manifests.items():
        query = plan[key]
        if (manifest["source_id"], manifest["scope"], manifest["url"], manifest["params"],
                manifest["listing_sale_status"], manifest["adapter"], manifest["method"]) != (
                query.source, query.scope, query.url, dict(query.params), query.sale_status, query.adapter,
                "POST" if query.content_type else "GET"):
            raise ValueError("manifest differs from source scope")
        if manifest["state"] not in ("complete", "empty_ok", "blocked", "failed", "partial") or not manifest["reason"]:
            raise ValueError("invalid manifest outcome")
        if not 1 <= len(manifest["pages"]) <= snapshot["max_pages_per_scope"]:
            raise ValueError("invalid number of listing pages")
        observed_pages[key] = set()
        for number, page in enumerate(manifest["pages"], 1):
            if page["page"] != number or page["url"] != query.request(number)[0]:
                raise ValueError("page is outside source scope")
            if "sha256" in page:
                check_sha256(page["sha256"])
                if page["http_status"] != 200 or not 0 < page["bytes"] <= lists.MAX_LIST_BYTES:
                    raise ValueError("invalid listing body evidence")
            if "source_rows" in page:
                if "sha256" not in page or page["source_rows"] < 0:
                    raise ValueError("listing rows lack body evidence")
                observed_pages[key].add(number)
        if manifest["state"] in ("complete", "empty_ok") and len(observed_pages[key]) != len(manifest["pages"]):
            raise ValueError("successful manifest contains an unparsed page")
    for row in products.values():
        manifest = manifests[row["manifest_id"]]
        if (row["insurer_id"] not in ids or not row["name"].strip() or not row["pages"]
                or not set(row["pages"]) <= observed_pages[manifest["id"]]
                or manifest["source_id"] not in ("klia", "knia", row["insurer_id"])):
            raise ValueError("product row lacks source or insurer evidence")
        if manifest["source_id"] in ("klia", "knia") and companies.get(row["company_as_listed"]) != row["insurer_id"]:
            raise ValueError("association company is unresolved")
        expected_id = stable_id("source_product", row["manifest_id"], row["insurer_id"], row["source_ref"],
                                row["name"], row["sale_period_as_listed"], row["category_as_listed"],
                                row["kind"] == "rider")
        if row["id"] != expected_id or row["kind"] not in ("product", "rider"):
            raise ValueError("invalid source product identity")
        product_counts[manifest["id"]] += 1
    for row in documents.values():
        product = products[row["source_product_id"]]
        has_reference = bool(row["source_ref"] or row["source_url"])
        if (row["doc_role"] not in roles or row["acquisition_status"] != "unqueried" or not row["pages"]
                or not set(row["pages"]) <= set(product["pages"])
                or row["discovery_status"] != ("reference_listed" if has_reference else "reference_unresolved")
                or row["id"] != stable_id("expected_document", product["id"], row["doc_role"],
                                          row["source_ref"], row["source_url"])):
            raise ValueError("invalid expected document evidence")
        if row["source_url"]:
            if https_origin(row["source_url"]) != https_origin(manifests[product["manifest_id"]]["url"]):
                raise ValueError("document references a different origin")
        doc_counts[product["manifest_id"]] += 1
        products_with_docs.add(product["id"])

    if products_with_docs != products.keys():
        raise ValueError("product row lacks an expected document")

    for key, manifest in manifests.items():
        if (manifest["product_rows"] != product_counts[key]
                or manifest["expected_document_rows"] != doc_counts[key]
                or (manifest["state"] == "complete" and not product_counts[key])
                or (manifest["state"] in ("empty_ok", "failed", "blocked") and product_counts[key])):
            raise ValueError("manifest row counts disagree with snapshot")


def write_snapshot(path, snapshot):
    # One atomic file contains manifests and both normalized sets of rows.
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            tmp = Path(f.name)
            f.write("{\n")
            for index, (name, value) in enumerate(snapshot.items()):
                if index:
                    f.write(",\n")
                f.write(f"  {json.dumps(name)}: ")
                if isinstance(value, list):
                    f.write("[")
                    for i, row in enumerate(value):
                        f.write((",\n" if i else "\n") + "    " + json.dumps(row, ensure_ascii=False))
                    f.write("\n  ]" if value else "]")
                else:
                    f.write(json.dumps(value))
            f.write("\n}\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--config", type=Path, help="crawler config for manual public list discovery")
    actions.add_argument("--check", action="store_true", help="validate a snapshot and the registry status offline")
    actions.add_argument("--sync-registry", action="store_true", help="update registry statuses from a validated snapshot")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--max-pages", type=int, default=7, choices=range(1, 21), metavar="1..20")
    args = parser.parse_args(argv)

    insurers = insurer_rows()
    try:
        if args.config:
            if args.snapshot is None:
                parser.error("manual discovery requires an explicit --snapshot output")
            config = load_config(args.config)
            if not config.network_enabled or os.environ.get(ENV_ALLOW_NETWORK) != "1":
                parser.error(f"manual discovery requires config network_enabled=true and {ENV_ALLOW_NETWORK}=1")
            hosts = set(json.loads((REG / "source_fetch_hosts.json").read_text(encoding="utf-8"))["hosts"])
            session = ListingSession(config, UrllibTransport(config), hosts | EXTRA_HOSTS)
            snapshot = discover(insurers, session.fetch, args.max_pages)
            validate(snapshot, insurers)
            write_snapshot(args.snapshot, snapshot)
        else:
            snapshot = json.loads((args.snapshot or SNAPSHOT).read_text(encoding="utf-8"))
            validate(snapshot, insurers)
            updated = refresh_registry(snapshot, [row.copy() for row in insurers])
            if args.sync_registry:
                atomic_write_csv(REG / "insurers.csv", updated)
            elif updated != insurers:
                raise ValueError("insurers.csv product-list statuses differ from snapshot")
    except (OSError, TransportError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"product discovery: {exc}\n")

    counts = Counter(m["state"] for m in snapshot["manifests"])
    print(json.dumps({"scopes": counts, "source_products": len(snapshot["source_products"]),
                      "expected_documents": len(snapshot["expected_documents"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
