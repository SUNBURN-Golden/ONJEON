"""ListObjectsV2 wire responses and the S3Store loop, without opening network sockets."""
import io
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from s3_stub import S3Stub  # noqa: E402
import source_archive as sa  # noqa: E402

try:
    import boto3  # noqa: F401
    from botocore.awsrequest import AWSResponse
    from urllib3.response import HTTPResponse
    HAVE_BOTO = True
except ImportError:
    HAVE_BOTO = False


class MemoryConnection:
    """Byte streams implementing the connection methods BaseHTTPRequestHandler uses."""

    def __init__(self, request):
        self.request = io.BytesIO(request)
        self.response = io.BytesIO()

    def makefile(self, *args):
        return self.request

    def sendall(self, body):
        self.response.write(body)


class Listing(unittest.TestCase):
    def setUp(self):
        # Capture the actual handler while suppressing the listening socket and server thread.
        with mock.patch("s3_stub.ThreadingHTTPServer") as server, mock.patch("s3_stub.threading.Thread"):
            server.return_value.server_address = ("127.0.0.1", 12345)
            self.stub = S3Stub()
            self.handler = server.call_args.args[1]
        self.addCleanup(self.stub.stop)

    def seed(self, keys, bucket="raw"):
        with self.stub.lock:
            self.stub.objects.update({(bucket, k): b"x" for k in keys})

    def request(self, path):
        connection = MemoryConnection(f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
        self.handler(connection, ("127.0.0.1", 0), self.stub.server)
        headers, _, body = connection.response.getvalue().partition(b"\r\n\r\n")
        lines = headers.decode().split("\r\n")
        status = int(lines[0].split()[1])
        return status, dict(line.split(": ", 1) for line in lines[1:]), body

    def page(self, **params):
        query = urlencode({"list-type": "2", **params})
        status, _headers, body = self.request(f"/raw?{query}")
        self.assertEqual(status, 200)
        return ET.fromstring(body)

    def test_continuation_pages_filter_sort_and_escape_keys(self):
        keys = ["docs/한.pdf", "docs/가 나&<.pdf", "docs/a+?.pdf"]
        self.seed(keys + ["other/ignored"])
        self.seed(["docs/other-bucket"], bucket="other")
        token, seen = None, []
        for index, key in enumerate(sorted(keys)):
            params = {"prefix": "docs/", "max-keys": 1}
            if token:
                params["continuation-token"] = token
            page = self.page(**params)
            self.assertEqual(page.findtext("ContinuationToken"), token)
            self.assertEqual(page.findtext("Prefix"), "docs/")
            self.assertEqual(page.findtext("MaxKeys"), "1")
            self.assertEqual(page.findtext("KeyCount"), "1")
            self.assertEqual(page.findtext("Contents/Key"), key)
            seen.extend(node.text for node in page.findall("Contents/Key"))
            self.assertEqual(page.findtext("IsTruncated"), str(index < 2).lower())
            next_token = page.findtext("NextContinuationToken")
            if index < 2:
                self.assertTrue(next_token)
                self.assertNotEqual(next_token, token)
            else:
                self.assertIsNone(next_token)
            token = next_token
        self.assertEqual(seen, sorted(keys))
        self.assertEqual(self.stub.counts(), {"class_a": 3, "class_b": 0, "put_bytes": 0})

    def test_default_limit_and_exact_page_boundary(self):
        keys = [f"docs/{i:04d}" for i in range(1001)]
        self.seed(keys)
        first = self.page(prefix="docs/")
        self.assertEqual(first.findtext("KeyCount"), "1000")
        self.assertEqual(first.findtext("MaxKeys"), "1000")
        self.assertEqual(first.findtext("IsTruncated"), "true")
        capped = self.page(prefix="docs/", **{"max-keys": 1001})
        self.assertEqual(capped.findtext("MaxKeys"), "1000")
        self.assertEqual(capped.findtext("KeyCount"), "1000")
        self.assertEqual(capped.findtext("IsTruncated"), "true")
        last = self.page(prefix="docs/", **{"continuation-token": first.findtext("NextContinuationToken")})
        self.assertEqual(last.findtext("KeyCount"), "1")
        self.assertEqual(last.findtext("Contents/Key"), keys[-1])
        self.assertEqual(last.findtext("IsTruncated"), "false")
        self.assertIsNone(last.find("NextContinuationToken"))
        # Exactly 1,000 matches must finish without an unnecessary empty page.
        with self.stub.lock:
            del self.stub.objects[("raw", keys[-1])]
        exact = self.page(prefix="docs/")
        self.assertEqual(exact.findtext("KeyCount"), "1000")
        self.assertEqual(exact.findtext("IsTruncated"), "false")
        self.assertIsNone(exact.find("NextContinuationToken"))

    def test_empty_and_zero_limit_pages_finish_without_token(self):
        self.seed(["docs/a"])
        for params in ({"prefix": "missing/"}, {"max-keys": 0}):
            with self.subTest(params=params):
                page = self.page(**params)
                self.assertEqual(page.findtext("KeyCount"), "0")
                self.assertEqual(page.findtext("IsTruncated"), "false")
                self.assertEqual(page.findall("Contents"), [])
                self.assertIsNone(page.find("NextContinuationToken"))

    def test_invalid_pagination_parameters_return_logged_error(self):
        for params in ({"max-keys": -1}, {"max-keys": "bad"},
                       {"continuation-token": "%%%"}, {"continuation-token": "/w=="}):
            with self.subTest(params=params):
                status, _headers, body = self.request(f"/raw?{urlencode({'list-type': '2', **params})}")
                self.assertEqual(status, 400)
                self.assertEqual(ET.fromstring(body).findtext("Code"), "InvalidArgument")
                self.assertEqual(self.stub.log[-1][3], 400)

    def send(self, request):
        """Keep botocore serialization/parsing; replace only the socket transport."""
        path = request.url[len(self.stub.endpoint):]
        status, headers, body = self.request(path)
        return AWSResponse(request.url, status, headers, HTTPResponse(body=io.BytesIO(body), preload_content=False))

    @unittest.skipUnless(HAVE_BOTO, "boto3 not installed")
    def test_s3_store_lists_all_three_pages_with_and_without_store_prefix(self):
        keys = [f"objects/{i:04d}" for i in range(2001)]
        self.seed(reversed(keys))
        self.seed([f"archive/{k}" for k in reversed(keys)])
        self.seed(["unrelated", "archive/unrelated"])
        self.seed(keys, bucket="other")
        for prefix in ("", "archive"):
            with self.subTest(prefix=prefix), mock.patch.dict(os.environ, {
                "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                "AWS_SESSION_TOKEN": "", "AWS_EC2_METADATA_DISABLED": "true",
            }):
                store = sa.S3Store(f"s3://raw/{prefix}", self.stub.endpoint)
                self.addCleanup(store.s3.close)
                before = len(self.stub.log)
                with mock.patch.object(store.s3._endpoint.http_session, "send", side_effect=self.send), \
                        mock.patch.object(store.s3, "list_objects_v2", wraps=store.s3.list_objects_v2) as listing:
                    self.assertEqual(store.list("objects/"), keys)
                calls = listing.call_args_list
                self.assertEqual(len(calls), 3)
                self.assertNotIn("ContinuationToken", calls[0].kwargs)
                self.assertTrue(calls[1].kwargs["ContinuationToken"])
                self.assertNotEqual(calls[1].kwargs["ContinuationToken"], calls[2].kwargs["ContinuationToken"])
                expected_prefix = f"{prefix}/objects/" if prefix else "objects/"
                self.assertEqual(self.stub.log[before:], [("list", "raw", expected_prefix, 200, 0)] * 3)
                self.assertEqual(self.stub.counts(before), {"class_a": 3, "class_b": 0, "put_bytes": 0})


if __name__ == "__main__":
    unittest.main()
