"""Polite HTTP fetcher: robots check -> host rate limit -> transport, with typed outcomes.

Rules:
- at most `config.max_attempts` attempts per request (default 3), exponential backoff + injected
  jitter for transient failures: timeouts, connection resets and 5xx (except 503 carrying
  Retry-After, which is handled like 429);
- 429 and 503-with-Retry-After honour Retry-After (delta seconds or HTTP-date): no request to
  that host is made before then; a second 429 the same UTC day stops the host for the rest of
  the day — or longer, when the server's own Retry-After reaches past midnight;
- 401/403, captcha/login/bot-block/geo-block markers in a bounded prefix of a textual body, an
  empty 2xx body, or any redirect (same host or another host: redirects are never followed)
  stop immediately with a typed Outcome: no retry, no header change, no alternate path;
- a body stream that fails inside the marker prefix is the same class of failure as request()
  raising (classified the same way, retried only if transient); past the prefix a TransportError
  reaches the body consumer, so a truncated body is never reported as a successful fetch;
- a refusal before the wire (NetworkDisabledError, RefusedRequestError, or a caller-side error
  like a disallowed header) is not a billable request and never leaks the host reservation;
- robots wire requests share the page limiter and source budget through an injected request
  callback and use the same bounded block-marker inspection; reservations cover the full
  response lifetime, including unread streaming bodies;
  hosts of different sources share one limiter budget;
- per-source daily request cap enforced (cap reached => Outcome kind deferred_cap);
- headers are fixed when fetch() is called; nothing here can change them per retry.

Reason strings come from the registry host_access vocabulary (reachable, origin_denied,
rate_limited, service_outage, connection_reset, tls_error, timeout, empty_reply, geo_blocked,
js_shell, redirect_loop, not_checked); the daily-cap outcome's kind is "deferred_cap" and its
reason is rate_limited (a self-imposed limit, not the host's).
Body inspection works on a bounded prefix (BODY_PREFIX_BYTES) so memory stays small.
"""
import email.utils
import random
import threading
import time
from dataclasses import dataclass
from datetime import timezone
from typing import Callable, Dict, Iterable, Iterator, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .config import CrawlerConfig
from .hostlimit import HostAtCapError, HostBusyError, HostRateLimiter
from .robots import RobotsCache, RobotsDecision
from .transport import (BodyTooLargeError, NetworkDisabledError, RefusedRequestError, Response,
                        Transport, TransportError)

DAY_S = 86400
BODY_PREFIX_BYTES = 32 * 1024

# Marker lists are deliberately specific: a bare "login"/"로그인"/"봇" appears in ordinary page
# chrome (login links, chatbot widgets) and would false-block healthy pages. A block means stop
# and record a gap — but we only stop on signals that really mean "we are not welcome here".
DEFAULT_BLOCK_MARKERS: Tuple[str, ...] = (
    "captcha",
    "recaptcha",
    "g-recaptcha",
    "hcaptcha",
    "bot detected",
    "access denied",
    "your ip has been blocked",
    "unusual traffic",
    "automated requests",
    "too many requests",
    "please log in",
    "login required",
    "sign in to continue",
    "로그인이 필요",
    "로그인 후 이용",
    "회원 전용",
    "접근이 차단",
    "접근 차단",
    "비정상적인 접근",
    "자동화된 접근",
    "봇 차단",
)

DEFAULT_GEO_MARKERS: Tuple[str, ...] = (
    "geo-block",
    "geoblock",
    "geo block",
    "not available in your country",
    "not available in your region",
    "해외 접근",
    "해외 ip",
    "해외에서 접속",
    "국내에서만",
)

DEFAULT_SERVICE_OUTAGE_MARKERS: Tuple[str, ...] = (
    "서비스 점검",
    "시스템 점검",
    "정기 점검",
    "작업 중입니다",
    "service outage",
    "scheduled maintenance",
    "under maintenance",
    "일시적인 오류",
    "일시적 오류",
)

DEFAULT_JS_SHELL_MARKERS: Tuple[str, ...] = (
    "window.__initial_state__",
    "window.__next_data__",
    "id=\"react-root\"",
    "id='react-root'",
    "id=\"root\"></div><script",
)

RETRYABLE_STATUS = frozenset({408})  # Request Timeout: transient, retried like a timeout

_TEXTUAL_TYPES = ("text", "html", "xml", "json", "javascript", "x-www-form-urlencoded")

_ROBOTS_REASONS = {
    "bad_url": "not_checked",
    "unsupported_scheme": "not_checked",
    "robots_forbidden": "origin_denied",
    "robots_disallow": "origin_denied",
    "robots_rate_limited": "rate_limited",
    "robots_server_error": "service_outage",
    "robots_unreachable": "connection_reset",
    "robots_too_large": "empty_reply",
    "robots_redirect_refused": "redirect_loop",
}


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
        rng: Callable[[], float] = random.random,
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
        # source -> (day_start_epoch, request_count)
        self._daily: Dict[str, Tuple[float, int]] = {}
        # host -> (429_count, day_start_epoch)
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
            return Outcome("blocked", "not_checked", url or "")
        if not isinstance(source, str) or not source:
            return Outcome("blocked", "not_checked", url)
        host = _host(url)
        if not host:
            return Outcome("blocked", "not_checked", url)
        if timeout is None:
            timeout = 30.0
        if max_bytes is None:
            max_bytes = self._config.object_cap_bytes

        # Over the per-source daily cap: no request of any kind, not even robots.txt.
        until = self._cap_blocked_until(source)
        if until is not None:
            return Outcome("deferred_cap", "rate_limited", url, blocked_until=until)

        # Host stopped by an earlier 429/Retry-After: no request before then.
        stop = self._host_stop_until.get(host)
        if stop is not None and self._clock() < stop:
            return Outcome("rate_limited", "rate_limited", url, blocked_until=stop)

        # One header set for the whole fetch: the robots check and every attempt see the same
        # headers, so a block can never be worked around by varying them between sub-requests.
        request_headers = dict(headers) if headers else {}
        try:
            robots = self._robots.check(
                url, request_headers,
                request=lambda *args: self._robots_request(source, *args),
            )
        except _Deferred as exc:
            exc.outcome.url = url
            return exc.outcome
        if not robots.allowed:
            return self._robots_outcome(url, robots)

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                self._reserve(url, source, robots.crawl_delay)
            except _Deferred as exc:
                return exc.outcome

            response = None
            released = False
            try:
                response = self._transport.request(url, request_headers, timeout, max_bytes)
            except TransportError as exc:
                # Free the host at failure time so the backoff below counts toward the
                # minimum interval; the repeat release in the finally is a no-op.
                self._limiter.release(host)
                released = True
                if isinstance(exc, (NetworkDisabledError, RefusedRequestError)):
                    self._unbump_daily(source)  # refused before the wire: not a billable request
                if isinstance(exc, NetworkDisabledError):
                    raise  # local policy refusal, not a host outcome: never retry, never swallow
                kind, reason, retryable = _classify_transport_error(exc)
                if not retryable or attempt == self._config.max_attempts:
                    return Outcome(kind, reason, url, attempts=attempt)
                self._sleep(_backoff(attempt, self._rng))
                continue
            except Exception:
                # Not a TransportError (caller misuse such as a disallowed header or a bad
                # timeout, or a transport bug): nothing reached the wire, so refund the
                # budget. The finally frees the host, then the error fails loudly.
                self._unbump_daily(source)
                raise
            finally:
                if response is None and not released:
                    self._limiter.release(host)

            outcome = None
            try:
                outcome = self._handle_response(url, host, response, attempt)
            finally:
                if outcome is None or outcome.kind != "success":
                    try:
                        response.close()
                    finally:
                        self._limiter.release(host)

            if outcome.kind == "retry":
                if attempt == self._config.max_attempts:
                    kind = "timeout" if outcome.reason == "timeout" else "blocked"
                    return Outcome(kind, outcome.reason, url, status=response.status, attempts=attempt)
                self._sleep(_backoff(attempt, self._rng))
                continue

            return outcome

        # Unreachable, but kept for type narrowing.
        return Outcome("blocked", "service_outage", url, attempts=self._config.max_attempts)

    def _handle_response(self, url: str, host: str, response: Response, attempt: int) -> Outcome:
        status = response.status

        if 300 <= status < 400:
            # Redirects are never followed — same host or not. A cross-host Location is a block.
            return Outcome("redirect", "redirect_loop", url, status=status, attempts=attempt)

        if status in (401, 403):
            prefix, _ = _read_prefix(response.body_iter, BODY_PREFIX_BYTES)
            reason = _block_reason(prefix, self._geo_markers)
            return Outcome("blocked", reason, url, status=status, attempts=attempt)

        # Record host-wide restrictions even when a body marker wins classification below.
        rate_limit = None
        if status == 429 or (status == 503 and "retry-after" in response.headers):
            rate_limit = self._rate_limit_outcome(url, host, response, attempt)

        head, body_error = b"", None
        if 200 <= status < 300 or _is_textual(response.headers.get("content-type")):
            head, body_error = _read_prefix(response.body_iter, BODY_PREFIX_BYTES)
            if _is_textual(response.headers.get("content-type")):
                blocked = self._marker_block(url, response, head, attempt, rate_limit)
                if blocked is not None:
                    return blocked

        if rate_limit is not None:
            return rate_limit

        if status in RETRYABLE_STATUS:
            return Outcome("retry", "timeout", url, status=status, attempts=attempt)

        if 500 <= status < 600:
            return Outcome("retry", "service_outage", url, status=status, attempts=attempt)

        if 400 <= status < 500:
            return Outcome("blocked", "origin_denied", url, status=status, attempts=attempt)

        if 200 <= status < 300:
            if body_error is not None:
                # A stream that dies inside the prefix window is the same class of failure
                # request() would have raised: classify it (and retry if transient) the same
                # way. Reporting success here would archive a truncated body as complete.
                kind, reason, retryable = _classify_transport_error(body_error)
                if not retryable or attempt == self._config.max_attempts:
                    return Outcome(kind, reason, url, status=status, attempts=attempt)
                return Outcome("retry", reason, url, status=status, attempts=attempt)
            if not head:
                return Outcome("blocked", "empty_reply", url, status=status, attempts=attempt)
            if _is_textual(response.headers.get("content-type")):
                text = head[:BODY_PREFIX_BYTES].decode("utf-8", errors="ignore").lower()
                if _has_marker(text, self._service_markers):
                    return Outcome("blocked", "service_outage", url, status=status, attempts=attempt)
                if _has_marker(text, self._js_markers):
                    return Outcome("blocked", "js_shell", url, status=status, attempts=attempt)
            wrapped = _BodyChain(head, response.body_iter, lambda: self._close_response(host, response))
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

    def _marker_block(self, url: str, response: Response, prefix: bytes, attempt: int,
                      rate_limit: Optional[Outcome] = None) -> Optional[Outcome]:
        text = prefix[:BODY_PREFIX_BYTES].decode("utf-8", errors="ignore").lower()
        if _has_marker(text, self._geo_markers):
            reason = "geo_blocked"
        elif _has_marker(text, self._block_markers):
            reason = "origin_denied"
        else:
            return None
        return Outcome("blocked", reason, url, status=response.status, attempts=attempt,
                       blocked_until=rate_limit.blocked_until if rate_limit is not None else None,
                       retry_after=rate_limit.retry_after if rate_limit is not None else None)

    def _rate_limit_outcome(self, url: str, host: str, response: Response, attempt: int) -> Outcome:
        now = self._clock()
        day_start = _day_start(now)
        count, last_day = self._host_429_day.get(host, (0, 0.0))
        if last_day != day_start:
            count = 0
        retry_after = _parse_retry_after(response.headers.get("retry-after"), now)
        if response.status == 429 and count >= 1:
            # A second 429 the same UTC day: stop the host for the rest of the day — and never
            # less than the Retry-After the server just sent, even when it lands past midnight.
            stop = _day_end(now)
            if retry_after is not None and retry_after > stop:
                stop = retry_after
        else:
            stop = retry_after if retry_after is not None else now
        with self._lock:
            if response.status == 429:
                self._host_429_day[host] = (count + 1, day_start)
            stop = max(stop, self._host_stop_until.get(host, 0.0))
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
        reason = _ROBOTS_REASONS.get(decision.reason, "service_outage")
        kind = "rate_limited" if reason == "rate_limited" else "blocked"
        return Outcome(kind, reason, url, blocked_until=decision.deferred_until)

    def _reserve(self, url: str, source: str, crawl_delay=None) -> None:
        host = _host(url)
        try:
            self._limiter.acquire(host, crawl_delay)
        except (HostAtCapError, HostBusyError):
            raise _Deferred(Outcome("blocked", "rate_limited", url)) from None
        with self._lock:
            stop = self._host_stop_until.get(host, 0.0)
            if self._clock() < stop:
                self._limiter.release(host)
                raise _Deferred(Outcome("rate_limited", "rate_limited", url, blocked_until=stop))
        until = self._bump_daily(source)
        if until is not None:
            self._limiter.release(host)
            raise _Deferred(Outcome("deferred_cap", "rate_limited", url, blocked_until=until))

    def _close_response(self, host: str, response: Response) -> None:
        try:
            response.close()
        finally:
            self._limiter.release(host)

    def _robots_request(self, source, url, headers, timeout, max_bytes):
        host = _host(url)
        self._reserve(url, source)
        try:
            response = self._transport.request(url, headers, timeout, max_bytes)
        except Exception as exc:
            self._limiter.release(host)
            if not isinstance(exc, TransportError) or isinstance(exc, (NetworkDisabledError, RefusedRequestError)):
                self._unbump_daily(source)
            raise
        head, body_error = b"", None
        try:
            rate_limit = None
            if response.status == 429 or (response.status == 503 and "retry-after" in response.headers):
                rate_limit = self._rate_limit_outcome(url, host, response, 1)
            if _is_textual(response.headers.get("content-type")):
                head, body_error = _read_prefix(response.body_iter, BODY_PREFIX_BYTES)
                blocked = self._marker_block(url, response, head, 1, rate_limit)
                if blocked is not None:
                    raise _Deferred(blocked)
            if rate_limit is not None:
                raise _Deferred(rate_limit)
        except BaseException:
            self._close_response(host, response)
            raise

        def body():
            # RobotsCache must see the complete stream, including any prefix read failure.
            if head:
                yield head
            if body_error is not None:
                raise body_error
            yield from response.body_iter

        return Response(response.status, response.headers, body(),
                        lambda: self._close_response(host, response))

    def _cap_blocked_until(self, source: str) -> Optional[float]:
        """Day-end epoch if the source is over its daily request cap, else None. Does not count."""
        with self._lock:
            now = self._clock()
            day_start, count = self._daily.get(source, (_day_start(now), 0))
            if now >= day_start + DAY_S:
                return None
            if count >= self._config.daily_request_cap_default:
                return day_start + DAY_S
            return None

    def _bump_daily(self, source: str) -> Optional[float]:
        """Count one real request; returns the day-end epoch if the cap was already reached."""
        with self._lock:
            now = self._clock()
            day_start, count = self._daily.get(source, (_day_start(now), 0))
            if now >= day_start + DAY_S:
                day_start, count = _day_start(now), 0
            if count >= self._config.daily_request_cap_default:
                return day_start + DAY_S
            self._daily[source] = (day_start, count + 1)
            return None

    def _unbump_daily(self, source: str) -> None:
        """Refund one counted request when the attempt never reached the wire."""
        with self._lock:
            day_start, count = self._daily.get(source, (_day_start(self._clock()), 0))
            if count > 0:
                self._daily[source] = (day_start, count - 1)


class _Deferred(Exception):
    def __init__(self, outcome: Outcome):
        self.outcome = outcome


class _BodyChain:
    """Yields the already-consumed head chunk(s), then the rest of the stream, then closes."""

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
        except BaseException:
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
    """Retry-After as an absolute epoch: delta-seconds or HTTP-date (GMT; naive treated as UTC)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return now + int(value)
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _classify_transport_error(exc: TransportError) -> Tuple[str, str, bool]:
    """(outcome kind, host_access reason, retryable) for a transport failure."""
    if isinstance(exc, BodyTooLargeError):
        return "blocked", "empty_reply", False  # unusable reply, not transient
    if isinstance(exc, RefusedRequestError):
        return "blocked", "not_checked", False  # a local refusal: retrying changes nothing
    msg = str(exc).lower()
    if "timeouterror" in msg:
        return "timeout", "timeout", True
    if "tls" in msg or "ssl" in msg:
        return "tls_error", "tls_error", False  # renegotiation/cipher failures are not transient
    if "connectionreseterror" in msg:
        return "connection_reset", "connection_reset", True
    return "connection_reset", "connection_reset", True


def _read_prefix(body_iter: Iterator[bytes], max_bytes: int) -> Tuple[bytes, Optional[TransportError]]:
    """Consume up to max_bytes (plus at most one chunk already taken) for marker scanning.

    Returns (prefix, error): error is the TransportError that ended the stream early, else
    None — a prefix shorter than max_bytes with a None error means the stream ended cleanly.
    The returned bytes were consumed from the iterator; a caller that keeps reading the body
    must hand them back first.
    """
    buf = bytearray()
    try:
        for chunk in body_iter:
            buf.extend(chunk)
            if len(buf) >= max_bytes:
                break
    except TransportError as exc:
        return bytes(buf), exc
    return bytes(buf), None


def _is_textual(content_type: Optional[str]) -> bool:
    """Marker scanning applies to textual/HTML bodies only; binary bodies (PDF, images) skip it."""
    if not content_type:
        return True
    low = content_type.lower()
    return any(tok in low for tok in _TEXTUAL_TYPES)


def _has_marker(text: str, markers: Tuple[str, ...]) -> bool:
    for marker in markers:
        if marker in text:
            return True
    return False


def _block_reason(prefix: bytes, geo_markers: Tuple[str, ...]) -> str:
    # The status already says "denied"; body markers only refine the reason.
    text = prefix.decode("utf-8", errors="ignore").lower()
    if _has_marker(text, geo_markers):
        return "geo_blocked"
    return "origin_denied"
