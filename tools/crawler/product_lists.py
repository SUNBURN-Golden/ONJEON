"""Pure parsers for first-source company/product disclosure lists."""
import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from .adapters._html import Element, ParseError, clean, expected_element, http_url, parse_html


MAX_LIST_BYTES = 8 * 1024 * 1024
ROLES = {
    "약관": "terms", "상품약관": "terms", "특약약관": "rider_terms",
    "사업방법서": "business_method", "요약서": "summary", "상품요약서": "summary",
}
EMPTY_MESSAGES = {"해당 데이터가 없습니다.", "조회된 데이터가 없습니다.", "등록된 상품이 없습니다.",
                  "조회된 내용이 없습니다.", "조회된 내역이 없습니다."}
PDF_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,98}\.pdf", re.I)
AIA_FILE = re.compile(r"javascript:downLoad\('([^']+)',\s*'(.*)'\)\s*;?", re.I | re.S)
HEUNGKUK_FILE = re.compile(r"fn_filedownX\('/Upload/gongsi/goods/',\s*'.*',\s*'([^']+)'\);.*", re.S)


@dataclass(frozen=True)
class Document:
    role: str
    source_ref: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class Product:
    name: str
    period: str | None
    category: str | None
    source_ref: str | None
    documents: tuple[Document, ...]
    company: str | None = None
    rider: bool = False


@dataclass(frozen=True)
class Listing:
    products: tuple[Product, ...]
    termination: str | None  # None means that the list boundary is unverified.
    last_page: int | None = None
    excluded: int = 0


def elements(root, tag):
    return [node for node in root.walk() if node.tag == tag]


def html(body, content_type):
    charset = re.search(r"charset\s*=\s*[\x22']?([\w-]+)", content_type, re.I)
    encoding = charset[1].lower() if charset else "utf-8-sig"
    if encoding in ("euc-kr", "ks_c_5601-1987", "windows-949"):
        encoding = "cp949"
    if encoding not in ("utf-8", "utf-8-sig", "cp949"):
        raise ParseError("unsupported_listing_encoding")
    return parse_html(body, encoding, max_bytes=MAX_LIST_BYTES, max_nodes=100_000)


def cells(row, tag):
    return [node for node in row.children if isinstance(node, Element) and node.tag == tag]


def marked(node, name):
    return name in (node.attrs.get("class") or "").split()


def require(condition, reason):
    if not condition:
        raise ParseError(reason)


def field(value):
    require(isinstance(value, str) and 0 < len(value) <= 2000 and bool(value.strip()), "invalid_product_field")
    return clean(value)


def token(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value),
            "invalid_source_identifier")
    return value


def out_of_scope(name):
    return bool(re.search(r"단체\s*(?:신용|보험|상해|취급)|퇴직\s*연금|^자동차\s*보험", name))


def table_rows(table):
    rows = elements(table, "tr")
    require(table.closed and bool(rows) and all(row.closed for row in rows), "incomplete_listing_table")
    return [cell.text().replace(" ", "") for cell in cells(rows[0], "th")], rows[1:]


def row_is_empty(row_cells):
    return len(row_cells) == 1 and row_cells[0].text() in EMPTY_MESSAGES


def table_groups(root, parser):
    # Carry the nearest category heading in document order. Only callers' tables
    # with a recognized listing header become products.
    category = ""
    for node in root.walk():
        if node.tag in ("h2", "h3", "h4", "h5", "h6"):
            category = node.text()
        elif node.tag == "table" and parser(node):
            yield category, node


def documents_from_columns(columns, row, rider, adapter, url):
    documents = []
    for heading, cell in zip(columns, row, strict=True):
        role = ROLES.get(heading)
        if not role:
            continue
        if role == "terms" and rider:
            role = "rider_terms"
        links = elements(cell, "a")
        if not links:
            documents.append(Document(role))
        for link in links:
            href = link.attrs.get("href") or ""
            if adapter == "aia":
                match = AIA_FILE.fullmatch(href)
                require(match and PDF_NAME.fullmatch(match[1]), "unknown_aia_download_reference")
                if "기초서류 변경 안내" in match[2]:
                    role_for_link = "notice"
                else:
                    role_for_link = role
                # Two legacy server filenames embed a host address. The column
                # establishes the role without persisting that locator.
                ref = None if re.match(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}_", match[1]) else match[1]
                documents.append(Document(role_for_link, ref))
            else:
                target = http_url(href, url)
                require(target and target.startswith("https://ec.aceinsurance.co.kr/jsp/file/WebProductFiledown.jsp?"),
                        "unknown_ace_download_reference")
                documents.append(Document(role, url=target))
    return tuple(documents)


def parse_version_tables(body, content_type, url, adapter, *, rider_list=False):
    root = html(body, content_type)
    if adapter == "aia":
        groups = list(table_groups(root, lambda table: marked(table, "default-table2")))
    else:
        groups = [(name, table) for name, table in table_groups(root, lambda _: True)
                  if table_rows(table)[0][:2] == ["상품명", "판매기간"]]
    require(bool(groups), "missing_version_tables")
    products, excluded = [], 0
    for category, table in groups:
        headers, rows = table_rows(table)
        require(headers[:2] == ["상품명", "판매기간"] and "terms" in {ROLES.get(h) for h in headers},
                "unexpected_version_columns")
        require(bool(rows), "missing_version_rows")
        if len(rows) == 1 and row_is_empty(cells(rows[0], "td")):
            continue
        rider = rider_list or "제도성특약" in category.replace(" ", "")
        name, remaining = "", 0
        for row in rows:
            data = cells(row, "td")
            if remaining:
                remaining -= 1
            else:
                require(len(data) == len(headers), "invalid_version_column_count")
                product_cell, *data = data
                name = field(product_cell.text())
                span = product_cell.attrs.get("rowspan", "1") or ""
                if adapter == "ace":
                    span = span.removesuffix("'")  # source emits e.g. rowspan=2'
                require(re.fullmatch(r"[1-9][0-9]{0,5}", span), "invalid_product_rowspan")
                remaining = int(span) - 1
                require(0 <= remaining < len(rows), "invalid_product_rowspan")
            require(len(data) == len(headers) - 1, "invalid_version_column_count")
            if out_of_scope(name) or out_of_scope(category):
                excluded += 1
                continue
            period = data[0].text() or None
            docs = documents_from_columns(headers[2:], data[1:], rider, adapter, url)
            products.append(Product(name, period, category or None, None, docs, rider=rider))
        require(not remaining, "truncated_product_rowspan")
    return Listing(tuple(products), "inline_version_tables", excluded=excluded)


def parse_heungkuk(body, content_type, page, mode, product_type):
    root = html(body, content_type)
    form = expected_element(root, "frm", "form")
    filters = {node.attrs.get("name"): node.attrs.get("value") for node in elements(form, "input")}
    require(filters.get("mode") == mode and filters.get("type") == product_type
            and not filters.get("searchvalue"), "heungkuk_filter_mismatch")
    tables = elements(form, "table")
    require(len(tables) == 1, "missing_heungkuk_table")
    headers, rows = table_rows(tables[0])
    require(headers == ["구분", "판매년도", "상품명", "판매일", "첨부파일"] and rows,
            "unexpected_heungkuk_columns")
    products, excluded = [], 0
    for row in rows:
        data = cells(row, "td")
        if len(rows) == 1 and row_is_empty(data):
            break
        require(len(data) == 5, "invalid_heungkuk_row")
        category, _, name, period = [cell.text() for cell in data[:4]]
        name = field(name)
        if out_of_scope(name) or out_of_scope(category):
            excluded += 1
            continue
        docs = []
        for link in elements(data[4], "a"):
            role = ROLES.get(link.text().replace(" ", ""))
            if not role:
                continue
            ref = HEUNGKUK_FILE.fullmatch(link.attrs.get("onclick") or "")
            # The label establishes the expected role even when a historical
            # download link has no usable file locator.
            docs.append(Document(role, ref[1] if ref and PDF_NAME.fullmatch(ref[1]) else None))
        if not any(doc.role == "terms" for doc in docs):
            docs.append(Document("terms"))
        products.append(Product(name, period or None, category or None, None, tuple(docs)))
    pagination = [node for node in elements(form, "div") if marked(node, "paginate")]
    require(len(pagination) == 1, "missing_heungkuk_pagination")
    links = elements(pagination[0], "a")
    selected = [link.text() for link in links if marked(link, "on")]
    if not (products or excluded) and page == 1 and selected in ([], ["1"]):
        return Listing((), "explicit_empty_row")
    require(selected == [str(page)], "heungkuk_page_number_mismatch")
    last = [link.attrs.get("href") for link in links if marked(link, "go_end")]
    require(len(last) == 1, "missing_heungkuk_last_page")
    if last[0]:
        match = re.fullmatch(r"javascript:goPage\(([1-9][0-9]{0,5})\);", last[0])
        require(match and int(match[1]) >= page, "invalid_heungkuk_last_page")
        last_page = int(match[1])
    else:
        require(not any(marked(link, "go_next") and link.attrs.get("href") for link in links),
                "heungkuk_next_without_last_page")
        last_page = page
    return Listing(tuple(products), "pagination_last_page" if last_page == page else None, last_page, excluded)


def parse_cardif(body, filters):
    obj = json.loads(body)
    require(obj["resultCode"] == 1, "cardif_listing_error")
    result = obj["data"]["result"]
    rows = result["productList"]
    require(isinstance(rows, list), "invalid_cardif_product_list")
    products, excluded = [], 0
    for row in rows:
        require(row["sellable"] == filters["saleYn"] and row["producttypeid"] == filters["productTypeId"],
                "cardif_filter_mismatch")
        name = field(row["productname"])
        if out_of_scope(name):
            excluded += 1
            continue
        # The list's product ID is distinct from the product code and sale edition.
        products.append(Product(name, None, filters["productTypeId"], token(row["productid"]),
                                tuple(Document(role) for role in ("terms", "business_method", "summary"))))
    return Listing(tuple(products), "product_list_array", excluded=excluded)


def parse_lifeplanet(body, content_type):
    root = html(body, content_type)
    scripts = [node for node in elements(root, "script") if node.closed]
    payloads = []
    for script in scripts:
        content = "".join(child for child in script.children if isinstance(child, str))
        for match in re.finditer(r"\bvar\s+result\s*=\s*(?=\{)", content):
            try:
                data, _ = json.JSONDecoder().raw_decode(content[match.end():])
            except ValueError:
                continue
            if isinstance(data.get("outData"), dict) and "prdList" in data["outData"]:
                payloads.append(data["outData"]["prdList"])
    require(len(payloads) == 1 and isinstance(payloads[0], list), "missing_lifeplanet_product_list")
    products, excluded = [], 0
    for row in payloads[0]:
        name = field(row["prdNm"])
        if out_of_scope(name):
            excluded += 1
            continue
        start, end = field(row["saleStYmd"]), field(row["saleEdYmd"])
        docs = []
        for key, role in (("insTxtPat", "terms"), ("prdMdPat", "business_method"), ("prdSryPat", "summary")):
            ref = row.get(key)
            require(not ref or isinstance(ref, str) and PDF_NAME.fullmatch(ref), "invalid_lifeplanet_file_reference")
            docs.append(Document(role, ref or None))
        products.append(Product(name, f"{start} ~ {end}", row.get("intyCd"), token(row["prdCd"]), tuple(docs)))
    return Listing(tuple(products), "embedded_product_list_array", excluded=excluded)


# The KNIA endpoint returns a JS data literal, not executable code. Only tokens in
# this JSON-shaped subset are admitted. No evaluation or object hooks execute it.
JS_TOKEN = re.compile(
    r"""\s*(?:(?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')"""
    r"""|(?P<word>[A-Za-z_$][A-Za-z0-9_$]*)|(?P<punc>[{}\[\]:,])"""
    r"""|(?P<number>-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?))""", re.S)
JS_ESCAPE = re.compile(r"\\(?:u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[\\/'\"bfnrt])")
JS_COLON = re.compile(r"\s*:")


def js_data(body):
    text = body.decode("utf-8-sig").strip()
    parts, index = [], 0
    while index < len(text):
        match = JS_TOKEN.match(text, index)
        require(match is not None, "unexpected_knia_literal_token")
        index = match.end()
        value = match.group(match.lastgroup)
        if match.lastgroup == "string":
            decoded = []
            inner, start = value[1:-1], 0
            while (escape := inner.find("\\", start)) >= 0:
                decoded.append(inner[start:escape])
                escaped = JS_ESCAPE.match(inner, escape)
                require(escaped is not None, "unsupported_knia_string_escape")
                code = escaped[0][1:]
                if code.startswith(("x", "u")):
                    decoded.append(chr(int(code[1:], 16)))
                else:
                    decoded.append({"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}.get(code, code))
                start = escaped.end()
            parts.append(json.dumps("".join(decoded) + inner[start:]))
        elif match.lastgroup == "word" and JS_COLON.match(text, index):
            parts.append(json.dumps(value))
        else:
            require(match.lastgroup != "word" or value in ("true", "false", "null"),
                    "unexpected_knia_literal_identifier")
            parts.append(value)
    return json.loads("".join(parts))


def parse_knia(body, url):
    rows = js_data(body)["list"]
    require(isinstance(rows, list), "missing_knia_list")
    products, excluded = [], 0
    for row in rows:
        company, name = field(row["P_CODE_NM"]), field(row["TP_NAME"])
        if out_of_scope(name):
            excluded += 1
            continue
        code = token(row["TP_CODE"])
        docs = [Document("terms")]
        summary = row.get("SUMMARY_SEQ")
        if summary not in (None, "", 0, "0"):
            require(re.fullmatch(r"[1-9][0-9]{0,11}", str(summary)), "invalid_knia_summary_reference")
            docs.append(Document("summary", str(summary), http_url(f"/file/download/{summary}.do", url)))
        products.append(Product(name, None, None, code, tuple(docs), company=company))
    return Listing(tuple(products), "single_comparison_array", excluded=excluded)


def parse_klia(body, content_type):
    root = html(body, content_type)
    headers_by_name = {"보험회사": "company", "보험회사명": "company", "회사명": "company",
                       "상품명": "product", "보험상품명": "product"}
    products, excluded = [], 0
    matched = False
    for table in elements(root, "table"):
        headers, rows = table_rows(table)
        columns = [headers_by_name.get(heading) for heading in headers]
        if "company" not in columns or "product" not in columns:
            continue
        matched = True
        for row in rows:
            data = cells(row, "td")
            if len(rows) == 1 and row_is_empty(data):
                continue
            require(len(data) == len(columns), "invalid_klia_columns")
            company = field(data[columns.index("company")].text())
            name = field(data[columns.index("product")].text())
            if out_of_scope(name):
                excluded += 1
                continue
            products.append(Product(name, None, None, None, (Document("terms"),), company=company))
    require(matched and (products or excluded), "klia_comparison_rows_unverified")
    # We have no live pagination contract for this robots-disallowed source.
    return Listing(tuple(products), None, excluded=excluded)


def parse_company_table(body, content_type):
    """Retain explicit version-table rows when a registered entry serves them directly."""
    products, excluded = [], 0
    for category, table in table_groups(html(body, content_type), lambda _: True):
        headers, rows = table_rows(table)
        if headers[:2] != ["상품명", "판매기간"] or not any(h in ROLES for h in headers[2:]):
            continue
        require(len(headers) == len(set(headers)), "ambiguous_company_table_columns")
        for row in rows:
            data = cells(row, "td")
            if len(rows) == 1 and row_is_empty(data):
                continue
            require(len(data) == len(headers), "invalid_company_table_row")
            if any("rowspan" in cell.attrs for cell in data):
                raise ParseError("unsupported_company_table_rowspan")
            name = field(data[0].text())
            if out_of_scope(name) or out_of_scope(category):
                excluded += 1
                continue
            roles = [ROLES[heading] for heading in headers[2:] if heading in ROLES]
            products.append(Product(name, data[1].text() or None, category or None, None,
                                    tuple(Document(role) for role in roles)))
    require(products or excluded, "company_listing_structure_unverified")
    return Listing(tuple(products), None, excluded=excluded)
