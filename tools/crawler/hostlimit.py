"""Per-host rate limiter for the polite crawler.

Enforces:
- concurrency 1 per host (only one in-flight request per host);
- a minimum interval between requests to the same host of
  max(config.per_host_min_interval_s, robots Crawl-delay);
- a global cap on the number of distinct hosts with an active reservation.

Time and sleep are injected so tests are deterministic and instant.
Hosts of different sources share the same limiter budget.
"""
import threading
import time
from typing import Callable, Optional

from .config import CrawlerConfig


class HostRateLimiterError(Exception):
    pass


class HostBusyError(HostRateLimiterError):
    """The requested host already has an active reservation."""

    pass


class HostAtCapError(HostRateLimiterError):
    """The global distinct-host cap has been reached."""

    def __init__(self, cap: int):
        self.cap = cap
        super().__init__(f"global host cap ({cap}) reached")


class HostRateLimiter:
    def __init__(
        self,
        config: CrawlerConfig,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._min_interval = float(config.per_host_min_interval_s)
        self._max_hosts = int(config.max_global_hosts)
        self._clock = clock if clock is not None else time.time
        self._sleep = sleep if sleep is not None else time.sleep
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._last: dict[str, float] = {}

    def acquire(self, host: str, robots_delay: Optional[float] = None) -> None:
        host = host.lower().strip()
        if not host:
            raise HostRateLimiterError("empty host")
        interval = max(self._min_interval, float(robots_delay) if robots_delay is not None else 0.0)
        while True:
            with self._lock:
                now = self._clock()
                if host in self._active:
                    raise HostBusyError(host)
                if host not in self._active and len(self._active) >= self._max_hosts:
                    raise HostAtCapError(self._max_hosts)
                wait = max(0.0, (self._last.get(host, 0.0) + interval) - now)
                if wait <= 0.0:
                    self._active.add(host)
                    self._last[host] = now
                    return
            self._sleep(wait)

    def release(self, host: str) -> None:
        host = host.lower().strip()
        with self._lock:
            self._active.discard(host)
            self._last[host] = self._clock()
