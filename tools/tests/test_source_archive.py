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
