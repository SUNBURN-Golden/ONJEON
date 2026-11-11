"""Offline scheduler: pure plans, explicit attempt/success recording, JSON state.

Each due allowed source has one queue entry (a registry URL); overdue periods
coalesce instead of accumulating an unbounded backlog. plan() returns these
derived queues without consuming them. runnable is an earliest-due dispatch
batch, one source per available host, within the limiter's global capacity.
Ties use source_id, independent of CSV order. The runner must replan/acquire
before dispatch; a plan itself reserves nothing and never enables collection.

A/B periods are 1/7 elapsed days. C is one UTC calendar month after the last
attempt, clamped to the month's last day. D is one attempted backfill, including
a failed attempt (fetch-level retries belong to the fetcher). A failure never
advances last_success. Source min_interval_s is an additional lower bound.
Daily caps count dispatch attempts in UTC days; wire request/retry caps remain
the fetcher's responsibility. Persisted next_due is authoritative (including
pending work); restore reapplies source minimum intervals and D consumption.
The caller persists to_dict() using its own I/O.
"""
import calendar
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from .config import CrawlerConfig
from .hostlimit import HostRateLimiter
from .registry import Source

DAY_S = 86400


def _timestamp(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError("time must be a finite nonnegative Unix timestamp")
    return float(value)


def _next_due(source, attempted_at):
    if source.tier == "D":
        return None
    if source.tier == "C":
        date = datetime.fromtimestamp(attempted_at, timezone.utc)
        year, month = (date.year + 1, 1) if date.month == 12 else (date.year, date.month + 1)
        due = date.replace(year=year, month=month,
                           day=min(date.day, calendar.monthrange(year, month)[1])).timestamp()
    else:
        due = attempted_at + DAY_S * (1 if source.tier == "A" else 7)
    return max(due, attempted_at + source.min_interval_s)


@dataclass(frozen=True)
class SourceState:
    next_due: float | None = 0.0
    last_attempt: float | None = None
    last_success: float | None = None
    attempt_day: int | None = None  # UTC day index, bounded accounting state
    attempts_today: int = 0

    def __post_init__(self):
        for value in (self.next_due, self.last_attempt, self.last_success):
            if value is not None:
                _timestamp(value)
        if (isinstance(self.attempts_today, bool) or not isinstance(self.attempts_today, int)
                or self.attempts_today < 0):
            raise ValueError("attempts_today must be a nonnegative integer")
        if self.attempt_day is not None and (isinstance(self.attempt_day, bool)
                or not isinstance(self.attempt_day, int) or self.attempt_day < 0):
            raise ValueError("attempt_day must be a nonnegative integer or null")
        if self.last_attempt is None:
            if self.last_success is not None or self.attempt_day is not None or self.attempts_today:
                raise ValueError("attempt accounting requires last_attempt")
        elif self.attempt_day != int(self.last_attempt // DAY_S) or self.attempts_today < 1:
            raise ValueError("inconsistent attempt accounting")


class Scheduler:
    def __init__(self, sources: Iterable[Source], *, config: CrawlerConfig | None = None,
                 limiter: HostRateLimiter | None = None,
                 clock: Callable[[], float] = time.time, state: dict | None = None):
        self._sources = {}
        for source in sources:
            if source.source_id in self._sources:
                raise ValueError("duplicate source_id")
            self._sources[source.source_id] = source
        self._config = config if config is not None else CrawlerConfig()
        self._limiter = limiter
        self._clock = clock
        self._states = {sid: SourceState() for sid in self._sources}
        if state is not None:
            if (set(state) != {"version", "sources"} or type(state["version"]) is not int
                    or state["version"] != 1 or not isinstance(state["sources"], dict)):
                raise ValueError("unsupported scheduler state")
            if state["sources"].keys() - self._sources.keys():
                raise ValueError("state contains unknown source_id")
            for sid, fields in state["sources"].items():
                self._states[sid] = SourceState(**fields)
            # Restore pending work without shortening the source's minimum interval.
            for sid, current in self._states.items():
                if current.last_attempt is not None:
                    source = self._sources[sid]
                    due = (None if source.tier == "D" or current.next_due is None else max(
                        current.next_due, current.last_attempt + source.min_interval_s))
                    self._states[sid] = SourceState(**{**asdict(current), "next_due": due})

    def _now(self, now):
        return _timestamp(self._clock() if now is None else now)

    def _cap(self, source):
        return (source.daily_cap if source.daily_cap is not None
                else self._config.daily_request_cap_default)

    @staticmethod
    def _count(current, now):
        return current.attempts_today if current.attempt_day == int(now // DAY_S) else 0

    def plan(self, now: float | None = None) -> dict:
        """Return detached JSON-compatible queues and a runnable dispatch batch.

        skipped_terms lists every disallowed source, even when it is not due.
        Due entries blocked by cap/host remain queued. No I/O, sleeps, state
        mutation, adapter execution, host reservation or attempt counting occurs.
        """
        now = self._now(now)
        availability = (self._limiter.snapshot(now) if self._limiter is not None else {
            "max_global_hosts": self._config.max_global_hosts, "active_hosts": [],
            "next_available": {}, "default_available_at": 0.0,
        })
        occupied = set(availability["active_hosts"])
        slots = max(0, availability["max_global_hosts"] - len(occupied))
        result = {"now": now, "queues": {}, "runnable": [], "skipped_terms": [],
                  "deferred_cap": [], "deferred_host": []}
        due = []
        for sid, source in sorted(self._sources.items()):
            current = self._states[sid]
            if source.terms_status != "allowed":
                result["skipped_terms"].append({"source_id": sid,
                                                "terms_status": source.terms_status})
            elif current.next_due is not None and current.next_due <= now:
                due.append((current.next_due, sid))
        for next_due, sid in sorted(due):
            source = self._sources[sid]
            entry = {"source_id": sid, "url": source.url, "host": source.host,
                     "adapter": source.adapter, "next_due": next_due}
            result["queues"][sid] = [entry.copy()]
            if self._count(self._states[sid], now) >= self._cap(source):
                result["deferred_cap"].append({"source_id": sid,
                                               "next_available": (int(now // DAY_S) + 1) * DAY_S})
                continue
            available_at = availability["next_available"].get(
                source.host, availability["default_available_at"])
            if source.host in occupied or slots == 0 or available_at > now:
                result["deferred_host"].append({"source_id": sid})
                continue
            result["runnable"].append(entry)
            occupied.add(source.host)
            slots -= 1
        return result

    def record_attempt(self, source_id: str, now: float | None = None) -> None:
        """Consume the source's due entry after the runner acquires its host.

        Guard terms/due/cap again. Host reservations belong to the runner, so this
        does not call acquire(). Use record_success only after a successful result.
        """
        now = self._now(now)
        source, current = self._sources[source_id], self._states[source_id]
        if source.terms_status != "allowed":
            raise ValueError("source terms do not allow scheduling")
        if current.next_due is None or current.next_due > now:
            raise ValueError("source is not due")
        if current.last_success is not None and now < current.last_success:
            raise ValueError("attempt time precedes last_success")
        count = self._count(current, now)
        if count >= self._cap(source):
            raise ValueError("source daily cap reached")
        self._states[source_id] = SourceState(
            next_due=_next_due(source, now), last_attempt=now,
            last_success=current.last_success, attempt_day=int(now // DAY_S),
            attempts_today=count + 1,
        )

    def record_success(self, source_id: str, now: float | None = None) -> None:
        """Record successful completion time; completion never shifts next_due."""
        now = self._now(now)
        current = self._states[source_id]
        if (current.last_attempt is None or now < current.last_attempt
                or (current.last_success is not None and now < current.last_success)):
            raise ValueError("success must follow the latest recorded attempt/success")
        self._states[source_id] = SourceState(**{**asdict(current), "last_success": now})

    def to_dict(self) -> dict:
        """Return detached state; json.dumps(..., allow_nan=False) is sufficient."""
        return {"version": 1, "sources": {
            sid: asdict(current) for sid, current in sorted(self._states.items())
        }}
