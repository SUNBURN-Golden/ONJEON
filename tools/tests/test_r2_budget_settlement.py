"""Audit 6: sequence races, ambiguous commits, bounded accounting and pagination.

Only synthetic data and loopback HTTP are used. The HTTP log is independent of
the meter and persisted amounts; Stubber checks continuation parameters exactly.
"""
import io
import json
import os
import signal
from unittest import mock

import test_r2_budget as fixture

b, sa = fixture.b, fixture.sa


@fixture.unittest.skipUnless(fixture.HAVE_BOTO, "boto3 >= 1.35 not installed")
class SettlementRobustness(fixture.Fixture):
    def setUp(self):
        super().setUp()
        from s3_stub import S3Stub
        self.stub = S3Stub()
        self.addCleanup(self.stub.stop)
        env = mock.patch.dict(os.environ, fixture.EMU)
        env.start()
        self.addCleanup(env.stop)
        clock = mock.patch.object(b, "time", wraps=b.time)
        self.clock = clock.start()
        self.clock.monotonic.return_value = 100.0
        self.addCleanup(clock.stop)
        self.write_policy(per_month_global=10)
        self.write_job(admissions_per_month=5, class_a=1000)

    def session(self):
        s = b.start(self.job_path, self.stub.endpoint, policy_path=self.policy_path,
                    gate_dir=self.gate_dir)
        self.addCleanup(s._restore_alarm)
        self.addCleanup(s.gate.leave)
        return s

    def records(self):
        return [json.loads(raw) for (bucket, key), raw in sorted(self.stub.objects.items())
                if bucket == "ledger" and key.startswith(b.LEDGER_PREFIX)]

    def assert_accounting(self, session, summary, rec):
        seen = self.stub.counts()
        seen["get_bytes"] = sum(len(self.stub.objects[(bucket, key)])
                                for kind, bucket, key, status, _ in self.stub.log
                                if kind == "get" and status == 200)
        for dim, actual in seen.items():
            self.assertEqual(summary["used"][dim], actual, dim)
            self.assertGreaterEqual(rec["amounts"][dim], actual, dim)
        for dim in b.DIMENSIONS:
            self.assertLessEqual(rec["amounts"][dim], session.reservation["amounts"][dim], dim)
        records, _ = b.Ledger(sa.S3Store("s3://ledger", self.stub.endpoint, ledger=True), session.policy).read()
        self.assertEqual(records, self.records())  # includes chain, policy and sequence verification
        self.assertIsNone(session.gate._lock)
        self.assertIsNone(b.ACTIVE)

    def competitor(self, s, losses):
        put = s.ledger.st.put_new
        raced = []

        def race(key, body, content_type):
            if key.startswith(b.LEDGER_PREFIX) and len(raced) < losses:
                # Same run_id is insufficient proof of our commit: alter outcome/amounts.
                winner = json.loads(body)
                winner["reservation_seq"] = -1  # competitor cannot settle our reservation
                winner["outcome"] = "other"
                winner["amounts"] = dict.fromkeys(b.DIMENSIONS, 0)
                raced.append(key)
                with self.stub.lock:
                    self.stub.objects[("ledger", key)] = json.dumps(winner).encode()
            return put(key, body, content_type)

        return mock.patch.object(s.ledger.st, "put_new", side_effect=race), raced

    def test_settlement_retries_sequence_race_with_fresh_hash_and_usage(self):
        s = self.session()
        patch, raced = self.competitor(s, 1)
        with patch:
            summary = b.finish("ok")
        self.assertEqual(summary["settlement"], 3)
        self.assertEqual(len(raced), 1)
        rec = self.records()[-1]
        self.assertEqual(rec["reservation_seq"], 1)
        self.assertEqual(rec["outcome"], "ok")
        writes = [e[3] for e in self.stub.log if e[0] == "put" and e[2].startswith(b.LEDGER_PREFIX)]
        self.assertEqual(writes, [200, 412, 200])
        self.assert_accounting(s, summary, rec)

    def test_exhausted_sequence_races_keep_full_reservation_and_release_gate(self):
        s = self.session()
        attempts = s.policy["per_request"]["reserve_attempts"]
        patch, raced = self.competitor(s, attempts + 1)
        with patch:
            summary = b.finish("failed")
        self.assertEqual(summary["settlement"], {"settlement_failed": "BudgetError"})
        self.assertEqual(len(raced), attempts)
        _, used = b.Ledger.usage(self.records(), "t", fixture.MONTH)
        self.assertEqual(used, fixture.PER_RUN)
        self.assertIsNone(s.gate._lock)
        self.assertIsNone(b.ACTIVE)

    def test_committed_reservation_followed_by_412_is_reconciled_without_duplicate(self):
        self.stub.committed_put_faults.append((b.LEDGER_PREFIX, 503))
        with mock.patch("botocore.endpoint.time.sleep", return_value=None):
            s = self.session()
        self.assertEqual(s.reservation["seq"], 1)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(s.meter.used["retries"], 1)
        summary = b.finish("ok")
        self.assertEqual(summary["settlement"], 2)
        self.assert_accounting(s, summary, self.records()[-1])

    def test_committed_settlement_followed_by_412_is_reconciled_and_confirmation_metered(self):
        s = self.session()
        self.stub.committed_put_faults.append((b.LEDGER_PREFIX, 503))
        with mock.patch("botocore.endpoint.time.sleep", return_value=None):
            summary = b.finish("ok")
        self.assertEqual(summary["settlement"], 2)
        self.assertEqual(len(self.records()), 2)
        writes = [e[3] for e in self.stub.log if e[0] == "put" and e[2].endswith("0000000002.json")]
        self.assertEqual(writes, [503, 412])
        self.assertEqual(summary["used"]["retries"], 1)
        self.assert_accounting(s, summary, self.records()[-1])

    def test_confirmation_get_retries_are_in_recorded_worst_case(self):
        s = self.session()
        key = f"{b.LEDGER_PREFIX}0000000002.json"
        self.stub.committed_put_faults.append((key, 503))
        self.stub.faults.extend([("GET", key, 503)] * 2)
        with mock.patch("botocore.endpoint.time.sleep", return_value=None):
            summary = b.finish("ok")
        self.assertEqual(summary["settlement"], 2)
        self.assertEqual(summary["used"]["retries"], 3)
        self.assert_accounting(s, summary, self.records()[-1])

    def test_reconciliation_read_failure_does_not_start_another_write(self):
        s = self.session()
        patch, _ = self.competitor(s, 1)
        key = f"{b.LEDGER_PREFIX}0000000002.json"
        self.stub.faults.append(("GET", key, 403))
        with patch:
            summary = b.finish("ok")
        self.assertEqual(summary["settlement"], {"settlement_failed": "BudgetError"})
        self.assertEqual(len(self.records()), 2)
        _, used = b.Ledger.usage(self.records(), "t", fixture.MONTH)
        self.assertEqual(used, fixture.PER_RUN)
        self.assertIsNone(s.gate._lock)

    def test_collision_at_final_slot_rechecks_cap_before_next_put(self):
        s = self.session()
        s.policy["per_request"]["max_ledger_records"] = 2
        patch, _ = self.competitor(s, 1)
        with patch:
            summary = b.finish("ok")
        self.assertEqual(summary["settlement"], {"settlement_failed": "BudgetError"})
        self.assertEqual(len(self.records()), 2)
        self.assertFalse(any(e[0] == "put" and e[2].endswith("0000000003.json") for e in self.stub.log))

    def test_expired_run_preserves_original_error_through_race_and_final_summary(self):
        s = self.session()
        patch, _ = self.competitor(s, 1)
        original = b.BudgetError("original workload deadline")
        self.clock.monotonic.return_value = s.meter.start + fixture.PER_RUN["seconds"] + 1
        with self.assertRaises(b.BudgetError) as raised:
            try:
                raise original
            finally:
                with patch:
                    summary = b.finish("failed")
        self.assertIs(raised.exception, original)
        self.assertEqual(summary["settlement"], 3)
        self.assertEqual(summary["used"]["seconds"], fixture.PER_RUN["seconds"] + 1)
        self.assertEqual(self.records()[-1]["amounts"]["seconds"], fixture.PER_RUN["seconds"])
        self.assertIsNone(s.gate._lock)
        if hasattr(signal, "SIGALRM"):
            self.assertEqual(signal.alarm(0), 0)

    def test_remaining_request_budget_still_blocks_race_retry(self):
        s = self.session()
        s.meter.limits["class_a"] = s.meter.used["class_a"] + 2  # tail LIST, losing PUT
        patch, _ = self.competitor(s, 1)
        with patch:
            summary = b.finish("ok")
        self.assertEqual(summary["settlement"], {"settlement_failed": "BudgetError"})
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(summary["used"]["class_a"], s.meter.limits["class_a"])

    def test_paginated_http_reads_and_race_retry_charge_every_page_and_body(self):
        self.stub.page_size = 1  # force IsTruncated on a small, valid ledger
        self.reserve(run_id="seed-one")
        self.reserve(run_id="seed-two")
        for key in self.ledger_store.list(b.LEDGER_PREFIX):
            self.stub.objects[("ledger", key)] = self.ledger_store.get(key)
        s = self.session()
        patch, _ = self.competitor(s, 1)
        with patch:
            summary = b.finish("ok")
        self.assertEqual(summary["settlement"], 5)
        pages = [e for e in self.stub.log if e[:3] == ("list", "ledger", b.LEDGER_PREFIX)]
        self.assertEqual(len(pages), 2 + 3 + 4)  # reserve, first tail, retry tail
        self.assert_accounting(s, summary, self.records()[-1])

    def test_truncated_admissions_and_ledger_pages_use_continuation_tokens(self):
        policy, job = self.load()
        meter = b.Meter(policy, job, job["per_run"], 600)
        budget = mock.Mock(policy=policy, meter=meter)
        store = sa.S3Store("s3://ledger", self.stub.endpoint, ledger=True, budget=budget)
        meter.attach(store.s3, "ledger")
        ledger = b.Ledger(store, policy)
        first = f"{b.LEDGER_PREFIX}0000000001.json"
        second = f"{b.LEDGER_PREFIX}0000000002.json"
        admission = f"{b.ADMISSION_PREFIX}{fixture.MONTH}/t/"
        record1 = {"seq": 1, "prev_sha256": None, "policy_sha256": policy["_sha256"]}
        raw1 = json.dumps(record1).encode()
        record2 = dict(record1, seq=2, prev_sha256=sa.sha256_bytes(raw1))
        raw2 = json.dumps(record2).encode()
        with fixture.Stubber(store.s3) as stub:
            for prefix, keys in ((b.ADMISSION_PREFIX, [admission + "one.json", admission + "two.json"]),
                                 (b.LEDGER_PREFIX, [first, second])):
                if prefix == b.LEDGER_PREFIX:
                    stub.add_response("list_objects_v2", {"IsTruncated": False},
                                      {"Bucket": "ledger", "Prefix": b.CHECKPOINT_PREFIX})
                stub.add_response("list_objects_v2", {"IsTruncated": True, "NextContinuationToken": "page2",
                                                      "Contents": [{"Key": keys[0]}]},
                                  {"Bucket": "ledger", "Prefix": prefix})
                stub.add_response("list_objects_v2", {"IsTruncated": False, "Contents": [{"Key": keys[1]}]},
                                  {"Bucket": "ledger", "Prefix": prefix, "ContinuationToken": "page2"})
                if prefix == b.ADMISSION_PREFIX:
                    self.assertEqual(ledger.admissions(), [(fixture.MONTH, "t", "one"), (fixture.MONTH, "t", "two")])
            for key, raw in ((first, raw1), (second, raw2)):
                stub.add_response("get_object", {"Body": io.BytesIO(raw)}, {"Bucket": "ledger", "Key": key})
            records, _ = ledger.read()
            self.assertEqual(records, [record1, record2])
            self.assertEqual(meter.used["get_bytes"], len(raw1) + len(raw2))
            self.assertEqual(meter.calls, 7)  # five LIST pages, two GETs; Stubber skips HTTP sends
            stub.assert_no_pending_responses()

    def test_unpinned_initialization_also_binds_ledger_body_meter_and_retry_policy(self):
        self.reserve(run_id="existing")
        key = self.ledger_store.list(b.LEDGER_PREFIX)[0]
        raw = self.ledger_store.get(key)
        self.stub.objects[("ledger", key)] = raw
        policy, _ = self.load()
        policy["per_request"]["max_attempts"] = 1
        factory = sa.S3Store
        stores = []

        def create(*args, **kwargs):
            store = factory(*args, **kwargs)
            stores.append(store)
            return store

        argv = ["r2_budget.py", "--endpoint-url", self.stub.endpoint, "init-pre-ledger",
                "--job", str(self.job_path), "--amounts", str(self.root / "unused.json")]
        with mock.patch.object(fixture.sys, "argv", argv), \
                mock.patch.object(b, "load_policy", return_value=policy), \
                mock.patch.object(sa, "S3Store", side_effect=create):
            with self.assertRaisesRegex(b.BudgetError, "can only be the first record"):
                b._cli()
        self.assertEqual(len(stores), 1)
        self.assertIsNotNone(stores[0].meter)
        self.assertEqual(stores[0].meter.used["get_bytes"], len(raw))
        self.assertEqual(stores[0].s3.meta.config.retries["total_max_attempts"], 1)


class AppendBounds(fixture.Fixture):
    def test_oversized_record_is_refused_before_put(self):
        policy, _ = self.load()
        ledger = b.Ledger(self.ledger_store, policy)
        with mock.patch.object(self.ledger_store, "put_new") as put:
            with self.assertRaisesRegex(b.BudgetError, "record exceeds"):
                ledger.append({"padding": "x" * b.RECORD_BYTES}, 0, None)
        put.assert_not_called()

    def test_shipped_profiles_keep_their_existing_caps_and_minimum(self):
        policy = b.load_policy()
        for profile in ("upload", "verify", "status"):
            job = b.load_job(b.ROOT / f"infra/r2/jobs/initial-119.json#{profile}", policy)
            self.assertGreaterEqual(job["per_run"]["retries"], b.profile_minimum(policy)["retries"])


if __name__ == "__main__":
    fixture.unittest.main()
