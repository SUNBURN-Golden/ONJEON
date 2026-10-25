"""Rebuildable per-source/URL cache, using one SQLite writer and a rollback journal.

The archive's observation JSON is authoritative; this DB is disposable. Call
record_observation only AFTER durably recording the observation, including unchanged
checks and failures (these are metadata records, never body spool entries).

Records use source_archive.put_observation's source_id/url/observed_at/sha256 fields.
Its extra mapping carries status (200 by default for legacy records), etag,
last_modified, next_due (epoch seconds), original_retained, and reason for failures.
A 200 verifies all bytes; a 304 preserves the last byte verification time. Failures
preserve the last successful object's metadata. Missing next_due means immediately
due at observed_at. Original retention defaults to true for legacy archived 200s.

Incremental records must be strictly chronological per source/URL. Rebuild accepts
unordered iterables, deduplicates identical records, and sorts on disk in SQLite;
conflicting records at the same source/URL/time are rejected. Both paths are atomic.
There is no network, archive writer, scheduler, clock, or body storage here.
"""
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, Iterator, Mapping, Optional

SCHEMA_VERSION = 1


class SchemaVersionError(ValueError):
    pass


@dataclass(frozen=True)
class CrawlState:
    source_id: str
    url: str
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    last_sha256: Optional[str] = None
    last_attempt: Optional[float] = None
    last_success: Optional[float] = None
    consecutive_failures: int = 0
    next_due: Optional[float] = None
    original_retained: bool = False
    last_verified: Optional[float] = None


def _number(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be finite nonnegative epoch seconds")
    return float(value)


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} must be a nonempty string without NUL")
    return value


def _validator(value, name):
    if value is not None and (not isinstance(value, str)
                              or any(c in value for c in "\r\n\x00")):
        raise ValueError(f"invalid {name}")
    return value or None


def _observation(record):
    if not isinstance(record, Mapping):
        raise ValueError("observation must be a JSON object")
    source_id = _text(record.get("source_id"), "source_id")
    url = _text(record.get("url"), "url")
    stamp = record.get("observed_at")
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when.tzinfo is None:
            raise ValueError("timezone required")
        attempted = _number(when.timestamp(), "observed_at")
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise ValueError("observed_at must be an ISO timestamp with timezone") from None
    status = record.get("status", 200)
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        raise ValueError("status must be an HTTP status or None")
    success = status in (200, 304)
    digest = record.get("sha256")
    if status == 200 and (not isinstance(digest, str)
                          or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
        raise ValueError("a 200 observation requires a lowercase SHA-256")
    if not success:
        _text(record.get("reason"), "failure reason")
    if "original_retained" in record and type(record["original_retained"]) is not bool:
        raise ValueError("original_retained must be boolean")
    due = _number(record.get("next_due", attempted), "next_due")
    etag = _validator(record.get("etag"), "etag")
    modified = _validator(record.get("last_modified"), "last_modified")
    return source_id, url, attempted, status, digest, due, etag, modified


class StateDB:
    """One same-thread connection; BEGIN IMMEDIATE serializes all state mutations.

    Contending writers fail immediately rather than sleeping or retrying. DELETE
    journal mode keeps WAL off while preserving crash rollback and atomic rebuilds.
    The caller owns the directory and the connection's lifetime.
    """

    def __init__(self, path):
        self._db = sqlite3.connect(str(path), timeout=0, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        try:
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise SchemaVersionError(f"unsupported state schema {version}; supported {SCHEMA_VERSION}")
            if version == 0 and self._db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise SchemaVersionError("unversioned database is not an empty state database")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA temp_store=FILE")
            if version == 0:
                with self._transaction():
                    self._db.execute("""CREATE TABLE crawler_state (
                        source_id TEXT NOT NULL, url TEXT NOT NULL,
                        etag TEXT, last_modified TEXT, last_sha256 TEXT,
                        last_attempt REAL, last_success REAL,
                        consecutive_failures INTEGER NOT NULL CHECK(consecutive_failures >= 0),
                        next_due REAL, original_retained INTEGER NOT NULL CHECK(original_retained IN (0,1)),
                        last_verified REAL, PRIMARY KEY(source_id, url)
                    ) WITHOUT ROWID""")
                    self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        except BaseException:
            self.close()
            raise

    @contextmanager
    def _transaction(self):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    @property
    def schema_version(self) -> int:
        return self._db.execute("PRAGMA user_version").fetchone()[0]

    @staticmethod
    def _state(row):
        if row is None:
            return None
        values = dict(row)
        values["original_retained"] = bool(values["original_retained"])
        return CrawlState(**values)

    def get(self, source_id: str, url: str) -> Optional[CrawlState]:
        return self._state(self._db.execute(
            "SELECT * FROM crawler_state WHERE source_id=? AND url=?", (source_id, url)).fetchone())

    def rows(self) -> Iterator[CrawlState]:
        for row in self._db.execute("SELECT * FROM crawler_state ORDER BY source_id, url"):
            yield self._state(row)

    def _apply(self, record):
        source, url, attempted, status, digest, due, etag, modified = _observation(record)
        old = self.get(source, url) or CrawlState(source, url)
        if old.last_attempt is not None and attempted <= old.last_attempt:
            raise ValueError("observations must advance time per source/URL")
        values = asdict(old)
        values.update(last_attempt=attempted, next_due=due)
        if status in (200, 304):
            if status == 304 and (old.last_sha256 is None or not old.original_retained):
                raise ValueError("304 requires a previous retained byte observation")
            values.update(last_success=attempted, consecutive_failures=0)
            if status == 200:
                values.update(last_sha256=digest, etag=etag, last_modified=modified,
                              last_verified=attempted,
                              original_retained=record.get("original_retained", True))
            else:
                # Omitted 304 validators retain the previous representation's values.
                values.update(etag=etag or old.etag, last_modified=modified or old.last_modified,
                              original_retained=record.get("original_retained", old.original_retained))
        else:
            values["consecutive_failures"] += 1
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        self._db.execute(f"INSERT OR REPLACE INTO crawler_state ({columns}) VALUES ({placeholders})",
                         tuple(values.values()))

    def record_observation(self, observation: Mapping) -> CrawlState:
        """Apply one already archived observation; reject stale/equal timestamps."""
        with self._transaction():
            self._apply(observation)
        return self.get(observation["source_id"], observation["url"])

    def rebuild_from_observations(self, observations: Iterable[Mapping]) -> None:
        """Replace all rows atomically, with bounded memory and no archive I/O.

        Complete history (including unchanged checks/failures and scheduling extras)
        is needed for exact recovery. Legacy archive records recover the fields they
        contain using the documented defaults; omitted facts cannot be inferred.
        """
        with self._transaction():
            self._db.execute("""CREATE TEMP TABLE rebuild_input (
                source_id TEXT, url TEXT, attempted REAL, body TEXT NOT NULL,
                PRIMARY KEY(source_id, url, attempted)) WITHOUT ROWID""")
            for observation in observations:
                source, url, attempted, *_ = _observation(observation)
                body = json.dumps(dict(observation), sort_keys=True, allow_nan=False)
                previous = self._db.execute(
                    "SELECT body FROM rebuild_input WHERE source_id=? AND url=? AND attempted=?",
                    (source, url, attempted)).fetchone()
                if previous is not None:
                    if previous[0] != body:
                        raise ValueError("conflicting observations at the same source/URL/time")
                    continue
                self._db.execute("INSERT INTO rebuild_input VALUES (?, ?, ?, ?)",
                                 (source, url, attempted, body))
            self._db.execute("DELETE FROM crawler_state")
            for row in self._db.execute(
                    "SELECT body FROM rebuild_input ORDER BY source_id, url, attempted"):
                self._apply(json.loads(row[0]))
            self._db.execute("DROP TABLE rebuild_input")

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
