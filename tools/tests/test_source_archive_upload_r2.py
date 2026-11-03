"""Audit 4: validate cached sample bytes before any immutable R2 upload.

Real S3Store with botocore Stubber, synthetic credentials and no network.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
class R2ArchiveSamples(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.samples = self.root / "samples.csv"
        self.body = b"<html>public disclosure</html>"
        self.row = dict(sample_id="sample", cache_path="page.html", format="html",
                        sha256=sa.sha256_bytes(self.body), url="https://example.invalid/disclosure",
                        retrieved_at="2026-11-03T01:02:03Z", doc_role="terms")
        self.args = argparse.Namespace(raw="s3://test-raw/archive", derived="s3://test-derived/archive",
                                       derived_src=str(self.root / "extracted"), cache=str(self.cache),
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
        self.derived = sa.store(self.args.derived, self.args.endpoint_url)
        self.addCleanup(self.raw.s3.close)
        self.addCleanup(self.derived.s3.close)
        self.assertEqual(self.raw.provider, "r2")
        self.assertEqual(self.derived.provider, "r2")
        self.write_samples(self.row)
        src = Path(self.args.derived_src)
        src.mkdir()
        (src / "page.tables.txt").write_bytes(b"synthetic table cells")

    def write_samples(self, *rows):
        with self.samples.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerows(rows)

    def archive(self):
        stores = {self.args.raw: self.raw, "s3://test-derived/archive": self.derived}
        with mock.patch.object(sa, "store", side_effect=lambda target, endpoint: stores[target]), \
                redirect_stdout(io.StringIO()) as out:
            code = sa.cmd_archive_samples(self.args)
        return code, json.loads(out.getvalue())

    def test_mismatched_cache_makes_no_raw_or_derived_requests(self):
        for body in (b"changed original", b"X" * len(self.body), b""):
            with self.subTest(body=body):
                (self.cache / self.row["cache_path"]).write_bytes(body)
                # Empty response queues reject even HEAD/GET, as well as any PUT.
                with Stubber(self.raw.s3), Stubber(self.derived.s3):
                    code, result = self.archive()
                self.assertEqual((code, result), (1, [dict(sample_id="sample",
                    status="hash_differs_from_samples_csv", sha256=sa.sha256_bytes(body))]))

    @staticmethod
    def queue_object(stub, key, body, content_type, *, existing=False):
        params = {"Bucket": "test-raw", "Key": f"archive/{key}"}
        checksum = base64.b64encode(hashlib.sha256(body).digest()).decode()
        head = dict(params, ChecksumMode="ENABLED")
        if existing:
            stub.add_response("head_object", {"ChecksumSHA256": checksum}, head)
        else:
            stub.add_client_error("head_object", service_error_code="404", http_status_code=404,
                                  expected_params=head)
            stub.add_response("put_object", {}, dict(params, Body=body, ContentType=content_type,
                                                      IfNoneMatch="*", ChecksumSHA256=checksum))

    def test_bad_row_is_skipped_and_matching_row_uploads_then_reruns_without_put(self):
        bad_body = b"unapproved cached bytes"
        bad = dict(self.row, sample_id="bad", cache_path="bad.html")
        (self.cache / bad["cache_path"]).write_bytes(bad_body)
        (self.cache / self.row["cache_path"]).write_bytes(self.body)
        self.write_samples(bad, self.row)
        self.args.derived = None
        observation = dict(source_id="sample", url=self.row["url"], observed_at=self.row["retrieved_at"],
                           sha256=self.row["sha256"], bytes=len(self.body), content_type="text/html",
                           object_key=sa.object_key(self.row["sha256"]), sample_id="sample",
                           doc_role="terms", format="html")
        observation_body = (json.dumps(observation, ensure_ascii=False, indent=2) + "\n").encode()
        observation_key = f"observations/sample/20261103T010203Z_{self.row['sha256'][:16]}.json"
        for existing in (False, True):
            with self.subTest(existing=existing), Stubber(self.raw.s3) as stub:
                self.queue_object(stub, sa.object_key(self.row["sha256"]), self.body, "text/html",
                                  existing=existing)
                self.queue_object(stub, observation_key, observation_body, "application/json",
                                  existing=existing)
                code, result = self.archive()
                stub.assert_no_pending_responses()
            self.assertEqual(code, 1 if not existing else 0)
            state = "already_present" if existing else "stored"
            self.assertEqual(result[-1], dict(sample_id="sample", sha256=self.row["sha256"],
                                              object=state, observation=state))
            if not existing:
                self.assertEqual(result[0], dict(sample_id="bad", status="hash_differs_from_samples_csv",
                                                 sha256=sa.sha256_bytes(bad_body)))
                self.assertEqual(len(result), 2)
                self.write_samples(self.row)
            else:
                self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
