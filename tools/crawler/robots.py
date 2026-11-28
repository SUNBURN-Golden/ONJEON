"""robots.txt policy over bytes supplied by the injected transport.

Group selection and rule matching follow RFC 9309: matching groups
are combined, the longest matching rule wins, Allow wins a tie, and `*` and a trailing `$` work.

Outcomes per host (RFC 9309, plus the project rule "when in doubt, do not fetch"):
  200            parse; Disallow/Allow honoured for our product token; Crawl-delay returned (else None)
  partial, non-plain-text, or encoded 2xx policies: defer as robots_unreachable
  remaining 2xx  treated as 200
  4xx except 401/403/429   robots.txt not found => everything allowed
  429            rate limited: host DEFERRED, reason robots_rate_limited
  2xx larger than the cap with nothing parseable (declared Content-Length too big, or no full line
                 within the cap): host DEFERRED, reason robots_too_large (never "allow everything")
  401, 403       host BLOCKED: deferred for the rest of the UTC day, reason robots_forbidden
  5xx, timeout, network error, bad/cross-host redirect, 1xx/other => host DEFERRED for the rest of the UTC
                 day; the host is never fetched meanwhile
  429, 503       hold lasts until the later of UTC day end and Retry-After
A parsed robots.txt is cached for ttl_s (default 24h) by origin; deferral is per host name. Time comes from
the injected clock (epoch seconds). The robots.txt request itself is made through the transport the caller
supplies, once per origin per TTL (cached in between); PoliteFetcher supplies a budgeted request callback.
Not a limiter, not thread-safe by itself (an RLock serialises check()).
"""
import re
import threading
import time
from codecs import BOM_UTF8
from dataclasses import dataclass
from string import ascii_letters, digits
from typing import Callable, Dict, Mapping, Optional, Tuple
from urllib.parse import quote, urljoin, urlsplit

from .transport import BodyTooLargeError, NetworkDisabledError, Transport, TransportError, retry_after_until
from .useragent import PRODUCT_NAME, build_user_agent

DAY_S = 86400
ROBOTS_MAX_BYTES = 512 * 1024  # RFC 9309: parse at least the first 500 KiB
MAX_REDIRECTS = 5
ROBOTS_ACCEPT = {"Accept": "text/plain"}
UNRESERVED = frozenset(ascii_letters + digits + "-._~")
URI_SAFE = ":/?#[]@!&'()+,;=%"  # Preserve delimiters and escapes, excluding robots operators.
ESCAPED_OCTET = re.compile(r"%([0-9a-fA-F]{2})")
Rule = Tuple[str, bool]  # normalized path pattern, allowance


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
    rulelines: Tuple[Rule, ...]
    crawl_delay: Optional[float]
    reason: str


class RobotsCache:
    def __init__(self, transport: Transport, user_agent: str, *, ttl_s: float = DAY_S,
                 clock: Callable[[], float] = time.time, timeout_s: float = 20.0,
                 follow_redirects: bool = True):
        self._transport = transport
        self._ua = user_agent
        self._ttl = ttl_s
        self._clock = clock
        self._timeout = timeout_s
        self._follow_redirects = follow_redirects
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
            if not _can_fetch(entry.rulelines, url):
                return RobotsDecision(False, "robots_disallow", entry.crawl_delay)
            return RobotsDecision(True, entry.reason, entry.crawl_delay)

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

    def _defer(self, host: str, now: float, reason: str, blocked: bool = False,
               retry_until: Optional[float] = None) -> None:
        until = (int(now // DAY_S) + 1) * DAY_S
        if retry_until is not None:
            until = max(until, retry_until)
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
                    if status in (429, 503):
                        received_at = self._clock()
                        reason = "robots_rate_limited" if status == 429 else "robots_server_error"
                        retry_until = retry_after_until(resp.headers.get("retry-after"), received_at)
                        self._defer(host, received_at, reason, retry_until=retry_until)
                        return None
                    if 300 <= status < 400:
                        if not self._follow_redirects:
                            self._defer(host, now, "robots_redirect_refused")
                            return None
                        target = urljoin(url, resp.headers.get("location", ""))
                        t = urlsplit(target)
                        if t.scheme not in ("http", "https") or (t.hostname or "").lower() != host:
                            self._defer(host, now, "robots_redirect_refused")
                            return None
                        url = target
                        continue
                    success = 200 <= status < 300
                    if success and (status == 206 or not _has_policy_headers(resp.headers)):
                        self._defer(host, now, "robots_unreachable")
                        return None
                    body = _read_capped(resp) if success else b""
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
        if 400 <= status < 500:
            entry = _Entry(now, (), None, "robots_not_found")
        elif 200 <= status < 300:
            if body is None:  # over the cap and nothing usable: we cannot know the rules, so do not fetch
                self._defer(host, now, "robots_too_large")
                return None
            # A challenge can be served as text/plain or without a Content-Type header.
            if any(line.lstrip(b" \t").startswith(b"<") for line in body.removeprefix(BOM_UTF8).splitlines()):
                self._defer(host, now, "robots_unreachable")
                return None
            entry = _parse(now, body)
        else:  # 5xx, 1xx, anything unexpected
            self._defer(host, now, "robots_server_error")
            return None
        self._entries[origin] = entry
        return entry


def _has_policy_headers(headers: Mapping[str, str]) -> bool:
    media_type = headers.get("content-type", "text/plain").partition(";")[0].strip().lower()
    encoding = headers.get("content-encoding", "identity").strip().lower()
    return media_type == "text/plain" and encoding == "identity" and "content-range" not in headers


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


def _normalize_path(value: str, *, rule: bool = False) -> str:
    """Normalize URI octets, treating * and trailing $ as operators only in rules."""
    def normalize_escape(match: re.Match) -> str:
        octet = chr(int(match[1], 16))
        return octet if octet in UNRESERVED else match[0].upper()

    anchor = rule and value.endswith("$")
    if anchor:
        value = value[:-1]
    safe = URI_SAFE + "*" if rule else URI_SAFE
    normalized = ESCAPED_OCTET.sub(normalize_escape, quote(value, safe=safe))
    return normalized + "$" if anchor else normalized


def _parse(now: float, body: bytes) -> _Entry:
    groups = []
    agents, rules, delay = set(), [], None
    for line in re.split(r"\r\n?|\n", body.decode("utf-8-sig", errors="replace")):
        name, colon, value = line.partition("#")[0].partition(":")
        if not colon:
            continue
        name, value = name.strip(" \t").lower(), value.strip(" \t")
        if name == "user-agent" and value:
            if rules:
                groups.append((agents, rules, delay))
                agents, rules, delay = set(), [], None
            agents.add(value.lower())
        elif agents and name in ("allow", "disallow"):
            rules.append((_normalize_path(value, rule=True), name == "allow"))
        elif agents and name == "crawl-delay" and value.isascii() and value.isdigit():
            # Extension records do not mark the end of a user-agent list.
            delay = max(delay or 0, float(value))
    if agents:
        groups.append((agents, rules, delay))

    token = PRODUCT_NAME.lower()
    selected = [(rules, delay) for agents, rules, delay in groups if token in agents]
    if not selected:
        selected = [(rules, delay) for agents, rules, delay in groups if "*" in agents]
    rulelines = tuple(rule for rules, _ in selected for rule in rules)
    delay = max((delay for _, delay in selected if delay is not None), default=None)
    return _Entry(now, rulelines, delay, "ok")


def _can_fetch(rulelines: Tuple[Rule, ...], url: str) -> bool:
    if not rulelines:
        return True
    parts = urlsplit(url)
    target = (parts.path or "/") + (f"?{parts.query}" if "?" in url.partition("#")[0] else "")
    path = _normalize_path(target)
    best_len, allowed = -1, True
    for pattern, allowance in rulelines:
        if not pattern or not _matches(pattern, path):
            continue  # an empty Disallow/Allow matches nothing
        if len(pattern) > best_len or (len(pattern) == best_len and allowance):
            best_len, allowed = len(pattern), allowance
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
