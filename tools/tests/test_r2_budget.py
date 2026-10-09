"""Spend limits (tools/r2_budget.py): run control, admission, reservation ledger, settlement, meter.

Ledger logic runs on a local write-once store; end-to-end runs use an in-process S3 stub (s3_stub.py)
that logs every HTTP request, so the tests compare what the server received with what the ledger
recorded. What must hold:
- before any read, a run is admitted by a durable record; every request it makes before reserving
  is bounded by the admission limits; an admission whose run never settles counts against the caps,
  so a refused run that is repeated is paid for each time;
- once the month's admissions are used up, a run stops after two HEADs (none on a machine that has
  seen the closure); a second run on the same machine is refused without any request;
- a reservation counts in full until its run settles; a settlement counts the worst case of its own
  write (every attempt), so a retried settlement never under-reports;
- a ledger that cannot be listed, read or verified stops the run; every request outside the job or
  over a limit is refused before it is sent.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r2_budget as b  # noqa: E402
import source_archive as sa  # noqa: E402

try:
    import boto3  # noqa: F401
    from botocore.stub import Stubber
    _model = boto3.client("s3", region_name="auto", aws_access_key_id="k",
                          aws_secret_access_key="s").meta.service_model
    HAVE_BOTO = "IfNoneMatch" in _model.operation_model("PutObject").input_shape.members
except ImportError:
    HAVE_BOTO = False

R2 = "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
FAKE = {"R2_ACCESS_KEY_ID": "k" * 32, "R2_SECRET_ACCESS_KEY": "s" * 64}
EMU = {"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing"}
BODY = b"pinned original"
KEY = sa.object_key(hashlib.sha256(BODY).hexdigest())
MONTH = b.now_utc().strftime("%Y-%m")
ADMISSION = {"put_bytes": 12288, "get_bytes": 100000, "class_a": 8, "class_b": 110, "retries": 3, "seconds": 120}
PER_RUN = {"put_bytes": 40000, "get_bytes": 200000, "class_a": 30, "class_b": 200, "retries": 12, "seconds": 600}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gate_dir = self.root / "gate"
        listing = self.root / "listing.json"
        listing.write_text(json.dumps({"listing_rule": "key-sha256-v1", "keys": 1,
                                       "objects": {KEY: hashlib.sha256(BODY).hexdigest()}}))
        self.listing = listing
        self.policy_path = self.root / "policy.json"
        self.write_policy()
        self.job_path = self.root / "job.json"
        self.write_job()
        self.ledger_store = sa.LocalStore(self.root / "ledger")

    def write_policy(self, per_month_global=0, max_runs_per_hour=1000, **caps):
        c = {"put_bytes": 10**9, "get_bytes": 10**9, "class_a": 1000, "class_b": 10**6, "retries": 1000,
             "seconds": 10**6}
        c.update(caps)
        self.policy_path.write_text(json.dumps({
            "ledger_bucket": "ledger", "caps": c,
            "per_request": {"max_object_bytes": 1024, "max_attempts": 3, "reserve_attempts": 3,
                            "max_ledger_records": 100},
            "admission": {"limits": ADMISSION, "per_month_global": per_month_global},
            "local_gate": {"max_runs_per_hour": max_runs_per_hour}}))

    def write_job(self, admissions_per_month=0, **caps):
        jc = {"put_bytes": 10**7, "get_bytes": 10**8, "class_a": 90, "class_b": 10**5, "retries": 10**3,
              "seconds": 10**5}  # class_a is the dimension the tests exhaust
        jc.update(caps)
        self.job_path.write_text(json.dumps({
            "job_id": "t", "admissions_per_month": admissions_per_month,
            "buckets": {"raw": {"listing": str(self.listing), "listing_sha256": b.sha256_file(self.listing)}},
            "job_caps": jc, "run_profiles": {"verify": PER_RUN}}))

    def tearDown(self):
        b.ACTIVE = None
        self.tmp.cleanup()

    def load(self):
        policy = b.load_policy(self.policy_path)
        return policy, b.load_job(self.job_path, policy)

    def reserve(self, store=None, run_id="run", admissions=()):
        policy, job = self.load()
        return b.reserve(b.Ledger(store or self.ledger_store, policy), policy, job, run_id, MONTH, list(admissions))

    def settle(self, ledger, rec, run_id, **amounts):
        count, prev = ledger.tail()
        a = {d: 0 for d in b.DIMENSIONS}
        a.update(amounts)
        ledger.append({"kind": "settlement", "job_id": "t", "run_id": run_id, "reservation_seq": rec["seq"],
                       "at": f"{MONTH}-09T00:00:00Z", "amounts": a}, count, prev)


class Reservation(Fixture):
    def test_reservation_is_written_before_work(self):
        rec, _, remaining = self.reserve()
        self.assertEqual((rec["seq"], rec["kind"], rec["amounts"]["class_a"]), (1, "reservation", 30))
        self.assertEqual(remaining["class_a"], 1000 - 30)

    def test_reruns_stop_at_the_job_cap(self):
        for i in range(3):
            self.reserve(run_id=f"r{i}")
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("job t", str(cm.exception))
        self.assertEqual(len(self.ledger_store.list(b.LEDGER_PREFIX)), 3)

    def test_global_cap_applies_across_jobs(self):
        self.write_policy(class_a=45)
        self.reserve()
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("global class_a", str(cm.exception))

    def test_reservations_leave_room_for_the_admissions_still_allowed(self):
        self.write_job(admissions_per_month=3)  # 3 x 8 class A must stay free: 90 - 24 = 66 -> 2 runs
        self.reserve(run_id="r1")
        self.reserve(run_id="r2")
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve(run_id="r3")
        self.assertIn("admission room", str(cm.exception))

    def test_settlement_returns_unused_allowance_only_up_to_the_reservation(self):
        policy, job = self.load()
        ledger = b.Ledger(self.ledger_store, policy)
        rec, _, _ = b.reserve(ledger, policy, job, "r1", MONTH, [])
        self.settle(ledger, rec, "r1", class_a=2)
        rec2, _, _ = b.reserve(ledger, policy, job, "r2", MONTH, [])
        self.settle(ledger, rec2, "r2", class_a=999)  # a settlement above the reservation is capped
        records, _ = ledger.read()
        _, used = b.Ledger.usage(records, "t", MONTH)
        self.assertEqual(used["class_a"], 2 + 30)

    def test_unsettled_runs_count_in_full_and_settlements_must_match_their_run(self):
        policy, job = self.load()
        ledger = b.Ledger(self.ledger_store, policy)
        b.reserve(ledger, policy, job, "r1", MONTH, [])  # crashed: never settled
        rec2, _, _ = b.reserve(ledger, policy, job, "r2", MONTH, [])
        self.settle(ledger, rec2, "someone-else")       # wrong run id: ignored
        records, _ = ledger.read()
        _, used = b.Ledger.usage(records, "t", MONTH)
        self.assertEqual(used["class_a"], 60)

    def test_unsettled_admissions_count_at_the_admission_limits_in_every_month(self):
        admissions = [(MONTH, "t", "a1"), ("2001-01", "t", "a2"), (MONTH, "other", "a3"), (MONTH, "t", "settled")]
        records = [{"kind": "reservation", "seq": 1, "run_id": "settled", "job_id": "t", "at": f"{MONTH}-09T00:00:00Z",
                    "amounts": {d: 1 for d in b.DIMENSIONS}},
                   {"kind": "settlement", "seq": 2, "run_id": "settled", "reservation_seq": 1, "job_id": "t",
                    "amounts": {d: 1 for d in b.DIMENSIONS}}]
        glob, job = b.Ledger.usage(records, "t", MONTH, admissions, ADMISSION)
        self.assertEqual(job["class_a"], 1 + 2 * ADMISSION["class_a"])        # a1 and last month's a2
        self.assertEqual(glob["class_a"], 1 + 2 * ADMISSION["class_a"])       # a1 and a3; a2 is another month
        self.assertEqual(glob["put_bytes"], 1 + 3 * ADMISSION["put_bytes"])   # storage is all-time

    def test_parallel_run_loses_the_race_and_rechecks(self):
        self.reserve(run_id="r1")
        self.reserve(run_id="r2")  # one reservation left in the job
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
                    b.reserve(b.Ledger(store, policy), policy, job, "other", MONTH, [])
                return store.put_new(key, body, ctype)

        with self.assertRaises(b.BudgetError) as cm:
            b.reserve(b.Ledger(Racing(), policy), policy, job, "run", MONTH, [])
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
        self.reserve(run_id="r1")
        self.reserve(run_id="r2")
        (self.root / "ledger/ledger/v1/0000000001.json").unlink()
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("gap", str(cm.exception))

    def test_edited_record_breaks_the_chain(self):
        self.reserve(run_id="r1")
        self.reserve(run_id="r2")
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
        self.reserve(run_id="r2")  # same ledger: fine
        import shutil
        shutil.rmtree(self.root / "ledger")  # someone deletes every record
        with self.assertRaises(b.BudgetError) as cm:
            self.reserve()
        self.assertIn("genesis", str(cm.exception))

    def test_profile_that_cannot_pay_for_its_control_records_is_rejected(self):
        doc = json.loads(self.job_path.read_text())
        doc["run_profiles"]["verify"]["class_a"] = 13  # needs admission 8 + tail 3 + settlement 3 = 14
        self.job_path.write_text(json.dumps(doc))
        with self.assertRaises(b.BudgetError) as cm:
            b.load_job(self.job_path, b.load_policy(self.policy_path))
        self.assertIn("class_a 13 < 14", str(cm.exception))

    def test_changed_listing_invalidates_the_job(self):
        self.listing.write_text(self.listing.read_text().replace("}}", "}, \"extra\": 1}"))
        with self.assertRaises(b.BudgetError):
            b.load_job(self.job_path)

    def test_initialised_ledger_refuses_init_without_any_request(self):
        """init-pre-ledger used to read the whole ledger before refusing, with nothing recorded."""
        with mock.patch.object(sys, "argv", ["r2_budget.py", "init-pre-ledger", "--job", str(self.job_path),
                                             "--amounts", "x.json"]), \
                mock.patch.object(sa, "S3Store", side_effect=AssertionError("no store may be created")):
            with self.assertRaises(b.BudgetError) as cm:
                b._cli()  # the repository policy pins the genesis record
        self.assertIn("nothing was sent", str(cm.exception))


class LocalGateChecks(Fixture):
    def gate(self, **kw):
        self.write_policy(**kw)
        return b.LocalGate(b.load_policy(self.policy_path), "t", self.gate_dir)

    def test_second_run_on_the_same_machine_is_refused(self):
        g1, g2 = self.gate(), self.gate()
        g1.enter()
        with self.assertRaises(b.BudgetError) as cm:
            g2.enter()
        self.assertIn("in progress", str(cm.exception))
        g1.leave()
        g2.enter()
        g2.leave()

    def test_runs_per_hour(self):
        for _ in range(2):
            g = self.gate(max_runs_per_hour=2)
            g.enter()
            g.leave()
        with self.assertRaises(b.BudgetError) as cm:
            self.gate(max_runs_per_hour=2).enter()
        self.assertIn("last hour", str(cm.exception))

    def test_remembered_closure_and_corrupt_state(self):
        g = self.gate()
        g.remember_closed("t")
        with self.assertRaises(b.BudgetError) as cm:
            self.gate().enter()
        self.assertIn("remembered", str(cm.exception))
        (self.gate_dir / "r2_gate.json").write_text("{broken")
        with self.assertRaises(b.BudgetError) as cm:
            self.gate().enter()
        self.assertIn("unreadable", str(cm.exception))


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

    def test_no_archive_request_before_a_reservation(self):
        m = self.meter()
        m.archive_allowed = False
        with self.assertRaises(b.BudgetError) as cm:
            m.check_call("GetObject", {"Bucket": "raw", "Key": KEY}, "archive")
        self.assertIn("before a reservation", str(cm.exception))

    def test_ledger_role_is_confined(self):
        m = self.meter()
        with self.assertRaises(b.BudgetError):
            m.check_call("PutObject", {"Bucket": "ledger", "Key": "objects/x", "Body": b""}, "ledger")
        with self.assertRaises(b.BudgetError):
            m.check_call("GetObject", {"Bucket": "raw", "Key": "ledger/v1/1"}, "ledger")
        with self.assertRaises(b.BudgetError):
            m.check_call("HeadObject", {"Bucket": "ledger", "Key": "ledger/v1/1"}, "ledger")
        m.check_call("ListObjectsV2", {"Bucket": "ledger", "Prefix": "ledger/v1/"}, "ledger")
        m.check_call("HeadObject", {"Bucket": "ledger", "Key": "closed/v1/2026-10/t.json"}, "ledger")

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
        m.start -= 601
        with self.assertRaises(b.BudgetError) as cm:
            m.check_call("GetObject", {"Bucket": "raw", "Key": KEY}, "archive")
        self.assertIn("run time", str(cm.exception))


@unittest.skipUnless(HAVE_BOTO, "boto3 >= 1.35 not installed")
class EndToEnd(Fixture):
    """Real botocore requests against the S3 stub; the server log is the ground truth."""

    def setUp(self):
        super().setUp()
        from s3_stub import S3Stub
        self.stub = S3Stub()
        self.env = mock.patch.dict(os.environ, EMU, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.stub.stop()
        super().tearDown()

    def session(self, gate_dir=None):
        return b.Session(str(self.job_path), self.stub.endpoint, policy_path=self.policy_path,
                         gate_dir=gate_dir or self.gate_dir)

    def run_once(self, gate_dir):
        before = len(self.stub.log)
        with self.assertRaises(b.BudgetError) as cm:
            self.session(gate_dir).open()
        return str(cm.exception), self.stub.counts(before), self.stub.log[before:]

    def test_repeated_refused_runs_are_recorded_then_closed(self):
        """Finding 1: a run refused after reading the ledger left no trace, so repeating it was free.
        Now each refused run is admitted first and counted; when the job's admissions are used up a
        closure marker stops further runs after two HEADs, and none at all on a machine that saw it."""
        self.write_policy(per_month_global=100)
        self.write_job(admissions_per_month=4, class_a=40)  # 30 per run + 4 x 8 admission room never fits
        observed = []
        for i in range(4):
            msg, c, _log = self.run_once(self.root / f"gate{i}")  # a fresh machine each time
            self.assertIn("job t class_a", msg)
            observed.append(c)
        admissions = [k for (bk, k) in self.stub.objects if bk == "ledger" and k.startswith(b.ADMISSION_PREFIX)]
        self.assertEqual(len(admissions), 4)  # every refused run left a durable record
        self.assertIn(("ledger", f"{b.CLOSED_PREFIX}{MONTH}/t.json"), self.stub.objects)
        for c in observed:  # what each refused run really sent is within what its admission counts
            for d in ("class_a", "class_b", "put_bytes"):
                self.assertLessEqual(c[d], ADMISSION[d], d)
        policy, job = self.load()
        ledger = b.Ledger(sa.S3Store("s3://ledger", self.stub.endpoint, ledger=True), policy)
        glob, used = b.Ledger.usage([], "t", MONTH, ledger.admissions(), ADMISSION)
        for d in ("class_a", "class_b", "put_bytes"):
            self.assertGreaterEqual(used[d], sum(c[d] for c in observed), d)
        for i in range(3):  # after closure: two HEADs, nothing else, nothing written
            msg, c, log = self.run_once(self.root / f"late{i}")
            self.assertIn("closed", msg)
            self.assertEqual([k for k, *_ in log], ["head", "head"])
        msg, c, log = self.run_once(self.root / "late0")  # this machine has seen the closure
        self.assertIn("remembered", msg)
        self.assertEqual(log, [])
        self.assertEqual(len([k for (bk, k) in self.stub.objects if k.startswith(b.ADMISSION_PREFIX)]), 4)

    def test_settlement_retry_is_counted_in_the_settlement(self):
        """Finding 2: the settlement added one Class A for its own PUT; a retried PUT was missing."""
        self.write_policy(per_month_global=10)
        self.write_job(admissions_per_month=5)
        before = len(self.stub.log)
        s = self.session()
        s.open()
        self.stub.faults.append(("PUT", f"{b.LEDGER_PREFIX}0000000002.json", 503))  # settlement's first try
        rec = s.settle("ok")
        self.assertEqual(rec.get("seq"), 2, rec)
        log = self.stub.log[before:]
        put_attempts = [x for x in log if x[0] == "put" and x[2].endswith("0000000002.json")]
        self.assertEqual([x[3] for x in put_attempts], [503, 200])  # failed once, then succeeded
        seen = self.stub.counts(before)
        for d in ("class_a", "class_b", "put_bytes"):
            self.assertGreaterEqual(rec["amounts"][d], seen[d], d)
        self.assertGreaterEqual(rec["amounts"]["retries"], 1)
        records, _ = b.Ledger(sa.S3Store("s3://ledger", self.stub.endpoint, ledger=True), self.load()[0]).read()
        _, used = b.Ledger.usage(records, "t", MONTH)
        self.assertGreaterEqual(used["class_a"], seen["class_a"])

    def test_admitted_run_spends_within_its_admission_before_reserving(self):
        self.write_policy(per_month_global=10)
        self.write_job(admissions_per_month=5)
        before = len(self.stub.log)
        s = self.session()
        s.open()
        seen = self.stub.counts(before)
        for d in ("class_a", "class_b", "put_bytes"):
            self.assertLessEqual(seen[d], ADMISSION[d], d)
        kinds = [k for k, *_ in self.stub.log[before:]]
        self.assertEqual(kinds[:3], ["head", "head", "put"])  # closure check, then the admission, then reads
        s.settle("ok")


@unittest.skipUnless(HAVE_BOTO, "boto3 >= 1.35 not installed")
class StoreNeedsBudget(Fixture):
    def test_r2_without_a_job_sends_nothing(self):
        with mock.patch.dict(os.environ, FAKE, clear=False):
            with self.assertRaises(SystemExit) as cm:
                sa.S3Store("s3://raw", R2)
        self.assertIn("budget job", str(cm.exception))

    def test_metered_store_refuses_before_the_request(self):
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
