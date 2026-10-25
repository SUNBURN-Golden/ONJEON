"""Member-company table discovery; rows preserve the printed name and address.

Only the configured table and exact column labels establish structure. Homepages
may belong to other hosts because the table explicitly enumerates companies;
this adapter returns references and never visits those sites.
"""
import codecs
from dataclasses import dataclass
from typing import Optional, Tuple

from ..adapter import DiscoveryManifest, DocumentRef
from ._html import (Element, MetadataAdapter, ParseError, block_reason, clean,
                    expected_element, http_url, parse_html, required_text)


@dataclass(frozen=True)
class MemberTableConfig:
    table_id: str = "members"
    name_header: str = "회사명"
    homepage_header: str = "홈페이지"
    address_header: str = "주소"
    empty_markers: tuple = ("no results", "검색 결과가 없습니다")
    encoding: str = "utf-8"

    def __post_init__(self):
        for name in ("table_id", "name_header", "homepage_header", "address_header", "encoding"):
            required_text(getattr(self, name), name)
        if len({clean(self.name_header), clean(self.homepage_header), clean(self.address_header)}) != 3:
            raise ValueError("column labels must be distinct")
        codecs.lookup(self.encoding)
        if isinstance(self.empty_markers, str):
            raise ValueError("empty_markers must be a sequence")
        object.__setattr__(self, "empty_markers", tuple(self.empty_markers))
        for marker in self.empty_markers:
            required_text(marker, "empty marker")


@dataclass(frozen=True)
class MemberRow:
    name: str
    homepage: str
    address: Optional[str] = None


@dataclass(frozen=True)
class MemberTableManifest(DiscoveryManifest):
    rows: Tuple[MemberRow, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, "rows", tuple(self.rows))


class MemberTableAdapter(MetadataAdapter):
    def __init__(self, source_id, config=None):
        super().__init__(source_id)
        self.config = config if config is not None else MemberTableConfig()
        if not isinstance(self.config, MemberTableConfig):
            raise TypeError("config must be MemberTableConfig")

    def discover(self, page_bytes, base_url):
        cfg = self.config
        rows, documents = [], []
        if not http_url(base_url):
            return MemberTableManifest((), "structure_changed", "invalid_source_url")
        try:
            root = parse_html(page_bytes, cfg.encoding)
            reason = block_reason(root)
            if reason:
                return MemberTableManifest((), "blocked", reason)
            table = expected_element(root, cfg.table_id, "table")
            if any(n.tag == "table" and n is not table for n in table.walk()):
                raise ParseError("nested_member_table")
            trs = [n for n in table.walk() if n.tag == "tr"]
            if not trs:
                raise ParseError("missing_table_headers")
            header_cells = [n for n in trs[0].children if isinstance(n, Element)]
            labels = [cell.text() for cell in header_cells]
            if (not trs[0].closed or not all(c.closed and c.tag == "th"
                    and c.attrs.get("colspan", "1") == "1" and c.attrs.get("rowspan", "1") == "1"
                    for c in header_cells)
                    or len(set(labels)) != len(labels)
                    or clean(cfg.name_header) not in labels or clean(cfg.homepage_header) not in labels):
                raise ParseError("missing_table_headers")
            name_index = labels.index(clean(cfg.name_header))
            home_index = labels.index(clean(cfg.homepage_header))
            address_index = labels.index(clean(cfg.address_header)) if clean(cfg.address_header) in labels else None
            empty_seen = False
            for tr in trs[1:]:
                cells = [n for n in tr.children if isinstance(n, Element)]
                if not tr.closed or not cells or not all(c.closed and c.tag == "td" for c in cells):
                    raise ParseError("invalid_member_row")
                if (len(cells) == 1 and not any(n.tag == "a" for n in tr.walk())
                        and cells[0].text().casefold() in {clean(m).casefold() for m in cfg.empty_markers}):
                    empty_seen = True
                    continue
                if len(cells) != len(labels) or any(c.attrs.get("colspan", "1") != "1"
                                                   or c.attrs.get("rowspan", "1") != "1" for c in cells):
                    raise ParseError("invalid_member_columns")
                name = cells[name_index].text()
                links = [n for n in cells[home_index].walk() if n.tag == "a"]
                if len(links) != 1 or not links[0].closed:
                    raise ParseError("invalid_member_homepage")
                homepage = http_url(links[0].attrs.get("href"), base_url)
                if not name or not homepage:
                    raise ParseError("invalid_member_identity")
                address = (cells[address_index].text() or None) if address_index is not None else None
                rows.append(MemberRow(name, homepage, address))
                documents.append(DocumentRef(homepage, "member_homepage", name))
            if empty_seen and not rows:
                return MemberTableManifest((), "empty_ok")
            if empty_seen or not rows:
                raise ParseError("unverified_empty_or_conflicting_table")
            return MemberTableManifest(tuple(documents), "complete", rows=tuple(rows))
        except ParseError as error:
            return MemberTableManifest(tuple(documents), "structure_changed", str(error), tuple(rows))
