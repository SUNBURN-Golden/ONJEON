"""Audit 3: restore only bytes matching the requested content-addressed R2 key.

Real S3Store reads, botocore Stubber responses, synthetic credentials, no network.
"""
import argparse
import base64
import csv
import hashlib
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import r2_budget
import source_archive as sa

try:
    from botocore.stub import Stubber
except ImportError:
    Stubber = None


@unittest.skipIf(Stubber is None, "boto3/botocore not installed")
class R2Fetch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.samples = self.root / "samples.csv"
        self.out = self.root / "restored"
        self.body = b"<html>public disclosure</html>"
        self.row = dict(sample_id="sample", cache_path="nested/page.html",
                        sha256=sa.sha256_bytes(self.body))
        self.args = argparse.Namespace(raw="s3://test-raw/archive", out=str(self.out),
                                       endpoint_url="https://audit-test.r2.cloudflarestorage.com")
        for patcher in (
            mock.patch.object(sa, "SAMPLES", self.samples),
            mock.patch.object(r2_budget, "ACTIVE", mock.Mock(
                meter=None, policy={"per_request": {"max_attempts": 1}})),
            mock.patch.dict(os.environ, {"R2_ACCESS_KEY_ID": "test-key",
                                         "R2_SECRET_ACCESS_KEY": "test-secret"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.raw = sa.store(self.args.raw, self.args.endpoint_url)
        self.addCleanup(self.raw.s3.close)
        self.assertEqual(self.raw.provider, "r2")
        self.write_samples(self.row)

    def write_samples(self, *rows):
        with self.samples.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerows(rows)

    def queue_get(self, stub, row, body, checksum=None):
        stream = io.BytesIO(body)
        response = {"Body": stream, "ContentLength": len(body)}
        if checksum is not None:
            response["ChecksumSHA256"] = checksum
        stub.add_response("get_object", response, {
            "Bucket": "test-raw", "Key": f"archive/{sa.object_key(row['sha256'])}",
        })
        return stream

    def fetch(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sa, "store", return_value=self.raw) as store, \
                redirect_stdout(out), redirect_stderr(err):
            code = sa.cmd_fetch(self.args)
        store.assert_called_once_with(self.args.raw, self.args.endpoint_url)
        return code, out.getvalue(), err.getvalue()

    def test_matching_bytes_restore_without_server_checksum(self):
        with Stubber(self.raw.s3) as stub:
            stream = self.queue_get(stub, self.row, self.body)
            code, out, err = self.fetch()
            stub.assert_no_pending_responses()
        self.assertEqual(code, 0)
        self.assertIn("restored originals", out)
        self.assertEqual(err, "")
        self.assertEqual((self.out / self.row["cache_path"]).read_bytes(), self.body)
        self.assertTrue(stream.closed)

    def test_overwritten_bytes_rejected_even_with_expected_server_checksum(self):
        expected_checksum = base64.b64encode(hashlib.sha256(self.body).digest()).decode()
        # Same length and empty replacements, with absent, forged, or replacement checksums.
        for body in (b"X" * len(self.body), b""):
            actual_checksum = base64.b64encode(hashlib.sha256(body).digest()).decode()
            for checksum in (None, expected_checksum, actual_checksum):
                for existing in (False, True):
                    with self.subTest(body=body, checksum=checksum, existing=existing), \
                            tempfile.TemporaryDirectory(dir=self.root) as output_root:
                        self.out = Path(output_root) / "restored"
                        self.args.out = str(self.out)
                        dest = self.out / self.row["cache_path"]
                        if existing:
                            dest.parent.mkdir(parents=True)
                            dest.write_bytes(b"keep existing destination")
                        with Stubber(self.raw.s3) as stub:
                            stream = self.queue_get(stub, self.row, body, checksum)
                            code, out, err = self.fetch()
                            stub.assert_no_pending_responses()
                        self.assertEqual(code, 1)
                        self.assertEqual(out, "")
                        self.assertIn("sample: hash_mismatch", err)
                        self.assertIn(sa.object_key(self.row["sha256"]), err)
                        self.assertIn(f"downloaded {sa.sha256_bytes(body)}", err)
                        self.assertNotIn(self.args.endpoint_url, err)
                        self.assertTrue(stream.closed)
                        if existing:
                            self.assertEqual(dest.read_bytes(), b"keep existing destination")
                        else:
                            self.assertFalse(self.out.exists())

    def test_corrupt_middle_object_stops_restore_and_preserves_verified_files(self):
        corrupt = dict(self.row, sample_id="corrupt", cache_path="corrupt/page.html")
        later = dict(self.row, sample_id="later", cache_path="later/page.html")
        self.write_samples(self.row, corrupt, later)
        with Stubber(self.raw.s3) as stub:
            self.queue_get(stub, self.row, self.body)
            self.queue_get(stub, corrupt, b"overwritten after the first GET")
            code, out, err = self.fetch()
            stub.assert_no_pending_responses()  # any GET for the later row would fail
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("corrupt: hash_mismatch", err)
        self.assertEqual((self.out / self.row["cache_path"]).read_bytes(), self.body)
        self.assertFalse((self.out / "corrupt").exists())
        self.assertFalse((self.out / "later").exists())


if __name__ == "__main__":
    unittest.main()
