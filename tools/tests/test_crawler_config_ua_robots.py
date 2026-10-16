"""crawler core 1 (config, user agent, robots, transport) plus the static no-circumvention guard.

One file on purpose (the node's allowed test path). FakeClock/FakeTransport live here, in tools/tests: the
production package tools/crawler ships no fake and no test hook. No sockets, no sleeping, no real network.
"""
import ast
import dataclasses
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import crawler  # noqa: E402
from crawler import config as c  # noqa: E402
from crawler import robots as r  # noqa: E402
from crawler import transport as t  # noqa: E402
from crawler import useragent as u  # noqa: E402
from crawler.config import CrawlerConfig  # noqa: E402
from crawler.transport import (BodyTooLargeError, NetworkDisabledError, Response, Transport,  # noqa: E402
                               TransportError)
from crawler.useragent import UserAgentError  # noqa: E402


# ---- fake transport / clock ----

class FakeClock:
    def __init__(self, now: float = 1_800_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeTransport(Transport):
    """routes: url -> (status, headers, body bytes) | Exception instance | callable(url) -> either of those.
    An unscripted URL raises AssertionError so a test cannot silently fetch something unexpected."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.requests = []  # (url, headers, timeout, max_bytes)

    def request(self, url, headers, timeout, max_bytes):
        self.requests.append((url, dict(headers or {}), timeout, max_bytes))
        if url not in self.routes:
            raise AssertionError(f"unscripted request: {url}")
        route = self.routes[url]
        if callable(route):
            route = route(url)
        if isinstance(route, Exception):
            raise route
        if isinstance(route, Response):
            return route
        status, headers, body = route
        return Response(status, headers, iter([body] if body else []))

    @property
    def urls(self):
        return [r[0] for r in self.requests]


# ---- config ----

class ConfigTest(unittest.TestCase):
    def test_defaults_are_safe(self):
        d = c.CrawlerConfig()
        self.assertIs(d.network_enabled, False)
        self.assertEqual(d.contact, "")
        self.assertEqual((d.per_host_min_interval_s, d.per_host_concurrency, d.max_global_hosts, d.max_attempts),
                         (5, 1, 4, 3))
        self.assertEqual((d.robots_cache_ttl_s, d.spool_cap_bytes, d.object_cap_bytes),
                         (86400, 1_500_000_000, 67108864))
        self.assertGreater(d.daily_request_cap_default, 0)
        self.assertTrue(d.spool_dir and d.state_db)

    def test_empty_file_object_gives_defaults(self):
        self.assertEqual(c.config_from_dict({}), c.CrawlerConfig())

    def test_frozen(self):
        d = c.CrawlerConfig()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.network_enabled = True

    def test_unknown_keys_rejected(self):
        with self.assertRaisesRegex(c.ConfigError, "unknown config keys: proxy, user_agent"):
            c.config_from_dict({"proxy": "x", "user_agent": "y"})

    def test_type_and_range_validation(self):
        bad = [
            {"network_enabled": 1}, {"network_enabled": "true"}, {"contact": 5},
            {"per_host_min_interval_s": 0}, {"per_host_min_interval_s": True}, {"per_host_min_interval_s": float("nan")},
            {"per_host_concurrency": 0}, {"per_host_concurrency": 1.5}, {"max_global_hosts": 100},
            {"max_attempts": 0}, {"daily_request_cap_default": -1}, {"robots_cache_ttl_s": 1},
            {"spool_dir": ""}, {"state_db": 3}, {"spool_cap_bytes": 0},
            {"object_cap_bytes": c.HARD_OBJECT_CAP_BYTES + 1},
            {"object_cap_bytes": 2000, "spool_cap_bytes": 1000},
        ]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(c.ConfigError):
                c.config_from_dict(data)

    def test_non_object_rejected(self):
        with self.assertRaises(c.ConfigError):
            c.config_from_dict([])

    def test_load_config_roundtrip_and_errors(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "crawler.json"
            p.write_text(json.dumps({"contact": "ops@example.org", "network_enabled": True, "max_attempts": 2}))
            cfg = c.load_config(p)
            self.assertEqual((cfg.contact, cfg.network_enabled, cfg.max_attempts), ("ops@example.org", True, 2))
            p.write_text('{"max_attempts": 1, "max_attempts": 2}')
            with self.assertRaisesRegex(c.ConfigError, "duplicate"):
                c.load_config(p)
            p.write_text("{not json")
            with self.assertRaises(c.ConfigError):
                c.load_config(p)
            p.write_bytes(b"\xff\xfe")
            with self.assertRaises(c.ConfigError):
                c.load_config(p)
            p.write_bytes(b" " * (c.MAX_CONFIG_FILE_BYTES + 1))
            with self.assertRaisesRegex(c.ConfigError, "too large"):
                c.load_config(p)

    def test_network_flag_has_no_code_path_other_than_the_file(self):
        # only the dataclass field / the JSON key; no env or argument override exists in the module
        src = Path(c.__file__).read_text()
        self.assertNotIn("environ", src)
        self.assertNotIn("getenv", src)


# ---- user agent ----

class UserAgentTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(u.build_user_agent("ops@example.org"),
                         f"ONJEON-SourceArchiver/{crawler.__version__} (+ops@example.org)")
        self.assertEqual(u.build_user_agent("https://example.org/bot-info", "1.2"),
                         "ONJEON-SourceArchiver/1.2 (+https://example.org/bot-info)")

    def test_from_config(self):
        cfg = CrawlerConfig(contact="ops@example.org")
        self.assertEqual(u.build_user_agent(cfg), u.build_user_agent("ops@example.org"))

    def test_deterministic(self):
        self.assertEqual({u.build_user_agent("ops@example.org") for _ in range(20)}, {u.build_user_agent("ops@example.org")})

    def test_empty_contact_refused(self):
        for contact in ("", "   ", None):
            with self.subTest(contact=contact), self.assertRaises(u.UserAgentError):
                u.build_user_agent(contact)
        with self.assertRaises(u.UserAgentError):
            u.build_user_agent(CrawlerConfig())  # default config has no contact

    def test_browser_like_refused(self):
        for contact in ("Mozilla/5.0 (X11; Linux x86_64)", "Chrome/120.0", "see Safari/605", "firefox@example.org",
                        "https://example.org/AppleWebKit", "MOZILLA/5.0", "opera@example.org"):
            with self.subTest(contact=contact), self.assertRaises(u.UserAgentError):
                u.build_user_agent(contact)

    def test_honest_contacts_with_lookalike_words_accepted(self):
        self.assertIn("operations@example.org", u.build_user_agent("operations@example.org"))
        self.assertIn("knowledge@example.org", u.build_user_agent("knowledge@example.org"))

    def test_unsafe_contact_refused(self):
        for contact in ("not a contact", "ops@example.org)", "a(b)@example.org", "ops@example.org\r\nX-Evil: 1",
                        "plain-text", "ftp://example.org/x", "ops@example.org, other@example.org"):
            with self.subTest(contact=contact), self.assertRaises(u.UserAgentError):
                u.build_user_agent(contact)

    def test_bad_version_refused(self):
        with self.assertRaises(u.UserAgentError):
            u.build_user_agent("ops@example.org", "1 (Mozilla)")

    def test_no_rotation_api(self):
        public = [n for n in dir(u) if not n.startswith("_")]
        for name in public:
            for word in ("rotat", "random", "choice", "pick", "spoof", "fake", "pool", "list"):
                self.assertNotIn(word, name.lower(), name)
        funcs = [n for n in public if callable(getattr(u, n)) and getattr(getattr(u, n), "__module__", "") == u.__name__]
        self.assertEqual(sorted(funcs), ["UserAgentError", "build_user_agent"])


# ---- robots ----

FIX = Path(__file__).resolve().parent / "fixtures" / "crawler"
UA = "ONJEON-SourceArchiver/0.1.0 (+ops@example.org)"
ROBOTS = "https://a.example/robots.txt"


def fixture(name):
    return (FIX / name).read_bytes()


def make(routes, **kw):
    clock = FakeClock()
    t = FakeTransport(routes)
    return r.RobotsCache(t, UA, clock=clock, **kw), t, clock


class RobotsTest(unittest.TestCase):
    def test_fixtures_are_marked_fixture(self):
        for p in FIX.glob("robots_*.txt"):
            self.assertIn("origin=fixture", p.read_text().splitlines()[0], p.name)

    def test_disallow_honoured_for_our_ua_and_allow_override(self):
        c, t, _ = make({ROBOTS: (200, {}, fixture("robots_basic.txt"))})
        self.assertFalse(c.check("https://a.example/admin/x").allowed)
        self.assertEqual(c.check("https://a.example/admin/x").reason, "robots_disallow")
        self.assertTrue(c.check("https://a.example/admin/public/x").allowed)
        self.assertTrue(c.check("https://a.example/private/x").allowed)  # '*' group does not apply: ours matches
        self.assertTrue(c.check("https://a.example/products?id=1").allowed)

    def test_longest_match_wins_regardless_of_order_and_allow_wins_ties(self):
        body = (b"User-agent: *\nAllow: /a\nDisallow: /a/b\nDisallow: /t\nAllow: /t\n"
                b"Disallow: /\nAllow: /pub/\n")
        c, _, _ = make({ROBOTS: (200, {}, body)})
        self.assertTrue(c.check("https://a.example/a").allowed)
        self.assertFalse(c.check("https://a.example/a/b/x").allowed)  # stdlib first-match would allow this
        self.assertTrue(c.check("https://a.example/t").allowed)  # tie => Allow
        self.assertFalse(c.check("https://a.example/other").allowed)
        self.assertTrue(c.check("https://a.example/pub/x").allowed)

    def test_wildcards_and_end_anchor(self):
        body = b"User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/cache\nDisallow: /q?*secret=\n"
        c, _, _ = make({ROBOTS: (200, {}, body)})
        self.assertFalse(c.check("https://a.example/docs/a.pdf").allowed)
        self.assertTrue(c.check("https://a.example/docs/a.pdf?x=1").allowed)  # '$' anchors the end
        self.assertTrue(c.check("https://a.example/docs/a.pdf.html").allowed)
        self.assertFalse(c.check("https://a.example/tmp123/cache/x").allowed)
        self.assertTrue(c.check("https://a.example/tmp123/other").allowed)
        self.assertFalse(c.check("https://a.example/q?a=1&secret=2").allowed)

    def test_matches_helper_edges(self):
        m = r._matches
        self.assertTrue(m("/", "/anything"))
        self.assertTrue(m("/a*", "/a"))
        self.assertTrue(m("*", "/x"))
        self.assertTrue(m("/a$", "/a"))
        self.assertFalse(m("/a$", "/ab"))
        self.assertFalse(m("/a*a$", "/a"))  # prefix and suffix must not overlap
        self.assertTrue(m("/a*a$", "/aa"))
        self.assertFalse(m("/x*y*z", "/x-z-y"))
        self.assertTrue(m("/x*y*z", "/x-y-z"))
        self.assertTrue(m("/" + "*a" * 200, "/" + "a" * 400))  # no catastrophic backtracking
        self.assertFalse(m("/" + "*a" * 200 + "b", "/" + "a" * 400))

    def test_empty_disallow_allows_everything(self):
        c, _, _ = make({ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n")})
        self.assertTrue(c.check("https://a.example/x").allowed)

    def test_star_group_applies_when_no_specific_group(self):
        c, _, _ = make({ROBOTS: (200, {}, fixture("robots_star_only.txt"))})
        self.assertFalse(c.check("https://a.example/secret/a").allowed)
        self.assertTrue(c.check("https://a.example/open").allowed)

    def test_other_bots_rules_do_not_apply(self):
        c, _, _ = make({ROBOTS: (200, {}, fixture("robots_other_bot_only.txt"))})
        self.assertTrue(c.check("https://a.example/anything").allowed)

    def test_disallow_all_for_us(self):
        c, _, _ = make({ROBOTS: (200, {}, fixture("robots_disallow_all_us.txt"))})
        d = c.check("https://a.example/")
        self.assertFalse(d.allowed)
        self.assertFalse(d.deferred)

    def test_empty_robots_allows_all(self):
        c, _, _ = make({ROBOTS: (200, {}, b"")})
        self.assertTrue(c.check("https://a.example/x").allowed)

    def test_crawl_delay_returned_or_none(self):
        c, _, _ = make({ROBOTS: (200, {}, fixture("robots_basic.txt"))})
        self.assertEqual(c.check("https://a.example/x").crawl_delay, 10)  # our group, not '*' (2)
        self.assertEqual(c.crawl_delay("https://a.example/x"), 10)
        c2, _, _ = make({ROBOTS: (200, {}, fixture("robots_star_only.txt"))})
        self.assertIsNone(c2.check("https://a.example/x").crawl_delay)
        c3, _, _ = make({ROBOTS: (200, {}, b"User-agent: *\nCrawl-delay: 7\n")})
        self.assertEqual(c3.check("https://a.example/x").crawl_delay, 7)

    def test_ttl_24h_with_injected_clock(self):
        c, t, clock = make({ROBOTS: (200, {}, fixture("robots_star_only.txt"))})
        c.check("https://a.example/a")
        c.check("https://a.example/b")
        self.assertEqual(len(t.requests), 1)
        clock.advance(86400 - 1)
        c.check("https://a.example/c")
        self.assertEqual(len(t.requests), 1)
        clock.advance(1)
        c.check("https://a.example/d")
        self.assertEqual(len(t.requests), 2)

    def test_ttl_comes_from_config(self):
        cfg = CrawlerConfig(contact="ops@example.org", robots_cache_ttl_s=120)
        t = FakeTransport({ROBOTS: (200, {}, b"")})
        clock = FakeClock()
        c = r.RobotsCache.from_config(t, cfg, clock)
        c.check("https://a.example/a")
        clock.advance(121)
        c.check("https://a.example/a")
        self.assertEqual(len(t.requests), 2)
        self.assertEqual(t.requests[0][1], {"Accept": "text/plain"})  # robots request carries no extra headers

    def test_robots_is_per_origin(self):
        c, t, _ = make({ROBOTS: (200, {}, b""), "https://b.example/robots.txt": (200, {}, b""),
                        "http://a.example/robots.txt": (200, {}, b""), "https://a.example:8443/robots.txt": (200, {}, b"")})
        for u in ("https://a.example/x", "https://b.example/x", "http://a.example/x", "https://a.example:8443/x"):
            self.assertTrue(c.check(u).allowed)
        self.assertEqual(len(t.requests), 4)

    def test_5xx_defers_host_for_the_day_and_never_fetches_again(self):
        for status in (500, 503, 599):
            with self.subTest(status=status):
                c, t, clock = make({ROBOTS: (status, {}, b"oops")})
                d = c.check("https://a.example/x")
                self.assertTrue(d.deferred)
                self.assertFalse(d.allowed)
                self.assertEqual(d.reason, "robots_server_error")
                self.assertEqual(d.deferred_until, (int(clock.now // 86400) + 1) * 86400)
                for _ in range(3):
                    self.assertFalse(c.check("https://a.example/other").allowed)
                self.assertEqual(len(t.requests), 1)  # not even robots.txt again; never the host
                clock.now = d.deferred_until  # next UTC day: try again
                t.routes[ROBOTS] = (200, {}, b"")
                self.assertTrue(c.check("https://a.example/x").allowed)
                self.assertEqual(len(t.requests), 2)

    def test_deferral_covers_all_origins_of_the_host(self):
        c, t, _ = make({ROBOTS: (503, {}, b"")})
        c.check("https://a.example/x")
        self.assertTrue(c.check("http://a.example/y").deferred)
        self.assertEqual(len(t.requests), 1)
        self.assertFalse(c.check("https://a.example:8443/y").allowed)

    def test_other_hosts_unaffected_by_deferral(self):
        c, _, _ = make({ROBOTS: (503, {}, b""), "https://b.example/robots.txt": (200, {}, b"")})
        self.assertTrue(c.check("https://a.example/x").deferred)
        self.assertTrue(c.check("https://b.example/x").allowed)

    def test_timeout_and_network_errors_defer(self):
        for exc in (TimeoutError("t"), TransportError("net"), OSError("reset")):
            with self.subTest(exc=type(exc).__name__):
                c, t, _ = make({ROBOTS: exc})
                d = c.check("https://a.example/x")
                self.assertTrue(d.deferred and not d.allowed)
                self.assertEqual(d.reason, "robots_unreachable")
                c.check("https://a.example/y")
                self.assertEqual(len(t.requests), 1)

    def test_error_while_streaming_body_defers(self):
        def boom():
            yield b"User-agent: *\n"
            raise TransportError("read failed")
        c, _, _ = make({ROBOTS: lambda url: Response(200, {}, boom())})
        self.assertTrue(c.check("https://a.example/x").deferred)

    def test_403_and_401_are_blocked_and_deferred_with_reason(self):
        for status in (401, 403):
            with self.subTest(status=status):
                c, t, _ = make({ROBOTS: (status, {}, b"")})
                d = c.check("https://a.example/x")
                self.assertTrue(d.blocked and d.deferred and not d.allowed)
                self.assertEqual(d.reason, "robots_forbidden")
                self.assertFalse(c.check("https://a.example/y").allowed)
                self.assertEqual(len(t.requests), 1)

    def test_404_and_other_4xx_allow_everything(self):
        for status in (404, 410, 400, 428):
            with self.subTest(status=status):
                c, t, clock = make({ROBOTS: (status, {}, b"<html>not found</html>")})
                d = c.check("https://a.example/anything")
                self.assertTrue(d.allowed)
                self.assertFalse(d.deferred or d.blocked)
                self.assertEqual(d.reason, "robots_not_found")
                self.assertIsNone(d.crawl_delay)
                c.check("https://a.example/more")
                self.assertEqual(len(t.requests), 1)  # cached for the TTL too

    def test_429_defers_the_host(self):
        c, t, _ = make({ROBOTS: (429, {}, b"")})
        d = c.check("https://a.example/x")
        self.assertTrue(d.deferred and not d.allowed and not d.blocked)
        self.assertEqual(d.reason, "robots_rate_limited")
        c.check("https://a.example/y")
        self.assertEqual(len(t.requests), 1)

    def test_same_host_redirect_followed_cross_host_refused(self):
        c, t, _ = make({ROBOTS: (301, {"Location": "https://a.example/new-robots.txt"}, b""),
                        "https://a.example/new-robots.txt": (200, {}, fixture("robots_star_only.txt"))})
        self.assertFalse(c.check("https://a.example/secret").allowed)
        self.assertEqual(len(t.requests), 2)
        c2, t2, _ = make({ROBOTS: (302, {"Location": "https://evil.example/robots.txt"}, b"")})
        d = c2.check("https://a.example/x")
        self.assertTrue(d.deferred and not d.allowed)
        self.assertEqual(d.reason, "robots_redirect_refused")
        self.assertEqual(t2.urls, [ROBOTS])  # the other host was never contacted

    def test_redirect_loop_and_missing_location_defer(self):
        c, t, _ = make({ROBOTS: (302, {"Location": ROBOTS}, b"")})
        self.assertTrue(c.check("https://a.example/x").deferred)
        self.assertEqual(len(t.requests), r.MAX_REDIRECTS + 1)
        c2, _, _ = make({ROBOTS: (302, {}, b"")})
        self.assertTrue(c2.check("https://a.example/x").deferred)

    def test_oversize_robots_is_cut_at_last_full_line(self):
        def big(url):
            def it():
                yield b"User-agent: *\nDisallow: /a\nDisallow: /b"  # the last line is incomplete
                raise BodyTooLargeError("cap")
            return Response(200, {}, it())
        c, t, _ = make({ROBOTS: big})
        self.assertFalse(c.check("https://a.example/a").allowed)
        self.assertTrue(c.check("https://a.example/b").allowed)  # incomplete rule dropped, not half-applied
        self.assertEqual(t.requests[0][3], r.ROBOTS_MAX_BYTES)

    def test_oversize_robots_with_nothing_readable_defers_the_host(self):
        # the real transport raises on a declared Content-Length > cap before yielding a single byte
        def refused(url):
            def it():
                raise BodyTooLargeError("declared Content-Length exceeds the cap")
                yield b""
            return Response(200, {}, it())
        c, t, _ = make({ROBOTS: refused})
        d = c.check("https://a.example/private")
        self.assertTrue(d.deferred and not d.allowed)
        self.assertEqual(d.reason, "robots_too_large")
        self.assertFalse(c.check("https://a.example/other").allowed)
        self.assertEqual(len(t.requests), 1)

    def test_oversize_robots_without_any_full_line_defers_the_host(self):
        def big(url):
            def it():
                yield b"User-agent: *"  # no newline before the cap
                raise BodyTooLargeError("cap")
            return Response(200, {}, it())
        c, _, _ = make({ROBOTS: big})
        self.assertEqual(c.check("https://a.example/x").reason, "robots_too_large")

    def test_network_disabled_propagates_and_does_not_defer(self):
        c, _, _ = make({ROBOTS: NetworkDisabledError("off")})
        with self.assertRaises(NetworkDisabledError):
            c.check("https://a.example/x")

    def test_unsupported_urls(self):
        c, t, _ = make({})
        for u in ("ftp://a.example/x", "file:///etc/passwd", "/relative", "https://a.example:99999999/x"):
            with self.subTest(url=u):
                self.assertFalse(c.check(u).allowed)
        self.assertEqual(t.requests, [])

    def test_utf8_bom_and_garbage_bytes_do_not_crash(self):
        c, _, _ = make({ROBOTS: (200, {}, b"\xef\xbb\xbfUser-agent: *\nDisallow: /x\n\xff\xfe\x00junk")})
        self.assertFalse(c.check("https://a.example/x").allowed)

    def test_ipv6_host_robots_url(self):
        c, t, _ = make({"http://[::1]:8080/robots.txt": (404, {}, b"")})
        self.assertTrue(c.check("http://[::1]:8080/x").allowed)
        self.assertEqual(t.urls, ["http://[::1]:8080/robots.txt"])


# ---- transport ----

UA_RE = r"^ONJEON-SourceArchiver/\S+ \(\+ops@example\.org\)$"


def cfg(**kw):
    return CrawlerConfig(contact="ops@example.org", **kw)


class FakeHttpResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v
        self._buf = io.BytesIO(body)
        self.read_sizes = []
        self.closed = False

    def read(self, n=-1):
        self.read_sizes.append(n)
        return self._buf.read(n)

    def close(self):
        self.closed = True


class NoSocketCase(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if k != t.ENV_ALLOW_NETWORK}
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
            env.pop(k, None)
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        for target in ("socket.socket.connect", "socket.create_connection", "socket.getaddrinfo"):
            q = mock.patch(target, side_effect=AssertionError("socket/DNS touched"))
            q.start()
            self.addCleanup(q.stop)


class GateTest(NoSocketCase):
    def refused_before_opener(self, tr, url):
        with mock.patch.object(tr._opener, "open", side_effect=AssertionError("opener used")) as op:
            with self.assertRaises(t.NetworkDisabledError):
                tr.request(url, None, 5, 1000)
            op.assert_not_called()

    def test_refused_by_default_before_any_socket(self):
        tr = t.UrllibTransport(cfg())
        for url in ("https://insurer.invalid/robots.txt", "http://203.0.113.9/x", "http://localhost/x",
                    "http://127.0.0.1.invalid/x", "http://0x7f.1/x",
                    "http://[2001:db8::1]/x"):
            with self.subTest(url=url):
                self.refused_before_opener(tr, url)

    def test_config_flag_alone_is_not_enough(self):
        self.refused_before_opener(t.UrllibTransport(cfg(network_enabled=True)), "https://insurer.invalid/x")

    def test_env_flag_alone_is_not_enough(self):
        with mock.patch.dict(os.environ, {t.ENV_ALLOW_NETWORK: "1"}):
            self.refused_before_opener(t.UrllibTransport(cfg()), "https://insurer.invalid/x")

    def test_env_flag_must_be_exactly_one(self):
        tr = t.UrllibTransport(cfg(network_enabled=True))
        for v in ("0", "true", "yes", "", "1 "):
            with self.subTest(v=v), mock.patch.dict(os.environ, {t.ENV_ALLOW_NETWORK: v}):
                self.refused_before_opener(tr, "https://insurer.invalid/x")

    def test_both_flags_pass_the_gate(self):
        tr = t.UrllibTransport(cfg(network_enabled=True))
        with mock.patch.dict(os.environ, {t.ENV_ALLOW_NETWORK: "1"}):
            tr.check_destination("https://insurer.invalid/x")  # gate only: no request is made
            with mock.patch.object(tr._opener, "open", return_value=FakeHttpResponse(200, {}, b"ok")) as op:
                with tr.request("https://insurer.invalid/x", None, 5, 1000) as r:
                    self.assertEqual(b"".join(r.body_iter), b"ok")
                op.assert_called_once()

    def test_loopback_literals_allowed_without_flags(self):
        tr = t.UrllibTransport(cfg())
        for url in ("http://127.0.0.1:8080/x", "http://127.9.9.9/x", "http://[::1]:9/x"):
            with self.subTest(url=url):
                tr.check_destination(url)

    def test_network_flag_cannot_be_set_from_transport_arguments(self):
        import inspect
        self.assertEqual(list(inspect.signature(t.UrllibTransport.__init__).parameters), ["self", "config"])
        self.assertIs(CrawlerConfig().network_enabled, False)

    def test_malformed_urls_refused(self):
        tr = t.UrllibTransport(cfg())
        for url in ("ftp://127.0.0.1/x", "file:///etc/passwd", "/x", "http://", "http://user:pw@127.0.0.1/x",
                    "http://127.0.0.1@insurer.invalid/x",
                    "http://127.0.0.1:99999/x"):
            with self.subTest(url=url), self.assertRaises(t.TransportError):
                tr.check_destination(url)

    def test_constructor_needs_an_honest_contact(self):
        with self.assertRaises(UserAgentError):
            t.UrllibTransport(CrawlerConfig())
        with self.assertRaises(UserAgentError):
            t.UrllibTransport(CrawlerConfig(contact="Mozilla/5.0"))


class OpenerTest(NoSocketCase):
    def test_env_proxies_are_ignored(self):
        proxies = {"HTTP_PROXY": "http://proxy.invalid:3128", "HTTPS_PROXY": "http://proxy.invalid:3128",
                   "http_proxy": "http://proxy.invalid:3128", "https_proxy": "http://proxy.invalid:3128",
                   "ALL_PROXY": "socks5://p.invalid"}
        seen = []

        def fake_do_open(self_, http_class, req, **kw):
            seen.append((req.host, req.selector, req.type))
            return FakeHttpResponse(200, {}, b"ok")

        with mock.patch.dict(os.environ, proxies):
            self.assertEqual(urllib.request.getproxies()["http"], "http://proxy.invalid:3128")  # the env is hostile
            tr = t.UrllibTransport(cfg())
            # ProxyHandler({}) defines no *_open methods, so OpenerDirector does not even list it: no proxy
            # handler (and no env lookup) exists in the opener. The explicit call is pinned by StaticTest below.
            self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) for h in tr._opener.handlers))
            with mock.patch.object(urllib.request.HTTPHandler, "do_open", fake_do_open):
                tr.request("http://127.0.0.1:1/x", None, 5, 10).close()
        self.assertEqual(seen, [("127.0.0.1:1", "/x", "http")])  # went to the target itself, not the proxy

    def test_explicit_empty_proxy_handler_has_no_proxies(self):
        h = urllib.request.ProxyHandler({})
        self.assertEqual(h.proxies, {})
        self.assertEqual([m for m in dir(h) if m.endswith("_open") and m != "proxy_open"], [])

    def test_opener_has_no_redirect_error_or_default_header_handlers(self):
        op = t.UrllibTransport(cfg())._opener
        kinds = {type(h) for h in op.handlers}
        self.assertEqual(kinds, {urllib.request.HTTPHandler, urllib.request.HTTPSHandler})
        self.assertFalse(any(isinstance(h, urllib.request.HTTPRedirectHandler) for h in op.handlers))
        self.assertFalse(any(isinstance(h, urllib.request.HTTPErrorProcessor) for h in op.handlers))
        self.assertEqual(op.addheaders, [])  # no Python-urllib default User-agent

    def test_redirect_is_returned_not_followed_and_headers_are_exact(self):
        tr = t.UrllibTransport(cfg())
        calls = []

        def fake_do_open(self_, http_class, req, **kw):
            calls.append(req)
            return FakeHttpResponse(302, {"Location": "http://127.0.0.1:2/elsewhere"}, b"moved")

        with mock.patch.object(urllib.request.HTTPHandler, "do_open", fake_do_open):
            with tr.request("http://127.0.0.1:1/start", {"If-None-Match": '"abc"'}, 5, 1000) as r:
                self.assertEqual(r.status, 302)
                self.assertEqual(r.headers["location"], "http://127.0.0.1:2/elsewhere")
        self.assertEqual(len(calls), 1)  # the redirect target was never requested
        sent = {k.lower(): v for k, v in calls[0].header_items()}
        self.assertEqual(set(sent), {"user-agent", "accept", "if-none-match", "host"})
        self.assertRegex(sent["user-agent"], UA_RE)
        self.assertEqual(sent["accept"], "*/*")
        self.assertEqual(calls[0].get_method(), "GET")

    def test_error_statuses_come_back_as_responses(self):
        tr = t.UrllibTransport(cfg())
        for status in (403, 404, 503):
            with mock.patch.object(urllib.request.HTTPHandler, "do_open", lambda *a, s=status, **k: FakeHttpResponse(s, {}, b"x")):
                with tr.request("http://127.0.0.1:1/x", None, 5, 10) as r:
                    self.assertEqual(r.status, status)


class HeadersAndLimitsTest(NoSocketCase):
    def setUp(self):
        super().setUp()
        self.tr = t.UrllibTransport(cfg())

    def test_only_allowed_headers(self):
        h = self.tr.build_headers({"accept": "text/html", "If-Modified-Since": "Wed, 21 Oct 2015 07:28:00 GMT"})
        self.assertEqual(h, {"User-Agent": self.tr.user_agent, "Accept": "text/html",
                             "If-Modified-Since": "Wed, 21 Oct 2015 07:28:00 GMT"})
        self.assertEqual(self.tr.build_headers(None), {"User-Agent": self.tr.user_agent, "Accept": "*/*"})

    def test_caller_cannot_override_user_agent_or_add_browser_headers(self):
        for name in ("User-Agent", "user-agent", "Referer", "Cookie", "Accept-Language", "Sec-Fetch-Mode",
                     "Authorization", "Range", "X-Forwarded-For", "Host"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.tr.build_headers({name: "x"})
        with self.assertRaises(ValueError):
            self.tr.build_headers({"Accept": "a\r\nX: y"})

    def test_argument_validation(self):
        for timeout in (0, -1, float("nan"), True, "5"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.tr.request("http://127.0.0.1:1/x", None, timeout, 10)
        for cap in (0, -5, 1.5, True, CrawlerConfig().object_cap_bytes + 1):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.tr.request("http://127.0.0.1:1/x", None, 5, cap)

    def test_body_cap_while_streaming(self):
        resp = FakeHttpResponse(200, {}, b"x" * 1000)
        with mock.patch.object(self.tr._opener, "open", return_value=resp):
            r = self.tr.request("http://127.0.0.1:1/x", None, 5, 300)
            got = bytearray()
            with self.assertRaises(t.BodyTooLargeError):
                for chunk in r.body_iter:
                    got += chunk
        self.assertEqual(len(got), 300)  # exactly the cap, never a byte more
        self.assertTrue(resp.closed)
        self.assertLessEqual(max(resp.read_sizes), 301)
        self.assertLessEqual(resp._buf.tell(), 301)  # did not slurp the rest

    def test_body_exactly_at_cap_is_fine_and_chunks_are_bounded(self):
        size = 3 * t.CHUNK_BYTES + 5
        resp = FakeHttpResponse(200, {}, b"y" * size)
        with mock.patch.object(self.tr._opener, "open", return_value=resp):
            r = self.tr.request("http://127.0.0.1:1/x", None, 5, size)
            chunks = list(r.body_iter)
        self.assertEqual(sum(map(len, chunks)), size)
        self.assertLessEqual(max(map(len, chunks)), t.CHUNK_BYTES)
        self.assertTrue(resp.closed)

    def test_declared_content_length_over_cap_reads_nothing(self):
        resp = FakeHttpResponse(200, {"Content-Length": "5000"}, b"z" * 5000)
        with mock.patch.object(self.tr._opener, "open", return_value=resp):
            r = self.tr.request("http://127.0.0.1:1/x", None, 5, 100)
            self.assertEqual(r.status, 200)
            with self.assertRaises(t.BodyTooLargeError):
                next(r.body_iter)
        self.assertEqual(resp.read_sizes, [])
        self.assertTrue(resp.closed)

    def test_hostile_content_length_never_raises_valueerror(self):
        for value, oversize in (("\u00b2", False), ("9" * 5000, True), ("abc", False), ("-5", False)):
            resp = FakeHttpResponse(200, {"Content-Length": value}, b"ok")
            with mock.patch.object(self.tr._opener, "open", return_value=resp):
                r = self.tr.request("http://127.0.0.1:1/x", None, 5, 100)
                if oversize:
                    with self.assertRaises(t.BodyTooLargeError):
                        next(r.body_iter)
                else:
                    self.assertEqual(b"".join(r.body_iter), b"ok")

    def test_close_without_iterating_closes_the_connection(self):
        resp = FakeHttpResponse(200, {}, b"abc")
        with mock.patch.object(self.tr._opener, "open", return_value=resp):
            self.tr.request("http://127.0.0.1:1/x", None, 5, 100).close()
        self.assertTrue(resp.closed)

    def test_network_errors_become_transport_errors_without_details(self):
        for exc in (urllib.error.URLError("secret-host-detail"), TimeoutError("t"), ConnectionResetError("r")):
            with self.subTest(exc=type(exc).__name__), mock.patch.object(self.tr._opener, "open", side_effect=exc):
                with self.assertRaises(t.TransportError) as cm:
                    self.tr.request("http://127.0.0.1:1/x", None, 5, 100)
                self.assertNotIn("secret-host-detail", str(cm.exception))

    def test_read_error_mid_stream_is_a_transport_error(self):
        resp = FakeHttpResponse(200, {}, b"abc")
        resp.read = mock.Mock(side_effect=ConnectionResetError("boom"))
        with mock.patch.object(self.tr._opener, "open", return_value=resp):
            r = self.tr.request("http://127.0.0.1:1/x", None, 5, 100)
            with self.assertRaises(t.TransportError):
                list(r.body_iter)
        self.assertTrue(resp.closed)

    def test_response_headers_are_lowercased_and_joined(self):
        resp = FakeHttpResponse(200, {"Content-Type": "text/html"}, b"")
        resp.headers["Set-Cookie"] = "a=1"
        resp.headers["Set-Cookie"] = "b=2"
        with mock.patch.object(self.tr._opener, "open", return_value=resp):
            r = self.tr.request("http://127.0.0.1:1/x", None, 5, 100)
        self.assertEqual(r.headers["content-type"], "text/html")
        self.assertEqual(r.headers["set-cookie"], "a=1, b=2")


class FakeTransportTest(unittest.TestCase):
    def test_fake_is_a_transport_and_lives_in_tests_only(self):
        self.assertIsInstance(FakeTransport(), t.Transport)
        self.assertFalse(any("fake" in p.name.lower() for p in (Path(t.__file__).parent).glob("*.py")))
        with self.assertRaises(AssertionError):
            FakeTransport().request("https://x.example/", None, 1, 1)


# ---- static guard ----

CRAWLER = Path(__file__).resolve().parent.parent / "crawler"
FILES = sorted(CRAWLER.glob("*.py"))

FORBIDDEN_NAMES = re.compile(
    r"rotat|spoof|user_?agents?_(list|pool)|ua_(list|pool)|random_?(ua|agent|header)|fake_?(ua|agent)|"
    r"ignore_robots|skip_robots|bypass|circumvent|disable_robots|socks|\btor\b|vpn|set_proxy|proxy_(url|list|pool)|"
    r"captcha|stealth|impersonat", re.IGNORECASE)
BROWSER_HEADERS = {"referer", "cookie", "accept-language", "accept-encoding", "sec-fetch-mode", "sec-fetch-site",
                   "sec-ch-ua", "upgrade-insecure-requests", "x-forwarded-for", "dnt", "origin", "authorization"}
PROXY_ENV = re.compile(r"http_proxy|https_proxy|all_proxy|no_proxy", re.IGNORECASE)


def idents(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id, node
        elif isinstance(node, ast.Attribute):
            yield node.attr, node
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.arg):
            yield node.arg, node
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg, node
        elif isinstance(node, ast.alias):
            yield node.name, node


class StaticTest(unittest.TestCase):
    def test_files_found(self):
        self.assertGreaterEqual({p.name for p in FILES}, {"__init__.py", "config.py", "useragent.py", "robots.py", "transport.py"})

    def test_no_circumvention_identifiers(self):
        for p in FILES:
            for name, node in idents(ast.parse(p.read_text(), str(p))):
                self.assertIsNone(FORBIDDEN_NAMES.search(name), f"{p.name}:{node.lineno} {name}")

    def test_no_randomness_in_ua_or_transport(self):
        for fname in ("useragent.py", "transport.py", "robots.py", "config.py"):
            tree = ast.parse((CRAWLER / fname).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({a.name.split(".")[0] for a in node.names} & {"random", "secrets"}, fname)
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or "").split(".")[0], {"random", "secrets"}, fname)

    def test_only_one_proxy_handler_use_and_it_is_empty(self):
        calls = []
        for p in FILES:
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.Call) and "proxy" in ast.unparse(node.func).lower():
                    calls.append((p.name, ast.unparse(node)))
        self.assertEqual(calls, [("transport.py", "urllib.request.ProxyHandler({})")])

    def test_no_proxy_env_reads_and_no_env_in_robots_or_useragent(self):
        for p in FILES:
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertIsNone(PROXY_ENV.search(node.value), f"{p.name}:{node.lineno}")
        for fname in ("useragent.py", "robots.py", "config.py"):
            self.assertNotIn("environ", (CRAWLER / fname).read_text(), fname)

    def test_no_browser_like_header_literals_or_user_agent_literals(self):
        for p in FILES:
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertNotIn(node.value.strip().lower(), BROWSER_HEADERS, f"{p.name}:{node.lineno}")
                    if p.name != "useragent.py":
                        self.assertNotRegex(node.value, re.compile(r"mozilla|chrome|safari|applewebkit", re.I), p.name)
        # the header whitelist is exactly what the spec allows
        sys.path.insert(0, str(CRAWLER.parent))
        from crawler.transport import ALLOWED_REQUEST_HEADERS
        self.assertEqual(ALLOWED_REQUEST_HEADERS, {"accept", "if-none-match", "if-modified-since"})

    def test_sockets_and_http_clients_only_in_transport(self):
        banned = {"socket", "urllib.request", "http.client", "ssl", "requests", "httpx", "aiohttp", "subprocess",
                  "selenium", "playwright", "boto3", "botocore"}
        for p in FILES:
            if p.name == "transport.py":
                continue
            for node in ast.walk(ast.parse(p.read_text())):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [(node.module or "")] + [f"{node.module}.{a.name}" for a in node.names]
                for m in mods:
                    self.assertNotIn(m, banned, f"{p.name}: imports {m}")

    def test_no_retry_with_changed_headers(self):
        # robots/transport never loop over header variants: the only loop in robots is the bounded redirect loop
        src = (CRAWLER / "robots.py").read_text()
        self.assertEqual(src.count(".request("), 1)
        tsrc = (CRAWLER / "transport.py").read_text()
        self.assertEqual(tsrc.count("self._opener.open("), 1)

    def test_stdlib_only(self):
        std = set(sys.stdlib_module_names)
        for p in FILES:
            for node in ast.walk(ast.parse(p.read_text())):
                if isinstance(node, ast.Import):
                    tops = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    tops = [(node.module or "").split(".")[0]]
                else:
                    continue
                for top in tops:
                    self.assertIn(top, std, f"{p.name}: {top}")


if __name__ == "__main__":
    unittest.main()
