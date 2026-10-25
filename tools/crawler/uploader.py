"""Upload a durable spool, with no writes by default.

Run with PYTHONPATH=tools python3 -m crawler.uploader --spool DIR --target file:///DIR.
See UPLOADER.md for accounting, failure/cleanup semantics and the gated R2 path.
"""
import argparse
import fcntl
import hashlib
import importlib
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import HARD_OBJECT_CAP_BYTES
from .gaps import GapWriter, epoch
from .spool import CHUNK_BYTES, META_CAP_BYTES, IntegrityError, Spool, _sync_dir
from .status import write_status

# Read-only reuse of the repository helper; storage/key rules stay there.
archive = importlib.import_module("source_archive")


class Refused(ValueError):
    """The requested storage mode has not been explicitly enabled."""


@contextmanager
def _locked(spool, clock):
    # Constructing Spool or calling list_pending performs recovery and writes.
    # Borrow its journal parser under its existing lock without either action.
    root = Path(spool.dir if isinstance(spool, Spool) else spool).resolve()
    view = object.__new__(Spool)
    view.dir, view.journal, view.clock = root, root / "journal.jsonl", clock
    with (root / ".lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with view.journal.open("rb") as journal:
                journal.seek(0, os.SEEK_END)
                if journal.tell():
                    journal.seek(-1, os.SEEK_END)
                    if journal.read(1) != b"\n":
                        raise IntegrityError("torn spool journal; recover before upload")
            yield view
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _marks(view, entry_id, event):
    return (row for row in view._events()
            if row["event"] == event and row.get("entry_id") == entry_id)


def _entries(view, include_uploaded=False):
    for row in view._events():
        if row["event"] != "prepared":
            continue
        identity, rec = row["entry_id"], row["observation"]
        if (not isinstance(identity, str) or not identity.isdecimal()
                or not isinstance(rec.get("sha256"), str)
                or len(rec["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in rec["sha256"])
                or type(rec.get("bytes")) is not int
                or not 0 <= rec["bytes"] <= HARD_OBJECT_CAP_BYTES
                or rec.get("object_key") != archive.object_key(rec["sha256"])):
            raise IntegrityError("invalid prepared archive reference")
        if not any(_marks(view, identity, "spooled")):
            raise IntegrityError("unfinished spool transaction; recover spool before upload")
        if include_uploaded or not any(_marks(view, identity, "uploaded")):
            entry = view._entry(row)
            for path in (entry.object_path, entry.observation_path):
                if archive.confined_path(view.dir, path.relative_to(view.dir)) != path:
                    raise IntegrityError("spool entry paths must not contain symlinks")
            yield entry


def _hash_file(path, cap=HARD_OBJECT_CAP_BYTES):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK_BYTES)
            if not chunk:
                break
            size += len(chunk)
            if size > cap:
                raise IntegrityError("file exceeds archive object cap")
            digest.update(chunk)
    return digest.hexdigest(), size


def _bounded_read(path, cap):
    with path.open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        if size > cap:
            raise IntegrityError("file exceeds archive object cap")
        body = stream.read(size)
        if stream.read(1):
            raise IntegrityError("file exceeds archive object cap")
        return body


class _Capture:
    """Ask source_archive to serialize/key an observation without storing it."""

    def put_new(self, key, body, content_type):
        self.key, self.body = key, body


def _observation(rec):
    capture = _Capture()
    core = {"source_id", "url", "observed_at", "sha256", "bytes", "content_type", "object_key"}
    archive.put_observation(capture, rec["source_id"], rec["url"], rec["observed_at"],
                            rec["sha256"], rec["bytes"], rec["content_type"],
                            {k: v for k, v in rec.items() if k not in core})
    return capture.key, capture.body


@dataclass(frozen=True)
class _Operation:
    key: str
    digest: str
    size: int
    content_type: str
    kind: str
    body: bytes | None = None
    path: Path | None = None
    record: dict | None = None


def _metadata(key, body, kind, rec=None, path=None):
    if len(body) > META_CAP_BYTES * 2:
        raise IntegrityError("archive metadata exceeds cap")
    return _Operation(key, archive.sha256_bytes(body), len(body), "application/json",
                      kind, body=body, record=rec, path=path)


def _operations(view, gaps, gap_urls, status_body, stamp):
    for entry in _entries(view):
        rec = entry.observation
        yield _Operation(archive.object_key(rec["sha256"]), rec["sha256"], rec["bytes"],
                         rec["content_type"], "object", path=entry.object_path)
        key, body = _observation(rec)
        yield _metadata(key, body, "observation", rec, entry.observation_path)
    if gaps is not None:
        for gap in gaps.records():
            # A metadata digest supplies the existing observation key suffix.
            # It is not presented as the hash of an acquired original.
            rec = gap.as_observation(gap_urls.get(gap.source_id) or "unknown")
            if not gap_urls.get(gap.source_id):
                rec["url"] = ""
            digest = archive.sha256_bytes(_json(rec))
            capture = _Capture()
            archive.put_observation(capture, gap.source_id, rec["url"], gap.observed_at,
                                    digest, 0, "application/json", gap.observation_extra())
            fields = json.loads(capture.body)
            for name in ("object_key", "sha256", "bytes"):
                del fields[name]
            yield _metadata(capture.key, _json(fields), "gap")
    yield _metadata(f"status/{stamp}.json", status_body, "status")


def _json(rec):
    return (json.dumps(rec, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


class _Local(archive.LocalStore):
    """LocalStore writes, bounded streaming checksum checks and verification."""

    def stored_sha256(self, key):
        try:
            path = self.root / key
            if path.stat().st_size > HARD_OBJECT_CAP_BYTES:
                return "oversized"  # always a conflict, without reading an unbounded object
            return _hash_file(path)[0]
        except FileNotFoundError:
            return archive.ABSENT

    def put_new(self, key, body, content_type):
        try:
            super().put_new(key, body, content_type)
        except archive.Exists:
            self._race = (key, body)
            raise

    def get(self, key):
        race = getattr(self, "_race", None)
        if race is not None and race[0] == key:
            del self._race
            # put_once's Exists comparison needs bytes. Reuse the input buffer
            # only after hashing the actual race winner from disk, so a second
            # capped object is never allocated and its normal no-op result holds.
            if self.stored_sha256(key) != archive.sha256_bytes(race[1]):
                raise archive.Conflict(key)
            return race[1]
        return _bounded_read(self.root / key, HARD_OBJECT_CAP_BYTES)


class _Remote:
    """Use the existing S3 store, refusing its unbounded GET fallback.

    No second object may be read while put_raw holds the upload buffer. Missing
    remote checksums or a concurrent create therefore stop and retain the spool.
    """

    def __init__(self, store):
        self.store = store

    def stored_sha256(self, key):
        digest = self.store.stored_sha256(key)
        if digest is None:
            raise IntegrityError("remote checksum unavailable; spool retained")
        return digest

    def put_new(self, key, body, content_type):
        return self.store.put_new(key, body, content_type)

    def get(self, key):
        raise IntegrityError("remote create race requires separate verification; spool retained")


def _prior_hash(operations, index, key):
    # Re-scan rather than retaining an unbounded set of all archive keys.
    for previous_index, op in enumerate(operations()):
        if previous_index >= index:
            break
        if op.key == key:
            return op.digest
    return archive.ABSENT


def _validate_source(op):
    if op.kind == "object":
        if _hash_file(op.path) != (op.digest, op.size):
            raise IntegrityError("spool object hash/size mismatch")
    elif op.kind == "observation":
        # Sidecars are durable evidence too; never silently upload journal data
        # if the published sidecar disagrees with it.
        side = json.loads(_bounded_read(op.path, META_CAP_BYTES * 2))
        if side != op.record:
            raise IntegrityError("spool observation mismatch")


def _transfer(target, apply, operations, output):
    counts = {"stored": 0, "already_present": 0, "bytes": 0, "total_bytes": 0}
    for index, op in enumerate(operations()):
        _validate_source(op)
        if apply:
            if op.kind == "object":
                body = _bounded_read(op.path, HARD_OBJECT_CAP_BYTES)
                if len(body) != op.size or archive.sha256_bytes(body) != op.digest:
                    raise IntegrityError("spool object changed during upload")
                _, state = archive.put_raw(target, body, op.content_type)
                del body
            elif op.kind == "observation":
                rec = op.record
                core = {"source_id", "url", "observed_at", "sha256", "bytes", "content_type", "object_key"}
                _, state = archive.put_observation(
                    target, rec["source_id"], rec["url"], rec["observed_at"],
                    rec["sha256"], rec["bytes"], rec["content_type"],
                    {k: v for k, v in rec.items() if k not in core})
            else:
                state = archive.put_once(target, op.key, op.body, op.content_type)
            if isinstance(target, archive.LocalStore):
                got, size = _hash_file(target.root / op.key)
                if (got, size) != (op.digest, op.size):
                    raise IntegrityError("archive re-read verification failed")
        else:
            prior = _prior_hash(operations, index, op.key)
            stored = target.stored_sha256(op.key)
            if any(value is not archive.ABSENT and value != op.digest
                   for value in (prior, stored)):
                raise archive.Conflict(op.key)
            state = "stored" if prior is archive.ABSENT and stored is archive.ABSENT else "already_present"
        counts[state] += 1
        counts["total_bytes"] += op.size
        if state == "stored":
            counts["bytes"] += op.size
        print(json.dumps({"key": op.key, "state": state, "bytes": op.size}), file=output)
    return counts


def _cleanup(view):
    for entry in _entries(view, include_uploaded=True):
        verified = any(row.get("verified_file") is True
                       for row in _marks(view, entry.entry_id, "uploaded"))
        if not verified:
            continue
        entry.observation_path.unlink(missing_ok=True)
        _sync_dir(entry.observation_path.parent)
        if not any(other.observation["sha256"] == entry.observation["sha256"]
                   for other in _entries(view)):
            entry.object_path.unlink(missing_ok=True)
            _sync_dir(entry.object_path.parent)


def upload(spool, target, mode="dry_run", *, allow_real_r2=False, job=None,
           endpoint_url=None, gaps=None, gap_urls=None, status=None, cleanup=False,
           clock=time.time, output=None):
    """Return an exit code; print JSONL plan/results and a final summary.

    gaps is a GapWriter (or JSONL path). status is optional caller monitoring
    data, capped like other metadata. R2 never acknowledges/cleans local entries
    in this node; only a completely verified file upload does so.
    """
    output = sys.stdout if output is None else output
    if mode not in ("dry_run", "apply"):
        raise Refused("mode must be dry_run or apply")
    apply = mode == "apply"
    remote = target.startswith("s3://")
    if not target.startswith("file://") and not remote:
        raise Refused("target must be file:// or explicitly enabled s3://")
    if remote and not (apply and allow_real_r2 and job
                       and os.environ.get("ONJEON_CRAWLER_ALLOW_R2") == "1"):
        raise Refused("s3:// requires --apply, --allow-real-r2, ONJEON_CRAWLER_ALLOW_R2=1 and --job")
    if cleanup and (not apply or remote):
        raise Refused("cleanup requires a verified file:// apply")
    if gaps is not None and not isinstance(gaps, GapWriter):
        gaps = GapWriter(gaps)
    now = epoch(clock())
    stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with _locked(spool, clock) as view:
        document_count = sum(1 for _ in _entries(view, include_uploaded=True))
        gap_count = sum(1 for _ in gaps.records()) if gaps else 0
        status_body = _json({"generated_at": now, "document_count": document_count,
                             "gap_count": gap_count, "upload_failed": False,
                             "status": status or {}})
        operations = lambda: _operations(view, gaps, gap_urls or {}, status_body, stamp)

        def run():
            st = archive.store(target, endpoint_url)
            if isinstance(st, archive.LocalStore):
                st = _Local(st.root)
            else:
                st = _Remote(st)
            counts = _transfer(st, apply, operations, output)
            summary = {"mode": mode, **counts, "upload_failed": False,
                       "class_a_estimate": counts["stored"],
                       "class_b_estimate": (2 if apply else 1) * (counts["stored"] + counts["already_present"]),
                       "accounting": "estimate: PUT per new key; HEAD/check plus verification; excludes ledger, LIST, retries and races"}
            print(json.dumps(summary), file=output)
            return 0

        # with_budget starts/settles the named budget before store() can create
        # any client. It maps Conflict -> 3 and budget stop -> 4, without retry.
        try:
            code = archive.with_budget(job if remote else None, endpoint_url, run)
        except (IntegrityError, ValueError, OSError) as exc:
            print(f"upload failed: {type(exc).__name__}", file=sys.stderr)
            code = 1
        if apply and code == 0 and not remote:
            # Defer ALL acknowledgements until objects, observations and status
            # have been re-read successfully. Partial failures retain all work.
            for entry in _entries(view):
                view._append("uploaded", entry_id=entry.entry_id, verified_file=True)
            if cleanup:
                _cleanup(view)
        if apply:
            failure_path = view.dir / "upload_status.json"
            if code or failure_path.exists():
                write_status(failure_path, {"generated_at": now, "exit_code": code,
                                           "upload_failed": bool(code),
                                           "spool": {"upload_failures": int(bool(code))}})
        if code:
            print(json.dumps({"exit_code": code, "upload_failed": True}), file=output)
        return code


def main(argv=None, *, clock=time.time):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spool", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-real-r2", action="store_true")
    parser.add_argument("--job")
    parser.add_argument("--endpoint-url")
    parser.add_argument("--gaps", help="GapWriter JSONL; missing URL stays empty")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args(argv)
    try:
        return upload(args.spool, args.target, "apply" if args.apply else "dry_run",
                      allow_real_r2=args.allow_real_r2, job=args.job,
                      endpoint_url=args.endpoint_url, gaps=args.gaps,
                      cleanup=args.cleanup, clock=clock)
    except (Refused, IntegrityError, ValueError, OSError) as exc:
        print(f"upload refused/failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
