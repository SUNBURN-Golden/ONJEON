"""Local archive keys are untrusted bucket data; all I/O must stay inside the root."""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as sa


class LocalStorePaths(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / "archive"
        self.root.mkdir()
        self.store = sa.LocalStore(self.root)
        self.outside = self.base / "outside"
        self.outside.mkdir()
        (self.outside / "sentinel").write_bytes(b"keep")

    def operations(self, key):
        return {
            "put_new": lambda: self.store.put_new(key, b"new", "text/plain"),
            "get": lambda: self.store.get(key),
            "exists": lambda: self.store.exists(key),
            "list": lambda: self.store.list(key),
        }

    def assert_rejected(self, key):
        for name, operation in self.operations(key).items():
            with self.subTest(key=key, operation=name):
                with self.assertRaises(ValueError):
                    operation()
        self.assertEqual((self.outside / "sentinel").read_bytes(), b"keep")
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), ["sentinel"])

    def test_traversal_absolute_and_noncanonical_keys_are_rejected(self):
        for key in ("../outside/sentinel", "a/../../outside/new", str(self.outside / "sentinel"),
                    ".", "..", "a/..", "a/../alias", "a/./b", "a//b", "//outside/x",
                    "a\\..\\outside", "C:/outside/x", "C:outside", "bad\x00key"):
            self.assert_rejected(key)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_empty_key_is_only_valid_for_listing_root(self):
        for name in ("put_new", "get", "exists"):
            with self.subTest(operation=name), self.assertRaises(ValueError):
                self.operations("")[name]()
        self.assertEqual(self.store.list(""), [])

    def test_directory_suffix_is_only_valid_for_listing(self):
        self.store.put_new("nested/file", b"stored", "text/plain")
        for name in ("put_new", "get", "exists"):
            with self.subTest(operation=name), self.assertRaises(ValueError):
                self.operations("nested/")[name]()
        self.assertEqual(self.store.list("nested/"), ["nested/file"])
        self.assert_rejected("nested//")

    def test_directory_and_file_symlinks_cannot_escape(self):
        (self.root / "link").symlink_to(self.outside, target_is_directory=True)
        (self.root / "file").symlink_to(self.outside / "sentinel")
        (self.root / "missing").symlink_to(self.outside / "new")
        for key in ("link/sentinel", "link/new/deep", "file", "missing"):
            self.assert_rejected(key)

    def test_listing_root_refuses_external_symlinks(self):
        for target in (self.outside, self.outside / "sentinel", self.outside / "missing"):
            with self.subTest(target=target):
                link = self.root / "link"
                link.symlink_to(target)
                try:
                    with self.assertRaises(ValueError):
                        self.store.list("")
                finally:
                    link.unlink()

    def test_nested_keys_roundtrip_and_preserve_write_once_behavior(self):
        key = "derived/hash/text/tool@1/약관.txt"
        self.assertEqual(sa.put_once(self.store, key, b"original", "text/plain"), "stored")
        self.assertTrue(self.store.exists(key))
        self.assertEqual(self.store.get(key), b"original")
        self.assertEqual(self.store.list("derived/"), [key])
        self.assertEqual(sa.put_once(self.store, key, b"original", "text/plain"), "already_present")
        with self.assertRaises(sa.Conflict):
            sa.put_once(self.store, key, b"changed", "text/plain")
        self.assertEqual(self.store.get(key), b"original")
        self.assertFalse(self.store.exists("missing/key"))
        self.assertEqual(self.store.list("missing/"), [])

    def test_relative_root_remains_anchored_after_chdir(self):
        previous = Path.cwd()
        try:
            os.chdir(self.base)
            store = sa.LocalStore("archive")
            os.chdir(self.outside)
            store.put_new("key", b"data", "text/plain")
        finally:
            os.chdir(previous)
        self.assertEqual((self.root / "key").read_bytes(), b"data")
        self.assertFalse((self.outside / "archive").exists())

    def test_preexisting_temporary_symlink_cannot_redirect_write(self):
        body = b"new"
        # The former predictable staging name must not be followed when a key is written.
        link = self.root / f"key.{os.getpid()}.{id(body)}.partial"
        link.symlink_to(self.outside / "sentinel")
        self.store.put_new("key", body, "text/plain")
        self.assertEqual(self.store.get("key"), body)
        self.assertEqual((self.outside / "sentinel").read_bytes(), b"keep")
        self.assertTrue(link.is_symlink())
        link.unlink()
        self.assertEqual(self.store.list(""), ["key"])

    def test_concurrent_create_is_not_overwritten_and_staging_file_is_removed(self):
        link = os.link

        def competing_create(src, dst):
            Path(dst).write_bytes(b"winner")
            return link(src, dst)

        with mock.patch.object(sa.os, "link", side_effect=competing_create):
            with self.assertRaises(sa.Exists):
                self.store.put_new("key", b"loser", "text/plain")
        self.assertEqual(self.store.get("key"), b"winner")
        self.assertEqual(list(self.root.iterdir()), [self.root / "key"])

    def test_copy_from_bucket_refuses_malicious_keys(self):
        for key in ("../outside/new", "nested/../../outside/sentinel", str(self.outside / "new")):
            with self.subTest(key=key):
                bucket = mock.Mock()
                bucket.list.return_value = [key]
                bucket.get.return_value = b"forged"
                args = argparse.Namespace(src="s3://fixture", dst=self.root.as_uri(), endpoint_url=None)
                err = io.StringIO()
                with mock.patch.object(sa, "store", side_effect=[bucket, self.store]), \
                        redirect_stdout(io.StringIO()) as out, redirect_stderr(err):
                    code = sa.with_budget(None, None, lambda: sa.cmd_copy(args))
                self.assertEqual(code, 1)
                self.assertIn("unsafe store key", err.getvalue())
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(list(self.root.iterdir()), [])
                self.assertEqual((self.outside / "sentinel").read_bytes(), b"keep")
                self.assertFalse((self.outside / "new").exists())

    def test_copy_cli_refuses_external_symlink_without_traceback(self):
        (self.root / "leak").symlink_to(self.outside / "sentinel")
        dst = self.base / "destination"
        result = subprocess.run([
            sys.executable, "-I", str(Path(sa.__file__)), "copy",
            "--src", self.root.as_uri(), "--dst", dst.as_uri(),
        ], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("unsafe store key", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(dst.exists())

    def test_normal_copy_is_idempotent(self):
        self.store.put_new("observations/public/1.json", b"{}", "application/json")
        dst = sa.LocalStore(self.base / "destination")
        args = argparse.Namespace(src=self.root.as_uri(), dst=dst.root.as_uri(), endpoint_url=None)
        for expected in ({"stored": 1, "already_present": 0}, {"stored": 0, "already_present": 1}):
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(sa.cmd_copy(args), 0)
            self.assertEqual(json.loads(out.getvalue()), expected)
        self.assertEqual(dst.get("observations/public/1.json"), b"{}")

    def test_budget_is_settled_on_unsafe_key(self):
        import r2_budget
        with mock.patch.object(r2_budget, "start"), \
                mock.patch.object(r2_budget, "finish", return_value=None) as finish, \
                redirect_stderr(io.StringIO()):
            code = sa.with_budget("fixture-job", None, lambda: self.store.get("../outside/sentinel"))
        self.assertEqual(code, 1)
        finish.assert_called_once_with("unsafe_store_key")


if __name__ == "__main__":
    unittest.main()
