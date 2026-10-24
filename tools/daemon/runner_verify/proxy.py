"""Test provider proxy (05 §1b): a local HTTP server that stands in for a model provider. A CLI that is pointed at it
(by its base-URL setting, with a dummy key) gets the answer the current mode prescribes, so the harness can see what
the CLI does with a 429, a 5xx, a 401, a stalled call or a normal answer. It counts calls and the tokens it served,
which is the metering the usage record can rest on (U-05). It forwards nothing to any provider.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ERRORS = {
    "429": (429, "rate_limit_error"),
    "500": (500, "api_error"),
    "503": (503, "api_error"),
    "529": (529, "overloaded_error"),
    "401": (401, "authentication_error"),
    "403": (403, "permission_error"),
    "400_quota": (400, "quota_exceeded_error"),
}
REPLY_TEXT = "ok"


class ProviderProxy:
    def __init__(self, mode="ok", reply_text=REPLY_TEXT, port=0):
        self.mode = mode
        self.reply_text = reply_text
        self.requests = []
        self.lock = threading.Lock()
        self.release = threading.Event()
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _body(self):
                n = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(n) if n else b""
                try:
                    return json.loads(raw) if raw else {}
                except ValueError:
                    return {}

            def do_GET(self):
                self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "test proxy"}})

            def do_POST(self):
                body = self._body()
                path = self.path.split("?")[0]
                mode = proxy.mode
                rec = {"ts_ns": time.time_ns(), "path": path, "mode": mode, "stream": bool(body.get("stream"))}
                if path.endswith("/count_tokens"):
                    proxy._add(rec, 200)
                    return self._json(200, {"input_tokens": 10})
                if not path.endswith("/v1/messages"):
                    proxy._add(rec, 404)
                    return self._json(404, {"type": "error", "error": {"type": "not_found_error", "message": "test proxy"}})
                if mode in ERRORS:
                    status, etype = ERRORS[mode]
                    proxy._add(rec, status)
                    return self._json(status, {"type": "error", "error": {"type": etype, "message": "test"}},
                                      {"retry-after": "1"} if status == 429 else {})
                if mode == "hang":
                    proxy._add(rec, "held")
                    proxy.release.wait(timeout=600)
                    return
                self._ok(body, rec)

            def _json(self, status, obj, headers=None):
                data = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def _ok(self, body, rec):
                tokens_in = max(1, len(json.dumps(body.get("messages", ""))) // 4)
                tokens_out = max(1, len(proxy.reply_text) // 4)
                rec.update(tokens_in=tokens_in, tokens_out=tokens_out)
                proxy._add(rec, 200)
                model = body.get("model", "test")
                message = {"id": "msg_test", "type": "message", "role": "assistant", "model": model, "content": [],
                           "stop_reason": None, "stop_sequence": None,
                           "usage": {"input_tokens": tokens_in, "output_tokens": 1}}
                if not body.get("stream"):
                    message.update(content=[{"type": "text", "text": proxy.reply_text}], stop_reason="end_turn",
                                   usage={"input_tokens": tokens_in, "output_tokens": tokens_out})
                    return self._json(200, message)
                events = [
                    ("message_start", {"type": "message_start", "message": message}),
                    ("content_block_start", {"type": "content_block_start", "index": 0,
                                             "content_block": {"type": "text", "text": ""}}),
                    ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                             "delta": {"type": "text_delta", "text": proxy.reply_text}}),
                    ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                    ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                                       "usage": {"output_tokens": tokens_out}}),
                    ("message_stop", {"type": "message_stop"}),
                ]
                data = "".join(f"event: {n}\ndata: {json.dumps(d)}\n\n" for n, d in events).encode()
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def _add(self, rec, status):
        rec["status"] = status
        with self.lock:
            self.requests.append(rec)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()

    def set_mode(self, mode, reply_text=None):
        self.mode = mode
        if reply_text is not None:
            self.reply_text = reply_text

    def mark(self):
        with self.lock:
            return len(self.requests)

    def since(self, mark):
        with self.lock:
            return list(self.requests[mark:])

    def message_calls(self, mark=0):
        return [r for r in self.since(mark) if r["path"].endswith("/v1/messages")]
