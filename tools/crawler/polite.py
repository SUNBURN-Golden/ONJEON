"""Polite HTTP fetcher: robots check -> host rate limit -> transport, with typed outcomes.

Rules:
- max 3 attempts per request (configurable), exponential backoff + injected jitter for
  timeouts and 5xx (except 503 with Retry-After);
- 429/503 honor Retry-After; a second 429 the same day stops the host for the day;
- 401/403, captcha/login/bot-block/geo-block markers, or a redirect to another host stop
  immediately with a typed Outcome and no retry / no header change / no alternate path;
- per-source daily request cap enforced (cap reached => Outcome deferred_cap);
- no way to alter headers per retry is exposed.

All body inspection works on a bounded prefix (BODY_PREFIX_BYTES) so memory stays small.
"""
import email.utils
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Iterator, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .config import CrawlerConfig
from .hostlimit import HostAtCapError, HostBusyError, HostRateLimiter
from .robots import RobotsCache, RobotsDecision
from .transport import Response, Transport, TransportError

DAY_S = 86400
BODY_PREFIX_BYTES = 32 * 1024

DEFAULT_BLOCK_MARKERS: Tuple[str, ...] = (
    "captcha",
    "recaptcha",
    "g-recaptcha",
    "로그인",
    "login",
    "bot detected",
    "bot block",
    "access denied",
    "your ip has been blocked",
    "차단",
    "봇",
)

DEFAULT_GEO_MARKERS: Tuple[str, ...] = (
    "geo-block",
    "geoblock",
    "geo block",
    "해외 접근",
    "해외 ip",
)

DEFAULT_SERVICE_OUTAGE_MARKERS: Tuple[str, ...] = (
    "점검",
    "service outage",
    "maintenance",
    "scheduled maintenance",
    "일시적인 오류",
    "일시적 오류",
)

DEFAULT_JS_SHELL_MARKERS: Tuple[str, ...] = (
    "window.__initial_state__",
    "window.__data__",
    "reactroot",
    "vue.js",
)

RETRYABLE_STATUS = frozenset({408})


@dataclass
class Outcome:
    kind: str
    reason: str
    url: str
    status: Optional[int] = None
    headers: Optional[Mapping[str, str]] = None
    body_iter: Optional[Iterator[bytes]] = None
    attempts: int = 0
    blocked_until: Optional[float] = None
    retry_after: Optional[float] = None

    def close(self) -> None:
        it = self.body_iter
        if it is not None:
            closer = getattr(it, "close", None)
            if closer:
                closer()
            self.body_iter = None


class PoliteFetcher:
    def __init__(
        self,
        transport: Transport,
        robots: RobotsCache,
        limiter: HostRateLimiter,
        config: CrawlerConfig,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = lambda: 0.0,
        block_markers: Optional[Iterable[str]] = None,
        geo_markers: Optional[Iterable[str]] = None,
        service_outage_markers: Optional[Iterable[str]] = None,
        js_shell_markers: Optional[Iterable[str]] = None,
    ):
        self._transport = transport
        self._robots = robots
        self._limiter = limiter
        self._config = config
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self._block_markers = tuple(m.lower() for m in (block_markers or DEFAULT_BLOCK_MARKERS))
        self._geo_markers = tuple(m.lower() for m in (geo_markers or DEFAULT_GEO_MARKERS))
        self._service_markers = tuple(m.lower() for m in (service_outage_markers or DEFAULT_SERVICE_OUTAGE_MARKERS))
        self._js_markers = tuple(m.lower() for m in (js_shell_markers or DEFAULT_JS_SHELL_MARKERS))
        self._lock = threading.Lock()
        # source -> (day_start_epoch, count)
        self._daily: Dict[str, Tuple[float, int]] = {}
        # host -> (count, day_start_epoch)
        self._host_429_day: Dict[str, Tuple[int, float]] = {}
        # host -> stop_until_epoch
        self._host_stop_until: Dict[str, float] = {}

    def fetch(
        self,
        url: str,
        source: str,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
        max_bytes: Optional[int] = None,
    ) -> Outcome:
        if not isinstance(url, str) or not url:
            return Outcome("blocked", "empty_reply", url or "")
        if not isinstance(source, str) or not source:
            return Outcome("blocked", "empty_reply", url)
        if timeout is None:
            timeout = 30.0
        if max_bytes is None:
            max_bytes = self._config.object_cap_bytes

        robots = self._robots.check(url)
        if not robots.allowed:
            return self._robots_outcome(url, robots)

        host = _host(url)
        robots_delay = robots.crawl_delay
        request_headers = dict(headers) if headers else {}

        for attempt in range(1, self._config.max_attempts + 1):
            cap = self._check_and_bump_daily_cap(source)
            if cap is not None:
                return cap

            stop = self._host_stop_until.get(host)
            if stop is not None and self._clock() < stop:
                return Outcome("rate_limited", "rate_limited", url, blocked_until=stop)

            try:
                self._limiter.acquire(host, robots_delay)
            except (HostAtCapError, HostBusyError):
                return Outcome("blocked", "rate_limited", url)

            try:
                response = self._transport.request(url, request_headers, timeout, max_bytes)
            except TransportError as exc:
                self._limiter.release(host)
                kind, reason = _classify_transport_error(exc)
                if attempt == self._config.max_attempts:
                    return Outcome(kind, reason, url, attempts=attempt)
                self._sleep(_backoff(attempt, self._rng))
                continue

            try:
                outcome = self._handle_response(url, host, response, attempt)
            finally:
                if outcome is None or outcome.kind != "success":
                    response.close()
                self._limiter.release(host)

            if outcome.kind == "retry":
                if attempt == self._config.max_attempts:
                    return Outcome("blocked", "service_outage", url, status=response.status, attempts=attempt)
                self._sleep(_backoff(attempt, self._rng))
                continue

            return outcome

        # Unreachable, but kept for type narrowing.
        return Outcome("blocked", "service_outage", url, attempts=self._config.max_attempts)

    def _handle_response(self, url: str, host: str, response: Response, attempt: int) -> Outcome:
        status = response.status

        if 300 <= status < 400:
            location = response.headers.get("location", "")
            target = _host(location) if location else ""
            if target and target != host:
                return Outcome("redirect", "redirect_loop", url, status=status, attempts=attempt)
            return Outcome("redirect", "redirect_loop", url, status=status, attempts=attempt)

        if status in (401, 403):
            prefix = _read_prefix(response.body_iter, BODY_PREFIX_BYTES)
            reason = _block_reason(prefix, self._block_markers, self._geo_markers)
            return Outcome("blocked", reason, url, status=status, attempts=attempt)

        if status == 429 or (status == 503 and "retry-after" in response.headers):
            return self._rate_limit_outcome(url, host, response, attempt)

        if 500 <= status < 600:
            return Outcome("retry", "service_outage", url, status=status, attempts=attempt)

        if 400 <= status < 500:
            return Outcome("blocked", "origin_denied", url, status=status, attempts=attempt)

        if 200 <= status < 300:
            prefix, rest = _peek_prefix(response.body_iter, BODY_PREFIX_BYTES)
            text = prefix.decode("utf-8", errors="ignore").lower()
            if _has_marker(text, self._block_markers):
                reason = _geo_or_origin(text, self._geo_markers)
                return Outcome("blocked", reason, url, status=status, attempts=attempt)
            if _has_marker(text, self._service_markers):
                return Outcome("blocked", "service_outage", url, status=status, attempts=attempt)
            if _has_marker(text, self._js_markers):
                return Outcome("blocked", "js_shell", url, status=status, attempts=attempt)
            wrapped = _BodyChain(rest, response.body_iter, response.close)
            return Outcome(
                "success",
                "reachable",
                url,
                status=status,
                headers=response.headers,
                body_iter=iter(wrapped),
                attempts=attempt,
            )

        return Outcome("blocked", "empty_reply", url, status=status, attempts=attempt)

    def _rate_limit_outcome(self, url: str, host: str, response: Response, attempt: int) -> Outcome:
        now = self._clock()
        day_start = _day_start(now)
        count, last_day = self._host_429_day.get(host, (0, 0.0))
        if last_day != day_start:
            count = 0
        retry_after = _parse_retry_after(response.headers.get("retry-after"), now)
        if count >= 1:
            stop = _day_end(now)
        else:
            stop = retry_after if retry_after is not None else now
        self._host_429_day[host] = (count + 1, day_start)
        self._host_stop_until[host] = stop
        return Outcome(
            "rate_limited",
            "rate_limited",
            url,
            status=response.status,
            attempts=attempt,
            blocked_until=stop,
            retry_after=retry_after,
        )

    def _robots_outcome(self, url: str, decision: RobotsDecision) -> Outcome:
        if decision.deferred:
            if decision.blocked or decision.reason == "robots_forbidden":
                return Outcome("blocked", "origin_denied", url, blocked_until=decision.deferred_until)
            if decision.reason == "robots_rate_limited":
                return Outcome("rate_limited", "rate_limited", url, blocked_until=decision.deferred_until)
            return Outcome("blocked", "service_outage", url, blocked_until=decision.deferred_until)
        return Outcome("blocked", "origin_denied", url)

    def _check_and_bump_daily_cap(self, source: str) -> Optional[Outcome]:
        with self._lock:
            now = self._clock()
            day_start, count = self._daily.get(source, (_day_start(now), 0))
            if now >= day_start + DAY_S:
                day_start, count = _day_start(now), 0
            if count >= self._config.daily_request_cap_default:
                return Outcome("deferred_cap", "deferred_cap", "", blocked_until=day_start + DAY_S)
            self._daily[source] = (day_start, count + 1)
        return None


class _BodyChain:
    __slots__ = ("_first", "_rest", "_close", "_done")

    def __init__(self, first: bytes, rest: Iterator[bytes], close: Callable[[], None]):
        self._first = first
        self._rest = rest
        self._close = close
        self._done = False

    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        if self._done:
            raise StopIteration
        if self._first:
            chunk, self._first = self._first, b""
            return chunk
        try:
            return next(self._rest)
        except StopIteration:
            self.close()
            raise

    def close(self) -> None:
        if not self._done:
            self._done = True
            if self._close:
                self._close()


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _day_start(now: float) -> float:
    return (int(now) // DAY_S) * DAY_S


def _day_end(now: float) -> float:
    return (int(now) // DAY_S + 1) * DAY_S


def _backoff(attempts_so_far: int, rng: Callable[[], float]) -> float:
    """Exponential backoff: 2**attempts_so_far seconds + injected jitter."""
    return (2 ** attempts_so_far) + rng()


def _parse_retry_after(value: Optional[str], now: float) -> Optional[float]:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return now + int(value)
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            return dt.timestamp()
        return dt.astimezone(time.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _classify_transport_error(exc: TransportError) -> Tuple[str, str]:
    msg = str(exc).lower()
    if "timeouterror" in msg:
        return "timeout", "timeout"
    if "tls" in msg or "ssl" in msg:
        return "tls_error", "tls_error"
    if "connectionreseterror" in msg:
        return "connection_reset", "connection_reset"
    return "connection_reset", "connection_reset"


def _read_prefix(body_iter: Iterator[bytes], max_bytes: int) -> bytes:
    buf = bytearray()
    for chunk in body_iter:
        need = max_bytes - len(buf)
        if need <= 0:
            break
        buf.extend(chunk[:need])
    return bytes(buf)


def _peek_prefix(body_iter: Iterator[bytes], max_bytes: int) -> Tuple[bytes, bytes]:
    buf = bytearray()
    leftover = b""
    for chunk in body_iter:
        if len(buf) >= max_bytes:
            leftover = chunk
            break
        need = max_bytes - len(buf)
        if len(chunk) <= need:
            buf.extend(chunk)
        else:
            buf.extend(chunk[:need])
            leftover = chunk[need:]
        if len(buf) >= max_bytes:
            break
    return bytes(buf), leftover


def _has_marker(text: str, markers: Tuple[str, ...]) -> bool:
    for marker in markers:
        if marker in text:
            return True
    return False


def _geo_or_origin(text: str, geo_markers: Tuple[str, ...]) -> str:
    if _has_marker(text, geo_markers):
        return "geo_blocked"
    return "origin_denied"


def _block_reason(prefix: bytes, block_markers: Tuple[str, ...], geo_markers: Tuple[str, ...]) -> str:
    text = prefix.decode("utf-8", errors="ignore").lower()
    return _geo_or_origin(text, geo_markers) if _has_marker(text, block_markers) else "origin_denied"
