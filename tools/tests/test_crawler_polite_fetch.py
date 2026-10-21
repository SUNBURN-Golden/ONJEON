"""crawler core 2 (host limiter, polite fetcher) tests.

No real network, no sleeping, no randomness except the injected rng.
"""
import email.utils
import re
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import crawler  # noqa: E402
from crawler.config import ConfigError, CrawlerConfig, config_from_dict  # noqa: E402
from crawler.hostlimit import HostAtCapError, HostBusyError, HostRateLimiter  # noqa: E402
from crawler.polite import BODY_PREFIX_BYTES, Outcome, PoliteFetcher  # noqa: E402
from crawler.robots import RobotsCache  # noqa: E402
from crawler.transport import (BodyTooLargeError, RefusedRequestError, Response,  # noqa: E402
                               Transport, TransportError)

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

    def test_robots_delay_below_config_min_uses_config(self):
        clock = FakeClock(1000.0)
        sleep = FakeSleeper(clock)
        cfg = CrawlerConfig(contact="ops@example.org", per_host_min_interval_s=5)
        lim = HostRateLimiter(cfg, clock=clock, sleep=sleep)
        lim.acquire("a.example", robots_delay=2.0)
        lim.release("a.example")
        lim.acquire("a.example", robots_delay=2.0)
        self.assertEqual(sleep.sleeps, [5.0])

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

    def test_empty_2xx_body_is_empty_reply(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (200, {}, b""),
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "empty_reply")
        self.assertEqual(out.attempts, 1)


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
        headers = {"If-None-Match": '"abc"', "Accept": "text/plain"}
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (500, {}, b"x"),
        }, config=CrawlerConfig(contact="ops@example.org", max_attempts=3))
        out = f.fetch("https://a.example/page", "src1", headers=headers)
        self.assertEqual(out.attempts, 3)
        page_headers = [h for url, h, _, _ in t.requests if url == "https://a.example/page"]
        self.assertEqual(page_headers, [dict(headers)] * 3)
        # the robots.txt sub-request saw the same caller headers too (Accept stays text/plain)
        self.assertEqual(t.requests[0][1]["If-None-Match"], '"abc"')

    def test_more_than_three_attempts_cannot_be_configured(self):
        # The spec's hard cap is 3 attempts per request; config validation enforces it so
        # no PoliteFetcher can ever be built with more.
        for n in (4, 5, 100):
            with self.subTest(max_attempts=n), self.assertRaises(ConfigError):
                config_from_dict({"max_attempts": n})
            with self.subTest(max_attempts=n), self.assertRaises(ConfigError):
                CrawlerConfig(contact="ops@example.org", max_attempts=n)


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

    def test_401_stops_immediately_no_retry(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (401, {}, b"unauthorized"),
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

    def test_geo_block_marker_in_200_body_stops_immediately(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (200, {"Content-Type": "text/html"},
                                     b"<p>this video is not available in your region</p>"),
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "geo_blocked")
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

    def test_redirect_to_same_host_is_not_followed_either(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (301, {"Location": "https://a.example/other"}, b""),
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "redirect")
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

    def test_429_honours_retry_after_http_date(self):
        clock = FakeClock(1_800_000_000.0)
        http_date = email.utils.formatdate(clock.now + 600, usegmt=True)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (429, {"Retry-After": http_date}, b""),
        }, clock=clock)
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "rate_limited")
        self.assertEqual(out.retry_after, clock.now + 600)
        self.assertEqual(out.blocked_until, clock.now + 600)

    def test_no_request_to_host_before_retry_after(self):
        clock = FakeClock(1_800_000_000.0)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (429, {"Retry-After": "120"}, b""),
        }, clock=clock)
        f.fetch("https://a.example/page", "src1")
        clock.advance(60)  # still inside the Retry-After window
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "rate_limited")
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 1)

    def test_503_with_retry_after_is_rate_limited(self):
        clock = FakeClock(1_800_000_000.0)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": (503, {"Retry-After": "30"}, b""),
        }, clock=clock)
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "rate_limited")
        self.assertEqual(out.blocked_until, clock.now + 30)

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

    def test_second_429_still_honours_a_retry_after_past_midnight(self):
        # 1_800_000_000 is 08:00 UTC; the day ends at 1_800_057_600. A second 429 carrying
        # Retry-After 60000 lands ~00:41 the next day: the day-stop must extend, not shrink.
        clock = FakeClock(1_800_000_000.0)
        responses = iter([
            (429, {"Retry-After": "0"}, b""),
            (429, {"Retry-After": "60000"}, b""),
        ])
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": lambda url: next(responses),
        }, clock=clock)
        f.fetch("https://a.example/page", "src1")
        clock.advance(60)
        second = f.fetch("https://a.example/page", "src1")
        expected = clock.now + 60000
        day_end = (int(clock.now // 86400) + 1) * 86400
        self.assertGreater(expected, day_end)
        self.assertEqual(second.blocked_until, expected)
        self.assertEqual(second.retry_after, expected)
        clock.now = day_end + 1  # past midnight, still inside the Retry-After window
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "rate_limited")
        self.assertEqual(out.blocked_until, expected)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 2)


class PoliteFetcherBodyStreamTest(unittest.TestCase):
    """A body stream that dies inside the marker-scan prefix must never become a silent
    truncated success; past the prefix the failure reaches the body consumer instead."""

    @staticmethod
    def _route_with_failing_body(error):
        """A fresh 200 Response per request: one chunk, then the stream dies."""
        def route(url):
            def body():
                yield b"x" * 100
                raise error
            return Response(200, {}, body())
        return route

    def test_mid_prefix_transport_error_is_retried_then_typed_failure(self):
        f, t, _, sleep = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": self._route_with_failing_body(
                TransportError("read failed: ConnectionResetError")),
        }, config=CrawlerConfig(contact="ops@example.org", max_attempts=3, per_host_min_interval_s=1))
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "connection_reset")
        self.assertEqual(out.reason, "connection_reset")
        self.assertEqual(out.attempts, 3)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 3)
        self.assertEqual(sleep.sleeps, [2.0, 4.0])

    def test_mid_prefix_timeout_is_retried_then_timeout(self):
        f, t, _, sleep = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": self._route_with_failing_body(
                TransportError("read failed: TimeoutError")),
        }, config=CrawlerConfig(contact="ops@example.org", max_attempts=2, per_host_min_interval_s=1))
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "timeout")
        self.assertEqual(out.reason, "timeout")
        self.assertEqual(out.attempts, 2)
        self.assertEqual(sleep.sleeps, [2.0])

    def test_mid_prefix_body_too_large_is_blocked_without_retry(self):
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": self._route_with_failing_body(
                BodyTooLargeError("body exceeds the cap")),
        }, config=CrawlerConfig(contact="ops@example.org", max_attempts=3, per_host_min_interval_s=1))
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "empty_reply")
        self.assertEqual(out.attempts, 1)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 1)

    def test_failure_past_the_prefix_reaches_the_body_consumer(self):
        def route(url):
            def body():
                yield b"y" * (BODY_PREFIX_BYTES + 10)
                yield b"tail"
                raise TransportError("read failed: ConnectionResetError")
            return Response(200, {}, body())
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": route,
        }, config=CrawlerConfig(contact="ops@example.org", per_host_min_interval_s=1))
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "success")
        got = bytearray()
        with self.assertRaises(TransportError):
            for chunk in out.body_iter:
                got += chunk
        self.assertEqual(got, b"y" * (BODY_PREFIX_BYTES + 10) + b"tail")

    def test_403_with_dying_body_still_stops_immediately(self):
        def route(url):
            def body():
                yield b"den"
                raise TransportError("read failed: ConnectionResetError")
            return Response(403, {}, body())
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": route,
        })
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual(out.kind, "blocked")
        self.assertEqual(out.reason, "origin_denied")
        self.assertEqual(out.attempts, 1)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 1)


class PoliteFetcherLocalRefusalTest(unittest.TestCase):
    """Errors raised by transport.request before anything reaches the wire must not leak the
    host reservation or spend daily budget."""

    def test_non_transport_error_frees_host_and_refunds_budget(self):
        cfg = CrawlerConfig(contact="ops@example.org", daily_request_cap_default=1,
                            max_attempts=1, per_host_min_interval_s=1)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": ValueError("header not allowed: X-Test"),
        }, config=cfg)
        with self.assertRaises(ValueError):
            f.fetch("https://a.example/page", "src1")
        t.routes["https://a.example/page"] = (200, {}, b"ok")
        # host reservation was released and the failed call did not spend the cap
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "success")
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "deferred_cap")

    def test_refused_request_is_a_typed_block_once_and_not_billed(self):
        cfg = CrawlerConfig(contact="ops@example.org", daily_request_cap_default=1,
                            max_attempts=3, per_host_min_interval_s=1)
        f, t, _, _ = make_fetcher({
            ROBOTS: (200, {}, b"User-agent: *\nDisallow:\n"),
            "https://a.example/page": RefusedRequestError("URLs with credentials are refused"),
        }, config=cfg)
        out = f.fetch("https://a.example/page", "src1")
        self.assertEqual((out.kind, out.reason), ("blocked", "not_checked"))
        self.assertEqual(out.attempts, 1)
        self.assertEqual(len([u for u in t.urls if u == "https://a.example/page"]), 1)
        t.routes["https://a.example/page"] = (200, {}, b"ok")
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "success")  # refunded
        self.assertEqual(f.fetch("https://a.example/page", "src1").kind, "deferred_cap")


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
        self.assertEqual(out.reason, "rate_limited")
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
        files = sorted(crawler_dir.rglob("*.py"))
        self.assertTrue(files)
        text = "\n".join(p.read_text() for p in files)
        # ProxyHandler is allowed only as the explicit empty handler in transport.py.
        for m in re.finditer(r"ProxyHandler", text):
            self.assertEqual(text[max(0, m.start() - 15):m.start()], "urllib.request.",
                             f"unexpected ProxyHandler at {m.start()}")
            self.assertEqual(text[m.end():m.end() + 4], "({})",
                             f"unexpected ProxyHandler at {m.start()}")
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
