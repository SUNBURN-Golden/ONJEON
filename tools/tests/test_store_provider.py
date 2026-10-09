"""S3-compatible store selection (AWS / Cloudflare R2 / emulator) and copy verification.

No network: S3 calls are checked with botocore's Stubber (skipped when boto3 is not installed).
R2 differs from AWS in what the archive relies on: region "auto", its own credentials, and no
SSE header (R2 encrypts at rest and rejects x-amz-server-side-encryption). The write-once
guarantee must still come from If-None-Match: * on every put.
"""
import base64
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
import r2_budget  # noqa: E402
import source_archive as sa  # noqa: E402

try:
    import boto3  # noqa: F401
    from botocore.stub import Stubber
    HAVE_BOTO = True
except ImportError:
    HAVE_BOTO = False


def boto_can_put_conditionally():
    model = boto3.client("s3", region_name="auto", aws_access_key_id="k", aws_secret_access_key="s").meta.service_model
    return "IfNoneMatch" in model.operation_model("PutObject").input_shape.members

R2 = "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
FAKE = {"R2_ACCESS_KEY_ID": "k" * 32, "R2_SECRET_ACCESS_KEY": "s" * 64}


class Provider(unittest.TestCase):
    def test_selection(self):
        self.assertEqual(sa.provider_of(None), "aws")
        self.assertEqual(sa.provider_of(R2), "r2")
        self.assertEqual(sa.provider_of("http://127.0.0.1:5000"), "emulator")

    def test_r2_requires_https(self):
        with self.assertRaises(SystemExit):
            sa.provider_of(R2.replace("https", "http"))

    def test_lookalike_host_is_not_r2(self):
        self.assertEqual(sa.provider_of("https://x.r2.cloudflarestorage.com.evil.example"), "emulator")


@unittest.skipUnless(HAVE_BOTO, "boto3 not installed")
class OldBotocore(unittest.TestCase):
    def test_store_refuses_to_write_without_conditional_put(self):
        if boto_can_put_conditionally():
            self.skipTest("installed botocore supports If-None-Match")
        r2_budget.ACTIVE = mock.Mock(meter=None, policy={"per_request": {"max_attempts": 3}})
        try:
            with mock.patch.dict(os.environ, FAKE, clear=False):
                with self.assertRaises(SystemExit) as cm:
                    sa.S3Store("s3://onjeon-raw-sources", R2)
        finally:
            r2_budget.ACTIVE = None
        self.assertIn("If-None-Match", str(cm.exception))


@unittest.skipUnless(HAVE_BOTO and boto_can_put_conditionally(), "boto3 missing or older than 1.35")
class R2Store(unittest.TestCase):
    """Request parameters only: a budget session without a meter (limits are tested in test_r2_budget)."""

    def setUp(self):
        r2_budget.ACTIVE = mock.Mock(meter=None, policy={"per_request": {"max_attempts": 3}})

    def tearDown(self):
        r2_budget.ACTIVE = None

    def store(self, endpoint=R2, env=FAKE):
        with mock.patch.dict(os.environ, env, clear=False):
            return sa.S3Store("s3://onjeon-raw-sources", endpoint)

    def test_no_budget_session_sends_nothing(self):
        r2_budget.ACTIVE = None
        with mock.patch.dict(os.environ, FAKE, clear=False):
            with self.assertRaises(SystemExit) as cm:
                sa.S3Store("s3://onjeon-raw-sources", R2)
        self.assertIn("budget job", str(cm.exception))

    def test_missing_r2_credentials_never_fall_back_to_aws_chain(self):
        env = {k: "" for k in FAKE}
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(SystemExit):
                sa.S3Store("s3://onjeon-raw-sources", R2)

    def test_endpoint_from_environment(self):
        with mock.patch.dict(os.environ, {**FAKE, "ONJEON_S3_ENDPOINT": R2}, clear=False):
            st = sa.S3Store("s3://onjeon-raw-sources")
        self.assertEqual(st.provider, "r2")
        self.assertEqual(st.s3.meta.region_name, "auto")

    def expected_put(self, body, sse):
        p = {"Bucket": "onjeon-raw-sources", "Key": "k", "Body": body, "ContentType": "text/plain",
             "IfNoneMatch": "*", "ChecksumSHA256": base64.b64encode(hashlib.sha256(body).digest()).decode()}
        if sse:
            p["ServerSideEncryption"] = "AES256"
        return p

    def test_r2_put_is_conditional_and_has_no_sse_header(self):
        st = self.store()
        with Stubber(st.s3) as stub:
            stub.add_response("put_object", {}, self.expected_put(b"x", sse=False))
            st.put_new("k", b"x", "text/plain")
            stub.assert_no_pending_responses()

    def test_aws_put_keeps_sse(self):
        with mock.patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "a", "AWS_SECRET_ACCESS_KEY": "b"}, clear=False):
            st = sa.S3Store("s3://onjeon-raw-sources", None)
        with Stubber(st.s3) as stub:
            stub.add_response("put_object", {}, self.expected_put(b"x", sse=True))
            st.put_new("k", b"x", "text/plain")

    def head_absent(self, stub):
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404)

    def test_stored_checksum_decides_without_sending_bytes(self):
        st = self.store()
        same = base64.b64encode(hashlib.sha256(b"x").digest()).decode()
        with Stubber(st.s3) as stub:
            stub.add_response("head_object", {"ChecksumSHA256": same},
                              {"Bucket": "onjeon-raw-sources", "Key": "k", "ChecksumMode": "ENABLED"})
            self.assertEqual(sa.put_once(st, "k", b"x", "text/plain"), "already_present")
            stub.add_response("head_object", {"ChecksumSHA256": same},
                              {"Bucket": "onjeon-raw-sources", "Key": "k", "ChecksumMode": "ENABLED"})
            with self.assertRaises(sa.Conflict):
                sa.put_once(st, "k", b"y", "text/plain")
            stub.assert_no_pending_responses()  # no put_object was sent

    def test_existing_key_without_checksum_is_compared_by_download_not_reuploaded(self):
        st = self.store()
        with Stubber(st.s3) as stub:
            stub.add_response("head_object", {}, {"Bucket": "onjeon-raw-sources", "Key": "k", "ChecksumMode": "ENABLED"})
            stub.add_response("get_object", {"Body": io.BytesIO(b"x")}, {"Bucket": "onjeon-raw-sources", "Key": "k"})
            self.assertEqual(sa.put_once(st, "k", b"x", "text/plain"), "already_present")
            stub.assert_no_pending_responses()

    def test_412_is_exists_and_put_once_compares_bytes(self):
        st = self.store()
        with Stubber(st.s3) as stub:
            self.head_absent(stub)
            stub.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
            stub.add_response("get_object", {"Body": io.BytesIO(b"x")}, {"Bucket": "onjeon-raw-sources", "Key": "k"})
            self.assertEqual(sa.put_once(st, "k", b"x", "text/plain"), "already_present")
            self.head_absent(stub)
            stub.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
            stub.add_response("get_object", {"Body": io.BytesIO(b"old")}, {"Bucket": "onjeon-raw-sources", "Key": "k"})
            with self.assertRaises(sa.Conflict):
                sa.put_once(st, "k", b"new", "text/plain")

    def test_other_errors_are_not_treated_as_exists(self):
        st = self.store()
        with Stubber(st.s3) as stub:
            stub.add_client_error("put_object", service_error_code="NotImplemented", http_status_code=501)
            with self.assertRaises(Exception) as cm:
                st.put_new("k", b"x", "text/plain")
            self.assertNotIsInstance(cm.exception, sa.Exists)


class VerifyCopy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.src_url, self.dst_url = f"file://{root}/src", f"file://{root}/dst"
        self.src, self.dst = sa.store(self.src_url), sa.store(self.dst_url)
        body = b"original"
        self.okey = sa.object_key(hashlib.sha256(body).hexdigest())
        for st in (self.src, self.dst):
            st.put_new(self.okey, body, "application/pdf")
            st.put_new("observations/s/1.json", b"{}", "application/json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self):
        rep = Path(self.tmp.name) / "r.json"
        a = mock.Mock(src=self.src_url, dst=self.dst_url, report=str(rep), endpoint_url=None, expected=None)
        with redirect_stdout(io.StringIO()):
            code = sa.cmd_verify_copy(a)
        return code, json.loads(rep.read_text())

    def test_identical(self):
        code, r = self.run_cmd()
        self.assertEqual((code, r["summary"]), (0, {"byte_identical": 2}))

    def test_missing_in_destination_fails(self):
        self.src.put_new("observations/s/2.json", b"{}", "application/json")
        code, r = self.run_cmd()
        self.assertEqual(code, 1)
        self.assertEqual(r["summary"].get("missing"), 1)

    def test_changed_bytes_fail(self):
        (Path(self.tmp.name) / "dst/observations/s/1.json").write_bytes(b"{\"x\":1}")
        code, r = self.run_cmd()
        self.assertEqual(code, 1)
        self.assertEqual(r["summary"].get("hash_mismatch"), 1)

    def test_extra_in_destination_is_reported(self):
        self.dst.put_new("observations/s/9.json", b"{}", "application/json")
        code, r = self.run_cmd()
        self.assertEqual(r["extra_in_destination"], ["observations/s/9.json"])
        self.assertEqual(code, 0)  # extra keys are reported; they are not a failed copy of the source

    def test_pinned_listing_without_source_store(self):
        lst = Path(self.tmp.name) / "listing.json"
        with redirect_stdout(io.StringIO()):
            sa.cmd_listing(mock.Mock(src=self.src_url, out=str(lst), endpoint_url=None))
        rep = Path(self.tmp.name) / "r.json"
        a = mock.Mock(src=None, expected=str(lst), dst=self.dst_url, report=str(rep), endpoint_url=None)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sa.cmd_verify_copy(a), 0)
        (Path(self.tmp.name) / "dst/observations/s/1.json").write_bytes(b"[]")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sa.cmd_verify_copy(a), 1)


if __name__ == "__main__":
    unittest.main()
