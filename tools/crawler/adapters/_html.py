"""Small, bounded HTML tree and URL helpers; parsing only, never I/O.

HTML listings are capped at 1 MiB (below the crawler's 64 MiB object cap),
8192 nodes and 64 levels. No complete document is decoded alongside the tree.
"""
import codecs
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..adapter import Classification, SourceAdapter

MAX_HTML_BYTES = 1024 * 1024
MAX_NODES = 8192
MAX_DEPTH = 64
MAX_TEXT = 8192
VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())


class ParseError(ValueError):
    pass


def clean(text):
    return " ".join(text.split())


@dataclass
class Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    closed: bool = False

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def text(self):
        parts = []
        size = 0

        def visit(element):
            nonlocal size
            for child in element.children:
                if isinstance(child, Element):
                    if child.tag not in ("script", "style", "template"):
                        if child.tag in ("br", "p", "div", "td", "th", "tr"):
                            parts.append(" ")
                        visit(child)
                        if child.tag in ("p", "div", "td", "th", "tr"):
                            parts.append(" ")
                else:
                    size += len(child)
                    if size > MAX_TEXT:
                        raise ParseError("text_limit")
                    parts.append(child)

        visit(self)
        return clean("".join(parts))


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("root", closed=True)
        self.stack = [self.root]
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > MAX_NODES or len(self.stack) >= MAX_DEPTH:
            raise ParseError("html_structure_limit")
        if len(dict(attrs)) != len(attrs):
            raise ParseError("duplicate_attributes")
        node = Element(tag, dict(attrs), closed=tag in VOID)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack[i].closed = True
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(page_bytes, encoding="utf-8"):
    if not isinstance(page_bytes, bytes):
        raise TypeError("page_bytes must be bytes")
    if len(page_bytes) > MAX_HTML_BYTES:
        raise ParseError("html_size_limit")
    parser = _Parser()
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    try:
        for offset in range(0, len(page_bytes), 16384):
            parser.feed(decoder.decode(page_bytes[offset:offset + 16384]))
        parser.feed(decoder.decode(b"", final=True))
        parser.close()
    except UnicodeError:
        raise ParseError("invalid_html_encoding") from None
    except AssertionError:
        # HTMLParser raises this for malformed marked sections in untrusted HTML.
        raise ParseError("malformed_html") from None
    return parser.root


def expected_element(root, element_id, tag=None):
    found = [node for node in root.walk() if node.attrs.get("id") == element_id]
    if len(found) != 1 or not found[0].closed or (tag and found[0].tag != tag):
        raise ParseError("missing_expected_structure")
    return found[0]


def http_url(href, base_url=""):
    """Resolve without trusting HTML base tags; drop fragments for de-duplication."""
    if not isinstance(href, str) or not href.strip():
        return None
    href = href.strip()
    if any(ord(char) < 33 for char in href) or "\\" in href:
        return None
    try:
        parts = urlsplit(urljoin(base_url, href))
        host, port = parts.hostname, parts.port
        if (parts.scheme not in ("http", "https") or not host
                or parts.username is not None or parts.password is not None):
            return None
        authority = f"[{host}]" if ":" in host else host
        if port is not None and (parts.scheme, port) not in (("http", 80), ("https", 443)):
            authority += f":{port}"
        return urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))
    except ValueError:
        return None


def required_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")


def block_reason(root):
    for node in root.walk():
        if node.tag == "input" and (node.attrs.get("type") or "").lower() == "password":
            return "login_required"
        if node.tag in ("title", "h1", "p"):
            text = node.text().casefold()
            for marker in ("captcha", "verify you are human", "login required", "로그인이 필요",
                           "access denied", "접근이 차단"):
                if marker in text:
                    return "access_blocked"
    return None


class MetadataAdapter(SourceAdapter):
    """All non-2xx responses become gaps; body remains untouched for the caller."""

    VERSION = "1.0.0"

    def __init__(self, source_id):
        super().__init__(source_id, self.VERSION)

    def classify(self, response):
        if not 200 <= response.status < 300:
            return Classification("gap", f"http_{response.status}")
        return Classification("ok")
