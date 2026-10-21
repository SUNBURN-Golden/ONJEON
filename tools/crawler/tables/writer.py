"""Versioned CSV writer for extracted coverage rows. Never overwrites.

write_table(rows, out_dir, extractor_version) validates every row ("no evidence, no row" at the
storage boundary), serializes to a fixed-header UTF-8 CSV, and writes it to a NEW file named
`table-<extractor_version>-<sha256 of content>.csv`:

- same rows + same version  -> same filename -> existing identical file is returned untouched (noop)
- same filename but different bytes on disk -> TableWriteError, the file is left as is
- a new extractor_version or new content -> a new filename; old files are never modified

CSV is stdlib `csv` with `\\n` line endings so the content hash is stable across platforms.
service_view(rows) is the read-side twin: it returns only the rows validate_row accepts — a
service reads valid rows only, never the raw extract output.
"""
import csv
import hashlib
import io
from pathlib import Path
from typing import Any, Iterable, List, Mapping

from .schema import COLUMNS, RowError, valid_version, validate_row


class TableWriteError(Exception):
    """The target file exists with different content; nothing was overwritten."""


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        raise RowError("boolean cell values are not allowed")
    if isinstance(value, int):
        return str(value)
    return str(value)


def serialize(rows: Iterable[Mapping[str, Any]]) -> bytes:
    """Fixed-column-order CSV bytes (UTF-8, `\\n` endings). Deterministic for a given row list."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for row in rows:
        w.writerow([_cell(row.get(c)) for c in COLUMNS])
    return buf.getvalue().encode("utf-8")


def table_filename(extractor_version: str, content: bytes) -> str:
    if not valid_version(extractor_version):
        raise ValueError("extractor_version must be [A-Za-z0-9][A-Za-z0-9._+@-]{0,62}")
    digest = hashlib.sha256(content).hexdigest()
    return f"table-{extractor_version}-{digest}.csv"


def write_table(rows: Iterable[Mapping[str, Any]], out_dir, extractor_version: str) -> Path:
    """Validate, serialize and write rows to a new versioned file; return its Path."""
    materialized = [dict(r) for r in rows]
    for i, row in enumerate(materialized):
        try:
            validate_row(row)
        except RowError as e:
            raise RowError(f"row {i}: {e}") from None
    content = serialize(materialized)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / table_filename(extractor_version, content)
    try:
        with path.open("xb") as f:  # 'x': never an overwrite, a new versioned file only
            f.write(content)
        return path
    except FileExistsError:
        if path.read_bytes() == content:
            return path  # identical content: the same file is a noop, not a rewrite
        raise TableWriteError(
            f"{path.name} exists with different content; refusing to overwrite") from None


def read_table(path) -> List[dict]:
    """Read a CSV written by write_table back into row dicts (all values strings)."""
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise TableWriteError("CSV header does not match the provisional schema column order")
        return [dict(r) for r in reader]


def service_view(rows: Iterable[Mapping[str, Any]]) -> List[dict]:
    """Only the rows that pass validate_row. A service never sees an invalid row."""
    out = []
    for row in rows:
        try:
            validate_row(row)
        except RowError:
            continue
        out.append(dict(row))
    return out
