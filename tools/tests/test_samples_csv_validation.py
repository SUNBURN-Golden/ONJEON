"""Untrusted sample hashes and source URLs must fail before archive/network I/O."""
import argparse
import copy
import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as sa
import validation_check as vc
import verify_sources as vs


BAD_HASHES = ("", "a" * 63, "a" * 65, "g" * 64, "a" * 63 + "\n",
              "a" * 64 + "\n", "../" * 20 + "file", "/tmp/file", "ab/cd/../../file",
              "ab/cd/" + "../" * 18 + "evil", "/tmp/" + "a" * 59,
              "..\\" * 20 + "evil", "ａ" * 64, "٠" * 64,
              None, 0, True, b"a" * 64, [], {})
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

    def test_each_row_is_checked_even_when_encoded_hashes_match(self):
        for row_index in range(len(vc.load()["samples"])):
            with self.subTest(row_index=row_index):
                data = vc.load()
                row = data["samples"][row_index]
                # Exactly 64 characters, but unsafe as either an object key or a filename.
                row["sha256"] = "ab/cd/" + "../" * 18 + "evil"
                self.assertEqual(len(row["sha256"]), 64)
                for family in data["families"].values():
                    for doc in family["documents"]:
                        if doc["sample_id"] == row["sample_id"]:
                            doc["sha256"] = row["sha256"]
                self.assertEqual(vc.check(data)[0], [
                    f"samples.csv: {row['sample_id']} sha256 must be 64 hex characters"])

    def test_csv_cli_rejects_bad_or_missing_sha256_and_accepts_valid_hex(self):
        for digest in (*[x for x in BAD_HASHES if isinstance(x, str)],
                       None, "0123456789abcdef" * 4, "ABCDEF0123456789" * 4):
            with self.subTest(digest=digest), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                row = dict(self.data["samples"][0])
                if digest is None:
                    del row["sha256"]  # Missing CSV column, distinct from an empty cell.
                else:
                    row["sha256"] = digest
                with (root / "samples.csv").open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerow(row)
                (root / "GAP_REPORT.md").write_text("| G01 | gap |\n", encoding="utf-8")
                output = io.StringIO()
                with mock.patch.object(vc, "VAL", root), \
                        mock.patch.object(sys, "argv", ["validation_check.py"]), \
                        redirect_stdout(output):
                    result = vc.main()
                if digest in ("0123456789abcdef" * 4, "ABCDEF0123456789" * 4):
                    self.assertEqual(result, 0, output.getvalue())
                    self.assertIn("internal consistency ok", output.getvalue())
                else:
                    self.assertEqual(result, 1, output.getvalue())
                    self.assertIn("samples.csv: sample sha256 must be 64 hex characters",
                                  output.getvalue())

    def test_object_key_rejects_bad_hashes_directly(self):
        for digest in BAD_HASHES:
            with self.subTest(digest=digest), self.assertRaisesRegex(
                    sa.UnsafeStoreKey, "sha256 must be 64 hex characters"):
                sa.object_key(digest)

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
