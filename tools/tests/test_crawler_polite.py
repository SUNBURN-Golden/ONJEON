"""crawler core 2 (host limiter, polite fetcher) tests.

No real network, no sleeping, no randomness except the injected rng.
"""
import ast
import re
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import crawler  # noqa: E402
from crawler.config import CrawlerConfig  # noqa: E402
from crawler.hostlimit import HostAtCapError, HostBusyError, HostRateLimiter  # noqa: E402
from crawler.polite import Outcome, PoliteFetcher  # noqa: E402
from crawler.robots import RobotsCache  # noqa: E402
from crawler.transport import Response, Transport, TransportError  # noqa: E402

UA = f"ONJEON-SourceArchiver/{crawler.__version__} (+ops@example.org)"
ROBOTS = "https://a.example/robots.txt"


class FakeClock:
    def __init__(self, now: float = 1_800_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSleeper:
    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.sleeps: List[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock.advance(seconds)


class FakeTransport(Transport):
    """url -> (status, headers, body) | Exception | callable.

    Unscripted URLs raise AssertionError so tests never silently fetch.
    """

    def __init__(self, routes: Optional[Dict[str, object]] = None):
        self.routes = dict(routes or {})
        self.requests: List[Tuple[str, Dict[str, str], float, int]] = []

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
        status, hdrs, body = route
        return Response(status, hdrs, iter([body] if body is not None else []))

    @property
    def urls(self) -> List[str]:
        return [r[0] for r in self.requests]


def make_fetcher(routes, config=None, clock=None, sleep=None, rng=lambda: 0.0):
    cfg = config or CrawlerConfig(contact="ops@example.org")
    clock = clock or FakeClock()
    sleep = sleep or FakeSleeper(clock)
    transport = FakeTransport(routes)
    robots = RobotsCache(transport, UA, clock=clock, timeout_s=20.0)
    limiter = HostRateLimiter(cfg, clock=clock, sleep=sleep)
    fetcher = PoliteFetcher(transport, robots, limiter, cfg, clock=clock, sleep=sleep, rng=rng)
    return fetcher, transport, clock, sleep


class HostRateLimiterTest(unittest.TestCase):
    def test_min_interval_enforced(self):
        clock = FakeClock(1000.0)
        sleep = FakeSleeper(clock)
        cfg = CrawlerConfig(contact="ops@example.org", per_host_min_interval_s=5)
        lim = HostRateLimiter(cfg, clock=clock, sleep=sleep)
        lim.acquire("a.example")
        lim.release("a.example")
        lim.acquire("a.example")
        self.assertEqual(sleep.sleeps, [5.0])

    def test_robots_delay_override(self):
        clock = FakeClock(1000.0)
        sleep = FakeSleeper(clock)
        cfg = CrawlerConfig(contact="ops@example.org", per_host_min_interval_s=1)
        lim = HostRateLimiter(cfg, clock=clock, sleep=sleep)
        lim.acquire("a.example", robots_delay=10.0)
        lim.release("a.example")
        lim.acquire("a.example", robots_delay=10.0)
        self.assertEqual(sleep.sleeps, [10.0])

    def test_concurrency_one_per_host(self):
        cfg = CrawlerConfig(contact="ops@example.org")
        lim = HostRateLimiter(cfg)
        lim.acquire("a.example")
        with self.assertRaises(HostBusyError):
            lim.acquire("a.example")
        lim.release("a.example")

    def test_global_host_cap(self):
        cfg = CrawlerConfig(contact="ops@example.org", max_global_hosts=2)
        lim = HostRateLimiter(cfg)
        lim.acquire("a.example")
        lim.acquire("b.example")
        with self.assertRaises(HostAtCapError) as cm:
            lim.acquire("c.example")
        self.assertEqual(cm.exception.cap, 2)
        lim.release("a.example")
        lim.acquire("c.example")

    def test_hosts_of_different_sources_share_the_cap(self):
        cfg = CrawlerConfig(contact="ops@example.org", max_global_hosts=2)
        lim = HostRateLimiter(cfg)
        lim.acquire("src1.example")
        lim.acquire("src2.example")
        with self.assertRaises(HostAtCapError):
            lim.acquire("src3.example")


class PoliteFetcherSuccessTest(unittest.TestCase):
    def test_success_returns_body_and_one_attempt(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (200, {}, b"hello"),
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "success")
        self.assertEqual(out.reason, "reachable")
        self.assertEqual(out.attempts, 1)
        self.assertEqual(out.status, 200)
        self.assertEqual(b"".join(out.body_iter), b"hello")
        self.assertEqual(t.urls, [ROBOTS, "https://a.example/page"])

    def test_robots_disallow_returns_blocked_without_fetch(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow: /private/\n"),
        })
        out = f.fetch("https://a.example/private/x", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "origin_denied")
        self.assertEqual(t.urls, [ROBOTS])

    def test_min_interval_enforced_between_two_fetches(self):
        clock = FakeClock(1000.0)
        sleep = FakeSleeper(clock)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (200, {}, b"ok"),
        }, config=CrawlerConfig(contact="ops@example.org", per_host_min_interval_s=5), clock=clock, sleep=sleep)
        f.fetch("https://a.example/page", "src1")
        f.fetch("https://a.example/page", "src1")
        self.assertEqual(sleep.sleeps, [5.0])
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 2)


class PoliteFetcherRetryTest(unittest.TestCase):
    def test_500_is_retried_three_times_then_blocked(self):
        f, t, _, sleep = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (500, {}, b"boom"),
        }, config=CrawlerConfig(contact="ops@example.org", max_attempts=3, per_host_min_interval_s=1))
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "service_outage")
        self.assertEqual(out.attempts, 3)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 3)
        self.assertEqual(sleep.sleeps, [2.0, 4.0])

    def test_timeout_is_retried_with_jitter(self):
        rng_values = [0.5, 0.25]
        f, t, _, sleep = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": TransportError("request failed: TimeoutError"),
        }, config=CrawlerConfig(contact="ops@example.org", max_attempts=3, per_host_min_interval_s=1), rng=lambda: rng_values.pop(0))
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "timeout")
        self.assertEqual(out.reason, "timeout")
        self.assertEqual(out.attempts, 3)
        self.assertEqual(sleep.sleeps, [2.5, 4.25])

    def test_headers_are_identical_across_retries(self):
        headers = {"If-None-Match": '"abc"'}
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (500, {}, b"x"),
        }, config=CrawlerConfig(contact="ops@example.org", max_attempts=3))
        out = f.fetch("https://a.example/page", "src1", headers=headers)
        self.assertEqual(out.attempts, 3)
        for _, h, _, _ in t.requests:
            if h:
                self.assertEqual(h.get("If-None-Match"), '"abc"')


class PoliteFetcherStopTest(unittest.TestCase):
    def test_403_stops_immediately_no_retry(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (403, {}, b"forbidden"),
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "origin_denied")
        self.assertEqual(out.attempts, 1)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 1)

    def test_captcha_marker_in_200_body_stops_immediately(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (200, {"Content-Type": "text/html"}, b"<div>recaptcha required</div>"),
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "origin_denied")
        self.assertEqual(out.attempts, 1)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 1)

    def test_redirect_to_other_host_is_not_followed(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (302, {"Location": "https://b.example/page"}, b""),
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "redirect")
        self.assertEqual(out.reason, "redirect_loop")
        self.assertEqual(out.attempts, 1)
        self.assertEqual([u for u in t.urls if u != ROBOTS], ["https://a.example/page"])


class PoliteFetcherRateLimitTest(unittest.TestCase):
    def test_429_honours_retry_after_seconds(self):
        clock = FakeClock(1_800_000_000.0)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (429, {"Retry-After": "120"}, b""),
        }, clock=clock)
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "rate_limited")
        self.assertEqual(out.reason, "rate_limited")
        self.assertEqual(out.retry_after, clock.now + 120)
        self.assertEqual(out.blocked_until, clock.now + 120)

    def test_second_429_same_day_stops_host_for_the_day(self):
        clock = FakeClock(1_800_000_000.0)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (429, {"Retry-After": "0"}, b""),
        }, clock=clock)
        first = f.fetch("https://a.example/page", "src1")
        self.assertEqual(first.retry_after, clock.now)
        clock.advance(1)  # past the first Retry-After
        second = f.fetch("https://a.example/page", "src1")
        self.assertEqual(second.kind, "rate_limited")
        self.assertEqual(second.blocked_until, (int(clock.now // 86400) + 1) * 86400)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 2)


class PoliteFetcherCapTest(unittest.TestCase):
    def test_daily_cap_reached_returns_deferred_cap(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (200, {}, b"ok"),
        }, config=CrawlerConfig(contact="ops@example.org", daily_request_cap_default=2, max_attempts=1))
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "success")
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "success")
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "deferred_cap")
        self.assertEqual(out.reason, "deferred_cap")
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 2)

    def test_daily_cap_resets_next_day(self):
        clock = FakeClock(1_800_000_000.0)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (200, {}, b"ok"),
        }, config=CrawlerConfig(contact="ops@example.org", daily_request_cap_default=1, max_attempts=1), clock=clock)
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "success")
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "deferred_cap")
        clock.advance(86400)
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "success")


class StaticPoliteTest(unittest.TestCase):
    def test_no_proxy_vpn_rotation_spoof_tokens_in_fetch_code(self):
        crawler_dir = Path(__file__).resolve().parent.parent / "crawler"
        files = sorted(crawler_dir.glob("*.py"))
        text = "\n".join(p.read_text() for p in files)
        # ProxyHandler is allowed only as the explicit empty handler in transport.py.
        for m in re.finditer(r"ProxyHandler", text):
            start = max(0, m.start() - 30)
            snippet = text[start:m.end() + 1]
            self.assertEqual(snippet, "urllib.request.ProxyHandler({})", f"unexpected ProxyHandler at {m.start()}")
        self.assertNotIn("X-Forwarded", text)
        self.assertNotIn("user_agents", text.lower())
        self.assertFalse(re.search(r"random\.choice\s*\([^)]*[Uu]ser[-_]?[Aa]gent", text, re.DOTALL))
        # Mozilla only in useragent.py (the honest filter).
        for p in files:
            if p.name == "useragent.py":
                continue
            self.assertNotIn("Mozilla", p.read_text(), p.name)


if __name__ == "__main__":
    unittest.main()
