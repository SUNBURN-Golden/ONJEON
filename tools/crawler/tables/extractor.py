"""Table extractor interface plus the sample extractor that proves the plumbing.

Extractor(version).extract(raw_bytes, raw_sha256, source_meta) -> list of row dicts in the
provisional schema of tables/schema.py. raw_sha256 is the sha256 of raw_bytes computed by the
caller (the archive layer); the extractor only copies it into source_raw_sha256 — evidence is
never invented. raw_bytes must already respect the caller's object cap (config.object_cap_bytes);
this layer adds no cap of its own.

SampleTextExtractor parses only the tiny synthetic fixture format — one coverage per line:

    coverage|conditions|amount|period|page

with `#`-prefixed comment lines (the fixture marks its origin as `# origin=fixture`) and blank
lines ignored. It exists to prove schema -> extract -> validate -> write plumbing. There is no
PDF, OCR, HTML or network parsing here, and none belongs in this node.
"""
import abc
from typing import Any, List, Mapping

from .schema import COLUMNS, is_sha256, valid_version


class ExtractError(ValueError):
    """The raw bytes or source_meta cannot be turned into rows honestly."""


# source_meta may only carry these columns; the extractor itself owns the parsed fields
# (coverage_name, conditions, amount, period, source_page), the evidence fields
# (source_raw_sha256, extractor_version) and status.
META_KEYS = frozenset({
    "insurer_id", "product_id", "coverage_id", "source_url", "observed_at",
    "effective_from", "effective_to", "effective_reason",
})


class Extractor(abc.ABC):
    """A versioned raw-bytes -> provisional-rows transform. No I/O, no network, no clock."""

    def __init__(self, version: str):
        if not valid_version(version):
            raise ValueError("extractor version must be [A-Za-z0-9][A-Za-z0-9._+@-]{0,62}")
        self.version = version

    @abc.abstractmethod
    def extract(self, raw_bytes: bytes, raw_sha256: str, source_meta: Mapping[str, Any]) -> List[dict]:
        """Return provisional-schema rows. May emit rows that fail validate_row; callers filter."""


class SampleTextExtractor(Extractor):
    """Parses the synthetic `coverage|conditions|amount|period|page` text fixture. Plumbing only."""

    def __init__(self, version: str = "sample-text@1"):
        super().__init__(version)

    def extract(self, raw_bytes: bytes, raw_sha256: str, source_meta: Mapping[str, Any]) -> List[dict]:
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise ExtractError("raw_bytes must be bytes")
        if not is_sha256(raw_sha256):
            raise ExtractError("raw_sha256 must be 64 lowercase hex chars: no evidence, no row")
        if not isinstance(source_meta, Mapping):
            raise ExtractError("source_meta must be a mapping")
        bad_meta = sorted(str(k) for k in source_meta if k not in META_KEYS)
        if bad_meta:
            raise ExtractError(f"source_meta keys not allowed: {', '.join(bad_meta)}")
        try:
            text = bytes(raw_bytes).decode("utf-8")
        except UnicodeDecodeError as e:
            raise ExtractError(f"raw bytes are not UTF-8 text: {type(e).__name__}") from None
        rows = []
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = [f.strip() for f in line.split("|")]
            if len(fields) != 5:
                raise ExtractError(f"line {lineno}: expected 5 `|`-separated fields, got {len(fields)}")
            coverage, conditions, amount, period, page = fields
            if not coverage:
                raise ExtractError(f"line {lineno}: coverage name must not be empty")
            if page.isdigit():
                page_value: Any = int(page)
            elif page:
                page_value = page  # explicit text locator for a page-less source
            else:
                raise ExtractError(f"line {lineno}: empty page: no evidence, no row")
            row = {c: "" for c in COLUMNS}
            for key in META_KEYS:
                if key in source_meta:
                    row[key] = source_meta[key]
            row.update({
                "coverage_name": coverage, "conditions": conditions, "amount": amount,
                "period": period, "source_page": page_value,
                "source_raw_sha256": raw_sha256, "extractor_version": self.version,
                # the sample parser verifies nothing; a downstream step must review every row
                "status": "needs_review",
            })
            rows.append(row)
        return rows

