"""CRAWL-08 offline evidence; all synthetic inputs have origin=fixture.

Only temporary local files and in-process fakes are used. No collector, network,
archive writes, environment files, real clocks, sleeps, or process changes.
"""
import ast
import json
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crawler import gaps as gap_module, status as status_module  # noqa: E402
from crawler.gaps import (GapRecord, GapSummary, GapWriter, NEXT_ACTIONS, REASONS,
                          evaluate_cycle)  # noqa: E402
from crawler.spool import Spool  # noqa: E402
from crawler.state import StateDB  # noqa: E402
from crawler.status import (SourceStatus, SpoolView, budget_ge_80_percent,
                            build_status, daily_summary, new_gap, stale_heartbeat,
                            upload_failed, write_status)  # noqa: E402

ORIGIN = "fixture"
NOW = 1_800_000_000
URL = "https://fixture.example/document.pdf"
EXPECTED_REASONS = {
    "service_outage", "connection_reset", "js_shell", "rate_limited", "timeout",
    "tls_error", "geo_blocked", "empty_reply", "robots_disallow", "robots_unreadable",
    "blocked", "structure_changed", "terms_unknown", "cap_reached",
}
EXPECTED_ACTIONS = {"wait", "find_official_api", "draft_inquiry", "terms_review"}


def gap(**kwargs):
    return GapRecord(**dict({"source_id": "fixture_source", "observed_at": NOW,
                             "reason": "timeout"}, **kwargs))


class OfflineTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for target in ("socket.socket", "urllib.request.urlopen", "subprocess.Popen",
                       "source_archive.S3Store", "time.sleep", "time.time"):
            patcher = mock.patch(target, side_effect=AssertionError("offline fixture only"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def snapshot(self, **overrides):
        values = {"state": [SourceStatus("fixture_source", NOW - 10, NOW - 20, NOW + 60)],
                  "spool": SpoolView(10, 100, 2), "gaps": GapSummary(0, 0),
                  "budget_view": {"percent": 25, "origin": ORIGIN}, "clock": lambda: NOW}
        values.update(overrides)
        return build_status(**values)


class GapTest(OfflineTest):
    def test_all_reason_and_action_combinations_roundtrip_append_and_never_succeed(self):
        self.assertEqual(REASONS, EXPECTED_REASONS)
        self.assertEqual(NEXT_ACTIONS, EXPECTED_ACTIONS)
        writer = GapWriter(self.root / "gaps.jsonl")
        before = b""
        with StateDB(self.root / "state.db") as db:
            for index, (reason, action) in enumerate(
                    (r, a) for r in sorted(EXPECTED_REASONS) for a in sorted(EXPECTED_ACTIONS)):
                with self.subTest(reason=reason, action=action):
                    # Even 200 and 304 wire responses can leave an uncovered range.
                    record = gap(reason=reason, next_action=action, observed_at=NOW + index,
                                 http_status=(200, 304, 403, None)[index % 4],
                                 robots_verdict="allow", terms_verdict="unknown",
                                 next_retry_at=NOW + index + 60)
                    writer.append(record)
                    after = writer.path.read_bytes()
                    self.assertTrue(after.startswith(before))
                    self.assertEqual(after.count(b"\n"), index + 1)
                    before = after
                    extra = record.observation_extra()
                    self.assertTrue(extra["gap"])
                    self.assertEqual(extra["reason"], reason)
                    self.assertIsNone(extra["status"])
                    observation = record.as_observation(URL)
                    self.assertFalse({"object_key", "sha256", "bytes"} & observation.keys())
                    self.assertFalse({"object_key", "sha256", "bytes"} & record.to_dict().keys())
                    state = db.record_observation(observation)
                    self.assertIsNone(state.last_success)
                    self.assertIsNone(state.last_sha256)
                    self.assertFalse(state.original_retained)
                    self.assertEqual(state.consecutive_failures, index + 1)
        records = list(GapWriter(writer.path).records())
        self.assertEqual(len(records), len(EXPECTED_REASONS) * len(EXPECTED_ACTIONS))
        self.assertEqual({r.reason for r in records}, EXPECTED_REASONS)
        self.assertEqual({r.next_action for r in records}, EXPECTED_ACTIONS)
        self.assertEqual(records[-1], record)
        self.assertEqual(json.loads(before.splitlines()[-1]), record.to_dict())

    def test_append_reopen_and_cursor_include_late_or_equal_timestamps(self):
        writer = GapWriter(self.root / "gaps.jsonl")
        self.assertEqual(writer.summary(), GapSummary(0, 0))
        writer.append(gap())
        writer.append(gap())
        self.assertEqual(writer.summary(), GapSummary(2, 2))
        self.assertEqual(writer.summary(), GapSummary(2, 2))  # no hidden acknowledgement
        reopened = GapWriter(writer.path)
        self.assertEqual(reopened.summary(2), GapSummary(2, 0))
        reopened.append(gap(observed_at=NOW - 100))
        self.assertEqual(reopened.summary(2), GapSummary(3, 1))
        for cursor in (-1, True, 1.5, 4):
            with self.subTest(cursor=cursor), self.assertRaises(ValueError):
                writer.summary(cursor)

    def test_three_failed_cycles_alert_once_success_resets_and_new_incident_alerts(self):
        writer = GapWriter(self.root / "gaps.jsonl")
        failures = 0
        for cycle in range(1, 6):
            # Three HTTP attempts in cycle 1 still count as one failed cycle.
            result = evaluate_cycle(failures, gap(attempts=3, observed_at=NOW + cycle))
            failures = result.consecutive_failures
            self.assertEqual(failures, cycle)
            self.assertEqual(result.alert, cycle == 3)
            self.assertEqual(result.gap is not None, cycle == 3)
            if result.gap is not None:
                writer.append(result.gap)
        self.assertEqual(writer.summary(), GapSummary(1, 1))
        result = evaluate_cycle(failures)
        self.assertEqual((result.consecutive_failures, result.gap, result.alert), (0, None, False))
        for count in range(3):
            result = evaluate_cycle(count, gap())
        self.assertTrue(result.alert)
        self.assertEqual(result.gap, gap())
        self.assertFalse(evaluate_cycle(0).alert)
        # A block is recorded immediately without waiting for three cycles.
        writer.append(gap(reason="blocked", http_status=403, attempts=1))
        self.assertEqual(writer.summary().gap_count, 2)

    def test_timestamp_normalization_and_no_request_policy_gap(self):
        record = gap(observed_at="2026-10-25T09:00:00+09:00", attempts=0,
                     next_retry_at="2026-10-25T01:00:00Z", reason="robots_disallow")
        self.assertEqual(record.observed_at, "2026-10-25T00:00:00Z")
        self.assertEqual(record.next_retry_at, "2026-10-25T01:00:00Z")
        self.assertEqual(record.attempts, 0)

    def test_invalid_record_and_policy_inputs(self):
        invalid = ({"source_id": ""}, {"source_id": "bad\x00"}, {"reason": "unknown"},
                   {"next_action": "retry_with_new_identity"}, {"http_status": 99},
                   {"http_status": 600}, {"http_status": True}, {"attempts": -1},
                   {"attempts": True}, {"robots_verdict": ""}, {"terms_verdict": 4},
                   {"observed_at": "2026-10-25T00:00:00"}, {"observed_at": float("nan")},
                   {"observed_at": -1}, {"observed_at": True},
                   {"next_retry_at": NOW - 1})
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                gap(**fields)
        with self.assertRaises(ValueError):
            gap().as_observation("")
        for count in (-1, True, 2.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                evaluate_cycle(count, gap())
        with self.assertRaises(ValueError):
            evaluate_cycle(0, {})
        for values in ((-1, 0), (1, 2), (True, 0), (2, -1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                GapSummary(*values)

    def test_torn_or_oversized_lines_preserved_and_locks_exclude_append(self):
        writer = GapWriter(self.root / "gaps.jsonl")
        writer.append(gap())
        reader = writer.records()
        next(reader)  # reader holds its nonblocking shared lock until closed
        before = writer.path.read_bytes()
        with self.assertRaises(BlockingIOError):
            writer.append(gap())
        reader.close()
        self.assertEqual(writer.path.read_bytes(), before)
        with writer.path.open("ab") as stream:
            stream.write(b'{"gap":')
        torn = writer.path.read_bytes()
        with self.assertRaises(ValueError):
            writer.append(gap())
        with self.assertRaises(ValueError):
            writer.summary()
        self.assertEqual(writer.path.read_bytes(), torn)
        oversized = GapWriter(self.root / "oversized.jsonl")
        with self.assertRaises(ValueError):
            oversized.append(gap(source_id="x" * gap_module.MAX_RECORD_BYTES))
        self.assertFalse(oversized.path.exists())
        oversized.path.write_bytes(b"x" * (gap_module.MAX_RECORD_BYTES + 1))
        with self.assertRaises(ValueError):
            oversized.summary()
        with self.assertRaises(ValueError):
            writer.append({})

    def test_unknown_version_or_corrupt_complete_lines_are_not_summarized(self):
        writer = GapWriter(self.root / "gaps.jsonl")
        for body in (b"not-json\n", b'{"schema_version":99,"gap":true}\n',
                     b'{"schema_version":1,"gap":false}\n', b"[]\n", b"{}\n",
                     b'{"schema_version":true,"gap":true}\n',
                     b'{"schema_version":1,"gap":true}\n'):
            with self.subTest(body=body):
                writer.path.write_bytes(body)
                with self.assertRaises(ValueError):
                    writer.summary()
                self.assertEqual(writer.path.read_bytes(), body)


class StatusTest(OfflineTest):
    def test_deterministic_heartbeat_versions_aggregation_and_input_immutability(self):
        rows = [SourceStatus("fixture_b", NOW - 5, NOW - 20, NOW + 100),
                SourceStatus("fixture_a"),
                SourceStatus("fixture_b", NOW - 10, NOW - 15, NOW + 50)]
        budget = {"percent": 12.5, "detail": {"origin": ORIGIN}}
        status = self.snapshot(state=iter(rows), budget_view=budget, gaps=GapSummary(5, 2))
        other = self.snapshot(state=[asdict(row) for row in reversed(rows)],
                              budget_view=budget, gaps={"gap_count": 5, "new_gaps": 2},
                              spool=asdict(SpoolView(10, 100, 2)))
        self.assertEqual(status, other)
        self.assertEqual(list(status["sources"]), ["fixture_a", "fixture_b"])
        self.assertEqual(status["generated_at"], NOW)
        self.assertEqual(status["sources"]["fixture_b"], {
            "last_success": NOW - 5, "last_failure": NOW - 15, "next_due": NOW + 50})
        self.assertEqual(status["sources"]["fixture_a"], {
            "last_success": None, "last_failure": None, "next_due": None})
        self.assertEqual((status["gap_count"], status["new_gaps"]), (5, 2))
        self.assertEqual(status["spool"], {
            "used_bytes": 10, "cap_bytes": 100, "pending_count": 2, "upload_failures": 0})
        self.assertEqual((status["schema_version"], status["gap_schema_version"]), (1, 1))
        self.assertIsInstance(status["crawler_version"], str)
        self.assertEqual(json.loads(json.dumps(status, allow_nan=False)), status)
        status["budget"]["detail"]["origin"] = "changed"
        self.assertEqual(budget["detail"]["origin"], ORIGIN)
        self.assertEqual(rows[0].last_success, NOW - 5)
        with mock.patch.object(status_module, "epoch", wraps=status_module.epoch):
            clock = mock.Mock(return_value=NOW)
            self.snapshot(clock=clock)
            clock.assert_called_once_with()

    def test_local_spool_metadata_snapshot_and_acknowledged_gap_cursor(self):
        spool = Spool(self.root / "spool", cap_bytes=1000, object_cap_bytes=1000,
                      clock=lambda: NOW)
        body = b"%PDF-1.7\n% origin=fixture\nsynthetic\n%%EOF\n"
        entry = spool.write_stream("fixture_source", URL, gap().observed_at,
                                   iter((body,)), "pdf", {"origin": ORIGIN}).entry
        writer = GapWriter(self.root / "gaps.jsonl")
        writer.append(gap())
        status = self.snapshot(spool=spool, gaps=writer.summary())
        self.assertEqual(status["spool"]["used_bytes"], len(body))
        self.assertEqual(status["spool"]["cap_bytes"], 1000)
        self.assertEqual(status["spool"]["pending_count"], 1)
        write_status(self.root / "status.json", status)
        previous = json.loads((self.root / "status.json").read_text())
        spool.mark_uploaded(entry.entry_id)  # local acknowledgement only
        refreshed = self.snapshot(spool=SpoolView.from_spool(spool, upload_failures=1),
                                  gaps=writer.summary(previous["gap_count"]))
        self.assertEqual(refreshed["spool"]["used_bytes"], len(body))
        self.assertEqual(refreshed["spool"]["pending_count"], 0)
        self.assertEqual((refreshed["gap_count"], refreshed["new_gaps"]), (1, 0))
        self.assertTrue(upload_failed(refreshed))
        self.assertTrue(entry.object_path.exists())

    def test_atomic_write_publishes_only_complete_json(self):
        path = self.root / "status.json"
        old = self.snapshot()
        write_status(path, old)
        old_bytes = path.read_bytes()
        new = self.snapshot(clock=lambda: NOW + 60)
        real_replace = status_module.os.replace

        def observe_replace(partial, destination):
            self.assertEqual(path.read_bytes(), old_bytes)
            self.assertEqual(json.loads(partial.read_text()), new)
            self.assertEqual(partial.parent, path.parent)
            real_replace(partial, destination)

        with mock.patch.object(status_module.os, "replace", side_effect=observe_replace) as rename:
            write_status(path, new)
            rename.assert_called_once()
        self.assertEqual(json.loads(path.read_text()), new)
        self.assertFalse(path.with_name("status.json.partial").exists())
        before = path.read_bytes()
        write_status(path, new)
        self.assertEqual(path.read_bytes(), before)

    def test_failed_serialization_fsync_or_replace_preserves_previous_status_and_cursor(self):
        path = self.root / "status.json"
        writer = GapWriter(self.root / "gaps.jsonl")
        previous = self.snapshot()
        write_status(path, previous)
        writer.append(gap())
        current = self.snapshot(gaps=writer.summary(previous["gap_count"]))
        for target in ("fsync", "replace"):
            with self.subTest(target=target), mock.patch.object(
                    status_module.os, target, side_effect=OSError("fixture disk failure")):
                with self.assertRaises(OSError):
                    write_status(path, current)
            self.assertEqual(json.loads(path.read_text()), previous)
            self.assertFalse(path.with_name("status.json.partial").exists())
            self.assertEqual(writer.summary(previous["gap_count"]), GapSummary(1, 1))
        for bad in (float("nan"), object()):
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                write_status(path, {"bad": bad})
            self.assertEqual(json.loads(path.read_text()), previous)
            self.assertFalse(path.with_name("status.json.partial").exists())
        write_status(path, current)
        self.assertEqual(writer.summary(current["gap_count"]), GapSummary(1, 0))

    def test_existing_partial_is_not_overwritten_or_deleted(self):
        path = self.root / "status.json"
        partial = path.with_name("status.json.partial")
        partial.write_bytes(b"origin=fixture abandoned writer")
        with self.assertRaises(FileExistsError):
            write_status(path, self.snapshot())
        self.assertEqual(partial.read_bytes(), b"origin=fixture abandoned writer")
        self.assertFalse(path.exists())

    def test_after_replacement_a_new_writers_partial_is_preserved(self):
        path = self.root / "status.json"
        partial = path.with_name("status.json.partial")
        real_replace = status_module.os.replace

        def replace_and_start_next_writer(source, destination):
            real_replace(source, destination)
            partial.write_bytes(b"origin=fixture next writer")

        with mock.patch.object(status_module.os, "replace", side_effect=replace_and_start_next_writer):
            write_status(path, self.snapshot())
        self.assertEqual(json.loads(path.read_text()), self.snapshot())
        self.assertEqual(partial.read_bytes(), b"origin=fixture next writer")

    def test_empty_summary_and_invalid_inputs(self):
        status = self.snapshot(state=[])
        self.assertEqual(status["sources"], {})
        for percent in (-0.01, True, "80", None, float("nan"), float("inf")):
            with self.subTest(percent=percent), self.assertRaises(ValueError):
                self.snapshot(budget_view={"percent": percent})
        for budget in ({}, [], {"percent": 1, "detail": float("nan")}):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                self.snapshot(budget_view=budget)
        for changes in ({"used_bytes": -1}, {"cap_bytes": 0}, {"pending_count": True},
                        {"upload_failures": -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.snapshot(spool=dict(asdict(SpoolView(0, 100, 0)), **changes))
        for changes in ({"source_id": ""}, {"last_success": float("inf")},
                        {"last_failure": True}, {"next_due": -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.snapshot(state=[dict(asdict(SourceStatus("fixture")), **changes)])
        for now in (-1, True, float("nan")):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.snapshot(clock=lambda: now)


class AlertTest(OfflineTest):
    def test_new_gap_and_upload_failure_zero_one_boundaries_are_pure(self):
        for count in (0, 1, 2):
            status = self.snapshot(gaps=GapSummary(10, count),
                                   spool=replace(SpoolView(0, 100, 0), upload_failures=count))
            before = json.dumps(status, sort_keys=True)
            self.assertEqual(new_gap(status), count > 0)
            self.assertEqual(upload_failed(status), count > 0)
            self.assertEqual(json.dumps(status, sort_keys=True), before)

    def test_budget_percent_boundary_and_over_budget(self):
        for percent, expected in ((0, False), (79.999, False), (80, True),
                                  (80.001, True), (100, True), (125, True)):
            with self.subTest(percent=percent):
                status = self.snapshot(budget_view={"percent": percent})
                self.assertEqual(budget_ge_80_percent(status), expected)

    def test_stale_heartbeat_strict_36_hour_boundary_and_injected_now(self):
        status = self.snapshot()
        for age, expected in ((-1, False), (0, False), (36 * 3600 - 1, False),
                              (36 * 3600, False), (36 * 3600 + 0.001, True)):
            with self.subTest(age=age):
                self.assertEqual(stale_heartbeat(status, NOW + age), expected)
        status["generated_at"] = gap().observed_at
        self.assertFalse(stale_heartbeat(status, NOW))

    def test_healthy_daily_one_liner_discloses_historical_gaps_and_suppresses_on_alerts(self):
        status = self.snapshot(gaps=GapSummary(7, 0))
        line = daily_summary(status, NOW)
        self.assertEqual(line, "Crawler OK: sources=1, gaps=7, pending=2, "
                              "spool=10/100 bytes, budget=25%")
        self.assertNotIn("\n", line)
        self.assertIsNone(daily_summary(self.snapshot(gaps=GapSummary(1, 1)), NOW))
        self.assertIsNone(daily_summary(self.snapshot(budget_view={"percent": 80}), NOW))
        self.assertIsNone(daily_summary(self.snapshot(spool=SpoolView(0, 100, 0, 1)), NOW))
        self.assertIsNone(daily_summary(status, NOW + 36 * 3600 + 1))


class StaticSafetyTest(unittest.TestCase):
    def test_new_modules_have_no_fetch_collection_secret_process_or_budget_execution(self):
        allowed_imports = {"fcntl", "json", "math", "os", "dataclasses", "datetime", "pathlib",
                           "collections.abc", "", "gaps"}
        forbidden_attributes = {"environ", "getenv", "system", "popen", "fork", "execv",
                                "spawnv", "urandom", "sleep", "time", "socket", "urlopen"}
        for module in (gap_module, status_module):
            with self.subTest(module=module.__name__):
                tree = ast.parse(Path(module.__file__).read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        self.assertTrue({alias.name for alias in node.names} <= allowed_imports)
                    elif isinstance(node, ast.ImportFrom):
                        self.assertIn(node.module or "", allowed_imports)
                    elif isinstance(node, ast.Attribute):
                        self.assertNotIn(node.attr, forbidden_attributes)
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, {"eval", "exec", "__import__"})


if __name__ == "__main__":
    unittest.main()
