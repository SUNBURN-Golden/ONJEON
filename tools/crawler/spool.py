"""Local, durable document queue; no network or archive writes.

Objects live at objects/aa/bb/hash; observation object_key is the archive's
objects/sha256/aa/bb/hash. Each call gets a distinct observation, even at the
same timestamp. cap_bytes counts retained object bytes (including uploaded ones),
not journal/sidecar overhead. Only the uploader may remove retained objects.

An exclusive, nonblocking directory lock serializes writers, recovery and upload
marks. Callers must also hold this lock when performing uploader cleanup. A
prepared journal record is fsynced before publishing either file; recovery
finishes that transaction before removing abandoned *.partial files. No random
names, sleeps, environment reads or collection entry points are needed.
"""
import fcntl
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .config import HARD_OBJECT_CAP_BYTES
from .transport import BodyTooLargeError, TransportError
from .validate import BodyStreamInfo, RejectionReason, validate_document

CHUNK_BYTES = 64 * 1024
META_CAP_BYTES = 64 * 1024
_TAIL_MARKER = b'{"event":"tail_recovered"}\n'


class IntegrityError(ValueError):
    """Stored bytes or durable transaction evidence disagree; nothing overwritten."""


@dataclass(frozen=True)
class PendingEntry:
    entry_id: str
    observation: dict
    observation_path: Path
    object_path: Path


@dataclass(frozen=True)
class Spooled:
    entry: PendingEntry
    deduplicated: bool


@dataclass(frozen=True)
class Rejected:
    reason: RejectionReason
    size_bytes: int


@dataclass(frozen=True)
class CapReached:
    cap_bytes: int
    used_bytes: int
    size_bytes: int


def _json(record):
    return (json.dumps(record, ensure_ascii=False, sort_keys=True,
                       allow_nan=False) + "\n").encode("utf-8")


def _sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir(path):
    if not path.exists():
        _mkdir(path.parent)
        path.mkdir(exist_ok=True)
        _sync_dir(path.parent)


def _chunks(stream):
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            return
        yield chunk


def _hash(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in _chunks(stream):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class Spool:
    def __init__(self, dir, cap_bytes=1_500_000_000,
                 object_cap_bytes=HARD_OBJECT_CAP_BYTES, clock=time.time):
        if type(cap_bytes) is not int or cap_bytes < 1:
            raise ValueError("cap_bytes must be a positive integer")
        if (type(object_cap_bytes) is not int
                or not 1 <= object_cap_bytes <= HARD_OBJECT_CAP_BYTES):
            raise ValueError("object_cap_bytes must be within the 64 MiB hard cap")
        self.dir = Path(dir).resolve()
        self.cap_bytes = cap_bytes
        self.object_cap_bytes = object_cap_bytes
        self.clock = clock
        _mkdir(self.dir)
        self.journal = self.dir / "journal.jsonl"
        self.temp_dir = self.dir / "tmp"
        with self.lock():
            _mkdir(self.temp_dir)
            _mkdir(self.dir / "objects")
            _mkdir(self.dir / "observations")
            self._seal_tail()
            self._recover()

    @contextmanager
    def lock(self):
        """Exclusive spool ownership, also required by separate uploader cleanup."""
        with (self.dir / ".lock").open("ab") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _seal_tail(self):
        # Preserve every existing byte. The marker discards the preceding torn
        # line even if its JSON happened to be complete before the crash.
        with self.journal.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell():
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    stream.write(b"\n" + _TAIL_MARKER)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_dir(self.dir)

    def _events(self, end_offset=None):
        with self.journal.open("rb") as stream:
            def read_line():
                return stream.readline() if end_offset is None else stream.readline(
                    max(0, end_offset - stream.tell()))

            line = read_line()
            while line:
                following = read_line()
                if following == _TAIL_MARKER:
                    line = read_line()
                    continue
                if not line.endswith(b"\n"):
                    return
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict) or "event" not in event:
                        raise ValueError("missing event")
                except (ValueError, UnicodeError) as exc:
                    raise IntegrityError("invalid complete journal record") from exc
                yield event
                line = following

    def _append(self, event, **fields):
        with self.journal.open("ab") as stream:
            stream.write(_json({"event": event, "at": self.clock(), **fields}))
            stream.flush()
            os.fsync(stream.fileno())

    def _entry(self, prepared):
        rec = prepared["observation"]
        digest = rec["sha256"]
        return PendingEntry(prepared["entry_id"], rec,
                            self.dir / "observations" / (prepared["entry_id"] + ".json"),
                            self.dir / "objects" / digest[:2] / digest[2:4] / digest)

    def _finish(self, prepared):
        entry = self._entry(prepared)
        temp = self.temp_dir / (entry.entry_id + ".partial")
        expected = (entry.observation["sha256"], entry.observation["bytes"])
        if entry.object_path.exists():
            if _hash(entry.object_path) != expected:
                raise IntegrityError("existing object hash mismatch")
            temp.unlink(missing_ok=True)
        else:
            if not temp.exists() or _hash(temp) != expected:
                raise IntegrityError("prepared object missing or hash mismatch")
            _mkdir(entry.object_path.parent)
            os.rename(temp, entry.object_path)
            _sync_dir(entry.object_path.parent)
        _sync_dir(self.temp_dir)
        body = _json(entry.observation)
        if entry.observation_path.exists():
            if entry.observation_path.read_bytes() != body:
                raise IntegrityError("existing observation mismatch")
        else:
            side_temp = self.temp_dir / (entry.entry_id + ".json.partial")
            with side_temp.open("wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(side_temp, entry.observation_path)
            _sync_dir(entry.observation_path.parent)
            _sync_dir(self.temp_dir)
        self._append("spooled", entry_id=entry.entry_id)
        return entry

    def _recover(self):
        prepared = None
        for event in self._events():
            if event["event"] == "prepared":
                if prepared is not None:
                    raise IntegrityError("overlapping prepared transactions")
                prepared = event
            elif event["event"] == "spooled":
                if prepared is None or prepared["entry_id"] != event["entry_id"]:
                    raise IntegrityError("spooled record without matching preparation")
                prepared = None
        if prepared is not None:
            self._finish(prepared)
        for path in self.temp_dir.glob("*.partial"):
            path.unlink()
        _sync_dir(self.temp_dir)

    @property
    def used_bytes(self):
        """Retained object bytes, including objects awaiting journal completion."""
        return sum(path.stat().st_size for path in (self.dir / "objects").rglob("*")
                   if path.is_file())

    def write_stream(self, source_id, url, observed_at, chunks, declared_type, meta=None):
        """Return Spooled, Rejected or CapReached; caller owns the input iterator.

        meta is a flat JSON mapping of provenance extras, e.g. request_path,
        response_code, adapter_version, user_agent_version, egress_country,
        content_type (response MIME), and content_length. Core hash/size/path
        fields cannot be overridden. Source chunks must already be bounded;
        this method never joins them. Exceptions outside transport errors are
        propagated after removing unprepared temporary files.
        """
        if not isinstance(source_id, str) or not re.fullmatch(r"[a-z0-9_]+", source_id):
            raise ValueError("source_id must be lower snake_case")
        if any(not isinstance(value, str) or not value for value in (url, observed_at)):
            raise ValueError("url and observed_at must be nonempty strings")
        extras = dict(meta or {})
        if set(extras) & {"source_id", "url", "observed_at", "sha256", "bytes", "object_key"}:
            raise ValueError("meta cannot override core observation fields")
        if len(_json(extras)) > META_CAP_BYTES:
            raise ValueError("meta exceeds 64 KiB")
        info = BodyStreamInfo((), content_type=extras.get("content_type"),
                              content_length=extras.get("content_length"),
                              object_cap_bytes=self.object_cap_bytes)
        content_type = info.content_type or {
            "pdf": "application/pdf", "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(declared_type, declared_type)
        with self.lock():
            self._seal_tail()
            self._recover()
            entry_id = str(self.journal.stat().st_size)
            temp = self.temp_dir / (entry_id + ".partial")
            self._append("begin", entry_id=entry_id)
            size = 0
            digest = hashlib.sha256()
            prepared = False

            def reject(reason):
                self._append("rejected", entry_id=entry_id, source_id=source_id,
                             url=url, observed_at=observed_at, reason=reason.value, bytes=size)
                return Rejected(reason, size)

            try:
                with temp.open("xb") as stream:
                    try:
                        for chunk in chunks:
                            if not isinstance(chunk, bytes):
                                return reject(RejectionReason.INVALID_STREAM)
                            size += len(chunk)
                            if size > self.object_cap_bytes:
                                return reject(RejectionReason.TOO_LARGE)
                            stream.write(chunk)
                            digest.update(chunk)
                    except BodyTooLargeError:
                        return reject(RejectionReason.TOO_LARGE)
                    except (TransportError, OSError):
                        return reject(RejectionReason.STREAM_ERROR)
                    stream.flush()
                    os.fsync(stream.fileno())
                _sync_dir(self.temp_dir)
                # Re-read the finished file, never the one-shot source iterator.
                with temp.open("rb") as stream:
                    validation = validate_document(BodyStreamInfo(
                        _chunks(stream), info.content_type, info.content_length,
                        self.object_cap_bytes), declared_type)
                if not validation.ok:
                    return reject(validation.reason)
                sha = digest.hexdigest()
                if _hash(temp) != (sha, size):
                    raise IntegrityError("finished temporary file hash mismatch")
                observation = {**extras, "source_id": source_id, "url": url,
                               "observed_at": observed_at, "sha256": sha, "bytes": size,
                               "content_type": content_type,
                               "object_key": f"objects/sha256/{sha[:2]}/{sha[2:4]}/{sha}"}
                record = {"entry_id": entry_id, "observation": observation}
                exists = self._entry(record).object_path.exists()
                used = self.used_bytes
                if not exists and used + size > self.cap_bytes:
                    self._append("cap_reached", entry_id=entry_id, bytes=size,
                                 used_bytes=used, cap_bytes=self.cap_bytes)
                    return CapReached(self.cap_bytes, used, size)
                # An append/fsync error can leave a complete prepared record on
                # disk. Preserve the temp until replay decides its ownership.
                prepared = True
                self._append("prepared", **record)
                return Spooled(self._finish(record), exists)
            finally:
                if not prepared:
                    temp.unlink(missing_ok=True)
                    _sync_dir(self.temp_dir)

    def list_pending(self):
        """Yield entries not marked uploaded, with bounded memory.

        Journal rescans trade read time for bounded memory over an arbitrarily
        long history. Snapshot the prepared work under the lock, then release
        it before yielding so an uploader can acknowledge each entry directly.
        New writes appear on the next listing; acknowledgements are checked
        as each entry is visited. Uploads/acknowledgements must be idempotent.
        """
        with self.lock():
            self._seal_tail()
            self._recover()
            end_offset = self.journal.stat().st_size
        for event in self._events(end_offset):
            if event["event"] == "prepared" and not any(
                mark["event"] == "uploaded" and mark["entry_id"] == event["entry_id"]
                for mark in self._events()
            ):
                yield self._entry(event)

    def mark_uploaded(self, entry_id):
        """Record the uploader's verified upload acknowledgement; delete nothing.

        Marks apply per observation: deduplicated bodies still have independent
        observation uploads. Repeated marks are harmless.
        """
        with self.lock():
            self._seal_tail()
            self._recover()
            if not any(event["event"] == "spooled" and event["entry_id"] == entry_id
                       for event in self._events()):
                raise KeyError(entry_id)
            self._append("uploaded", entry_id=entry_id)
