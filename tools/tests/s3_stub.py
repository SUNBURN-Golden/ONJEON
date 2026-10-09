"""A minimal in-memory S3 endpoint for tests (path-style, no auth): PutObject with If-None-Match,
GetObject, HeadObject, ListObjectsV2. Every HTTP request is logged, and faults can be queued, so a
test can compare what the server actually received with what the budget ledger recorded."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from xml.sax.saxutils import escape


class S3Stub:
    def __init__(self):
        self.objects = {}   # (bucket, key) -> bytes
        self.log = []       # (kind, bucket, key_or_prefix, status, body_bytes); kind: put/get/head/list
        self.faults = []    # [(method, key_prefix, status)] each used once
        self.lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _target(self):
                u = urlparse(self.path)
                parts = u.path.lstrip("/").split("/", 1)
                return parts[0], unquote(parts[1]) if len(parts) > 1 else "", parse_qs(u.query)

            def _send(self, status, body=b"", headers=None):
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _error(self, status, code):
                self._send(status, f"<Error><Code>{code}</Code><Message>{code}</Message></Error>".encode(),
                           {"Content-Type": "application/xml"})

            def _fault(self, key):
                with stub.lock:
                    for i, (m, prefix, status) in enumerate(stub.faults):
                        if m == self.command and key.startswith(prefix):
                            del stub.faults[i]
                            return status
                return None

            def _handle(self):
                bucket, key, q = self._target()
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                logged = key or q.get("prefix", [""])[0]
                kind = {"PUT": "put", "HEAD": "head"}.get(self.command, "get" if key else "list")
                status = self._fault(logged)
                if status:
                    with stub.lock:
                        stub.log.append((kind, bucket, logged, status, len(body)))
                    return self._error(status, "ServiceUnavailable" if status >= 500 else "Fault")
                with stub.lock:
                    if self.command == "PUT":
                        if self.headers.get("If-None-Match") == "*" and (bucket, key) in stub.objects:
                            result = (412, None)
                        else:
                            stub.objects[(bucket, key)] = body
                            result = (200, None)
                    elif self.command in ("GET", "HEAD") and key:
                        obj = stub.objects.get((bucket, key))
                        result = (200, obj) if obj is not None else (404, None)
                    else:  # ListObjectsV2
                        prefix = q.get("prefix", [""])[0]
                        keys = sorted(k for (b, k) in stub.objects if b == bucket and k.startswith(prefix))
                        result = (200, keys)
                    stub.log.append((kind, bucket, logged, result[0], len(body)))
                code, payload = result
                if self.command == "PUT":
                    return self._send(200, b"", {"ETag": '"x"'}) if code == 200 else self._error(412, "PreconditionFailed")
                if self.command in ("GET", "HEAD") and key:
                    if code == 404:
                        return self._error(404, "NoSuchKey") if self.command == "GET" else self._send(404)
                    return self._send(200, payload, {"ETag": '"x"', "Content-Type": "application/octet-stream"})
                items = "".join(f"<Contents><Key>{escape(k)}</Key><Size>1</Size></Contents>" for k in payload)
                xml = (f'<?xml version="1.0" encoding="UTF-8"?><ListBucketResult><Name>{bucket}</Name>'
                       f"<Prefix>{escape(q.get('prefix', [''])[0])}</Prefix><KeyCount>{len(payload)}</KeyCount>"
                       f"<MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>{items}</ListBucketResult>")
                return self._send(200, xml.encode(), {"Content-Type": "application/xml"})

            do_PUT = do_GET = do_HEAD = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def counts(self, since=0):
        """Requests received since log index `since`, by billing class, with request bytes."""
        c = {"class_a": 0, "class_b": 0, "put_bytes": 0}
        for kind, _bucket, _key, _status, n in self.log[since:]:
            c["class_a" if kind in ("put", "list") else "class_b"] += 1
            if kind == "put":
                c["put_bytes"] += n
        return c

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
