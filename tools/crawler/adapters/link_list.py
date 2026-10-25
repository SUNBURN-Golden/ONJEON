"""Configured disclosure links, with one forward pagination edge per page.

The caller supplies the 1-based page_number on every discovery and increments it
when following next_page. At max_pages, an unvisited successor makes discovery
structure_changed with pagination_limit, never a falsely complete manifest.
Adapters neither follow links nor keep traversal state. Callers also de-duplicate
visited page URLs across a crawl; a self-link is rejected here.
"""
import codecs
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..adapter import DiscoveryManifest, DocumentRef
from ._html import (MetadataAdapter, ParseError, block_reason, clean, expected_element,
                    http_url, parse_html, required_text)


@dataclass(frozen=True)
class LinkListConfig:
    container_id: str = "documents"
    suffixes: tuple = (".pdf", ".hwp", ".zip")
    href_pattern: str = ""
    pattern_kind: str = "pdf"
    allowed_hosts: tuple = ()  # exact hostnames added to the current page's hostname
    max_pages: int = 10
    next_text: tuple = ("next", "다음")  # also recognises rel=next outside the container
    empty_markers: tuple = ("no results", "검색 결과가 없습니다")
    encoding: str = "utf-8"

    def __post_init__(self):
        for name in ("container_id", "encoding"):
            required_text(getattr(self, name), name)
        codecs.lookup(self.encoding)
        if type(self.max_pages) is not int or not 1 <= self.max_pages <= 1000:
            raise ValueError("max_pages must be between 1 and 1000")
        for name in ("suffixes", "allowed_hosts", "next_text", "empty_markers"):
            values = getattr(self, name)
            if isinstance(values, str):
                raise ValueError(f"{name} must be a sequence")
            values = tuple(values)
            for value in values:
                required_text(value, name)
            object.__setattr__(self, name, values)
        if any(s not in (".pdf", ".hwp", ".zip") for s in self.suffixes):
            raise ValueError("unsupported document suffix")
        if self.pattern_kind not in ("pdf", "hwp", "zip"):
            raise ValueError("unsupported pattern_kind")
        if not isinstance(self.href_pattern, str):
            raise ValueError("href_pattern must be text")
        if self.href_pattern:
            re.compile(self.href_pattern)
        if not self.suffixes and not self.href_pattern:
            raise ValueError("at least one suffix or pattern is required")
        for host in self.allowed_hosts:
            url = http_url("https://" + host)
            if not url or urlsplit(url).hostname != host.lower() or urlsplit(url).netloc != host.lower():
                raise ValueError("allowed_hosts must contain exact hostnames")


class LinkListAdapter(MetadataAdapter):
    def __init__(self, source_id, config=None):
        super().__init__(source_id)
        self.config = config if config is not None else LinkListConfig()
        if not isinstance(self.config, LinkListConfig):
            raise TypeError("config must be LinkListConfig")
        self._pattern = re.compile(self.config.href_pattern) if self.config.href_pattern else None

    def discover(self, page_bytes, base_url, *, page_number=1):
        cfg = self.config
        if type(page_number) is not int or not 1 <= page_number <= cfg.max_pages:
            raise ValueError("page_number must be between 1 and max_pages")
        base = http_url(base_url)
        if not base:
            return DiscoveryManifest((), "structure_changed", "invalid_source_url")
        documents, seen, successors = [], set(), {}
        try:
            root = parse_html(page_bytes, cfg.encoding)
            reason = block_reason(root)
            if reason:
                return DiscoveryManifest((), "blocked", reason)
            container = expected_element(root, cfg.container_id)
            allowed = {urlsplit(base).hostname, *(h.lower() for h in cfg.allowed_hosts)}
            for node in root.walk():
                if node.tag != "a":
                    continue
                title = node.text()
                is_next = ("next" in (node.attrs.get("rel") or "").lower().split()
                           or title.casefold() in {clean(t).casefold() for t in cfg.next_text})
                if not is_next:
                    continue
                url = http_url(node.attrs.get("href"), base)
                if not node.closed or not url or urlsplit(url).hostname not in allowed or url == base:
                    raise ParseError("invalid_next_page")
                successors.setdefault(url, DocumentRef(url, "next_page", title or None))
            if len(successors) > 1:
                raise ParseError("ambiguous_next_page")
            for node in container.walk():
                if node.tag != "a":
                    continue
                url = http_url(node.attrs.get("href"), base)
                if not url or urlsplit(url).hostname not in allowed or url in successors:
                    continue
                path = urlsplit(url).path.lower()
                kind = next((s[1:] for s in cfg.suffixes if path.endswith(s)), None)
                if kind is None and self._pattern and self._pattern.search(url):
                    kind = cfg.pattern_kind
                if kind and url not in seen:
                    if not node.closed:
                        raise ParseError("unclosed_document_link")
                    seen.add(url)
                    documents.append(DocumentRef(url, kind, node.text() or None))
            if successors and page_number == cfg.max_pages:
                return DiscoveryManifest(documents, "structure_changed", "pagination_limit")
            documents.extend(successors.values())
            if documents:
                return DiscoveryManifest(documents, "complete")
            if any(clean(marker).casefold() in container.text().casefold() for marker in cfg.empty_markers):
                return DiscoveryManifest((), "empty_ok")
            raise ParseError("unverified_empty_listing")
        except ParseError as error:
            return DiscoveryManifest(documents, "structure_changed", str(error))
