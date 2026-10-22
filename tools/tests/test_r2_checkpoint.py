"""Ledger checkpoints (tools/r2_budget.py, infra/r2/checkpoint/DESIGN.md) and the bucket lock rules (O14).

What must hold:
- usage computed from a checkpoint plus the records after it equals usage computed from every record
  (settled, unsettled, stale, old months, pre-ledger, admissions of settled and unsettled runs), for
  one checkpoint and for a chain of two;
- a run's reads after a checkpoint do not grow with the ledger (one GET for the checkpoint, one per later
  record, one for the checkpoint's own last record when nothing follows it), and the record limit applies
  to the records after the checkpoint;
- a checkpoint that is malformed, from another policy or genesis, not the ledger's, or that understates
  the ledger is not trusted: runs stop, and `audit` recomputes it from the raw records;
- two checkpoint writers cannot diverge (write-once key); a checkpoint too big for the status profile is
  not written; the meter lets the ledger role touch checkpoint/ but still not HEAD it;
- a run settles correctly even when a checkpoint was written during the run;
- the lock rule file has no indefinite lock, is a proposal (nothing applied), and the checker rejects
  indefinite, unbounded or unapproved variants; nothing under infra/r2/checkpoint holds a secret.
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r2_budget as b  # noqa: E402
import source_archive as sa  # noqa: E402
import test_r2_budget as base  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CP_DIR = ROOT / "infra/r2/checkpoint"
MONTH = base.MONTH
DIMS = b.DIMENSIONS


def amounts(**kw):
    a = {d: 0 for d in DIMS}
    a.update(kw)
    return a


class Counting(sa.LocalStore):
    """Wraps a local store and records what a run asks of it."""

    def __init__(self, st):
        super().__init__(st.root)
        self.st, self.gets, self.lists = st, [], []

    def get(self, key):
        self.gets.append(key)
        return self.st.get(key)

    def list(self, prefix):
        self.lists.append(prefix)
        return self.st.list(prefix)

    def put_new(self, key, body, ctype):
        return self.st.put_new(key, body, ctype)

    def exists(self, key):
        return self.st.exists(key)


class LedgerFixture(base.Fixture):
    def setUp(self):
        super().setUp()
        self.write_policy(per_month_global=50, class_a=10**7)
        self.write_job(admissions_per_month=50, class_a=10**7, put_bytes=10**9)
        self.policy, self.job = self.load()
        self.ledger = b.Ledger(self.ledger_store, self.policy)

    def runs(self, n, ledger=None, settle=True, first=0, at=None, job_id="t", month=MONTH):
        """n runs appended directly (reserve, then settle). Returns the run ids."""
        ledger = ledger or self.ledger
        count, prev = ledger.tail() if self.ledger_store.list(b.LEDGER_PREFIX) else (0, None)
        ids = []
        for i in range(first, first + n):
            run = f"run{i:04d}"
            at_i = at or f"{month}-09T00:00:{i % 60:02d}Z"
            rec, prev = ledger.append({"kind": "reservation", "job_id": job_id, "run_id": run, "at": at_i,
                                       "amounts": amounts(class_a=30, class_b=20, put_bytes=1000, get_bytes=500,
                                                          retries=2, seconds=60)}, count, prev)
            count += 1
            if settle:
                _rec, prev = ledger.append({"kind": "settlement", "job_id": job_id, "run_id": run,
                                            "reservation_seq": rec["seq"], "at": at_i,
                                            "amounts": amounts(class_a=2 + i % 5, class_b=3, put_bytes=100 + i,
                                                               get_bytes=50, seconds=5)}, count, prev)
                count += 1
            ids.append(run)
        return ids

    def fresh(self, store=None):
        return b.Ledger(store or self.ledger_store, self.policy)

    def checkpoint(self, at=None, store=None):
        led = self.fresh(store)
        out = b.write_checkpoint(led, at)
        return led, out


class Equivalence(LedgerFixture):
    """The checkpoint is a summary: it must not change what the caps see."""

    def scenario(self):
        led = self.ledger
        # pre-ledger usage first, like the real ledger, then a month long gone, then this month
        led.append({"kind": "pre_ledger_usage", "job_id": "t", "run_id": "pre-ledger", "at": "2001-01-05T00:00:00Z",
                    "amounts": amounts(put_bytes=5000, class_a=9, class_b=9, get_bytes=77, seconds=3)}, 0, None)
        self.runs(3, month="2001-01", first=0)                      # settled, old month
        self.runs(2, month=MONTH, first=10)                         # settled, this month
        self.runs(1, settle=False, month=MONTH, first=20)           # unsettled and recent
        self.runs(1, settle=False, at="2001-02-01T00:00:00Z", first=21)  # unsettled and dead for years
        self.runs(2, job_id="other", month=MONTH, first=30)         # another job
        self.runs(2, month=MONTH, first=40)
        records, _ = self.fresh().read(full=True)
        # the stale one belongs to an old month; the recent one is stamped with the real clock below
        for r in records:
            if r.get("run_id") == "run0020":
                r["at"] = f"{MONTH}-09T00:00:30Z"
        admissions = [(m, j, run) for run, m, j in [
            ("run0000", "2001-01", "t"), ("run0010", MONTH, "t"), ("run0011", MONTH, "t"), ("run0020", MONTH, "t"),
            ("run0021", "2001-02", "t"), ("run0030", MONTH, "other"), ("run0040", MONTH, "t")]]
        admissions += [(MONTH, "t", "refused1"), ("2001-01", "t", "refused2"), (MONTH, "other", "refused3"),
                       ("2001-03", "other", "refused4")]  # runs that never reserved
        return records, admissions

    def usage(self, records, month, admissions, base_cp=None):
        return b.Ledger.usage(records, "t", month, admissions, base.ADMISSION, base_cp)

    @staticmethod
    def soon_after(record):
        """A checkpoint is written shortly after the last record it covers."""
        return (b.dt.datetime.strptime(record["at"], "%Y-%m-%dT%H:%M:%SZ") + b.dt.timedelta(hours=1)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")

    def cp(self, prev_cp, records, admissions, upto, at):
        return {"month": b.month_of(at), "seq": upto, "state": b.checkpoint_state(prev_cp, records, admissions, at)}

    def test_checkpoint_plus_tail_equals_all_records(self):
        records, admissions = self.scenario()
        for read_month in (MONTH, "2099-01"):
            want = self.usage(records, read_month, admissions)
            for cut in range(1, len(records)):
                cp = self.cp(None, records[:cut], admissions, cut, self.soon_after(records[cut - 1]))
                got = self.usage(records[cut:], read_month, admissions, cp)
                self.assertEqual(got, want, f"cut {cut} read month {read_month}")

    def test_a_chain_of_two_checkpoints_equals_all_records(self):
        records, admissions = self.scenario()
        want = self.usage(records, MONTH, admissions)
        for c1 in range(1, len(records) - 2, 3):
            cp1 = self.cp(None, records[:c1], admissions, c1, self.soon_after(records[c1 - 1]))
            for c2 in range(c1 + 1, len(records), 4):
                cp2 = self.cp(cp1, records[c1:c2], admissions, c2, self.soon_after(records[c2 - 1]))
                self.assertEqual(self.usage(records[c2:], MONTH, admissions, cp2), want, (c1, c2))

    def test_months_before_the_checkpoint_are_folded_into_job_totals(self):
        records, admissions = self.scenario()
        state = b.checkpoint_state(None, records, admissions, b.stamp())
        self.assertTrue(any(t["month"] == "past" for t in state["totals"]))
        self.assertTrue(all(t["month"] in ("past", MONTH) for t in state["totals"]))
        self.assertLess(len(json.dumps(state)), b.CHECKPOINT_BYTES)

    def test_open_reservation_settles_after_the_checkpoint(self):
        self.runs(2)
        self.runs(1, settle=False, at=b.stamp(), first=5)       # run0005: open at the checkpoint
        records, prev = self.fresh().read(full=True)
        cp = self.cp(None, records, [], len(records), b.stamp())
        self.assertEqual([r["run_id"] for r in cp["state"]["open"]], ["run0005"])
        self.ledger.append({"kind": "settlement", "job_id": "t", "run_id": "run0005",
                            "reservation_seq": records[-1]["seq"], "at": b.stamp(),
                            "amounts": amounts(class_a=1)}, len(records), prev)
        after, _ = self.fresh().read(full=True)
        got = self.usage(after[len(records):], MONTH, [], cp)
        self.assertEqual(got, self.usage(after, MONTH, []))
        self.assertEqual(got[1]["class_a"], 2 + 3 + 1)           # two settled runs (2 and 3) and the late one (1)

    def test_a_late_settlement_of_a_dead_reservation_is_ignored(self):
        self.runs(1, settle=False, at="2001-02-01T00:00:00Z")
        records, _ = self.fresh().read(full=True)
        cp = self.cp(None, records, [], 1, b.stamp())
        self.assertEqual(cp["state"]["open"], [])
        late = {"kind": "settlement", "run_id": "run0000", "reservation_seq": 1, "amounts": amounts(class_a=1)}
        full = self.usage(records, MONTH, [])
        self.assertEqual(self.usage([dict(late, seq=2)], MONTH, [], cp)[1]["class_a"], 30)
        self.assertEqual(full[1]["class_a"], 30)


class Reads(LedgerFixture):
    def test_no_checkpoint_behaves_as_before(self):
        self.runs(3)
        records, _ = self.fresh().read()
        self.assertEqual(len(records), 6)
        self.runs(48, first=3)
        with self.assertRaises(b.BudgetError) as cm:
            self.fresh().read()
        self.assertIn("checkpoint before running", str(cm.exception))

    def test_checkpoint_then_more_records(self):
        self.runs(49)
        led, out = self.checkpoint()
        self.assertEqual(out["status"], "written")
        self.assertEqual(out["seq"], 98)
        self.runs(30, first=49)                          # records 99..158
        counting = Counting(self.ledger_store)
        led = self.fresh(counting)
        records, prev = led.read()
        self.assertEqual((led.base_seq, len(records), records[0]["seq"], records[-1]["seq"]), (98, 60, 99, 158))
        self.assertEqual(sum(k.startswith(b.LEDGER_PREFIX) for k in counting.gets), 60)
        self.assertEqual(sum(k.startswith(b.CHECKPOINT_PREFIX) for k in counting.gets), 1)
        self.assertIn(b.CHECKPOINT_PREFIX, counting.lists)
        rec, _sha, _left = b.reserve(led, self.policy, self.job, "next", MONTH, [])
        self.assertEqual(rec["seq"], 159)
        self.assertEqual(led.tail()[0], 159)

    def test_reads_do_not_grow_with_the_age_of_the_ledger(self):
        self.runs(49)
        self.checkpoint()
        self.runs(1, first=49)
        gets = []
        for extra in (0, 3):
            self.runs(extra, first=100 + extra)
            counting = Counting(self.ledger_store)
            self.fresh(counting).read()
            gets.append(len(counting.gets))
        self.assertEqual(gets[0] + 2 * 3, gets[1])       # only the records after the checkpoint cost a GET

    def test_nothing_after_the_checkpoint_costs_two_gets(self):
        self.runs(5)
        self.checkpoint()
        counting = Counting(self.ledger_store)
        led = self.fresh(counting)
        records, prev = led.read()
        self.assertEqual(records, [])
        self.assertEqual(prev, led.base["tail_sha256"])
        self.assertEqual(len(counting.gets), 2)          # the checkpoint and its last ledger record

    def test_record_limit_applies_after_the_checkpoint(self):
        self.runs(49)
        self.checkpoint()
        self.runs(51, first=49)                          # 102 more records
        with self.assertRaises(b.BudgetError) as cm:
            self.fresh().read()
        self.assertIn("after the last checkpoint", str(cm.exception))

    def test_listing_follows_full_blocks(self):
        def fake(keys):
            class S:
                lists = []

                def list(self, prefix):
                    self.lists.append(prefix)
                    return sorted(k for k in keys if k.startswith(prefix))
            return S()
        key = lambda i: f"{b.LEDGER_PREFIX}{i:010d}.json"  # noqa: E731
        led = b.Ledger(fake([key(i) for i in range(1, 1006)]), self.policy)
        led.base, led.base_seq = {"tail_sha256": "x"}, 998
        keys = led._segment_keys()
        self.assertEqual((keys[0], keys[-1], len(keys)), (key(999), key(1005), 7))
        self.assertEqual(led.st.lists, [f"{b.LEDGER_PREFIX}0000000", f"{b.LEDGER_PREFIX}0000001"])
        led2 = b.Ledger(fake([key(i) for i in range(1, 15)]), self.policy)
        led2.base, led2.base_seq = {"tail_sha256": "x"}, 10
        self.assertEqual(len(led2._segment_keys()), 4)
        self.assertEqual(led2.st.lists, [f"{b.LEDGER_PREFIX}0000000"])

    def test_listing_stops_when_the_tail_ends_at_a_block_boundary(self):
        # "Full" is judged from the block just listed, not from the accumulated keys: a tail ending at
        # seq % 1000 == 999 must still stop after the next (empty) block, not list blocks forever.
        def fake(keys):
            class S:
                lists = []

                def list(self, prefix):
                    self.lists.append(prefix)
                    return sorted(k for k in keys if k.startswith(prefix))
            return S()
        key = lambda i: f"{b.LEDGER_PREFIX}{i:010d}.json"  # noqa: E731
        led = b.Ledger(fake([key(i) for i in range(1, 2000)]), self.policy)
        led.base, led.base_seq = {"tail_sha256": "x"}, 1500
        keys = led._segment_keys()
        self.assertEqual((keys[0], keys[-1], len(keys)), (key(1501), key(1999), 499))
        self.assertEqual(led.st.lists, [f"{b.LEDGER_PREFIX}0000001", f"{b.LEDGER_PREFIX}0000002"])
        led2 = b.Ledger(fake([key(i) for i in range(1, 2000)]), self.policy)
        led2.base, led2.base_seq = {"tail_sha256": "x"}, 1999      # checkpoint at the tail itself
        self.assertEqual(led2._segment_keys(), [])
        self.assertEqual(led2.st.lists, [f"{b.LEDGER_PREFIX}0000002"])
        led3 = b.Ledger(fake([key(i) for i in range(1, 2000)]), self.policy)
        led3.base, led3.base_seq = {"tail_sha256": "x"}, 1990      # same edge with a read limit
        self.assertEqual(len(led3._segment_keys(limit=100)), 9)
        self.assertEqual(led3.st.lists, [f"{b.LEDGER_PREFIX}0000001", f"{b.LEDGER_PREFIX}0000002"])


class Distrust(LedgerFixture):
    def setUp(self):
        super().setUp()
        self.runs(5)
        self.led, _ = self.checkpoint()
        self.cp_key = f"{b.CHECKPOINT_PREFIX}{10:010d}.json"
        self.cp_path = self.ledger_store.root / self.cp_key

    def edit(self, fn):
        doc = json.loads(self.cp_path.read_text())
        fn(doc)
        self.cp_path.write_text(json.dumps(doc))

    def refuses(self, text):
        with self.assertRaises(b.BudgetError) as cm:
            self.fresh().read()
        self.assertIn(text, str(cm.exception))

    def test_good_checkpoint_is_read(self):
        self.assertEqual(self.fresh().read()[0], [])

    def test_malformed(self):
        self.cp_path.write_text("not json")
        self.refuses("not JSON")
        self.cp_path.write_text(json.dumps({"format": "x"}))
        self.refuses("malformed")

    def test_key_and_document_must_agree(self):
        self.edit(lambda d: d.__setitem__("seq", 9))
        self.refuses("malformed")

    def test_unknown_policy(self):
        self.edit(lambda d: d.__setitem__("policy_sha256", "0" * 64))
        self.refuses("unknown policy")

    def test_genesis_pin(self):
        policy = dict(self.policy, ledger_genesis_sha256="1" * 64)
        with self.assertRaises(b.BudgetError) as cm:
            b.Ledger(self.ledger_store, policy).read()
        self.assertIn("genesis", str(cm.exception))

    def test_foreign_key_among_checkpoints(self):
        self.ledger_store.put_new(f"{b.CHECKPOINT_PREFIX}notes.txt", b"x", "text/plain")
        self.refuses("foreign key")

    def test_the_last_record_replaced_or_removed_after_the_checkpoint(self):
        last = self.ledger_store.root / f"{b.LEDGER_PREFIX}{10:010d}.json"
        original = last.read_bytes()
        last.write_bytes(original + b" ")
        self.refuses("missing or was replaced")
        last.unlink()
        self.refuses("unreadable")

    def test_a_record_after_the_checkpoint_must_chain_to_it(self):
        self.led.append({"kind": "reservation", "job_id": "t", "run_id": "x", "at": b.stamp(), "amounts": amounts()},
                        10, "f" * 64)
        self.refuses("chain broken")

    def test_checkpoint_ahead_of_the_ledger(self):
        (self.ledger_store.root / f"{b.LEDGER_PREFIX}{10:010d}.json").unlink()
        (self.ledger_store.root / f"{b.LEDGER_PREFIX}{9:010d}.json").unlink()
        self.refuses("unreadable")

    def test_audit_accepts_an_honest_chain_and_catches_an_understating_checkpoint(self):
        self.runs(5, first=5)
        self.checkpoint()                                  # second checkpoint at 20
        out = b.audit_checkpoints(self.fresh())
        self.assertEqual((out["checkpoints"], out["records"], out["last_checkpoint_seq"]), (2, 20, 20))
        second = self.ledger_store.root / f"{b.CHECKPOINT_PREFIX}{20:010d}.json"
        doc = json.loads(second.read_text())
        for t in doc["state"]["totals"]:
            t["amounts"] = [0] * len(DIMS)                 # a checkpoint that hides all usage
        second.write_text(json.dumps(doc))
        with self.assertRaises(b.BudgetError) as cm:
            b.audit_checkpoints(self.fresh())
        self.assertIn("summary differs", str(cm.exception))

    def test_audit_catches_a_broken_chain_and_a_wrong_tail(self):
        self.runs(2, first=5)
        self.checkpoint()
        second = self.ledger_store.root / f"{b.CHECKPOINT_PREFIX}{14:010d}.json"
        doc = json.loads(second.read_text())
        good = json.dumps(doc)
        doc["prev_checkpoint"]["sha256"] = "2" * 64
        second.write_text(json.dumps(doc))
        with self.assertRaises(b.BudgetError) as cm:
            b.audit_checkpoints(self.fresh())
        self.assertIn("chain broken", str(cm.exception))
        doc = json.loads(good)
        doc["tail_sha256"] = "3" * 64
        second.write_text(json.dumps(doc))
        with self.assertRaises(b.BudgetError) as cm:
            b.audit_checkpoints(self.fresh())
        self.assertIn("tail hash", str(cm.exception))


class Writing(LedgerFixture):
    def test_nothing_new_writes_nothing(self):
        self.runs(2)
        self.checkpoint()
        _, out = self.checkpoint()
        self.assertEqual(out, {"status": "nothing_new", "seq": 4})
        self.assertEqual(len(self.ledger_store.list(b.CHECKPOINT_PREFIX)), 1)

    def test_checkpoint_is_write_once_and_a_second_writer_may_agree_but_not_diverge(self):
        self.runs(3)
        first, second, third = self.fresh(), self.fresh(), self.fresh()
        stale, stale_prev = second.read()                    # both read the ledger before the first wrote
        seen, seen_prev = third.read()
        self.assertEqual(b.write_checkpoint(first)["status"], "written")
        with mock.patch.object(second, "read", return_value=(stale, stale_prev)):
            self.assertEqual(b.write_checkpoint(second)["status"], "already_present")
        liar = seen[:-1] + [dict(seen[-1], amounts=amounts(class_a=1))]   # a writer that saw other history
        with mock.patch.object(third, "read", return_value=(liar, seen_prev)):
            with self.assertRaises(b.BudgetError) as cm:
                b.write_checkpoint(third)
        self.assertIn("different checkpoint", str(cm.exception))
        self.assertEqual(len(self.ledger_store.list(b.CHECKPOINT_PREFIX)), 1)

    def test_a_checkpoint_too_big_for_the_profile_is_not_written(self):
        self.runs(3)
        with mock.patch.object(b, "CHECKPOINT_BYTES", 200):
            with self.assertRaises(b.BudgetError) as cm:
                b.write_checkpoint(self.fresh())
        self.assertIn("nothing was written", str(cm.exception))
        self.assertEqual(self.ledger_store.list(b.CHECKPOINT_PREFIX), [])

    def test_realistic_state_fits_with_room_to_spare(self):
        self.runs(20, month="2026-01")
        self.runs(20, month=MONTH, first=20, job_id="other")
        self.runs(10, month=MONTH, first=40, settle=False, at=b.stamp())
        out = b.write_checkpoint(self.fresh())
        self.assertLess(out["bytes"], b.CHECKPOINT_BYTES // 2)

    def test_second_checkpoint_chains_to_the_first(self):
        self.runs(2)
        led, _ = self.checkpoint()
        self.runs(2, first=2)
        led, out = self.checkpoint()
        doc = json.loads((self.ledger_store.root / f"{b.CHECKPOINT_PREFIX}{out['seq']:010d}.json").read_text())
        self.assertEqual(doc["prev_checkpoint"]["seq"], 4)
        self.assertEqual(doc["prev_checkpoint"]["sha256"], led.base_sha)
        self.assertEqual(doc["seq"], 8)


class MeterAndProfiles(LedgerFixture):
    def test_ledger_role_may_touch_checkpoints_but_not_head_them(self):
        policy, job = self.load()
        m = b.Meter(policy, job, job["per_run"], 600)
        m.check_call("GetObject", {"Bucket": "ledger", "Key": f"{b.CHECKPOINT_PREFIX}{1:010d}.json"}, "ledger")
        m.check_call("ListObjectsV2", {"Bucket": "ledger", "Prefix": b.CHECKPOINT_PREFIX}, "ledger")
        m.check_call("PutObject", {"Bucket": "ledger", "Key": f"{b.CHECKPOINT_PREFIX}{1:010d}.json", "Body": b"{}"},
                     "ledger")
        with self.assertRaises(b.BudgetError):
            m.check_call("HeadObject", {"Bucket": "ledger", "Key": f"{b.CHECKPOINT_PREFIX}{1:010d}.json"}, "ledger")
        with self.assertRaises(b.BudgetError):
            m.check_call("GetObject", {"Bucket": "ledger", "Key": "checkpoints/v1/x"}, "ledger")

    def test_shipped_status_profile_can_pay_for_a_checkpoint_write(self):
        policy = b.load_policy()
        job = b.load_job(str(ROOT / "infra/r2/jobs/initial-119.json#status"), policy)
        need = (policy["admission"]["limits"]["put_bytes"] + b.settlement_worst_case(policy)["put_bytes"]
                + b.CHECKPOINT_BYTES)
        self.assertGreaterEqual(job["per_run"]["put_bytes"], need)
        self.assertLessEqual(policy["admission"]["limits"]["class_a"] + 3 + 1, job["per_run"]["class_a"])


@unittest.skipUnless(base.HAVE_BOTO, "boto3>=1.35 needed")
class EndToEnd(base.Fixture):
    """Real botocore requests against the S3 stub; the server log is the ground truth."""

    def setUp(self):
        super().setUp()
        from s3_stub import S3Stub
        self.stub = S3Stub()
        self.env = mock.patch.dict(os.environ, base.EMU, clear=False)
        self.env.start()
        self.write_policy(per_month_global=50, class_a=10**7)
        self.write_job(admissions_per_month=50, class_a=10**7, put_bytes=10**9)

    def tearDown(self):
        self.env.stop()
        self.stub.stop()
        super().tearDown()

    def run_session(self, n, checkpoint=False, tag="g"):
        out = []
        for i in range(n):
            s = b.Session(str(self.job_path), self.stub.endpoint, policy_path=self.policy_path,
                          gate_dir=self.root / f"{tag}{i}")
            s.open()
            if checkpoint:
                out.append(b.write_checkpoint(s.ledger))
            s.settle("ok")
        return out

    def ledger_gets(self, before):
        return [x[2] for x in self.stub.log[before:] if x[0] == "get" and x[3] == 200 and x[2].startswith(b.LEDGER_PREFIX)]

    def test_runs_after_a_checkpoint_read_only_what_follows_it(self):
        self.run_session(8)                                    # records 1..16
        out = self.run_session(1, checkpoint=True, tag="c")    # reservation 17, checkpoint 17, settlement 18
        self.assertEqual(out[0]["status"], "written")
        self.assertEqual(out[0]["seq"], 17)
        before = len(self.stub.log)
        self.run_session(1, tag="n")
        gets = self.ledger_gets(before)
        self.assertTrue(all(int(g[-15:-5]) > 17 for g in gets), gets)   # nothing at or before the checkpoint
        self.assertLessEqual(len(gets), 4)

    def test_settlement_after_a_checkpoint_written_during_the_run(self):
        self.run_session(3)
        s = b.Session(str(self.job_path), self.stub.endpoint, policy_path=self.policy_path, gate_dir=self.root / "g")
        s.open()
        out = b.write_checkpoint(s.ledger)
        rec = s.settle("ok")
        self.assertEqual((out["seq"], rec["seq"]), (7, 8))
        led = b.Ledger(sa.S3Store("s3://ledger", self.stub.endpoint, ledger=True), s.policy)
        records, _ = led.read()
        self.assertEqual([r["seq"] for r in records], [8])
        _, used = b.Ledger.usage(records, "t", MONTH, [], base.ADMISSION, led.base)
        self.assertLess(used["class_a"], 4 * base.PER_RUN["class_a"])      # settled runs count what they measured
        self.assertEqual(b.audit_checkpoints(led)["checkpoints"], 1)

    def test_meter_charges_the_checkpoint_write(self):
        self.run_session(2)
        s = b.Session(str(self.job_path), self.stub.endpoint, policy_path=self.policy_path, gate_dir=self.root / "g")
        s.open()
        before_put = s.meter.snapshot()["put_bytes"]
        out = b.write_checkpoint(s.ledger)
        self.assertEqual(s.meter.snapshot()["put_bytes"] - before_put, out["bytes"])
        s.settle("ok")


class LockRules(unittest.TestCase):
    def doc(self):
        return json.loads((CP_DIR / "lock_rules.json").read_text(encoding="utf-8"))

    def test_shipped_rules_are_a_proposal_without_any_indefinite_lock(self):
        d = self.doc()
        self.assertEqual(b.check_lock_rules(d), [])
        self.assertEqual(d["status"], "proposed_not_applied")
        self.assertIsNone(d["approval"])
        for r in d["rules"]:
            self.assertEqual(r["condition"]["type"], "Age", r["id"])
            self.assertFalse(r["enabled"], r["id"])
            days = r["condition"]["max_age_days"]
            self.assertTrue(days is None or 1 <= days <= b.MAX_LOCK_DAYS, r["id"])

    def test_proposal_covers_the_o14_targets(self):
        pairs = {(r["bucket"], r["prefix"]) for r in self.doc()["rules"]}
        for want in [("onjeon-raw-sources", "objects/"), ("onjeon-raw-sources", "observations/"),
                     ("onjeon-budget-ledger", "ledger/v1/"), ("onjeon-budget-ledger", "checkpoint/v1/")]:
            self.assertIn(want, pairs)

    def test_checker_rejects_indefinite_and_unbounded_locks(self):
        for cond in ({"type": "Indefinite"}, {"type": "Date", "date": "2030-01-01"},
                     {"type": "Age", "max_age_days": 0}, {"type": "Age", "max_age_days": -1},
                     {"type": "Age", "max_age_days": b.MAX_LOCK_DAYS + 1}, {"type": "Age", "max_age_days": True},
                     {"type": "Age", "max_age_days": "forever"}, {}):
            d = self.doc()
            d["rules"][0]["condition"] = cond
            self.assertTrue(b.check_lock_rules(d), cond)

    def test_checker_rejects_unapproved_or_incomplete_approval(self):
        d = self.doc()
        d["status"] = "approved"
        self.assertTrue(any("unset" in p for p in b.check_lock_rules(d)))
        for r in d["rules"]:
            r["condition"]["max_age_days"] = 30
        self.assertTrue(any("approval" in p for p in b.check_lock_rules(d)))
        d["approval"] = {"by": "owner", "at": "2026-11-01", "record": "docs/decisions/x.md"}
        d["status"] = "approved"
        self.assertEqual(b.check_lock_rules(d), [])
        p = self.doc()
        p["approval"] = {"by": "owner", "at": "x", "record": "y"}
        self.assertTrue(b.check_lock_rules(p))

    def test_checker_rejects_enabled_proposal_foreign_bucket_and_bad_prefix(self):
        for edit in (lambda d: d["rules"][0].__setitem__("enabled", True),
                     lambda d: d["rules"][0].__setitem__("bucket", "somewhere-else"),
                     lambda d: d["rules"][0].__setitem__("prefix", "objects"),
                     lambda d: d["rules"].append(copy.deepcopy(d["rules"][0])),
                     lambda d: d.__setitem__("rules", [])):
            d = self.doc()
            edit(d)
            self.assertTrue(b.check_lock_rules(d))

    def test_cli_checks_the_shipped_file_without_a_request(self):
        r = subprocess.run([sys.executable, "-I", str(ROOT / "tools/r2_budget.py"), "lock-rules"],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["status"], out["problems"]), ("proposed_not_applied", []))
        with tempfile.TemporaryDirectory() as t:
            bad = self.doc()
            bad["rules"][0]["condition"] = {"type": "Indefinite"}
            p = Path(t) / "bad.json"
            p.write_text(json.dumps(bad))
            r = subprocess.run([sys.executable, "-I", str(ROOT / "tools/r2_budget.py"), "lock-rules", "--file", str(p)],
                               capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 1)


class RecordsAndDocs(unittest.TestCase):
    SECRET = re.compile(r"[0-9a-f]{32}\.r2\.cloudflarestorage|cfut_[A-Za-z0-9]|AKIA[0-9A-Z]{12}|"
                        r"(?i:secret[_ ]?access[_ ]?key)\s*[:=]\s*[A-Za-z0-9/+]{20,}|"
                        r"(?i:access[_ ]?key[_ ]?id)\s*[:=]\s*[A-Za-z0-9]{16,}|claude-(?:fable|opus|sonnet|haiku)-\d")

    def test_files_exist(self):
        for name in ("README.md", "DESIGN.md", "LOCK_RULES.md", "lock_rules.json", "TOKENS.md", "CONCURRENCY.md",
                     "VERIFICATION.md", "real_r2_record.json"):
            self.assertTrue((CP_DIR / name).is_file(), name)

    def test_no_secret_endpoint_or_model_id_under_the_checkpoint_directory(self):
        for p in CP_DIR.rglob("*"):
            if p.is_file():
                self.assertIsNone(self.SECRET.search(p.read_text(encoding="utf-8")), p.name)

    def test_real_r2_record_is_honest(self):
        rec = json.loads((CP_DIR / "real_r2_record.json").read_text(encoding="utf-8"))
        self.assertIn(rec["status"], ("not_run", "executed_with_failures", "done"))
        ids = [c["id"] for c in rec["checks"]]
        self.assertEqual(len(ids), len(set(ids)))
        results = [c["result"] for c in rec["checks"]]
        self.assertTrue(set(results) <= {"pass", "fail", "not_run"})
        self.assertTrue(rec["reason"])
        for c in rec["checks"]:
            if c["result"] != "not_run":
                self.assertTrue(c.get("evidence"), c["id"])
        if rec["status"] == "not_run":
            self.assertTrue(all(r == "not_run" for r in results))
            self.assertIsNone(rec.get("run_at"))
        else:  # something was run: when, where, and with what credential scope
            for k in ("run_at", "environment", "token_scope_record"):
                self.assertTrue(rec.get(k), k)
            self.assertTrue(any(r != "not_run" for r in results))
            for c in rec["checks"]:
                if c["result"] == "not_run":  # a skipped check names why
                    self.assertIn("미확인", c["evidence"], c["id"])
        if rec["status"] == "done":  # a single failure or unverified item keeps it from done
            self.assertTrue(all(r == "pass" for r in results))
            self.assertTrue(rec.get("target_sha"))
        else:
            self.assertTrue(any(r != "pass" for r in results) or rec["status"] == "not_run")

    def test_real_r2_record_and_verification_doc_agree(self):
        rec = json.loads((CP_DIR / "real_r2_record.json").read_text(encoding="utf-8"))
        doc = (CP_DIR / "VERIFICATION.md").read_text(encoding="utf-8")
        for c in rec["checks"]:
            self.assertIn(f"`{c['id']}`", doc, c["id"])
        self.assertIn(f"`status: {rec['status']}`", doc)
        failed = [c["id"] for c in rec["checks"] if c["result"] == "fail"]
        for cid in failed:
            self.assertRegex(doc, rf"`{cid}`[^\n]*fail", cid)

    def test_no_indefinite_lock_and_none_applied(self):
        rules = json.loads((CP_DIR / "lock_rules.json").read_text(encoding="utf-8"))
        self.assertEqual(b.check_lock_rules(rules), [])
        rec = json.loads((CP_DIR / "real_r2_record.json").read_text(encoding="utf-8"))
        lock = next(c for c in rec["checks"] if c["id"] == "bucket-lock-not-applied-without-approval")
        self.assertNotEqual(lock["result"], "fail")

    def test_record_checks_are_the_o17_verification_items(self):
        rec = json.loads((CP_DIR / "real_r2_record.json").read_text(encoding="utf-8"))
        want = {"admission-before-read", "closure-after-limit", "local-gate-one-at-a-time", "reservation-race-412",
                "settlement-worst-case", "conditional-write-412", "ledger-tail-and-checkpoint", "checkpoint-write-once",
                "meter-matches-server-count", "token-scope-no-admin", "bucket-lock-not-applied-without-approval"}
        self.assertEqual({c["id"] for c in rec["checks"]}, want)


if __name__ == "__main__":
    unittest.main()
