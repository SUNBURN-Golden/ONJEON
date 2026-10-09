"""Spend limits (tools/r2_budget.py): reservation ledger, fail-closed reads, per-request meter.

The ledger runs on a local write-once store here; the meter is exercised with botocore's Stubber
(no network). What must hold:
- a run reserves its whole allowance before any archive request, and reservations never come back,
  so re-running or running in parallel cannot exceed the job or global caps;
- a ledger that cannot be listed, read or verified stops the run;
- every request outside the job (operation, bucket, key, bytes, storage class) or over a limit is
  refused before it is sent.
"""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import r2_budget as b  # noqa: E402
import source_archive as sa  # noqa: E402

try:
    import boto3  # noqa: F401
    from botocore.stub import Stubber
    HAVE_BOTO = True
except ImportError:
    HAVE_BOTO = False

R2 = "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
FAKE = {"R2_ACCESS_KEY_ID": "k" * 32, "R2_SECRET_ACCESS_KEY": "s" * 64}
BODY = b"pinned original"
KEY = sa.object_key(hashlib.sha256(BODY).hexdigest())


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        listing = self.root / "listing.json"
        listing.write_text(json.dumps({"listing_rule": "key-sha256-v1", "keys": 1,
                                       "objects": {KEY: hashlib.sha256(BODY).hexdigest()}}))
        self.policy_path = self.root / "policy.json"
        self.write_policy(class_a=1000)
        per_run = {"put_bytes": 100, "get_bytes": 1000, "class_a": 10, "class_b": 50, "retries": 2, "seconds": 60}
        self.job_path = self.root / "job.json"
        self.job_path.write_text(json.dumps({
            "job_id": "t", "buckets": {"raw": {"listing": str(listing), "listing_sha256": b.sha256_file(listing)}},
            "job_caps": {"put_bytes": 300, "get_bytes": 3000, "class_a": 30, "class_b": 150, "retries": 6,
                         "seconds": 180},
            "run_profiles": {"verify": per_run}}))
        self.ledger_store = sa.LocalStore(self.root / "ledger")

    def write_policy(self, **caps):
        c = {"put_bytes": 10**9, "get_bytes": 10**9, "class_a": 1000, "class_b": 10**6, "retries": 100,
             "seconds": 10**6}
        c.update(caps)
        self.policy_path.write_text(json.dumps({
            "ledger_bucket": "ledger", "caps": c,
            "per_request": {"max_object_bytes": 1024, "max_attempts": 3, "reserve_attempts": 3,
                            "max_ledger_records": 100}}))

    def tearDown(self):
        self.tmp.cleanup()

    def load(self):
        return b.load_policy(self.policy_path), b.load_job(self.job_path)

    def reserve(self, store=None):
        policy, job = self.load()
        return b.reserve(b.Ledger(store or self.ledger_store, policy), policy, job, "run")


class Reservation(Fixture):
    def test_reservation_is_written_before_work(self):
        rec, _, remaining = self.reserve()
        self.assertEqual((rec["seq"], rec["kind"], rec["amounts"]["class_a"]), (1, "reservation", 10))
        self.assertEqual(remaining["class_a"], 1000 - 10)

    def test_reruns_stop_at_the_job_cap(self):
        for _ in range(3):
            self.reserve()
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("job t", str(cm.exception))
        self.assertEqual(len(self.ledger_store.list(b.LEDGER_PREFIX)), 3)  # the refused run wrote nothing

    def test_global_cap_applies_across_jobs(self):
        self.write_policy(class_a=15)
        self.reserve()
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("global class_a", str(cm.exception))

    def settle(self, ledger, rec, run_id, **amounts):
        records, prev = ledger.read()
        a = {d: 0 for d in b.DIMENSIONS}
        a.update(amounts)
        ledger.append({"kind": "settlement", "job_id": "t", "run_id": run_id, "reservation_seq": rec["seq"],
                       "at": "2026-10-09T00:00:00Z", "amounts": a}, records, prev)

    def test_settlement_returns_unused_allowance_only_up_to_the_reservation(self):
        policy, job = self.load()
        ledger = b.Ledger(self.ledger_store, policy)
        rec, _, _ = b.reserve(ledger, policy, job, "r1")
        self.settle(ledger, rec, "r1", class_a=2)
        rec2, _, _ = b.reserve(ledger, policy, job, "r2")
        self.settle(ledger, rec2, "r2", class_a=999)  # a settlement above the reservation is capped
        records, _ = ledger.read()
        _, used = b.Ledger.usage(records, "t", "2026-10")
        self.assertEqual(used["class_a"], 2 + 10)

    def test_unsettled_runs_count_in_full_and_settlements_must_match_their_run(self):
        policy, job = self.load()
        ledger = b.Ledger(self.ledger_store, policy)
        rec, _, _ = b.reserve(ledger, policy, job, "r1")   # crashed: never settled
        rec2, _, _ = b.reserve(ledger, policy, job, "r2")
        self.settle(ledger, rec2, "someone-else")           # wrong run id: ignored
        records, _ = ledger.read()
        _, used = b.Ledger.usage(records, "t", "2026-10")
        self.assertEqual(used["class_a"], 20)

    def test_parallel_run_loses_the_race_and_rechecks(self):
        """Two runs read the same ledger; the second write gets Exists, re-reads, and is refused when
        the first run used the last allowance."""
        self.reserve()
        self.reserve()  # one reservation left in the job
        policy, job = self.load()
        store = self.ledger_store
        other = {"done": False}

        class Racing:
            def list(self, prefix):
                return store.list(prefix)

            def get(self, key):
                return store.get(key)

            def put_new(self, key, body, ctype):
                if not other["done"]:  # the competing run writes the same seq first
                    other["done"] = True
                    b.reserve(b.Ledger(store, policy), policy, job, "other")
                return store.put_new(key, body, ctype)

        with self.assertRaises(b.BudgetError) as cm:
            b.reserve(b.Ledger(Racing(), policy), policy, job, "run")
        self.assertIn("job t", str(cm.exception))
        self.assertEqual(len(store.list(b.LEDGER_PREFIX)), 3)

    def test_local_create_is_atomic(self):
        self.ledger_store.put_new("ledger/v1/x", b"a", "x")
        with self.assertRaises(sa.Exists):
            self.ledger_store.put_new("ledger/v1/x", b"b", "x")
        self.assertEqual(self.ledger_store.get("ledger/v1/x"), b"a")


class FailClosed(Fixture):
    def test_list_failure_stops(self):
        class Broken:
            def list(self, prefix):
                raise OSError("network")
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve(Broken())
        self.assertIn("ledger list failed", str(cm.exception))

    def test_unreadable_record_stops(self):
        self.reserve()
        (self.root / "ledger/ledger/v1/0000000001.json").write_bytes(b"{not json")
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("unreadable", str(cm.exception))

    def test_deleted_record_is_a_gap(self):
        self.reserve()
        self.reserve()
        (self.root / "ledger/ledger/v1/0000000001.json").unlink()
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("gap", str(cm.exception))

    def test_edited_record_breaks_the_chain(self):
        self.reserve()
        self.reserve()
        p = self.root / "ledger/ledger/v1/0000000001.json"
        rec = json.loads(p.read_text())
        rec["amounts"]["class_a"] = 0  # someone lowers recorded usage
        p.write_text(json.dumps(rec, sort_keys=True, indent=1) + "\n")
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("chain broken", str(cm.exception))

    def test_record_under_unknown_policy_stops(self):
        self.reserve()
        self.write_policy(class_a=999)  # policy changed without listing the old hash
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("unknown policy", str(cm.exception))

    def test_emptied_or_replaced_ledger_is_refused_once_genesis_is_pinned(self):
        self.reserve()
        genesis = hashlib.sha256((self.root / "ledger/ledger/v1/0000000001.json").read_bytes()).hexdigest()
        doc = json.loads(self.policy_path.read_text())
        old_sha = b.sha256_file(self.policy_path)
        doc.update(ledger_genesis_sha256=genesis, previous_policy_sha256=[old_sha])
        self.policy_path.write_text(json.dumps(doc))
        self.reserve()  # same ledger: fine
        import shutil
        shutil.rmtree(self.root / "ledger")  # someone deletes every record
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("genesis", str(cm.exception))

    def test_changed_listing_invalidates_the_job(self):
        listing = self.root / "listing.json"
        listing.write_text(listing.read_text().replace("}}", "}, \"extra\": 1}"))
        with self.assertRaises(b.BudgetError):
            b.load_job(self.job_path)


class MeterChecks(Fixture):
    def meter(self, **limits):
        policy, job = self.load()
        lim = dict(job["per_run"])
        lim.update(limits)
        return b.Meter(policy, job, lim, lim["seconds"])

    def test_only_job_operations_buckets_keys_and_bytes(self):
        m = self.meter()
        bad = [("DeleteObject", {"Bucket": "raw", "Key": KEY}, "operation"),
               ("CreateMultipartUpload", {"Bucket": "raw", "Key": KEY}, "operation"),
               ("GetObject", {"Bucket": "other", "Key": KEY}, "bucket other"),
               ("GetObject", {"Bucket": "raw", "Key": "objects/sha256/00/00/x"}, "pinned listing"),
               ("PutObject", {"Bucket": "raw", "Key": KEY, "Body": b"other bytes"}, "pinned SHA-256"),
               ("PutObject", {"Bucket": "raw", "Key": KEY, "Body": BODY, "StorageClass": "STANDARD_IA"},
                "storage class")]
        for op, params, why in bad:
            with self.assertRaises(b.BudgetError, msg=op) as cm:
                m.check_call(op, params, "archive")
            self.assertIn(why, str(cm.exception))
        m.check_call("PutObject", {"Bucket": "raw", "Key": KEY, "Body": BODY}, "archive")

    def test_ledger_role_is_confined(self):
        m = self.meter()
        with self.assertRaises(b.BudgetError):
            m.check_call("PutObject", {"Bucket": "ledger", "Key": "objects/x", "Body": b""}, "ledger")
        with self.assertRaises(b.BudgetError):
            m.check_call("GetObject", {"Bucket": "raw", "Key": "ledger/v1/1"}, "ledger")
        m.check_call("ListObjectsV2", {"Bucket": "ledger", "Prefix": "ledger/v1/"}, "ledger")

    def test_every_attempt_is_charged_and_retries_are_capped(self):
        m = self.meter(class_b=3, retries=1)
        req = mock.Mock(body=b"")
        m.check_call("GetObject", {"Bucket": "raw", "Key": KEY}, "archive")
        m.on_send(req)
        m.on_send(req)  # botocore retry: second attempt of the same call
        self.assertEqual((m.used["class_b"], m.used["retries"]), (2, 1))
        with self.assertRaises(b.BudgetError) as cm:
            m.on_send(req)  # a second retry would exceed retries=1
        self.assertIn("retries", str(cm.exception))

    def test_class_a_and_put_bytes(self):
        m = self.meter(put_bytes=len(BODY) * 2 - 1)
        m.check_call("PutObject", {"Bucket": "raw", "Key": KEY, "Body": BODY}, "archive")
        m.on_send(mock.Mock(body=BODY, headers={}))
        self.assertEqual((m.used["class_a"], m.used["put_bytes"]), (1, len(BODY)))
        m.check_call("PutObject", {"Bucket": "raw", "Key": KEY, "Body": BODY}, "archive")
        with self.assertRaises(b.BudgetError):
            m.on_send(mock.Mock(body=BODY, headers={}))

    def test_streamed_body_is_counted_from_content_length(self):
        """Found on the emulator: botocore sent the body as a stream and bytes were counted as 0."""
        import io
        m = self.meter()
        m.check_call("PutObject", {"Bucket": "raw", "Key": KEY, "Body": BODY}, "archive")
        m.on_send(mock.Mock(body=io.BytesIO(BODY), headers={"Content-Length": str(len(BODY))}))
        self.assertEqual(m.used["put_bytes"], len(BODY))
        m.check_call("PutObject", {"Bucket": "raw", "Key": KEY, "Body": BODY}, "archive")
        with self.assertRaises(b.BudgetError) as cm:
            m.on_send(mock.Mock(body=io.BytesIO(BODY), headers={}))
        self.assertIn("size unknown", str(cm.exception))

    def test_get_bytes_and_deadline(self):
        m = self.meter(get_bytes=10)
        with self.assertRaises(b.BudgetError):
            m.charge_get_bytes(11)
        m = self.meter()
        m.start -= 61
        with self.assertRaises(b.BudgetError) as cm:
            m.check_call("GetObject", {"Bucket": "raw", "Key": KEY}, "archive")
        self.assertIn("run time", str(cm.exception))


@unittest.skipUnless(HAVE_BOTO, "boto3 not installed")
class StoreNeedsBudget(Fixture):
    def tearDown(self):
        b.ACTIVE = None
        super().tearDown()

    def test_r2_without_a_job_sends_nothing(self):
        with mock.patch.dict(os.environ, FAKE, clear=False):
            with self.assertRaises(SystemExit) as cm:
                sa.S3Store("s3://raw", R2)
        self.assertIn("budget job", str(cm.exception))

    def test_metered_store_refuses_before_the_request(self):
        model = boto3.client("s3", region_name="auto", aws_access_key_id="k",
                             aws_secret_access_key="s").meta.service_model
        if "IfNoneMatch" not in model.operation_model("PutObject").input_shape.members:
            self.skipTest("botocore older than 1.35: the store refuses to start at all")
        policy, job = self.load()
        session = mock.Mock(policy=policy, meter=b.Meter(policy, job, job["per_run"], 60))
        b.ACTIVE = session
        with mock.patch.dict(os.environ, FAKE, clear=False):
            st = sa.S3Store("s3://raw", R2)
        with Stubber(st.s3) as stub:  # no response queued: any request that got through would fail
            with self.assertRaises(b.BudgetError):
                st.s3.delete_object(Bucket="raw", Key=KEY)
            with self.assertRaises(b.BudgetError):
                st.s3.get_object(Bucket="raw", Key="not/pinned")
            stub.assert_no_pending_responses()
        self.assertEqual(session.meter.calls, 0)


if __name__ == "__main__":
    unittest.main()
