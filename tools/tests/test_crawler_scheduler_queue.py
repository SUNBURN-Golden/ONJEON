"""CRAWL-03 offline acceptance; every synthetic source has origin=fixture.

No real registry rows, fetching, sleeps, environment reads or external writes.
"""
import ast
import csv
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crawler.config import CrawlerConfig
from crawler.hostlimit import HostBusyError, HostRateLimiter
from crawler.registry import RegistryError, Source, load_registry
from crawler.scheduler import DAY_S, Scheduler

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures/crawler/scheduler_sources.csv"


def epoch(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


class FakeClock:
    def __init__(self, now=epoch("2026-01-31T12:00:00")):
        self.now = now

    def __call__(self):
        return self.now


def source(sid="a", host=None, **fields):
    """origin=fixture; .example addresses are never requested."""
    return Source(sid, f"https://{host or sid + '.example'}/listing",
                  **{"terms_status": "allowed", "tier": "A", **fields})


def ids(plan, key="runnable"):
    return [entry["source_id"] for entry in plan[key]]


def seeded_state(sid, attempted_at, next_due, count=1, last_success=None):
    return {"version": 1, "sources": {sid: {
        "next_due": next_due, "last_attempt": attempted_at,
        "last_success": last_success, "attempt_day": int(attempted_at // DAY_S),
        "attempts_today": count,
    }}}


class OfflineCase(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "socket.getaddrinfo",
                       "time.sleep"):
            patcher = mock.patch(target, side_effect=AssertionError("offline test"))
            patcher.start()
            self.addCleanup(patcher.stop)


class RegistryTest(OfflineCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.csv"
            path.write_text(text, encoding="utf-8")
            before = path.read_bytes()
            real_open = Path.open
            modes = []

            def read_only(p, mode="r", *args, **kwargs):
                modes.append(mode)
                self.assertEqual(mode, "r")
                return real_open(p, mode, *args, **kwargs)

            with mock.patch.object(Path, "open", read_only):
                result = load_registry(path)
            self.assertEqual(modes, ["r"])
            self.assertEqual(before, path.read_bytes())
            return result

    def test_real_header_with_only_synthetic_rows_is_read_only(self):
        # Copy just the real header; do not load any real registry rows.
        with (ROOT / "data/registry/sources.csv").open(encoding="utf-8") as stream:
            header = stream.readline()
        columns = next(csv.reader([header]))
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        writer.writerow({"source_id": "fixture-a", "url": "https://a.example/",
                         "notes": "origin=fixture"})
        rows = self.load_text(buffer.getvalue())
        self.assertEqual(rows, [Source("fixture-a", "https://a.example/")])
        self.assertEqual(Scheduler(rows).plan(0)["runnable"], [])

    def test_optional_fields_and_empty_defaults(self):
        rows = load_registry(FIXTURE)
        self.assertEqual(rows[0], Source("daily", "https://a.example/disclosures", "allowed",
                                         "A", 5, "listing", 2))
        self.assertEqual(rows[2].daily_cap, None)
        self.assertEqual(rows[-1].terms_status, "unknown")
        self.assertEqual(self.load_text("source_id,url,notes\nf,https://f.example/,origin=fixture\n")[0].tier,
                         "C")

    def test_bom_crlf_quoted_extras_and_whitespace(self):
        rows = self.load_text('\ufeffsource_id,url,terms_status,tier,notes\r\n'
                              ' f ,https://F.Example/path, allowed , B ,"origin=fixture, synthetic"\r\n')
        self.assertEqual(rows[0].host, "f.example")
        self.assertEqual(rows[0].source_id, "f")
        self.assertEqual(rows[0].tier, "B")

    def test_empty_registry_with_valid_header(self):
        self.assertEqual(self.load_text("source_id,url\n"), [])

    def test_invalid_csv_and_policy_fail_closed(self):
        bad = ["", "source_id\nf\n", "source_id,url,url\nf,x,x\n",
               "source_id,url\nf,https://f.example/,extra\n",
               "source_id,url\nf,https://f.example/\nf,https://g.example/\n",
               "source_id,url\nf\n", "source_id,url\n,https://f.example/\n"]
        for field, value in (("terms_status", "yes"), ("terms_status", "Allowed"),
                             ("tier", "E"), ("min_interval_s", "nan"),
                             ("min_interval_s", "inf"), ("min_interval_s", "-1"),
                             ("daily_cap", "1.5"), ("daily_cap", "-1")):
            bad.append(f"source_id,url,{field},notes\nf,https://f.example/,{value},origin=fixture\n")
        for text in bad:
            with self.subTest(text=text), self.assertRaises(RegistryError):
                self.load_text(text)

    def test_source_validation_and_host_normalization(self):
        for url in ("relative", "file:///tmp/fixture", "https:///no-host", "https://[bad/",
                    "https://a.example:bad/", "https://u:p@a.example/"):
            with self.subTest(url=url), self.assertRaises(RegistryError):
                Source("fixture", url)
        for fields in ({"daily_cap": True}, {"daily_cap": -1}, {"daily_cap": 1.5},
                       {"min_interval_s": True}, {"min_interval_s": float("nan")},
                       {"adapter": 2}):
            with self.subTest(fields=fields), self.assertRaises(RegistryError):
                source(**fields)
        self.assertEqual(Source("fixture", "https://A.Example:8443/").host, "a.example")


class SchedulerTest(OfflineCase):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock()

    def test_terms_gate_applies_to_all_tiers_and_attempt_recording(self):
        sources = [source(tier + status, tier=tier, terms_status=status)
                   for tier in "ABCD" for status in ("unknown", "restricted")]
        sources += [Source("missing", "https://missing.example/"), source("allowed")]
        scheduler = Scheduler(sources, clock=self.clock)
        plan = scheduler.plan()
        self.assertEqual(ids(plan), ["allowed"])
        self.assertEqual(set(plan["queues"]), {"allowed"})
        self.assertEqual(set(ids(plan, "skipped_terms")), {s.source_id for s in sources[:-1]})
        for item in sources[:-1]:
            with self.assertRaisesRegex(ValueError, "terms"):
                scheduler.record_attempt(item.source_id)

    def test_daily_weekly_and_monthly_boundaries_with_injected_clock(self):
        for tier, expected in (("A", self.clock.now + DAY_S),
                               ("B", self.clock.now + 7 * DAY_S),
                               ("C", epoch("2026-02-28T12:00:00"))):
            with self.subTest(tier=tier):
                scheduler = Scheduler([source(tier=tier)], clock=self.clock)
                self.assertEqual(ids(scheduler.plan()), ["a"])
                scheduler.record_attempt("a")
                self.assertEqual(scheduler.to_dict()["sources"]["a"]["next_due"], expected)
                self.assertEqual(ids(scheduler.plan(expected - 0.001)), [])
                self.assertEqual(ids(scheduler.plan(expected)), ["a"])

    def test_monthly_leap_day_and_year_rollover(self):
        for start, end in (("2024-01-31", "2024-02-29"), ("2026-12-31", "2027-01-31"),
                           ("2026-03-31", "2026-04-30")):
            scheduler = Scheduler([source(tier="C")])
            scheduler.record_attempt("a", epoch(start))
            self.assertEqual(scheduler.to_dict()["sources"]["a"]["next_due"], epoch(end))

    def test_one_off_is_consumed_even_on_failure_and_survives_restart(self):
        for successful in (False, True):
            with self.subTest(successful=successful):
                sources = [source(tier="D")]
                scheduler = Scheduler(sources, clock=self.clock)
                self.assertEqual(ids(scheduler.plan()), ["a"])
                scheduler.record_attempt("a")
                if successful:
                    scheduler.record_success("a", self.clock.now + 3)
                self.assertEqual(scheduler.to_dict()["sources"]["a"]["next_due"], None)
                restored = Scheduler(sources, state=json.loads(json.dumps(scheduler.to_dict())))
                self.assertEqual(ids(restored.plan(self.clock.now + 1000 * DAY_S)), [])
                with self.assertRaisesRegex(ValueError, "not due"):
                    restored.record_attempt("a", self.clock.now + DAY_S)

    def test_attempt_success_and_failure_are_separate(self):
        scheduler = Scheduler([source()], clock=self.clock)
        with self.assertRaises(ValueError):
            scheduler.record_success("a")
        scheduler.record_attempt("a")
        first = scheduler.to_dict()["sources"]["a"]
        self.assertEqual(first["last_attempt"], self.clock.now)
        self.assertIsNone(first["last_success"])
        scheduler.record_success("a", self.clock.now + 10)
        completed = scheduler.to_dict()["sources"]["a"]
        self.assertEqual(completed["last_success"], self.clock.now + 10)
        self.assertEqual(completed["next_due"], first["next_due"])
        self.clock.now += DAY_S
        scheduler.record_attempt("a")  # failed: no record_success
        self.assertEqual(scheduler.to_dict()["sources"]["a"]["last_success"], completed["last_success"])
        with self.assertRaises(ValueError):
            scheduler.record_success("a", completed["last_success"])

    def test_source_interval_can_extend_tier_period(self):
        scheduler = Scheduler([source(min_interval_s=2 * DAY_S)], clock=self.clock)
        scheduler.record_attempt("a")
        self.assertEqual(ids(scheduler.plan(self.clock.now + DAY_S)), [])
        self.assertEqual(ids(scheduler.plan(self.clock.now + 2 * DAY_S)), ["a"])
        with self.assertRaisesRegex(ValueError, "not due"):
            scheduler.record_attempt("a", self.clock.now + DAY_S)

    def test_earliest_due_then_id_regardless_of_registry_order(self):
        sources = [source("z"), source("b"), source("a")]
        state = {"version": 1, "sources": {
            "a": {"next_due": 500}, "z": {"next_due": 100}, "b": {"next_due": 500}}}
        first = Scheduler(sources, state=state).plan(1000)
        second = Scheduler(reversed(sources), state=state).plan(1000)
        self.assertEqual(first, second)
        self.assertEqual(ids(first), ["z", "a", "b"])
        self.assertEqual(list(first["queues"]), ["z", "a", "b"])

    def test_overdue_sources_coalesce_to_one_entry(self):
        scheduler = Scheduler([source()], clock=self.clock)
        plan = scheduler.plan(self.clock.now + 1000 * DAY_S)
        self.assertEqual(len(plan["queues"]["a"]), 1)
        self.assertEqual(plan["queues"]["a"][0]["url"], "https://a.example/listing")

    def test_cap_zero_never_runs_but_is_queued(self):
        scheduler = Scheduler([source(daily_cap=0)], clock=self.clock)
        plan = scheduler.plan()
        self.assertEqual(ids(plan), [])
        self.assertEqual(ids(plan, "deferred_cap"), ["a"])
        self.assertEqual(list(plan["queues"]), ["a"])
        with self.assertRaisesRegex(ValueError, "cap"):
            scheduler.record_attempt("a")

    def test_per_source_caps_utc_boundary_and_default(self):
        midnight = epoch("2026-02-02")
        attempted_at = midnight - 100
        config = CrawlerConfig(daily_request_cap_default=2)
        sources = [source("explicit", daily_cap=1), source("default"), source("uncapped", daily_cap=3)]
        state = {"version": 1, "sources": {}}
        for s in sources:
            # Restore pending queue work and its persisted per-source daily counters.
            state["sources"].update(seeded_state(s.source_id, attempted_at, midnight - 1,
                                                 count=2)["sources"])
        scheduler = Scheduler(sources, config=config, state=state)
        plan = scheduler.plan(midnight - 1)
        self.assertEqual(ids(plan), ["uncapped"])
        self.assertEqual(ids(plan, "deferred_cap"), ["default", "explicit"])
        self.assertTrue(all(item["next_available"] == midnight for item in plan["deferred_cap"]))
        with self.assertRaisesRegex(ValueError, "cap"):
            scheduler.record_attempt("explicit", midnight - 1)
        self.assertEqual(ids(scheduler.plan(midnight)), ["default", "explicit", "uncapped"])
        scheduler.record_attempt("explicit", midnight)
        current = scheduler.to_dict()["sources"]["explicit"]
        self.assertEqual(current["attempts_today"], 1)
        self.assertEqual(current["attempt_day"], int(midnight // DAY_S))

    def test_plan_has_no_io_and_returns_detached_json_data(self):
        scheduler = Scheduler(load_registry(FIXTURE), clock=self.clock)
        before = scheduler.to_dict()
        with mock.patch("builtins.open", side_effect=AssertionError("plan I/O")), \
                mock.patch.object(Path, "open", side_effect=AssertionError("plan I/O")):
            first = scheduler.plan()
            second = scheduler.plan()
            json.dumps(first, allow_nan=False)
        self.assertEqual(first, second)
        self.assertEqual(before, scheduler.to_dict())
        first["queues"]["daily"][0]["url"] = "changed"
        daily = next(item for item in first["runnable"] if item["source_id"] == "daily")
        self.assertEqual(daily["url"], "https://a.example/disclosures")
        self.assertEqual(scheduler.plan(), second)

    def test_explicit_now_does_not_read_clock(self):
        clock = mock.Mock(side_effect=AssertionError("clock read"))
        scheduler = Scheduler([source()], clock=clock)
        scheduler.plan(100)
        scheduler.record_attempt("a", 100)
        scheduler.record_success("a", 101)
        clock.assert_not_called()

    def test_state_roundtrip_retains_plans_caps_and_success(self):
        sources = load_registry(FIXTURE)
        scheduler = Scheduler(sources, clock=self.clock)
        scheduler.record_attempt("daily")
        scheduler.record_success("daily", self.clock.now + 2)
        scheduler.record_attempt("backfill")
        state = json.loads(json.dumps(scheduler.to_dict(), allow_nan=False))
        restored = Scheduler(sources, clock=self.clock, state=state)
        self.assertEqual(restored.to_dict(), state)
        self.assertEqual(restored.plan(), scheduler.plan())
        self.assertEqual(restored.plan(self.clock.now + 40 * DAY_S),
                         scheduler.plan(self.clock.now + 40 * DAY_S))
        state["sources"]["daily"]["next_due"] = 0
        exported = restored.to_dict()
        exported["sources"].clear()
        self.assertNotEqual(restored.to_dict(), state)
        self.assertIn("daily", restored.to_dict()["sources"])

    def test_restore_obeys_new_terms_interval_and_cap(self):
        scheduler = Scheduler([source()], clock=self.clock)
        scheduler.record_attempt("a")
        state = scheduler.to_dict()
        restricted = Scheduler([source(terms_status="restricted")], state=state)
        self.assertEqual(ids(restricted.plan(self.clock.now + 100 * DAY_S)), [])
        extended = Scheduler([source(min_interval_s=3 * DAY_S)], state=state)
        self.assertEqual(ids(extended.plan(self.clock.now + DAY_S)), [])
        disabled = Scheduler([source(daily_cap=0)], state=state)
        self.assertEqual(ids(disabled.plan(self.clock.now + DAY_S)), [])

    def test_invalid_state_time_and_duplicate_sources_fail(self):
        for now in (-1, float("nan"), float("inf"), True, "100"):
            with self.subTest(now=now), self.assertRaises(ValueError):
                Scheduler([source()]).plan(now)
        for state in ({}, {"version": 2, "sources": {}},
                      {"version": True, "sources": {}},
                      {"version": 1, "sources": {"missing": {}}},
                      {"version": 1, "sources": {"a": {"next_due": float("nan")}}},
                      {"version": 1, "sources": {"a": {"attempts_today": -1}}},
                      {"version": 1, "sources": {"a": {"last_success": 100}}}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                Scheduler([source()], state=state)
        with self.assertRaises(ValueError):
            Scheduler([source(), source()])


class HostFairnessTest(OfflineCase):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock(1000)
        self.config = CrawlerConfig(per_host_min_interval_s=5, max_global_hosts=2)
        self.sleep = mock.Mock(side_effect=AssertionError("planner must not sleep"))
        self.limiter = HostRateLimiter(self.config, clock=self.clock, sleep=self.sleep)

    def scheduler(self, sources, state=None):
        return Scheduler(sources, config=self.config, limiter=self.limiter,
                         clock=self.clock, state=state)

    def test_busy_earliest_host_does_not_block_another_host(self):
        self.limiter.acquire("a.example")
        scheduler = self.scheduler([source("a"), source("b")])
        self.assertEqual(ids(scheduler.plan()), ["b"])
        self.assertEqual(ids(scheduler.plan(), "deferred_host"), ["a"])
        self.assertEqual(set(scheduler.plan()["queues"]), {"a", "b"})
        self.limiter.release("a.example")
        self.assertEqual(ids(scheduler.plan()), ["b"])
        self.clock.now += 5
        self.assertEqual(ids(scheduler.plan()), ["a", "b"])

    def test_known_robots_delay_and_release_interval_are_respected(self):
        self.limiter.acquire("a.example", robots_delay=10)
        self.clock.now += 3
        self.limiter.release("a.example")
        scheduler = self.scheduler([source("a"), source("b")])
        self.assertEqual(ids(scheduler.plan(1012.999)), ["b"])
        self.assertEqual(ids(scheduler.plan(1013)), ["a", "b"])
        self.sleep.assert_not_called()

    def test_one_source_per_host_and_global_slots_in_dispatch_batch(self):
        scheduler = self.scheduler([source("a", "SHARED.example"), source("b", "shared.example"),
                                    source("c"), source("d")])
        self.assertEqual(ids(scheduler.plan()), ["a", "c"])
        self.assertEqual(ids(scheduler.plan(), "deferred_host"), ["b", "d"])
        self.limiter.acquire("other.example")
        self.assertEqual(ids(scheduler.plan()), ["a"])
        self.limiter.acquire("another.example")
        self.assertEqual(ids(scheduler.plan()), [])

    def test_cap_blocked_source_does_not_consume_shared_host_slot(self):
        scheduler = self.scheduler([source("a", "shared.example", daily_cap=0),
                                    source("b", "shared.example")])
        self.assertEqual(ids(scheduler.plan()), ["b"])
        self.assertEqual(ids(scheduler.plan(), "deferred_cap"), ["a"])

    def test_snapshot_is_detached_and_does_not_acquire_or_read_clock(self):
        self.limiter.acquire("a.example")
        self.limiter._clock = mock.Mock(side_effect=AssertionError("snapshot clock"))
        first = self.limiter.snapshot(1000)
        first["active_hosts"].clear()
        first["next_available"].clear()
        self.assertEqual(self.limiter.snapshot(1000)["active_hosts"], ["a.example"])
        self.limiter._clock.assert_not_called()
        self.limiter._clock = self.clock
        with self.assertRaises(HostBusyError):
            self.limiter.acquire("a.example")

    def test_initial_epoch_availability_matches_acquire(self):
        scheduler = self.scheduler([source()])
        self.assertEqual(ids(scheduler.plan(0)), [])
        self.assertEqual(ids(scheduler.plan(5)), ["a"])


class StaticBoundaryTest(unittest.TestCase):
    def test_new_modules_cannot_fetch_write_or_read_environment(self):
        # No fetch code in this node. Existing crawler static guards additionally
        # scan the whole package for circumvention and browser headers.
        allowed = {"calendar", "csv", "math", "time", "dataclasses", "datetime",
                   "pathlib", "typing", "urllib.parse", "config", "hostlimit", "registry"}
        for name in ("registry.py", "scheduler.py"):
            path = ROOT / "tools/crawler" / name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    self.assertTrue({alias.name for alias in node.names} <= allowed)
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed)
                elif isinstance(node, ast.Call):
                    called = ast.unparse(node.func)
                    self.assertNotIn(called.split(".")[-1],
                                     {"fetch", "request", "urlopen", "write", "write_text",
                                      "write_bytes", "getenv", "sleep", "system", "Popen"})
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "open":
                        self.assertEqual(name, "registry.py")
                        self.assertEqual(ast.literal_eval(node.args[0]), "r")


if __name__ == "__main__":
    unittest.main()
