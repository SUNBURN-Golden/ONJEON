"""Deterministic local monitoring snapshots and pure alert predicates.

build_status takes iterable SourceStatus rows (or equivalent mappings), a
SpoolView/mapping or local Spool, a GapSummary, caller-provided budget_view with
percent in percentage points, and a clock returning epoch seconds. Multiple URL
rows for a source are reduced to latest successes/failures and earliest due time.
The caller supplies last_failure from observation history: StateDB alone loses
that historical timestamp after recovery, so it cannot reconstruct this input.

Pass GapWriter.summary(previous_status['gap_count']) for gaps. Only advance that
cursor after write_status succeeds. No budget tool, network, messenger or daily
scheduler is invoked. All times in the output are epoch seconds or null.
"""
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from . import __version__
from .gaps import GapSummary, SCHEMA_VERSION as GAP_SCHEMA_VERSION, _count, _sync_dir, _text, epoch

SCHEMA_VERSION = 1
STALE_AFTER_SECONDS = 36 * 60 * 60


@dataclass(frozen=True)
class SourceStatus:
    source_id: str
    last_success: float | None = None
    last_failure: float | None = None
    next_due: float | None = None

    def __post_init__(self):
        _text(self.source_id, "source_id")
        for name in ("last_success", "last_failure", "next_due"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, epoch(value))


@dataclass(frozen=True)
class SpoolView:
    used_bytes: int
    cap_bytes: int
    pending_count: int
    upload_failures: int = 0

    def __post_init__(self):
        for name in ("used_bytes", "cap_bytes", "pending_count", "upload_failures"):
            _count(getattr(self, name), name)
        if self.cap_bytes == 0:
            raise ValueError("cap_bytes must be positive")

    @classmethod
    def from_spool(cls, spool, *, upload_failures=0):
        """Count local entries through Spool's recovery-aware public iterator.

        Spool may finish a prepared local transaction before listing entries;
        its recovery streams bodies in bounded chunks. Nothing is uploaded.
        This is monitoring, not a transaction across the spool and state stores.
        Callers needing a coordinated snapshot can supply a precomputed view.
        """
        return cls(spool.used_bytes, spool.cap_bytes,
                   sum(1 for _ in spool.list_pending()), upload_failures)


def _budget(view):
    # A JSON round trip validates and detaches nested caller-owned data.
    if not isinstance(view, Mapping):
        raise ValueError("budget_view must be a mapping with percent")
    result = json.loads(json.dumps(dict(view), allow_nan=False))
    percent = result.get("percent")
    if (isinstance(percent, bool) or not isinstance(percent, (int, float))
            or percent < 0):
        raise ValueError("budget percent must be a finite nonnegative number")
    return result


def build_status(state, spool, gaps, budget_view, clock):
    """Build without acknowledging gaps, changing source state, or a real clock."""
    generated_at = epoch(clock())
    sources = {}
    for row in state:
        item = row if isinstance(row, SourceStatus) else SourceStatus(**row)
        target = sources.setdefault(item.source_id, {
            "last_success": None, "last_failure": None, "next_due": None})
        for name in target:
            value, previous = getattr(item, name), target[name]
            if value is not None:
                target[name] = value if previous is None else (
                    min(previous, value) if name == "next_due" else max(previous, value))
    if isinstance(spool, Mapping):
        spool = SpoolView(**spool)
    elif not isinstance(spool, SpoolView):
        spool = SpoolView.from_spool(spool)
    if not isinstance(gaps, GapSummary):
        gaps = GapSummary(**gaps)
    return {
        "schema_version": SCHEMA_VERSION,
        "crawler_version": __version__,
        "gap_schema_version": GAP_SCHEMA_VERSION,
        "generated_at": generated_at,
        "sources": dict(sorted(sources.items())),
        "gap_count": gaps.gap_count,
        "new_gaps": gaps.new_gaps,
        "spool": asdict(spool),
        "budget": _budget(budget_view),
    }


def write_status(path, status):
    """Publish a complete JSON snapshot by fsync + atomic sibling replacement.

    The deterministic .partial name is exclusive: concurrent writers fail rather
    than sharing it. A preexisting partial is left for its owner/inspection. No
    randomness is needed. Parent directory must already exist. Serialization or
    pre-replace I/O failures preserve the previous status and remove our partial.
    A directory fsync failure after replacement propagates; retry is safe.
    """
    path = Path(path)
    partial = path.with_name(path.name + ".partial")
    # Stream encoding avoids allocating a second full JSON snapshot.
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, allow_nan=False)
    created = False
    try:
        with partial.open("x", encoding="utf-8") as stream:
            created = True
            for chunk in encoder.iterencode(status):
                stream.write(chunk)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial, path)
        created = False  # another writer may now own a new partial at this name
        _sync_dir(path.parent)
    finally:
        if created:
            partial.unlink(missing_ok=True)


def new_gap(status):
    return _count(status["new_gaps"], "new_gaps") > 0


def budget_ge_80_percent(status):
    return _budget(status["budget"])["percent"] >= 80


def upload_failed(status):
    return _count(status["spool"]["upload_failures"], "upload_failures") > 0


def stale_heartbeat(status, now):
    return epoch(now) - epoch(status["generated_at"]) > STALE_AFTER_SECONDS


def daily_summary(status, now):
    """Return the caller-scheduled healthy one-liner, or None if any alert fires.

    Historical gaps remain in the denominator and are stated even after their
    incident alert was acknowledged. This function sends nothing.
    """
    if (new_gap(status) or budget_ge_80_percent(status) or upload_failed(status)
            or stale_heartbeat(status, now)):
        return None
    return (f"Crawler OK: sources={len(status['sources'])}, gaps={status['gap_count']}, "
            f"pending={status['spool']['pending_count']}, "
            f"spool={status['spool']['used_bytes']}/{status['spool']['cap_bytes']} bytes, "
            f"budget={status['budget']['percent']:g}%")
