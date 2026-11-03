"""Untrusted sample hashes and source URLs must fail before archive/network I/O."""
import argparse
import copy
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as sa
import validation_check as vc
import verify_sources as vs


BAD_HASHES = ("", "a" * 63, "a" * 65, "g" * 64, "a" * 63 + "\n",
              "../" * 20 + "file", "/tmp/file", "ab/cd/../../file", None)
BAD_URLS = ("", "http://example.org/file", "file:///tmp/file", "ftp://example.org/file",
            "//example.org/file", "https:///file", "https://user:pass@example.org/file",
            "https://example.org:bad/file", "https://example.org:0/file",
            "https://example.org:65536/file", " https://example.org/file",
            "https://example.org/\nfile", "https://example.org\\evil/file", None)


class SampleMetadata(unittest.TestCase):
    def setUp(self):
        self.data = {"samples": [{"sample_id": "sample", "sha256": "a" * 64,
                                 "url": "https://example.org/file", "derived_manifest_sha256": "b" * 64}],
                     "gaps": {"G01"}, "families": {}, "screens": {}}

    def test_existing_samples_and_valid_hex_https_metadata_pass(self):
        self.assertEqual(vc.check(vc.load())[0], [])
        for digest in ("a" * 64, "0123456789abcdef" * 4, "ABCDEF0123456789" * 4):
            for url in ("https://example.org/file?q=1", "HTTPS://EXAMPLE.org:443/file",
                        "https://example.org:8443/file", "https://[::1]/file"):
                with self.subTest(digest=digest, url=url):
                    self.data["samples"][0].update(sha256=digest, url=url)
                    self.assertEqual(vc.check(self.data)[0], [])
                    self.assertEqual(sa.object_key(digest), f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}")

    def test_bad_hashes_are_metadata_errors_independent_of_encoded_documents(self):
        for value in BAD_HASHES:
            with self.subTest(value=value):
                data = copy.deepcopy(self.data)
                data["samples"][0]["sha256"] = value
                self.assertTrue(any("samples.csv: sample sha256 must be 64 hex characters" in e
                                    for e in vc.check(data)[0]))

    def test_bad_urls_are_metadata_errors(self):
        for value in BAD_URLS:
            with self.subTest(value=value):
                data = copy.deepcopy(self.data)
                data["samples"][0]["url"] = value
                self.assertTrue(any("samples.csv: sample url must be an HTTPS URL" in e
                                    for e in vc.check(data)[0]))

    def test_invalid_hash_is_rejected_before_any_store_probe_or_read(self):
        raw = mock.Mock()
        args = argparse.Namespace(raw="file:///unused", endpoint_url=None)
        for digest in BAD_HASHES:
            with self.subTest(digest=digest), tempfile.TemporaryDirectory() as tmp:
                args.out = tmp
                row = {"sample_id": "sample", "sha256": digest, "cache_path": "document.pdf"}
                with mock.patch.object(sa, "store", return_value=raw), \
                        mock.patch.object(vs.tempfile, "mkdtemp", return_value=tmp), \
                        mock.patch.object(sa.csv, "DictReader", return_value=[row]), \
                        mock.patch.object(sa, "SAMPLES", mock.MagicMock()), \
                        redirect_stderr(io.StringIO()):
                    self.assertEqual(sa.with_budget(None, None, lambda: sa.cmd_fetch(args)), 1)
                    self.assertEqual(sa.with_budget(None, None, lambda: sa.cmd_verify(args)), 1)
                    with self.assertRaises(sa.UnsafeStoreKey):
                        vs.materialize(args, [row])
                raw.get.assert_not_called()
                raw.exists.assert_not_called()
                raw.list.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
