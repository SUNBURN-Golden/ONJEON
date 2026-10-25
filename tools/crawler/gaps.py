"""Append-only local evidence of uncovered collection ranges; never an acquisition.

A source_id identifies the caller's uncovered denominator range. Record blocks
immediately; evaluate_cycle is the separate policy for repeated failed cycles
(not HTTP attempts). Persist its returned gap before acting on its alert flag.
Callers may seed the pure policy with durable counters from crawler.state.
No network, uploader, scheduler, environment access, or retries live here.
"""
import fcntl
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 64 * 1024
REASONS = frozenset({
    "service_outage", "connection_reset", "js_shell", "rate_limited",
    "timeout", "tls_error", "geo_blocked", "empty_reply", "robots_disallow",
    "robots_unreadable", "blocked", "structure_changed", "terms_unknown", "cap_reached",
})
NEXT_ACTIONS = frozenset({"wait", "find_official_api", "draft_inquiry", "terms_review"})


def epoch(value):
    """Finite nonnegative epoch seconds or an ISO timestamp with a timezone."""
    if isinstance(value, str):
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("timezone required")
            value = stamp.timestamp()
        except (ValueError, OverflowError):
            raise ValueError("timestamp requires an ISO timezone") from None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError("timestamp must be finite nonnegative epoch seconds")
    return float(value)


def _stamp(value):
    return datetime.fromtimestamp(epoch(value), timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} must be nonempty text without NUL")


def _count(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class GapRecord:
    source_id: str
    observed_at: str
    reason: str
    http_status: int | None = None
    robots_verdict: str | None = None
    terms_verdict: str | None = None
    attempts: int = 1
    next_retry_at: str | None = None
    next_action: str = "wait"

    def __post_init__(self):
        _text(self.source_id, "source_id")
        object.__setattr__(self, "observed_at", _stamp(self.observed_at))
        if self.reason not in REASONS:
            raise ValueError("unknown gap reason")
        if self.next_action not in NEXT_ACTIONS:
            raise ValueError("unknown next action")
        if self.http_status is not None and (
                type(self.http_status) is not int or not 100 <= self.http_status <= 599):
            raise ValueError("http_status must be an HTTP status or None")
        for name in ("robots_verdict", "terms_verdict"):
            value = getattr(self, name)
            if value is not None:
                _text(value, name)
        _count(self.attempts, "attempts")  # zero is valid when policy prevents a request
        if self.next_retry_at is not None:
            object.__setattr__(self, "next_retry_at", _stamp(self.next_retry_at))
            if epoch(self.next_retry_at) < epoch(self.observed_at):
                raise ValueError("next_retry_at precedes observed_at")

    def to_dict(self):
        return {"schema_version": SCHEMA_VERSION, "gap": True, **asdict(self)}

    def observation_extra(self):
        """Uploader extras, flattened like source_archive observations.

        status=None deliberately overrides the state cache's legacy 200 default:
        even an HTTP 200 JS shell is a failure. http_status preserves wire evidence.
        These metadata-only observations have no object_key, hash, or body bytes.
        """
        fields = asdict(self)
        del fields["source_id"], fields["observed_at"]
        return {"gap": True, "status": None, **fields}

    def as_observation(self, url):
        _text(url, "url")
        return {"source_id": self.source_id, "url": url,
                "observed_at": self.observed_at, **self.observation_extra()}


@dataclass(frozen=True)
class CycleResult:
    consecutive_failures: int
    gap: GapRecord | None
    alert: bool


def evaluate_cycle(previous_failures, failure=None):
    """One completed cycle: None means success; emit once on the third failure.

    Attempts inside a failed cycle do not advance this counter. A fourth failed
    cycle keeps the counter, without repeating the same incident alert. Success
    resets it and allows a later incident to emit again. This function is pure.
    """
    _count(previous_failures, "previous_failures")
    if failure is None:
        return CycleResult(0, None, False)
    if not isinstance(failure, GapRecord):
        raise ValueError("failure must be a GapRecord or None")
    count = previous_failures + 1
    return CycleResult(count, failure if count == 3 else None, count == 3)


@dataclass(frozen=True)
class GapSummary:
    gap_count: int
    new_gaps: int

    def __post_init__(self):
        _count(self.gap_count, "gap_count")
        _count(self.new_gaps, "new_gaps")
        if self.new_gaps > self.gap_count:
            raise ValueError("new_gaps exceeds gap_count")


class GapWriter:
    """Local JSONL, bounded records, fsynced append, nonblocking writer lock.

    Readers reject malformed records; appends refuse torn tails and preserve them
    for inspection. No repair truncates evidence. One record is held at a time.
    Reopening never clears the log. Summary reads do not acknowledge records.
    """

    def __init__(self, path):
        self.path = Path(path)

    def append(self, record):
        if not isinstance(record, GapRecord):
            raise ValueError("record must be a GapRecord")
        data = (json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True,
                           allow_nan=False) + "\n").encode("utf-8")
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError("gap record exceeds metadata cap")
        with self.path.open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stream.seek(0, os.SEEK_END)
            if stream.tell():
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    raise ValueError("incomplete gap log tail; evidence preserved")
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            _sync_dir(self.path.parent)

    def records(self):
        try:
            stream = self.path.open("rb")
        except FileNotFoundError:
            return
        with stream:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
            while True:
                line = stream.readline(MAX_RECORD_BYTES + 1)
                if not line:
                    return
                if len(line) > MAX_RECORD_BYTES or not line.endswith(b"\n"):
                    raise ValueError("invalid gap log line; evidence preserved")
                fields = json.loads(line)
                if (not isinstance(fields, dict)
                        or type(fields.get("schema_version")) is not int
                        or fields.pop("schema_version", None) != SCHEMA_VERSION
                        or fields.pop("gap", None) is not True):
                    raise ValueError("unsupported gap record")
                try:
                    yield GapRecord(**fields)
                except TypeError as exc:
                    raise ValueError("invalid gap record fields") from exc

    def summary(self, previous_count=0):
        """Use the last successfully published status's gap_count as the cursor.

        Ordinals include late observations and identical timestamps. There is no
        hidden acknowledgement: a failed status write can safely be retried.
        gap_count is cumulative evidence, not a count of currently open incidents.
        """
        _count(previous_count, "previous_count")
        count = sum(1 for _ in self.records())
        if previous_count > count:
            raise ValueError("gap log is behind the previous summary")
        return GapSummary(count, count - previous_count)


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
