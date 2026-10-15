"""Regression tests for tools/source_archive.py write paths (local store; no network, no S3).

Found in the 839ecdb review: put_derived_for() treated an existing derived key with different
content as already_present, so the stored file stayed old while the manifest recorded the new
input's hash. Every write now goes through put_once(): same bytes -> already_present,
different bytes -> Conflict, nothing overwritten.
"""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as sa  # noqa: E402


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.raw = sa.LocalStore(self.root / "raw")
        self.derived = sa.LocalStore(self.root / "derived")

    def tearDown(self):
        self.tmp.cleanup()


class PutOnce(Base):
    def test_same_bytes_is_already_present(self):
        self.assertEqual(sa.put_once(self.raw, "k", b"old", "text/plain"), "stored")
        self.assertEqual(sa.put_once(self.raw, "k", b"old", "text/plain"), "already_present")

    def test_different_bytes_conflict_and_keep_old(self):
        sa.put_once(self.raw, "k", b"old", "text/plain")
        with self.assertRaises(sa.Conflict):
            sa.put_once(self.raw, "k", b"changed", "text/plain")
        self.assertEqual(self.raw.get("k"), b"old")


class Raw(Base):
    def test_raw_object_is_idempotent(self):
        d1, s1 = sa.put_raw(self.raw, b"pdf-bytes", "application/pdf")
        d2, s2 = sa.put_raw(self.raw, b"pdf-bytes", "application/pdf")
        self.assertEqual((d1, s1, s2), (sha(b"pdf-bytes"), "stored", "already_present"))

    def test_corrupted_raw_object_is_a_conflict(self):
        digest = sha(b"pdf-bytes")
        key = sa.object_key(digest)
        (self.root / "raw" / key).parent.mkdir(parents=True)
        (self.root / "raw" / key).write_bytes(b"tampered")
        with self.assertRaises(sa.Conflict):
            sa.put_raw(self.raw, b"pdf-bytes", "application/pdf")


class Observations(Base):
    args = ("kb_sample", "https://example.org/a", "2026-10-09T04:43:40Z", "a" * 64, 10, "text/html")

    def test_identical_observation_is_already_present(self):
        k1, s1 = sa.put_observation(self.raw, *self.args, {"note": "x"})
        k2, s2 = sa.put_observation(self.raw, *self.args, {"note": "x"})
        self.assertEqual((k1, s1, s2), (k2, "stored", "already_present"))

    def test_same_key_different_record_is_a_conflict(self):
        k, _ = sa.put_observation(self.raw, *self.args, {"note": "x"})
        before = self.raw.get(k)
        with self.assertRaises(sa.Conflict):
            sa.put_observation(self.raw, *self.args, {"note": "different"})
        self.assertEqual(self.raw.get(k), before)


class Derived(Base):
    def write_src(self, text):
        src = self.root / f"src-{sha(text.encode())[:8]}"
        src.mkdir()
        (src / "terms.layout.txt").write_text(text, encoding="utf-8")
        return src

    def test_changed_derived_input_is_a_conflict_not_a_duplicate(self):
        row = {"sample_id": "s", "cache_path": "x/terms.pdf", "format": "text_pdf"}
        digest = "b" * 64
        sa.put_derived_for(self.derived, self.write_src("old"), digest, row)
        key = next(k for k in self.derived.list("derived/") if k.endswith("terms.layout.txt"))
        with self.assertRaises(sa.Conflict):
            sa.put_derived_for(self.derived, self.write_src("changed"), digest, row)
        self.assertEqual(self.derived.get(key), b"old")

    def test_same_derived_input_rerun_is_fine(self):
        row = {"sample_id": "s", "cache_path": "x/terms.pdf", "format": "text_pdf"}
        src = self.write_src("same")
        self.assertEqual(sa.put_derived_for(self.derived, src, "c" * 64, row)["outputs"], 1)
        # the manifest key is time-stamped per run; the output file itself must be already_present
        sa.put_derived_for(self.derived, src, "c" * 64, row)


class CopyCommand(Base):
    def test_copy_stops_on_conflict(self):
        sa.put_once(self.raw, "observations/x/1.json", b"src", "application/json")
        dst = sa.LocalStore(self.root / "dst")
        sa.put_once(dst, "observations/x/1.json", b"different", "application/json")
        argv = ["source_archive.py", "copy", "--src", f"file://{self.root}/raw", "--dst", f"file://{self.root}/dst"]
        old, sys.argv = sys.argv, argv
        try:
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = sa.main()
        finally:
            sys.argv = old
        self.assertEqual(code, 3)
        self.assertIn("conflict", err.getvalue())
        self.assertEqual(dst.get("observations/x/1.json"), b"different")


class StorageErrors(unittest.TestCase):
    """with_budget must not leak the endpoint (R2 account id) when botocore fails."""
    ENDPOINT = "https://0123456789abcdef.r2.cloudflarestorage.com"

    class FakeBotoError(Exception):
        pass

    def run_with(self, exc):
        def boom():
            raise exc
        err = io.StringIO()
        with mock.patch.object(sa, "boto_errors", lambda: (self.FakeBotoError,)), redirect_stderr(err):
            code = sa.with_budget(None, None, boom)
        return code, err.getvalue()

    def test_boto_error_prints_type_only(self):
        code, err = self.run_with(self.FakeBotoError(f'Could not connect to the endpoint URL: "{self.ENDPOINT}/bkt"'))
        self.assertEqual(code, 5)
        self.assertIn("FakeBotoError", err)
        self.assertNotIn("0123456789abcdef", err)
        self.assertNotIn("cloudflarestorage", err)
        self.assertNotIn("Traceback", err)

    def test_other_errors_still_propagate(self):
        with self.assertRaises(ValueError):
            self.run_with(ValueError("bug"))

    def test_budget_settles_as_storage_error(self):
        import r2_budget
        with mock.patch.object(r2_budget, "start"), \
                mock.patch.object(r2_budget, "finish", return_value=None) as fin, \
                mock.patch.object(sa, "boto_errors", lambda: (self.FakeBotoError,)), \
                redirect_stderr(io.StringIO()):
            code = sa.with_budget("job", None, lambda: (_ for _ in ()).throw(self.FakeBotoError(self.ENDPOINT)))
        self.assertEqual(code, 5)
        fin.assert_called_once_with("storage_error")

    def test_boto_errors_empty_without_botocore(self):
        with mock.patch.dict(sys.modules, {"botocore": None, "botocore.exceptions": None}):
            self.assertEqual(sa.boto_errors(), ())

    def test_real_botocore_classes_when_installed(self):
        try:
            from botocore.exceptions import EndpointConnectionError
        except ImportError:
            self.skipTest("botocore not installed")
        err = io.StringIO()
        def boom():
            raise EndpointConnectionError(endpoint_url=self.ENDPOINT)
        with redirect_stderr(err):
            self.assertEqual(sa.with_budget(None, None, boom), 5)
        self.assertNotIn("0123456789abcdef", err.getvalue())
        self.assertIn("EndpointConnectionError", err.getvalue())


class ConfinedPath(unittest.TestCase):
    """samples.csv cache_path is data: it must never reach outside the cache/output directory."""

    def test_normal_relative_path_resolves_inside(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(sa.confined_path(t, "a/b.pdf"), Path(t).resolve() / "a" / "b.pdf")

    def test_escapes_are_refused(self):
        with tempfile.TemporaryDirectory() as t:
            for bad in ("../x", "a/../../x", "/etc/x", "", ".", "a/.."):
                with self.subTest(bad=bad), self.assertRaises(sa.UnsafeCachePath):
                    sa.confined_path(t, bad)

    def test_symlink_out_of_base_is_refused(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as outside:
            (Path(t) / "link").symlink_to(outside)
            with self.assertRaises(sa.UnsafeCachePath):
                sa.confined_path(t, "link/x")

    def rows(self, cache_path):
        return [{"sample_id": "s", "cache_path": cache_path, "sha256": "0" * 64, "url": "u", "format": "html",
                 "doc_role": "d", "retrieved_at": "t"}]

    def test_fetch_refuses_traversal_before_writing(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "out"
            out.mkdir()
            raw = mock.Mock()
            with mock.patch.object(sa, "store", return_value=raw), \
                    mock.patch.object(sa, "SAMPLES", self.write_samples(t, "../escaped.txt")):
                with self.assertRaises(sa.UnsafeCachePath):
                    sa.cmd_fetch(mock.Mock(raw="file:///x", endpoint_url=None, out=str(out)))
            raw.get.assert_not_called()
            self.assertFalse((Path(t) / "escaped.txt").exists())

    def test_fetch_exit_code_via_with_budget(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(sa.with_budget(None, None, self.raise_unsafe), 1)

    @staticmethod
    def raise_unsafe():
        raise sa.UnsafeCachePath("x")

    def write_samples(self, t, cache_path):
        import csv
        p = Path(t) / "samples.csv"
        rows = self.rows(cache_path)
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return p

    def test_archive_samples_does_not_upload_files_outside_cache(self):
        with tempfile.TemporaryDirectory() as t:
            cache = Path(t) / "cache"
            cache.mkdir()
            (Path(t) / "secret.txt").write_bytes(b"not a source")
            args = mock.Mock(raw="file:///x", derived=None, endpoint_url=None, cache=str(cache))
            with mock.patch.object(sa, "store", return_value=mock.Mock()), \
                    mock.patch.object(sa, "put_raw") as put_raw, \
                    mock.patch.object(sa, "SAMPLES", self.write_samples(t, "../secret.txt")), \
                    redirect_stdout(io.StringIO()) as out:
                code = sa.cmd_archive_samples(args)
            put_raw.assert_not_called()
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.getvalue())[0]["status"], "unsafe_cache_path")


if __name__ == "__main__":
    unittest.main()


class DerivedAssociation(unittest.TestCase):
    """839ecdb follow-up: two samples sharing a directory got each other's derived files."""

    def test_shared_directory_files_go_to_their_own_original(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "klia"
            src.mkdir()
            (src / "list.tables.txt").write_text("list", encoding="utf-8")
            (src / "info_popup.tables.txt").write_text("popup", encoding="utf-8")
            store = sa.LocalStore(Path(t) / "derived")
            sa.put_derived_for(store, src, "1" * 64, {"sample_id": "a", "cache_path": "klia/list.html", "format": "html"})
            sa.put_derived_for(store, src, "2" * 64, {"sample_id": "b", "cache_path": "klia/info_popup.html", "format": "html"})
            a = [k for k in store.list(f"derived/{'1' * 64}/") if "manifests" not in k]
            b = [k for k in store.list(f"derived/{'2' * 64}/") if "manifests" not in k]
            self.assertEqual([k.rsplit("/", 1)[1] for k in a], ["list.tables.txt"])
            self.assertEqual([k.rsplit("/", 1)[1] for k in b], ["info_popup.tables.txt"])

    def test_scanned_ocr_pages_belong_to_the_scan(self):
        row = {"cache_path": "scan/terms.pdf", "format": "scanned_pdf"}
        self.assertTrue(sa.belongs_to("ocr/p-01.txt", row))
        self.assertTrue(sa.belongs_to("ocr_all.txt", row))
        self.assertFalse(sa.belongs_to("ocr/p-01.txt", {"cache_path": "x/terms.pdf", "format": "text_pdf"}))
