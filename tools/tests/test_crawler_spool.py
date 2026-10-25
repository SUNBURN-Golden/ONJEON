"""CRAWL-07 offline evidence; all synthetic input has origin=fixture.

Only local temporary files and in-process failures are used. No collector,
network, R2, process control, environment reads, delays or real clock is needed.
"""
import ast
import hashlib
import json
import os
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as archive  # noqa: E402
from crawler import spool as module  # noqa: E402
from crawler.config import HARD_OBJECT_CAP_BYTES  # noqa: E402
from crawler.spool import CapReached, IntegrityError, Rejected, Spool, Spooled  # noqa: E402
from crawler.transport import BodyTooLargeError, TransportError  # noqa: E402
from crawler.validate import RejectionReason  # noqa: E402

BODY = b"%PDF-1.7\n% origin=fixture\nsynthetic document\n%%EOF\n"
URL = "https://fixture.example/document.pdf"
STAMP = "2026-10-25T00:00:00Z"
NOW = 1_800_000_000
META = {"origin": "fixture", "request_path": "/document.pdf", "response_code": 200,
        "adapter_version": "fixture-adapter@1", "user_agent_version": "fixture-agent@1",
        "egress_country": "KR", "content_type": "application/pdf"}


class MemoryArchive:
    def __init__(self):
        self.data = {}

    def put_new(self, key, body, content_type):
        self.data[key] = body


class SpoolTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "spool"
        for target in ("socket.socket", "urllib.request.urlopen", "subprocess.Popen",
                       "source_archive.S3Store"):
            patcher = mock.patch(target, side_effect=AssertionError("offline fixture only"))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.spool = self.new_spool()

    def new_spool(self, **kwargs):
        return Spool(self.root, clock=lambda: NOW, **kwargs)

    def write(self, body=BODY, *, spool=None, chunks=None, meta=None, **kwargs):
        return (spool or self.spool).write_stream(
            "fixture_source", URL, STAMP,
            chunks if chunks is not None else iter((body[:9], body[9:])),
            kwargs.pop("declared_type", "pdf"), META if meta is None else meta, **kwargs)

    def events(self):
        return list(self.spool._events())

    def objects(self):
        return [path for path in (self.root / "objects").rglob("*") if path.is_file()]

    def assert_empty(self):
        self.assertEqual(self.objects(), [])
        self.assertEqual(list((self.root / "tmp").iterdir()), [])
        self.assertEqual(list((self.root / "observations").iterdir()), [])
        self.assertEqual(list(self.spool.list_pending()), [])

    def test_atomic_object_and_sidecar_match_archive_fields_and_values(self):
        renames = []
        real_rename = os.rename

        def rename(src, dst):
            self.assertFalse(dst.exists())
            self.assertEqual(src.parent, self.root / "tmp")
            # A prepared record is already durable when either file is published.
            self.assertEqual(self.events()[-1]["event"], "prepared")
            renames.append(dst)
            real_rename(src, dst)

        with mock.patch.object(module.os, "rename", side_effect=rename):
            result = self.write()
        self.assertIsInstance(result, Spooled)
        self.assertFalse(result.deduplicated)
        entry = result.entry
        sha = hashlib.sha256(BODY).hexdigest()
        self.assertEqual(entry.object_path, self.root / "objects" / sha[:2] / sha[2:4] / sha)
        self.assertEqual(entry.object_path.read_bytes(), BODY)
        self.assertEqual(renames, [entry.object_path, entry.observation_path])
        store = MemoryArchive()
        key, _ = archive.put_observation(store, "fixture_source", URL, STAMP,
                                        sha, len(BODY), "application/pdf", META)
        reference = json.loads(store.data[key])
        actual = json.loads(entry.observation_path.read_bytes())
        self.assertEqual(set(actual), set(reference))
        self.assertEqual(actual, reference)
        self.assertEqual(entry.observation, actual)
        self.assertEqual(self.spool.used_bytes, len(BODY))
        self.assertEqual(list(self.spool.list_pending()), [entry])
        self.assertEqual(list((self.root / "tmp").iterdir()), [])

    def test_same_bytes_same_timestamp_one_immutable_object_two_observations(self):
        first = self.write()
        original = first.entry.object_path.stat()
        second = self.write(chunks=iter([BODY]))
        self.assertTrue(second.deduplicated)
        self.assertEqual(first.entry.object_path, second.entry.object_path)
        self.assertNotEqual(first.entry.observation_path, second.entry.observation_path)
        self.assertEqual(first.entry.observation, second.entry.observation)
        self.assertEqual(first.entry.object_path.stat().st_ino, original.st_ino)
        self.assertEqual(first.entry.object_path.stat().st_mtime_ns, original.st_mtime_ns)
        self.assertEqual(len(self.objects()), 1)
        self.assertEqual(len(list(self.new_spool().list_pending())), 2)

    def test_streaming_memory_is_far_below_object_size(self):
        count = 384  # 24 MiB generated lazily, 64 KiB at a time.
        produced = 0

        def chunks():
            nonlocal produced
            yield BODY
            for _ in range(count):
                produced += 1
                yield b"x" * module.CHUNK_BYTES

        tracemalloc.start()
        try:
            result = self.write(chunks=chunks())
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertIsInstance(result, Spooled)
        self.assertEqual(produced, count)
        self.assertEqual(result.entry.observation["bytes"], len(BODY) + count * module.CHUNK_BYTES)
        self.assertLess(peak, 2 * 1024 * 1024)

    def test_per_object_cap_aborts_before_requesting_next_chunk(self):
        spool = self.new_spool(object_cap_bytes=len(BODY))

        def chunks():
            yield BODY
            yield b"overflow"
            self.fail("overflow must stop consuming the source")

        result = self.write(spool=spool, chunks=chunks())
        self.assertEqual(result, Rejected(RejectionReason.TOO_LARGE, len(BODY) + 8))
        self.assert_empty()
        self.assertEqual(self.events()[-1]["reason"], "too_large")
        self.assertIsInstance(self.write(spool=spool), Spooled)  # Exact cap is admitted.

    def test_total_cap_refuses_without_deleting_and_dedup_still_fits(self):
        spool = self.new_spool(cap_bytes=len(BODY))
        first = self.write(spool=spool)
        spool = self.new_spool(cap_bytes=len(BODY))
        snapshot = {path: path.read_bytes() for path in self.root.rglob("*")
                    if path.is_file() and path.name != "journal.jsonl"}
        changed = BODY + b"origin=fixture; second edition"
        result = self.write(changed, spool=spool)
        self.assertEqual(result, CapReached(len(BODY), len(BODY), len(changed)))
        for path, content in snapshot.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertTrue(self.write(spool=spool).deduplicated)
        self.assertEqual(spool.used_bytes, len(BODY))
        self.assertEqual(len(list(spool.list_pending())), 2)
        spool.mark_uploaded(first.entry.entry_id)
        # Acknowledgement frees no local capacity; cleanup belongs to the uploader.
        self.assertIsInstance(self.write(changed, spool=spool), CapReached)
        self.assertEqual(len(self.objects()), 1)

    def test_validation_rejections_are_journaled_without_spooling(self):
        cases = (
            (b"", {}, "pdf", RejectionReason.EMPTY),
            (b"<html>login required</html>", {}, "pdf", RejectionReason.LOGIN_HTML),
            (b"<html>captcha</html>", {}, "pdf", RejectionReason.CHALLENGE_HTML),
            (b"origin=fixture; invalid", {}, "pdf", RejectionReason.MAGIC_MISMATCH),
            (BODY, {"content_type": "text/html"}, "pdf", RejectionReason.MIME_MISMATCH),
            (BODY, {"content_length": len(BODY) + 1}, "pdf", RejectionReason.LENGTH_MISMATCH),
            (BODY, {}, "unknown", RejectionReason.UNSUPPORTED_TYPE),
        )
        for body, extra, kind, reason in cases:
            with self.subTest(reason=reason):
                result = self.write(body, meta={"origin": "fixture", **extra}, declared_type=kind)
                self.assertEqual(result.reason, reason)
                self.assertEqual(self.events()[-1]["reason"], reason.value)
                self.assert_empty()

    def test_document_formats_and_response_mime_are_preserved(self):
        cases = ((BODY, "pdf", "application/pdf"),
                 (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 origin=fixture", "doc", "application/msword"),
                 (b"PK\x03\x04 origin=fixture", "docx",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
        for body, kind, mime in cases:
            with self.subTest(kind=kind):
                result = self.write(body, declared_type=kind, meta={"origin": "fixture"})
                self.assertEqual(result.entry.observation["content_type"], mime)
        result = self.write(meta={"origin": "fixture", "content_type": "application/pdf; fixture=1"})
        self.assertEqual(result.entry.observation["content_type"], "application/pdf; fixture=1")

    def test_input_stream_failures_cleanup_and_record_reasons(self):
        for error, reason in ((TransportError("fixture"), RejectionReason.STREAM_ERROR),
                              (OSError("fixture"), RejectionReason.STREAM_ERROR),
                              (BodyTooLargeError("fixture"), RejectionReason.TOO_LARGE)):
            def chunks():
                yield BODY
                raise error
            with self.subTest(error=type(error)):
                self.assertEqual(self.write(chunks=chunks()).reason, reason)
                self.assert_empty()
        self.assertEqual(self.write(chunks=iter([BODY, "origin=fixture"])).reason,
                         RejectionReason.INVALID_STREAM)
        self.assert_empty()

    def test_unexpected_source_exception_propagates_and_removes_temp(self):
        def chunks():
            yield BODY
            raise RuntimeError("fixture")
        with self.assertRaises(RuntimeError):
            self.write(chunks=chunks())
        self.assert_empty()

    def test_validation_reads_finished_temp_and_detects_tampering(self):
        real_validate = module.validate_document

        def validate(info, declared):
            paths = list((self.root / "tmp").glob("*.partial"))
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].read_bytes(), BODY)
            result = real_validate(info, declared)
            paths[0].write_bytes(BODY + b"origin=fixture; altered")
            return result

        with mock.patch.object(module, "validate_document", side_effect=validate):
            with self.assertRaises(IntegrityError):
                self.write()
        self.assert_empty()

    def test_dedup_verifies_existing_hash_and_never_overwrites_corruption(self):
        entry = self.write().entry
        corrupt = b"origin=fixture; corrupted bytes"
        entry.object_path.write_bytes(corrupt)
        with self.assertRaises(IntegrityError):
            self.write()
        self.assertEqual(entry.object_path.read_bytes(), corrupt)
        self.assertEqual(len(list((self.root / "observations").iterdir())), 1)

    def test_restart_removes_orphans_and_preserves_pending_and_uploaded(self):
        first = self.write().entry
        second = self.write(BODY + b"origin=fixture; edition2").entry
        self.spool.mark_uploaded(first.entry_id)
        self.spool.mark_uploaded(first.entry_id)
        orphan = self.root / "tmp" / "fixture-orphan.partial"
        orphan.write_bytes(b"origin=fixture")
        keep = self.root / "tmp" / "fixture-unrelated.txt"
        keep.write_text("origin=fixture")
        restarted = self.new_spool()
        self.assertFalse(orphan.exists())
        self.assertTrue(keep.exists())
        self.assertEqual(list(restarted.list_pending()), [second])
        self.assertTrue(first.object_path.exists())
        self.assertTrue(first.observation_path.exists())
        self.assertEqual(restarted.used_bytes, len(BODY) * 2 + len(b"origin=fixture; edition2"))
        with self.assertRaises(KeyError):
            restarted.mark_uploaded("fixture_missing")

    def test_truncated_tail_is_ignored_and_new_appends_survive_second_restart(self):
        first = self.write().entry
        original = self.spool.journal.read_bytes()
        for tail in (b'{"event":"uploaded","entry_id":',
                     json.dumps({"event": "uploaded", "entry_id": first.entry_id}).encode()):
            with self.subTest(tail=tail):
                self.spool.journal.write_bytes(original + tail)
                restarted = self.new_spool()
                self.assertEqual(list(restarted.list_pending()), [first])
                self.assertTrue(restarted.journal.read_bytes().startswith(original + tail))
                second = self.write(spool=restarted).entry
                self.assertEqual(list(self.new_spool().list_pending()), [first, second])

    def test_pending_iterator_allows_upload_marks_and_snapshots_new_writes(self):
        first = self.write().entry
        second = self.write().entry
        pending = self.spool.list_pending()
        self.assertEqual(next(pending), first)
        self.spool.mark_uploaded(first.entry_id)
        third = self.write().entry
        self.spool.mark_uploaded(second.entry_id)
        self.assertEqual(list(pending), [])
        self.assertEqual(list(self.spool.list_pending()), [third])

    def test_complete_corrupt_journal_record_fails_closed(self):
        with self.spool.journal.open("ab") as stream:
            stream.write(b"origin=fixture; invalid JSON\n")
        with self.assertRaises(IntegrityError):
            self.new_spool()

    def test_recovery_finishes_crashes_before_each_publication_and_commit(self):
        for point in ("object", "sidecar", "commit"):
            with self.subTest(point=point):
                spool = Spool(self.root / point, clock=lambda: NOW)
                real_rename = os.rename
                real_append = spool._append

                def rename(src, dst):
                    if ((point == "object" and "objects" in dst.parts)
                            or (point == "sidecar" and dst.suffix == ".json")):
                        raise OSError("fixture crash")
                    real_rename(src, dst)

                def append(event, **fields):
                    if point == "commit" and event == "spooled":
                        raise OSError("fixture crash")
                    real_append(event, **fields)

                with mock.patch.object(module.os, "rename", side_effect=rename), \
                        mock.patch.object(spool, "_append", side_effect=append):
                    with self.assertRaises(OSError):
                        self.write(spool=spool)
                restarted = Spool(spool.dir, clock=lambda: NOW)
                pending = list(restarted.list_pending())
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0].object_path.read_bytes(), BODY)
                self.assertEqual(json.loads(pending[0].observation_path.read_bytes()),
                                 pending[0].observation)
                self.assertEqual(list(restarted.temp_dir.iterdir()), [])
                self.assertEqual(list(Spool(spool.dir, clock=lambda: NOW).list_pending()), pending)

    def test_recovery_finishes_deduplicated_observation_without_republishing_object(self):
        first = self.write().entry
        with mock.patch.object(self.spool, "_finish", side_effect=OSError("fixture crash")):
            with self.assertRaises(OSError):
                self.write()
        restarted = self.new_spool()
        self.assertEqual(len(list(restarted.list_pending())), 2)
        self.assertEqual(self.objects(), [first.object_path])
        self.assertEqual(list(restarted.temp_dir.iterdir()), [])

    def test_recovery_rejects_corrupt_prepared_bytes_without_deleting_evidence(self):
        with mock.patch.object(self.spool, "_finish", side_effect=OSError("fixture crash")):
            with self.assertRaises(OSError):
                self.write()
        temp = next(self.spool.temp_dir.glob("*.partial"))
        corrupt = b"origin=fixture; corrupted temporary bytes"
        temp.write_bytes(corrupt)
        with self.assertRaises(IntegrityError):
            self.new_spool()
        self.assertEqual(temp.read_bytes(), corrupt)
        self.assertEqual(self.objects(), [])

    def test_uncertain_prepare_append_preserves_temp_for_replay(self):
        real_append = self.spool._append

        def append(event, **fields):
            real_append(event, **fields)
            if event == "prepared":
                raise OSError("fixture: acknowledgement of journal fsync lost")

        with mock.patch.object(self.spool, "_append", side_effect=append):
            with self.assertRaises(OSError):
                self.write()
        self.assertEqual(len(list(self.spool.temp_dir.glob("*.partial"))), 1)
        pending = list(self.new_spool().list_pending())
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].object_path.read_bytes(), BODY)

    def test_recovery_refuses_conflicting_sidecar_without_overwriting_it(self):
        real_append = self.spool._append

        def append(event, **fields):
            if event == "spooled":
                raise OSError("fixture crash")
            real_append(event, **fields)

        with mock.patch.object(self.spool, "_append", side_effect=append):
            with self.assertRaises(OSError):
                self.write()
        sidecar = next((self.root / "observations").glob("*.json"))
        conflict = b'{"origin":"fixture","conflict":true}\n'
        sidecar.write_bytes(conflict)
        with self.assertRaises(IntegrityError):
            self.new_spool()
        self.assertEqual(sidecar.read_bytes(), conflict)
        self.assertEqual(self.objects()[0].read_bytes(), BODY)

    def test_fsync_includes_journal_and_files_before_publication(self):
        real_sync = os.fsync
        synced = []

        def sync(fd):
            stat = os.fstat(fd)
            synced.append((stat.st_dev, stat.st_ino))
            return real_sync(fd)

        with mock.patch.object(module.os, "fsync", side_effect=sync):
            result = self.write()
        # Rename preserves the inode of each fsynced temporary file.
        for path in (self.spool.journal, result.entry.object_path,
                     result.entry.observation_path, result.entry.object_path.parent,
                     result.entry.observation_path.parent, self.spool.temp_dir):
            stat = path.stat()
            self.assertIn((stat.st_dev, stat.st_ino), synced)
        self.assertTrue(all(event["at"] == NOW for event in self.events()))

    def test_lock_prevents_second_writer_or_recovery_from_deleting_active_temp(self):
        with self.spool.lock():
            active = self.spool.temp_dir / "fixture-active.partial"
            active.write_bytes(b"origin=fixture")
            with self.assertRaises(BlockingIOError):
                self.new_spool()
            with self.assertRaises(BlockingIOError):
                self.write()
            self.assertTrue(active.exists())

    def test_invalid_configuration_metadata_and_ids_are_rejected_before_streaming(self):
        for settings in ({"cap_bytes": 0}, {"cap_bytes": True},
                         {"object_cap_bytes": 0}, {"object_cap_bytes": True},
                         {"object_cap_bytes": HARD_OBJECT_CAP_BYTES + 1}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.new_spool(**settings)
        for metadata in ({"sha256": "origin=fixture"}, {"bytes": 3}, {"object_key": "../fixture"},
                         {"source_id": "fixture"}, {"content_length": -1},
                         {"content_type": 12}, {"origin": "fixture", "x": "x" * 65536}):
            with self.subTest(metadata=metadata.keys()), self.assertRaises((ValueError, TypeError)):
                self.write(meta=metadata)
        for source in ("../fixture", "fixture/escape", "FIXTURE", ""):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.spool.write_stream(source, URL, STAMP, iter([BODY]), "pdf", META)
        self.assert_empty()

    def test_spool_has_no_collection_or_environment_entry_points(self):
        tree = ast.parse(Path(module.__file__).read_text())
        imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, ast.Import)}
        self.assertFalse(imports & {"socket", "urllib", "http", "boto3", "subprocess"})
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                self.assertNotIn((node.value.id, node.attr),
                                 {("os", "environ"), ("os", "getenv"), ("os", "system")})


if __name__ == "__main__":
    unittest.main()
