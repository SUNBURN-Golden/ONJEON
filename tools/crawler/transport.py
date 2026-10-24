"""Transport layer: the only crawler code that can open a socket.

Transport.request(url, headers, timeout, max_bytes) -> Response(status, headers, body_iter).
UrllibTransport (stdlib) rules:
- any non-loopback host is refused BEFORE a socket is opened unless config.network_enabled is true AND
  the environment has ONJEON_CRAWLER_ALLOW_NETWORK=1. Loopback means a literal 127.0.0.0/8 or ::1
  address (no DNS lookup is ever needed to decide).
- the only headers sent are User-Agent (the configured honest one), Accept, and the conditional headers
  If-None-Match / If-Modified-Since; anything else a caller passes is an error, never silently sent.
- redirects are NOT followed: a 3xx is returned and the caller validates the target (same host).
  Non-2xx statuses are returned as responses, not raised.
- environment proxies are ignored (an explicit empty proxy handler); there is no proxy support.
- the body is streamed in bounded chunks and never exceeds max_bytes (BodyTooLargeError).
"""
import abc
import http.client
import ipaddress
import math
import os
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Iterator, Mapping, Optional
from urllib.parse import urlsplit

from .config import CrawlerConfig
from .useragent import build_user_agent

ENV_ALLOW_NETWORK = "ONJEON_CRAWLER_ALLOW_NETWORK"
CHUNK_BYTES = 64 * 1024
ALLOWED_REQUEST_HEADERS = frozenset({"accept", "if-none-match", "if-modified-since"})
DEFAULT_ACCEPT = "*/*"


class TransportError(Exception):
    pass


class NetworkDisabledError(TransportError):
    """A non-loopback request was refused before any socket was opened."""


class RefusedRequestError(TransportError):
    """The request itself is refused before any socket opens (bad URL, credentials, scheme)."""


class BodyTooLargeError(TransportError):
    """The body exceeded max_bytes; no byte beyond the cap was yielded."""


@dataclass
class Response:
    status: int
    headers: Mapping[str, str]
    body_iter: Iterator[bytes]
    _close: Optional[Callable[[], None]] = field(default=None, repr=False)

    def __post_init__(self):
        self.headers = {str(k).lower(): str(v) for k, v in dict(self.headers).items()}

    def close(self) -> None:
        close, self._close = self._close, None
        if close:
            close()
        closer = getattr(self.body_iter, "close", None)
        if closer:
            closer()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Transport(abc.ABC):
    @abc.abstractmethod
    def request(self, url: str, headers: Optional[Mapping[str, str]], timeout: float, max_bytes: int) -> Response:
        """GET url. Never follows redirects. body_iter yields at most max_bytes in total."""


def is_loopback_host(host: Optional[str]) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _split(url: str):
    try:
        parts = urlsplit(url)
        host, _ = parts.hostname, parts.port
    except ValueError:
        raise RefusedRequestError("malformed URL") from None
    if parts.scheme not in ("http", "https") or not host:
        raise RefusedRequestError("only absolute http(s) URLs are supported")
    if parts.username is not None or parts.password is not None:
        raise RefusedRequestError("URLs with credentials are refused")
    return parts, host


def _build_opener() -> urllib.request.OpenerDirector:
    """Minimal opener: no env proxies, no redirect handler, no error processor (3xx/4xx/5xx come back as
    responses), no file/ftp/data handlers, no default User-agent."""
    opener = urllib.request.OpenerDirector()
    opener.add_handler(urllib.request.ProxyHandler({}))
    opener.add_handler(urllib.request.HTTPHandler())
    opener.add_handler(urllib.request.HTTPSHandler())
    opener.addheaders = []
    return opener


class UrllibTransport(Transport):
    def __init__(self, config: CrawlerConfig):
        self._config = config
        self.user_agent = build_user_agent(config)  # raises when contact is empty / browser-like
        self._opener = _build_opener()

    def check_destination(self, url: str) -> None:
        """Raise NetworkDisabledError unless the URL may be requested. Opens no socket."""
        _, host = _split(url)
        if is_loopback_host(host):
            return
        if not self._config.network_enabled:
            raise NetworkDisabledError("network access is disabled in the crawler config")
        if os.environ.get(ENV_ALLOW_NETWORK) != "1":
            raise NetworkDisabledError(f"network access needs {ENV_ALLOW_NETWORK}=1 in the environment")

    def build_headers(self, headers: Optional[Mapping[str, str]]) -> dict:
        out = {"User-Agent": self.user_agent, "Accept": DEFAULT_ACCEPT}
        for name, value in (headers or {}).items():
            low = str(name).lower()
            if low not in ALLOWED_REQUEST_HEADERS:
                raise ValueError(f"header not allowed: {name}")
            if not isinstance(value, str) or any(c in value for c in "\r\n\x00"):
                raise ValueError(f"bad header value for {name}")
            out["Accept" if low == "accept" else name] = value
        return out

    def request(self, url: str, headers: Optional[Mapping[str, str]], timeout: float, max_bytes: int) -> Response:
        self.check_destination(url)
        req_headers = self.build_headers(headers)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 0 < max_bytes <= self._config.object_cap_bytes:
            raise ValueError("max_bytes must be between 1 and config.object_cap_bytes")
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        try:
            resp = self._opener.open(req, timeout=timeout)
        except (OSError, http.client.HTTPException) as e:  # URLError, timeouts, TLS failures
            detail = type(e).__name__
            inner = getattr(e, "reason", None)  # URLError wraps the real OSError
            if isinstance(inner, OSError):
                detail = f"{detail}({type(inner).__name__})"
            raise TransportError(f"request failed: {detail}") from None
        hdrs = {}
        for k, v in resp.headers.items():
            k = k.lower()
            hdrs[k] = f"{hdrs[k]}, {v}" if k in hdrs else v
        return Response(resp.status, hdrs, _stream(resp, hdrs.get("content-length"), max_bytes), resp.close)


def _declared_length(value: Optional[str]) -> Optional[int]:
    """Parse Content-Length; anything unparsable (non-ASCII digits, absurd length) counts as unknown."""
    if not value:
        return None
    value = value.strip()
    if not (value.isascii() and value.isdigit()):
        return None
    return int(value) if len(value) <= 18 else 1 << 62


def _stream(resp, content_length: Optional[str], max_bytes: int) -> Iterator[bytes]:
    try:
        declared = _declared_length(content_length)
        if declared is not None and declared > max_bytes:
            raise BodyTooLargeError("declared Content-Length exceeds the cap")
        total = 0
        while True:
            try:
                chunk = resp.read(min(CHUNK_BYTES, max_bytes - total + 1))
            except (OSError, http.client.HTTPException) as e:
                raise TransportError(f"read failed: {type(e).__name__}") from None
            if not chunk:
                return
            total += len(chunk)
            if total > max_bytes:
                keep = len(chunk) - (total - max_bytes)
                if keep > 0:
                    yield chunk[:keep]
                raise BodyTooLargeError("body exceeds the cap")
            yield chunk
    finally:
        resp.close()
