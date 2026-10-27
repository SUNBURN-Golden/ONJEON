"""CRAWL-09 offline evidence; synthetic records and bytes have origin=fixture.

No S3 success path is executed here: every remote case either fails an explicit
gate or stops in budget admission before a client can be constructed.
"""
import ast
import hashlib
import io
import itertools
import json
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import r2_budget as budget  # noqa: E402
import source_archive as archive  # noqa: E402
from crawler import uploader  # noqa: E402
from crawler.config import HARD_OBJECT_CAP_BYTES  # noqa: E402
from crawler.gaps import GapRecord, GapWriter  # noqa: E402
from crawler.spool import IntegrityError, Spool  # noqa: E402
from crawler.status import upload_failed  # noqa: E402

BODY = b"%PDF-1.7\n% origin=fixture\nsynthetic original\n%%EOF\n"
URL = "https://fixture.example/document.pdf"
STAMP = "2026-10-25T00:00:00Z"
NOW = 1_800_000_000
META = {"origin": "fixture", "response_code": 200, "content_type": "application/pdf"}


def snapshot(root):
    return sorted((str(p.relative_to(root)), p.read_bytes() if p.is_file() else None)
                  for p in root.rglob("*"))


class UploaderTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.spool = Spool(self.root / "spool", clock=lambda: NOW)
        self.target_dir = self.root / "archive"
        self.target = self.target_dir.as_uri()
        self.out = io.StringIO()
        self.err = io.StringIO()
        for target in ("socket.socket", "urllib.request.urlopen", "subprocess.Popen",
                       "source_archive.S3Store", "time.sleep"):
            patcher = mock.patch(target, side_effect=AssertionError("offline fixture only"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, body=BODY, observed_at=STAMP):
        return self.spool.write_stream("fixture_source", URL, observed_at,
                                       iter((body,)), "pdf", META).entry

    def upload(self, mode="dry_run", **kwargs):
        with redirect_stderr(self.err):
            return uploader.upload(self.spool, self.target, mode,
                                   clock=lambda: NOW, output=self.out, **kwargs)

    def rows(self):
        return [json.loads(line) for line in self.out.getvalue().splitlines()]

    def marks(self):
        return [row for row in self.spool._events() if row["event"] == "uploaded"]

    def expected(self, entry, target):
        rec = entry.observation
        digest, _ = archive.put_raw(target, BODY, rec["content_type"])
        extra = {key: value for key, value in META.items() if key != "content_type"}
        return archive.put_observation(target, rec["source_id"], rec["url"],
                                       rec["observed_at"], digest, len(BODY),
                                       rec["content_type"], extra)[0]

    def test_default_cli_and_api_write_nothing_and_report_new_key_estimate(self):
        self.write()
        before = snapshot(self.root)
        self.assertEqual(self.upload(), 0)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.target_dir.exists())
        rows = self.rows()
        self.assertEqual([r["state"] for r in rows[:-1]], ["stored"] * 3)
        self.assertEqual(rows[-1]["class_a_estimate"], 3)  # original + observation + status
        self.assertEqual(rows[-1]["class_b_estimate"], 3)
        self.assertEqual(rows[-1]["bytes"], sum(r["bytes"] for r in rows[:-1]))
        self.assertEqual(rows[-1]["mode"], "dry_run")
        with redirect_stdout(self.out):
            self.assertEqual(uploader.main(["--spool", str(self.spool.dir),
                                            "--target", self.target], clock=lambda: NOW), 0)
        self.assertEqual(snapshot(self.root), before)

    def test_dry_run_existing_keys_and_within_batch_dedup_use_archive_rules(self):
        first = self.write()
        self.write()
        before = snapshot(self.root)
        self.assertEqual(self.upload(), 0)
        summary = self.rows()[-1]
        self.assertEqual((summary["stored"], summary["already_present"]), (3, 2))
        self.assertEqual(snapshot(self.root), before)
        self.expected(first, archive.LocalStore(self.target_dir))
        before = snapshot(self.root)
        self.out.seek(0)
        self.out.truncate()
        self.assertEqual(self.upload(), 0)
        summary = self.rows()[-1]
        self.assertEqual((summary["stored"], summary["already_present"]), (1, 4))
        self.assertEqual(snapshot(self.root), before)

    def test_apply_matches_source_archive_exactly_and_verifies_before_marks(self):
        entry = self.write()
        canonical = archive.LocalStore(self.root / "canonical")
        observation_key = self.expected(entry, canonical)
        original_hash = uploader._hash_file
        verified = []

        def read_hash(path, *args):
            if self.target_dir in path.parents:
                self.assertEqual(self.marks(), [])
                verified.append(str(path.relative_to(self.target_dir)))
            return original_hash(path, *args)

        with mock.patch.object(archive, "put_raw", wraps=archive.put_raw) as raw, \
                mock.patch.object(archive, "put_observation", wraps=archive.put_observation) as obs, \
                mock.patch.object(uploader, "_hash_file", side_effect=read_hash):
            self.assertEqual(self.upload("apply"), 0)
        self.assertTrue(raw.called)
        self.assertTrue(any(isinstance(c.args[0], archive.LocalStore) for c in obs.call_args_list))
        dest = archive.LocalStore(self.target_dir)
        for key in canonical.list(""):
            self.assertEqual(dest.get(key), canonical.get(key))
        self.assertIn(observation_key, verified)
        self.assertTrue(any(key.startswith("status/") for key in verified))
        self.assertEqual([mark["entry_id"] for mark in self.marks()], [entry.entry_id])
        self.assertTrue(self.marks()[0]["verified_file"])
        self.assertTrue(entry.object_path.exists())
        self.assertTrue(entry.observation_path.exists())
        self.assertEqual(list(self.spool.list_pending()), [])

    def test_same_bytes_are_already_present_without_rewrite(self):
        entry = self.write()
        self.expected(entry, archive.LocalStore(self.target_dir))
        original = uploader._Local.put_new
        writes = []

        def put(st, key, body, ctype):
            writes.append(key)
            return original(st, key, body, ctype)

        with mock.patch.object(uploader._Local, "put_new", new=put):
            self.assertEqual(self.upload("apply"), 0)
        self.assertEqual(len(writes), 1)
        self.assertTrue(writes[0].startswith("status/"))
        self.assertEqual([r["state"] for r in self.rows()[:2]], ["already_present"] * 2)
        self.assertEqual(self.rows()[-1]["class_a_estimate"], 1)
        # A retry with the same timestamp and no pending documents is a no-op.
        before = snapshot(self.target_dir)
        self.assertEqual(self.upload("apply"), 0)
        self.assertEqual(snapshot(self.target_dir), before)

    def test_changed_bytes_at_existing_object_or_observation_stop_exit_three(self):
        for kind in ("object", "observation"):
            with self.subTest(kind=kind):
                entry = self.write()
                store = archive.LocalStore(self.target_dir)
                observation_key = self.expected(entry, store)
                key = archive.object_key(entry.observation["sha256"]) if kind == "object" else observation_key
                path = self.target_dir / key
                path.write_bytes(b"origin=fixture conflicting bytes")
                before = snapshot(self.target_dir)
                self.assertEqual(self.upload("apply", cleanup=True), 3)
                self.assertEqual(snapshot(self.target_dir), before)
                self.assertEqual(self.marks(), [])
                self.assertTrue(entry.object_path.exists())
                self.assertTrue(entry.observation_path.exists())
                path.unlink()

    def test_dry_run_conflict_also_writes_nothing(self):
        entry = self.write()
        path = self.target_dir / archive.object_key(entry.observation["sha256"])
        path.parent.mkdir(parents=True)
        path.write_bytes(b"origin=fixture conflict")
        before = snapshot(self.root)
        self.assertEqual(self.upload(), 3)
        self.assertEqual(snapshot(self.root), before)

    def test_verification_failure_keeps_all_entries_and_sets_alert(self):
        first = self.write()
        self.write(observed_at="2026-10-25T01:00:00Z")
        original = uploader._hash_file

        def bad_hash(path, *args):
            if (self.target_dir in path.parents and "observations" in path.parts
                    and path.exists()):
                return "0" * 64, 0
            return original(path, *args)

        with mock.patch.object(uploader, "_hash_file", side_effect=bad_hash):
            self.assertEqual(self.upload("apply", cleanup=True), 1)
        self.assertEqual(self.marks(), [])
        self.assertEqual(len(list(self.spool.list_pending())), 2)
        self.assertTrue(first.object_path.exists())
        flag = json.loads((self.spool.dir / "upload_status.json").read_text())
        self.assertTrue(upload_failed(flag))

    def test_cleanup_removes_only_verified_spool_entries_and_never_archive(self):
        first = self.write()
        second = self.write(observed_at="2026-10-25T01:00:00Z")
        self.assertEqual(self.upload("apply"), 0)
        archived = snapshot(self.target_dir)
        # A later pending entry shares the same body: cleanup must retain it.
        pending = self.write(observed_at="2026-10-25T02:00:00Z")
        with uploader._locked(self.spool, lambda: NOW) as view:
            uploader._cleanup(view)
        self.assertFalse(first.observation_path.exists())
        self.assertFalse(second.observation_path.exists())
        self.assertTrue(pending.object_path.exists())
        self.assertEqual(snapshot(self.target_dir), archived)
        self.out = io.StringIO()
        with redirect_stderr(self.err):
            self.assertEqual(uploader.upload(self.spool, self.target, "apply", cleanup=True,
                                             clock=lambda: NOW + 1, output=self.out), 0)
        self.assertFalse(pending.object_path.exists())
        self.assertFalse(pending.observation_path.exists())
        for path, body in archived:
            if body is not None:
                self.assertEqual((self.target_dir / path).read_bytes(), body)

    def test_cleanup_ignores_unverified_marks(self):
        entry = self.write()
        self.spool.mark_uploaded(entry.entry_id)
        with uploader._locked(self.spool, lambda: NOW) as view:
            uploader._cleanup(view)
        self.assertTrue(entry.object_path.exists())
        self.assertTrue(entry.observation_path.exists())

    def test_gap_and_status_use_existing_prefixes_without_claiming_acquisition(self):
        writer = GapWriter(self.spool.dir / "gaps.jsonl")
        gap = GapRecord("fixture_source", STAMP, "blocked", http_status=403)
        writer.append(gap)
        before = snapshot(self.root)
        self.assertEqual(self.upload(gaps=writer), 0)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(self.rows()[-1]["class_a_estimate"], 2)
        self.out = io.StringIO()
        self.assertEqual(self.upload("apply", gaps=writer, gap_urls={"fixture_source": URL},
                                     status={"origin": "fixture"}), 0)
        files = [p for p in self.target_dir.rglob("*") if p.is_file()]
        self.assertEqual({p.relative_to(self.target_dir).parts[0] for p in files},
                         {"observations", "status"})
        obs_path = next(p for p in files if "observations" in p.parts)
        rec = json.loads(obs_path.read_text())
        self.assertTrue(rec["gap"])
        self.assertIsNone(rec["status"])
        self.assertEqual(rec["reason"], "blocked")
        self.assertEqual(rec["http_status"], 403)
        self.assertEqual(rec["url"], URL)
        self.assertFalse({"object_key", "sha256", "bytes"} & rec.keys())
        capture = uploader._Capture()
        digest = archive.sha256_bytes(uploader._json(gap.as_observation(URL)))
        key, _ = archive.put_observation(capture, gap.source_id, URL, gap.observed_at,
                                        digest, 0, "application/json", gap.observation_extra())
        self.assertEqual(str(obs_path.relative_to(self.target_dir)), key)
        status_path = next(p for p in files if "status" in p.parts)
        self.assertEqual(json.loads(status_path.read_text())["gap_count"], 1)
        self.assertFalse(json.loads(status_path.read_text())["upload_failed"])
        self.assertEqual(writer.summary().gap_count, 1)  # gap evidence never removed

    def test_every_missing_remote_gate_refuses_before_client_or_budget(self):
        for apply, allow, env, job in itertools.product((False, True), repeat=4):
            if all((apply, allow, env, job)):
                continue
            with self.subTest(apply=apply, allow=allow, env=env, job=job), \
                    mock.patch.dict("os.environ", {"ONJEON_CRAWLER_ALLOW_R2": "1" if env else "0"}), \
                    mock.patch.object(archive, "store") as factory, \
                    mock.patch.object(archive, "with_budget") as wrapper:
                before = snapshot(self.root)
                with self.assertRaises(uploader.Refused):
                    uploader.upload(self.spool, "s3://fixture", "apply" if apply else "dry_run",
                                    allow_real_r2=allow, job="fixture-job" if job else None,
                                    clock=lambda: NOW, output=self.out)
                factory.assert_not_called()
                wrapper.assert_not_called()
                self.assertEqual(snapshot(self.root), before)

    def test_budget_stop_passes_job_and_endpoint_then_keeps_spool_with_alert(self):
        entry = self.write()
        before = snapshot(self.target_dir)
        with mock.patch.dict("os.environ", {"ONJEON_CRAWLER_ALLOW_R2": "1"}), \
                mock.patch.object(budget, "start", side_effect=budget.BudgetError("fixture stop")) as start, \
                mock.patch.object(budget, "finish", return_value=None) as finish, \
                mock.patch.object(archive, "store") as factory, redirect_stderr(self.err):
            code = uploader.upload(self.spool, "s3://fixture", "apply", allow_real_r2=True,
                                   job="fixture-job", endpoint_url="http://127.0.0.1:1",
                                   clock=lambda: NOW, output=self.out)
        self.assertEqual(code, 4)
        start.assert_called_once_with("fixture-job", "http://127.0.0.1:1")
        finish.assert_called_once_with("budget_stop")
        factory.assert_not_called()
        self.assertEqual(snapshot(self.target_dir), before)
        self.assertEqual(self.marks(), [])
        self.assertTrue(entry.object_path.exists())
        self.assertTrue(entry.observation_path.exists())
        flag = json.loads((self.spool.dir / "upload_status.json").read_text())
        self.assertTrue(flag["upload_failed"])
        self.assertTrue(upload_failed(flag))
        self.assertEqual(self.rows()[-1], {"exit_code": 4, "upload_failed": True})

    def test_budget_stop_after_documents_preserves_every_entry_and_recovery_clears_alert(self):
        entry = self.write()
        original = archive.put_once
        attempted_status = []

        def stop(st, key, body, ctype):
            if key.startswith("status/"):
                attempted_status.append(key)
                raise budget.BudgetError("origin=fixture budget stop")
            return original(st, key, body, ctype)

        with mock.patch.object(archive, "put_once", side_effect=stop):
            self.assertEqual(self.upload("apply", cleanup=True), 4)
        self.assertEqual(len(attempted_status), 1)  # no retry
        self.assertEqual(self.marks(), [])
        self.assertTrue(entry.object_path.exists())
        self.assertTrue(entry.observation_path.exists())
        flag_path = self.spool.dir / "upload_status.json"
        self.assertTrue(upload_failed(json.loads(flag_path.read_text())))
        self.assertEqual(self.upload("apply"), 0)
        self.assertFalse(upload_failed(json.loads(flag_path.read_text())))

    def test_in_batch_observation_collision_matches_apply_conflict(self):
        self.write()
        self.spool.write_stream("fixture_source", URL, STAMP, iter((BODY,)), "pdf",
                                {**META, "response_code": 201})
        before = snapshot(self.root)
        self.assertEqual(self.upload(), 3)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(self.upload("apply"), 3)
        self.assertEqual(self.marks(), [])

    def test_create_race_keeps_if_absent_semantics_without_a_second_object(self):
        store = uploader._Local(self.target_dir)
        key = archive.object_key(archive.sha256_bytes(BODY))
        original = archive.LocalStore.put_new

        for winner, expected in ((BODY, "already_present"), (b"origin=fixture other", None)):
            path = self.target_dir / key
            path.unlink(missing_ok=True)

            def race(st, candidate, body, ctype):
                original(st, candidate, winner, ctype)
                raise archive.Exists(candidate)

            with mock.patch.object(archive.LocalStore, "put_new", new=race):
                if expected:
                    self.assertEqual(archive.put_raw(store, BODY, "application/pdf")[1], expected)
                else:
                    with self.assertRaises(archive.Conflict):
                        archive.put_raw(store, BODY, "application/pdf")
            self.assertEqual(path.read_bytes(), winner)

    def _check_duplicate_local_upload_memory(self):
        size = 2 * 1024 * 1024
        body = BODY + b"x" * (size - len(BODY))
        self.write(body)
        archive.put_raw(archive.LocalStore(self.target_dir), body, "application/pdf")
        del body
        tracemalloc.start()
        try:
            self.assertEqual(self.upload("apply"), 0)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, size + 1024 * 1024)

    def test_remote_adapter_never_falls_back_to_an_unbounded_download(self):
        # Exercise only the adapter interface, never an s3:// upload or client.
        backend = mock.Mock()
        adapter = uploader._Remote(backend)
        backend.stored_sha256.return_value = None
        with self.assertRaises(IntegrityError):
            adapter.stored_sha256("fixture-key")
        backend.stored_sha256.return_value = archive.ABSENT
        self.assertIs(adapter.stored_sha256("fixture-key"), archive.ABSENT)
        with self.assertRaises(IntegrityError):
            adapter.get("fixture-key")
        backend.get.assert_not_called()
        adapter.put_new("fixture-key", BODY, "application/pdf")
        backend.put_new.assert_called_once_with("fixture-key", BODY, "application/pdf")

    def test_spool_symlinks_are_refused_before_cleanup_can_reach_archive(self):
        entry = self.write()
        archived = self.spool.dir / "retained" / entry.object_path.name
        archived.parent.mkdir()
        entry.object_path.rename(archived)
        entry.object_path.parent.rmdir()
        entry.object_path.parent.symlink_to(archived.parent, target_is_directory=True)
        before = snapshot(self.root)
        with self.assertRaises(IntegrityError):
            self.upload("apply", cleanup=True)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(archived.read_bytes(), BODY)

    def test_corrupt_spool_and_sidecar_cannot_be_acknowledged(self):
        entry = self.write()
        entry.object_path.write_bytes(b"origin=fixture corrupt")
        self.assertEqual(self.upload("apply", cleanup=True), 1)
        self.assertEqual(self.marks(), [])
        entry.object_path.write_bytes(BODY)
        entry.observation_path.write_text('{"origin":"fixture"}')
        self.assertEqual(self.upload("apply", cleanup=True), 1)
        self.assertEqual(self.marks(), [])

    def test_capped_reads_hashes_and_sparse_oversize_object(self):
        entry = self.write()
        with entry.object_path.open("r+b") as stream:
            stream.truncate(HARD_OBJECT_CAP_BYTES + 1)
        with self.assertRaises(IntegrityError):
            uploader._bounded_read(entry.object_path, HARD_OBJECT_CAP_BYTES)
        self.assertEqual(self.upload(), 1)
        self.assertEqual(self.marks(), [])

    def test_incomplete_transaction_dry_run_preserves_evidence(self):
        self.write()
        # A torn journal must be recovered by the spool owner, not by dry-run.
        with self.spool.journal.open("ab") as stream:
            stream.write(b'{"origin":"fixture"')
        before = snapshot(self.root)
        with self.assertRaises(IntegrityError):
            self.upload()
        self.assertEqual(snapshot(self.root), before)

    def test_invalid_modes_targets_and_cleanup_are_refused(self):
        for target, mode, cleanup in ((self.target, "other", False),
                                      ("https://fixture.example", "apply", False),
                                      (self.target, "dry_run", True)):
            with self.subTest(target=target, mode=mode), self.assertRaises(uploader.Refused):
                uploader.upload(self.spool, target, mode, cleanup=cleanup, clock=lambda: NOW)

    def test_static_no_fetch_secrets_or_archive_delete_interface(self):
        tree = ast.parse(Path(uploader.__file__).read_text())
        forbidden = {"socket", "urllib", "http", "subprocess", "boto3", "botocore",
                     "requests", "random", "threading"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertFalse({name.name.split(".")[0] for name in node.names} & forbidden)
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], forbidden)
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"delete_object", "delete_objects", "rmtree", "system", "sleep"})
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if ast.unparse(node.func) == "os.environ.get":
                    self.assertEqual(ast.literal_eval(node.args[0]), "ONJEON_CRAWLER_ALLOW_R2")
                if ast.unparse(node.func) == "importlib.import_module":
                    self.assertEqual(ast.literal_eval(node.args[0]), "source_archive")


class UploaderMemoryTest(unittest.TestCase):
    def test_duplicate_local_upload_memory_is_one_object_plus_bounded_metadata(self):
        # Python 3.13 pathlib interns path components. In a shared test process,
        # resizing the global intern table can add megabytes to tracemalloc's
        # peak, depending on earlier tests. Measure in a fresh interpreter;
        # the probe still uses UploaderTest's offline guards and original cap.
        probe = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--memory-probe"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)


if __name__ == "__main__":
    if sys.argv[1:] == ["--memory-probe"]:
        suite = unittest.TestSuite([UploaderTest("_check_duplicate_local_upload_memory")])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(not result.wasSuccessful())
    unittest.main()
