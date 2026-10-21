"""PROVISIONAL row schema for extracted coverage tables.

THIS SCHEMA IS PROVISIONAL. It is NOT the data contract: docs/data/ owns the contract, and when the
contract defines the coverage-table row shape this module must be updated to match (or replaced).
Until then these column names are an implementation detail of tools/crawler/tables/ and must not
be treated as the contractual vocabulary.

Column order is fixed; it is the CSV header written by writer.write_table.

  insurer_id          insurer identifier string (may be empty while unassigned)
  product_id          product identifier string (may be empty while unassigned)
  coverage_id         coverage/특약 identifier string (may be empty while unassigned)
  coverage_name       coverage name as printed in the source document
  conditions          conditions text (가입조건/지급조건) as printed, not yet normalized
  amount              amount text as printed, not yet normalized
  period              period text as printed, not yet normalized
  effective_from      effective start (ISO-8601 text); may be empty only with effective_reason
  effective_to        effective end (ISO-8601 text); may be empty only with effective_reason
  effective_reason    REQUIRED iff effective_from or effective_to is empty: states why
  source_raw_sha256   REQUIRED: 64 lowercase hex chars, sha256 of the raw source bytes
  source_page         REQUIRED: positive int page number, or a non-empty text-locator string
                      (for page-less sources such as serialized HTML table text)
  source_url          URL the raw bytes came from (may be empty for local/fixture sources)
  observed_at         observation timestamp, ISO-8601 text (injected by the caller)
  extractor_version   version string of the Extractor that produced the row
  status              one of {"verified", "needs_review"}

Evidence rule ("no evidence, no row"): a row without a valid source_raw_sha256 AND a valid
source_page is never a row. validate_row enforces it; writer.write_table re-enforces it at the
storage boundary; writer.service_view drops any row that fails it.
"""
import re
from typing import Any, Mapping

COLUMNS = (
    "insurer_id", "product_id", "coverage_id", "coverage_name", "conditions", "amount", "period",
    "effective_from", "effective_to", "effective_reason",
    "source_raw_sha256", "source_page", "source_url", "observed_at", "extractor_version", "status",
)
COLUMN_SET = frozenset(COLUMNS)
STATUSES = frozenset({"verified", "needs_review"})

_SHA256 = re.compile(r"[0-9a-f]{64}")
_SIGNED_INT = re.compile(r"[+-]?[0-9]+")
VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+@-]{0,62}")


class RowError(ValueError):
    """A row violates the provisional schema; the row must not be stored or served."""


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def valid_version(value: Any) -> bool:
    return isinstance(value, str) and VERSION_RE.fullmatch(value) is not None


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _valid_page(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 1
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        if _SIGNED_INT.fullmatch(text):
            return int(text) >= 1  # a CSV-read page like "3" is a page, "0"/"-3" are not
        return True  # an explicit text-locator for a page-less source
    return False


def validate_row(row: Any) -> None:
    """Raise RowError on the first schema violation; return None for a valid row."""
    if not isinstance(row, Mapping):
        raise RowError("row must be a mapping")
    unknown = sorted(str(k) for k in row if k not in COLUMN_SET)
    if unknown:
        raise RowError(f"unknown columns: {', '.join(unknown)}")
    for key, value in row.items():
        if isinstance(value, bool) or not isinstance(value, (str, int, type(None))):
            raise RowError(f"column {key}: value must be a string or integer")
        if isinstance(value, str) and "\x00" in value:
            raise RowError(f"column {key}: value contains NUL")
    if not is_sha256(row.get("source_raw_sha256")):
        raise RowError("source_raw_sha256 must be 64 lowercase hex chars: no evidence, no row")
    if not _valid_page(row.get("source_page")):
        raise RowError("source_page must be a positive int or a non-empty text locator: no evidence, no row")
    status = row.get("status")
    if status not in STATUSES:
        raise RowError(f"status must be one of {sorted(STATUSES)}")
    if not valid_version(row.get("extractor_version")):
        raise RowError("extractor_version must be a non-empty version string")
    if _is_empty(row.get("effective_from")) or _is_empty(row.get("effective_to")):
        if _is_empty(row.get("effective_reason")):
            raise RowError("empty effective_from/effective_to needs a non-empty effective_reason")
