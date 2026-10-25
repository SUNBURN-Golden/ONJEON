"""robots.txt policy over bytes supplied by the injected transport (stdlib urllib.robotparser logic).

Parsing and group selection are stdlib (RobotFileParser.parse / Entry.applies_to). Rule matching is RFC 9309
instead of the stdlib's first-match-wins with literal paths: the longest matching rule wins, Allow wins a tie,
`*` and a trailing `$` work (stdlib would silently ignore `Disallow: /*.pdf$`, the unsafe direction).

Outcomes per host (RFC 9309, plus the project rule "when in doubt, do not fetch"):
  200            parse; Disallow/Allow honoured for our product token; Crawl-delay returned (else None)
  other 2xx      treated as 200
  4xx except 401/403/429   robots.txt not found => everything allowed
  429            rate limited: host DEFERRED for the rest of the UTC day, reason robots_rate_limited
  2xx larger than the cap with nothing parseable (declared Content-Length too big, or no full line
                 within the cap): host DEFERRED, reason robots_too_large (never "allow everything")
  401, 403       host BLOCKED: deferred for the rest of the UTC day, reason robots_forbidden
  5xx, timeout, network error, bad/cross-host redirect, 1xx/other => host DEFERRED for the rest of the UTC
                 day; the host is never fetched meanwhile
A parsed robots.txt is cached for ttl_s (default 24h) by origin; deferral is per host name. Time comes from
the injected clock (epoch seconds). The robots.txt request itself is made through the transport the caller
supplies, once per origin per TTL (cached in between); PoliteFetcher supplies a budgeted request callback.
Not a limiter, not thread-safe by itself (an RLock serialises check()).
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .transport import BodyTooLargeError, NetworkDisabledError, Transport, TransportError
from .useragent import PRODUCT_NAME, build_user_agent

DAY_S = 86400
ROBOTS_MAX_BYTES = 512 * 1024  # RFC 9309: parse at least the first 500 KiB
MAX_REDIRECTS = 5
ROBOTS_ACCEPT = {"Accept": "text/plain"}


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    reason: str  # ok | robots_not_found | robots_disallow | robots_forbidden | robots_server_error | ...
    crawl_delay: Optional[float] = None
    deferred_until: Optional[float] = None  # epoch seconds; set => do not fetch this host before then
    blocked: bool = False  # robots 401/403

    @property
    def deferred(self) -> bool:
        return self.deferred_until is not None


@dataclass
class _Entry:
    fetched_at: float
    parser: Optional[RobotFileParser]  # None => no robots.txt (4xx): allow all
    crawl_delay: Optional[float]
    reason: str


class RobotsCache:
    def __init__(self, transport: Transport, user_agent: str, *, ttl_s: float = DAY_S,
                 clock: Callable[[], float] = time.time, timeout_s: float = 20.0):
        self._transport = transport
        self._ua = user_agent
        self._ttl = ttl_s
        self._clock = clock
        self._timeout = timeout_s
        self._entries: Dict[Tuple[str, str, int], _Entry] = {}
        self._deferred: Dict[str, Tuple[float, str, bool]] = {}
        self._lock = threading.RLock()

    @classmethod
    def from_config(cls, transport: Transport, config, clock: Callable[[], float] = time.time) -> "RobotsCache":
        return cls(transport, build_user_agent(config), ttl_s=config.robots_cache_ttl_s, clock=clock)

    def check(self, url: str, headers: Optional[Mapping[str, str]] = None, *, request=None) -> RobotsDecision:
        """May we fetch `url`? Fetches robots.txt for its origin when not cached (or older than the TTL).

        `headers` are forwarded to the robots.txt request so every sub-request of one fetch carries
        identical headers; Accept stays text/plain (a robots.txt is always wanted as plain text).
        """
        parts = urlsplit(url)
        try:
            host, port = parts.hostname, parts.port
        except ValueError:
            return RobotsDecision(False, "bad_url")
        if parts.scheme not in ("http", "https") or not host:
            return RobotsDecision(False, "unsupported_scheme")
        origin = (parts.scheme, host.lower(), port or (443 if parts.scheme == "https" else 80))
        with self._lock:
            now = self._clock()
            hit = self._deferral(origin[1], now)
            if hit:
                return hit
            entry = self._entries.get(origin)
            if entry is None or now - entry.fetched_at >= self._ttl:
                entry = self._fetch(origin, now, headers, request)
                if entry is None:
                    return self._deferral(origin[1], now)
            if entry.parser is None:
                return RobotsDecision(True, entry.reason, None)
            if not _can_fetch(entry.parser, url):
                return RobotsDecision(False, "robots_disallow", entry.crawl_delay)
            return RobotsDecision(True, "ok", entry.crawl_delay)

    def crawl_delay(self, url: str) -> Optional[float]:
        return self.check(url).crawl_delay

    def _deferral(self, host: str, now: float) -> Optional[RobotsDecision]:
        d = self._deferred.get(host)
        if d is None:
            return None
        until, reason, blocked = d
        if now >= until:
            del self._deferred[host]
            return None
        return RobotsDecision(False, reason, None, until, blocked)

    def _defer(self, host: str, now: float, reason: str, blocked: bool = False) -> None:
        until = (int(now // DAY_S) + 1) * DAY_S
        self._deferred[host] = (until, reason, blocked)
        for key in [k for k in self._entries if k[1] == host]:
            del self._entries[key]

    def _fetch(self, origin, now: float, headers: Optional[Mapping[str, str]] = None, request=None) -> Optional[_Entry]:
        scheme, host, port = origin
        authority = f"[{host}]" if ":" in host else host
        default_port = 443 if scheme == "https" else 80
        url = f"{scheme}://{authority}{'' if port == default_port else f':{port}'}/robots.txt"
        req_headers = dict(headers or {})
        req_headers.update(ROBOTS_ACCEPT)
        try:
            for _ in range(MAX_REDIRECTS + 1):
                with (request or self._transport.request)(url, req_headers, self._timeout, ROBOTS_MAX_BYTES) as resp:
                    status = resp.status
                    if 300 <= status < 400:
                        target = urljoin(url, resp.headers.get("location", ""))
                        t = urlsplit(target)
                        if t.scheme not in ("http", "https") or (t.hostname or "").lower() != host:
                            self._defer(host, now, "robots_redirect_refused")
                            return None
                        url = target
                        continue
                    body = _read_capped(resp) if 200 <= status < 300 else b""
                break
            else:
                self._defer(host, now, "robots_redirect_refused")
                return None
        except NetworkDisabledError:
            raise
        except (TransportError, OSError):
            self._defer(host, now, "robots_unreachable")
            return None
        if status in (401, 403):
            self._defer(host, now, "robots_forbidden", blocked=True)
            return None
        if status == 429:
            self._defer(host, now, "robots_rate_limited")
            return None
        if 400 <= status < 500:
            entry = _Entry(now, None, None, "robots_not_found")
        elif 200 <= status < 300:
            if body is None:  # over the cap and nothing usable: we cannot know the rules, so do not fetch
                self._defer(host, now, "robots_too_large")
                return None
            entry = _parse(now, body)
        else:  # 5xx, 1xx, anything unexpected
            self._defer(host, now, "robots_server_error")
            return None
        self._entries[origin] = entry
        return entry


def _read_capped(resp) -> Optional[bytes]:
    """Whole robots body, at most ROBOTS_MAX_BYTES; an over-long file is cut at the last full line.

    None when the cap was hit and no full line was read (e.g. the transport refused on a declared
    Content-Length before yielding anything): an empty result must not be mistaken for "no rules".
    """
    buf = bytearray()
    try:
        for chunk in resp.body_iter:
            buf += chunk
    except BodyTooLargeError:
        cut = buf.rfind(b"\n")
        return bytes(buf[:cut + 1]) if cut >= 0 else None
    return bytes(buf)


def _parse(now: float, body: bytes) -> _Entry:
    rp = RobotFileParser()
    rp.parse(body.decode("utf-8-sig", errors="replace").splitlines())
    delay = rp.crawl_delay(PRODUCT_NAME)
    return _Entry(now, rp, float(delay) if delay is not None else None, "ok")


def _group(rp: RobotFileParser):
    for entry in rp.entries:
        if entry.applies_to(PRODUCT_NAME):
            return entry
    return rp.default_entry


def _can_fetch(rp: RobotFileParser, url: str) -> bool:
    group = _group(rp)
    if group is None:
        return True
    parts = urlsplit(url)
    path = unquote(parts.path or "/") + (f"?{unquote(parts.query)}" if parts.query else "")
    best_len, allowed = -1, True
    for rule in group.rulelines:
        pattern = unquote(rule.path)  # RuleLine re-quotes its path (turning * and $ into %2A, %24)
        if not pattern or not _matches(pattern, path):
            continue  # an empty Disallow/Allow matches nothing
        if len(pattern) > best_len or (len(pattern) == best_len and rule.allowance):
            best_len, allowed = len(pattern), rule.allowance
    return allowed


def _matches(pattern: str, path: str) -> bool:
    """Prefix match with `*` wildcards and an optional trailing `$` anchor (no regex, no backtracking blowup)."""
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    first, *rest = pattern.split("*")
    if not path.startswith(first):
        return False
    pos = len(first)
    if not rest:
        return not anchored or pos == len(path)
    for mid in rest[:-1]:
        i = path.find(mid, pos)
        if i < 0:
            return False
        pos = i + len(mid)
    last = rest[-1]
    if anchored:
        return len(path) - len(last) >= pos and path.endswith(last)
    return path.find(last, pos) >= 0
