"""CRAWL-06 offline evidence: all synthetic observations/bodies have origin=fixture.

Only temporary SQLite files and in-process archive/response fakes are used. There
is no transport construction, real network, R2, environment access, or sleeping.
"""
import ast
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as archive  # noqa: E402
from crawler.changes import conditional_headers, decide, full_verification_due  # noqa: E402
from crawler.config import (CrawlerConfig, ConfigError, DEFAULT_VERIFY_EVERY_S,  # noqa: E402
                            HARD_OBJECT_CAP_BYTES, config_from_dict)
from crawler.state import CrawlState, SCHEMA_VERSION, SchemaVersionError, StateDB  # noqa: E402
from crawler.transport import BodyTooLargeError, Response, TransportError  # noqa: E402

BASE = 1_800_000_000
URL = "https://fixture.example/policy.pdf"
BODY = b'{"origin":"fixture","edition":1}'
CHANGED = b'{"origin":"fixture","edition":2}'
MODIFIED = "Thu, 01 Jan 2026 00:00:00 GMT"


def sha(body):
    return hashlib.sha256(body).hexdigest()


class MemoryArchive:
    """source_archive storage interface; immutable fixture bytes stay in process."""

    def __init__(self):
        self.objects = {}

    def put_new(self, key, body, content_type):
        if key in self.objects:
            raise archive.Exists(key)
        self.objects[key] = body

    def get(self, key):
        return self.objects[key]


def observation(at=0, *, source="fixture_source", url=URL, body=BODY, **extra):
    store = MemoryArchive()
    extra = {"origin": "fixture", **extra}
    key, _ = archive.put_observation(
        store, source, url, datetime.fromtimestamp(BASE + at, timezone.utc).isoformat(),
        sha(body), len(body), "application/json", extra)
    return json.loads(store.get(key))


def response(body=BODY, status=200, **headers):
    return Response(status, headers, iter([body[:7], body[7:]]))


def unread_body():
    raise AssertionError("a 304 body must not be consumed")
    yield b""  # pragma: no cover


class OfflineTest(unittest.TestCase):
    def setUp(self):
        self.no_socket = mock.patch("socket.socket", side_effect=AssertionError("offline test"))
        self.no_r2 = mock.patch.object(archive, "S3Store", side_effect=AssertionError("offline test"))
        self.no_socket.start()
        self.no_r2.start()
        self.addCleanup(self.no_socket.stop)
        self.addCleanup(self.no_r2.stop)

    def db(self, path=":memory:"):
        db = StateDB(path)
        self.addCleanup(db.close)
        return db

    def initial(self, db=None, **extra):
        db = db or self.db()
        return db.record_observation(observation(
            etag='"fixture-v1"', last_modified=MODIFIED, **extra))


class ChangeDetectionTest(OfflineTest):
    def test_new_hash_and_validators_are_captured_and_sent_next_time(self):
        db = self.db()
        result = decide(response(ETag='W/"fixture-v1"', **{"Last-Modified": MODIFIED}), None)
        self.assertEqual((result.kind, result.status, result.sha256, result.size_bytes),
                         ("new", 200, sha(BODY), len(BODY)))
        self.assertTrue(result.needs_spool)
        self.assertEqual(result.version_key, archive.object_key(sha(BODY)))
        state = db.record_observation(observation(**result.observation_extra(
            next_due=BASE + 86400, original_retained=True)))
        self.assertEqual(conditional_headers(state, clock=lambda: BASE + 1),
                         {"If-None-Match": 'W/"fixture-v1"', "If-Modified-Since": MODIFIED})
        self.assertEqual((state.last_attempt, state.last_success, state.last_verified),
                         (BASE, BASE, BASE))
        self.assertEqual(state.next_due, BASE + 86400)

    def test_304_and_same_hash_write_no_spool_entries_and_keep_old_versions(self):
        db = self.db()
        store = MemoryArchive()
        spool = mock.Mock()
        results = []
        state = None
        for offset, reply, body in (
                (0, response(ETag='"bad-etag"'), BODY),
                (1, Response(304, {}, unread_body()), None),
                (2, response(ETag='"renamed-etag"'), BODY),
                (3, response(CHANGED, ETag='"renamed-etag"'), CHANGED)):
            result = decide(reply, state)
            if result.needs_spool:
                spool.put(result.version_key, body)
                digest, _ = archive.put_raw(store, body, "application/json")
                self.assertEqual(digest, result.sha256)
            else:
                self.assertEqual(spool.put.call_count, 1)
            record = observation(offset, body=body or BODY, **result.observation_extra(
                next_due=BASE + offset + 1, original_retained=True))
            state = db.record_observation(record)
            self.assertEqual(state.last_verified, BASE + (0 if offset == 1 else offset))
            results.append(result)
        self.assertEqual([r.kind for r in results],
                         ["new", "unchanged", "unchanged_same_hash", "changed"])
        self.assertEqual(spool.put.call_count, 2)
        self.assertNotEqual(results[0].version_key, results[-1].version_key)
        self.assertEqual(store.get(results[0].version_key), BODY)
        self.assertEqual(store.get(results[-1].version_key), CHANGED)
        self.assertEqual(state.last_sha256, sha(CHANGED))

    def test_monthly_verification_ignores_bad_etag_and_304_does_not_postpone_it(self):
        db = self.db()
        state = self.initial(db)
        every = DEFAULT_VERIFY_EVERY_S
        self.assertFalse(full_verification_due(state, clock=lambda: BASE + every - 1))
        state = db.record_observation(observation(every - 1, status=304))
        self.assertEqual(state.last_success, BASE + every - 1)
        self.assertEqual(state.last_verified, BASE)
        self.assertTrue(conditional_headers(state, clock=lambda: BASE + every - 1))
        self.assertTrue(full_verification_due(state, clock=lambda: BASE + every))
        self.assertEqual(conditional_headers(state, clock=lambda: BASE + every), {})
        result = decide(response(CHANGED, ETag=state.etag), state)
        self.assertEqual(result.kind, "changed")
        state = db.record_observation(observation(every, body=CHANGED,
            **result.observation_extra(next_due=BASE + every + 1, original_retained=True)))
        self.assertFalse(full_verification_due(state, clock=lambda: BASE + every + 1))
        self.assertEqual(conditional_headers(state, clock=lambda: BASE + every + 1),
                         {"If-None-Match": '"fixture-v1"'})

    def test_missing_or_unretained_state_and_zero_interval_force_full_bytes(self):
        state = self.initial()
        for current in (None, CrawlState("fixture_source", URL),
                        replace(state, original_retained=False), replace(state, last_verified=None)):
            with self.subTest(state=current):
                self.assertEqual(conditional_headers(current, clock=lambda: BASE + 1), {})
        self.assertEqual(conditional_headers(state, clock=lambda: BASE + 1, verify_every_s=0), {})
        self.assertEqual(conditional_headers(state, clock=lambda: BASE + 5, verify_every_s=5), {})
        self.assertTrue(conditional_headers(state, clock=lambda: BASE + 4, verify_every_s=5))

    def test_individual_validators_and_changed_200_clears_missing_validators(self):
        state = self.initial()
        self.assertEqual(conditional_headers(replace(state, etag=None), clock=lambda: BASE + 1),
                         {"If-Modified-Since": MODIFIED})
        self.assertEqual(conditional_headers(replace(state, last_modified=None), clock=lambda: BASE + 1),
                         {"If-None-Match": '"fixture-v1"'})
        result = decide(response(ETag='"v2"'), state)
        self.assertEqual((result.kind, result.etag, result.last_modified),
                         ("unchanged_same_hash", '"v2"', None))
        updated = decide(Response(304, {"ETag": '"304-updated"'}, unread_body()), state)
        self.assertEqual((updated.etag, updated.last_modified), ('"304-updated"', MODIFIED))

    def test_unsolicited_304_and_non_success_statuses_are_rejected_without_reading(self):
        for state in (None, CrawlState("fixture_source", URL),
                      replace(self.initial(), original_retained=False)):
            with self.subTest(state=state), self.assertRaises(ValueError):
                decide(Response(304, {}, unread_body()), state)
        for status in (201, 206, 301, 401, 403, 404, 429, 500, 503):
            with self.subTest(status=status), self.assertRaises(ValueError):
                decide(Response(status, {}, unread_body()), self.initial())

    def test_hashing_is_streamed_up_to_hard_cap(self):
        chunk = b'origin=fixture\n' * 4096
        repeats = HARD_OBJECT_CAP_BYTES // len(chunk)
        result = decide(Response(200, {}, (chunk for _ in range(repeats))), None)
        expected = hashlib.sha256()
        for _ in range(repeats):
            expected.update(chunk)
        self.assertEqual((result.sha256, result.size_bytes),
                         (expected.hexdigest(), len(chunk) * repeats))

    def test_caps_lengths_chunk_types_and_stream_errors_never_return_decisions(self):
        cases = (
            (response(**{"Content-Length": "999"}), 5, BodyTooLargeError),
            (response(), len(BODY) - 1, BodyTooLargeError),
            (response(**{"Content-Length": str(len(BODY) + 1)}), 100, ValueError),
            (response(**{"Content-Length": "invalid"}), 100, ValueError),
            (Response(200, {}, iter(["origin=fixture"])), 100, ValueError),
        )
        for reply, cap, error in cases:
            with self.subTest(reply=reply), self.assertRaises(error):
                decide(reply, None, object_cap_bytes=cap)
        for cap in (0, -1, True, HARD_OBJECT_CAP_BYTES + 1):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                decide(response(), None, object_cap_bytes=cap)
        def broken():
            yield BODY
            raise TransportError("fixture truncated stream")
        with self.assertRaises(TransportError):
            decide(Response(200, {}, broken()), None)
        self.assertEqual(decide(response(**{"Content-Length": str(len(BODY))}), None).sha256,
                         sha(BODY))

    def test_config_and_clock_validation(self):
        self.assertEqual(CrawlerConfig().verify_every_s, 30 * 86400)
        self.assertFalse(CrawlerConfig().network_enabled)
        self.assertEqual(config_from_dict({"verify_every_s": 12}).verify_every_s, 12)
        self.assertEqual(config_from_dict({"verify_every_s": 0}).verify_every_s, 0)
        for bad in (-1, True, "12", float("inf"), float("nan")):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                config_from_dict({"verify_every_s": bad})
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                conditional_headers(None, clock=lambda: BASE, verify_every_s=bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                conditional_headers(None, clock=lambda: bad)

    def test_header_injection_is_rejected(self):
        with self.assertRaises(ValueError):
            decide(response(ETag="fixture\r\nInjected: value"), None)
        state = replace(self.initial(), last_modified="fixture\ninvalid")
        with self.assertRaises(ValueError):
            conditional_headers(state, clock=lambda: BASE + 1)


class StateTest(OfflineTest):
    def test_schema_recorded_and_rows_survive_reopen_without_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite3"
            with StateDB(path) as db:
                state = self.initial(db)
                self.assertEqual(db.schema_version, SCHEMA_VERSION)
            with StateDB(path) as db:
                self.assertEqual(list(db.rows()), [state])
                self.assertIs(db.get("fixture_source", URL).original_retained, True)
            with closing(sqlite3.connect(path)) as reader:
                self.assertEqual(reader.execute("PRAGMA journal_mode").fetchone()[0], "delete")
                self.assertEqual(reader.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertFalse(Path(str(path) + "-wal").exists())

    def test_newer_and_unknown_unversioned_schema_refused_without_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "newer.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
            before = path.read_bytes()
            with self.assertRaises(SchemaVersionError):
                StateDB(path)
            self.assertEqual(path.read_bytes(), before)
            with closing(sqlite3.connect(path)) as db:
                db.execute("PRAGMA user_version=0")
                db.execute("CREATE TABLE unknown_schema (origin TEXT)")
                db.commit()
            with self.assertRaises(SchemaVersionError):
                StateDB(path)

    def test_failures_preserve_success_metadata_and_reset_only_on_success(self):
        db = self.db()
        first = self.initial(db)
        for at, status in ((1, 403), (2, None)):
            current = db.record_observation(observation(at, status=status,
                reason="fixture blocked" if status else "fixture timeout", body=CHANGED,
                etag='"must-not-replace"', original_retained=False, next_due=BASE + 100))
            self.assertEqual(current.consecutive_failures, at)
            self.assertEqual(replace(current, last_attempt=first.last_attempt,
                                     consecutive_failures=0, next_due=first.next_due), first)
        recovered = db.record_observation(observation(3, status=304))
        self.assertEqual(recovered.consecutive_failures, 0)
        self.assertEqual((recovered.last_success, recovered.last_verified), (BASE + 3, BASE))
        self.assertEqual((recovered.etag, recovered.last_modified), (first.etag, first.last_modified))
        recovered = db.record_observation(observation(4, body=CHANGED, original_retained=False))
        self.assertFalse(recovered.original_retained)
        self.assertEqual((recovered.etag, recovered.last_modified), (None, None))
        self.assertEqual(recovered.last_sha256, sha(CHANGED))
        with self.assertRaises(ValueError):
            db.record_observation(observation(5, status=304))
        self.assertEqual(db.get("fixture_source", URL), recovered)

    def test_first_failure_and_independent_source_url_rows(self):
        db = self.db()
        failed = db.record_observation(observation(status=None, reason="fixture timeout"))
        self.assertEqual(failed.consecutive_failures, 1)
        self.assertIsNone(failed.last_sha256)
        self.assertIsNone(failed.last_success)
        self.assertIsNone(failed.last_verified)
        self.assertFalse(failed.original_retained)
        self.assertTrue(decide(response(), failed).needs_spool)
        db.record_observation(observation(source="fixture_other"))
        db.record_observation(observation(url=URL + "?edition=2", body=CHANGED))
        self.assertEqual(len(list(db.rows())), 3)
        self.assertIsNone(db.get("missing", URL))
        self.assertEqual(db.get("fixture_source", URL), failed)

    def test_rebuild_round_trip_from_actual_archive_json_unordered_and_duplicated(self):
        live, rebuilt = self.db(), self.db()
        history = [
            observation(etag='"first"', last_modified=MODIFIED, next_due=BASE + 50),
            observation(1, status=304, etag='"304-tag"', next_due=BASE + 100),
            observation(2, status=200, etag='"same-hash"', next_due=BASE + 200),
            observation(3, body=CHANGED, original_retained=False, next_due=BASE + 300),
            observation(4, status=503, reason="fixture outage", next_due=BASE + 400),
            observation(5, status=None, reason="fixture timeout", next_due=BASE + 500),
            observation(source="fixture_other", body=CHANGED),
            observation(url=URL + "?historic=1"),
            observation(1, url=URL + "?historic=1", status=403, reason="fixture blocked"),
        ]
        for record in history:
            live.record_observation(record)
        rebuilt.record_observation(observation(source="fixture_stale"))
        rebuilt.rebuild_from_observations(iter(list(reversed(history)) + [history[4]]))
        self.assertEqual(list(rebuilt.rows()), list(live.rows()))
        self.assertEqual(rebuilt.get("fixture_source", URL).consecutive_failures, 2)
        self.assertIsNone(rebuilt.get("fixture_stale", URL))
        rebuilt.rebuild_from_observations(iter(history))
        self.assertEqual(list(rebuilt.rows()), list(live.rows()))

    def test_rebuild_is_atomic_on_invalid_history_or_iterator_failure(self):
        db = self.db()
        first = self.initial(db)
        for history in ([observation(1, status=304)],
                        [observation(), observation(etag='"conflicting"')],
                        [observation(1), observation(2, sha256="bad")]):
            with self.subTest(history=history), self.assertRaises(ValueError):
                db.rebuild_from_observations(iter(history))
            self.assertEqual(list(db.rows()), [first])
        def broken():
            yield observation(1)
            raise RuntimeError("fixture interrupted history")
        with self.assertRaises(RuntimeError):
            db.rebuild_from_observations(broken())
        self.assertEqual(list(db.rows()), [first])
        db.rebuild_from_observations(iter([]))
        self.assertEqual(list(db.rows()), [])

    def test_malformed_and_stale_observations_do_not_mutate_state(self):
        db = self.db()
        first = self.initial(db)
        for change in ({"observed_at": "2026-01-01"}, {"observed_at": None},
                       {"source_id": ""}, {"url": ""}, {"status": True},
                       {"status": 403}, {"sha256": "bad"}, {"next_due": float("nan")},
                       {"original_retained": 1}, {"etag": "invalid\nheader"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                db.record_observation({**observation(1), **change})
            self.assertEqual(list(db.rows()), [first])
        for at in (0, -1):
            with self.subTest(at=at), self.assertRaises(ValueError):
                db.record_observation(observation(at))
        self.assertEqual(list(db.rows()), [first])

    def test_legacy_observation_defaults_and_timezone_ordering(self):
        record = observation()
        db = self.db()
        state = db.record_observation(record)
        self.assertTrue(state.original_retained)
        self.assertEqual(state.next_due, BASE)
        later = observation(1)
        later["observed_at"] = datetime.fromtimestamp(BASE + 1, timezone.utc).astimezone(
            timezone(timedelta(hours=9))).isoformat()
        db.rebuild_from_observations(iter([later, record]))
        self.assertEqual(db.get("fixture_source", URL).last_attempt, BASE + 1)

    def test_single_writer_contention_fails_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite3"
            with StateDB(path) as db, closing(sqlite3.connect(path, timeout=0)) as other:
                other.execute("BEGIN IMMEDIATE")
                with self.assertRaises(sqlite3.OperationalError):
                    db.record_observation(observation())
                other.rollback()
                self.initial(db)


class StaticBoundaryTest(unittest.TestCase):
    def test_new_modules_have_no_fetch_or_archive_write_dependencies(self):
        root = Path(__file__).resolve().parent.parent / "crawler"
        allowed_imports = {"json", "math", "re", "sqlite3", "contextlib", "dataclasses",
                           "datetime", "typing", "hashlib", "time", "config", "state", "transport"}
        forbidden_calls = {"open", "request", "fetch", "put_raw", "put_observation", "sleep",
                           "system", "popen", "getenv"}
        for filename in ("changes.py", "state.py"):
            tree = ast.parse((root / filename).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(a.name in allowed_imports for a in node.names))
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed_imports)
                elif isinstance(node, ast.Call):
                    name = getattr(node.func, "id", getattr(node.func, "attr", None))
                    self.assertNotIn(name, forbidden_calls, filename)


if __name__ == "__main__":
    unittest.main()
