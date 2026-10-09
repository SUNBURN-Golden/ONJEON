#!/usr/bin/env python3
"""Spend limits for the S3-API archive (Cloudflare R2; also AWS). ADR-0017, infra/r2/BUDGET.md.

R2 has no hard spending cap; a Cloudflare budget alert only sends an email. The limits here are
enforced by this client before each request is sent:

  policy  infra/r2/budget_policy.json   global caps (per UTC month, stored bytes for all time)
  job     infra/r2/jobs/<job>.json      what one job may touch (buckets, operations, the exact keys
                                        and their SHA-256) and its caps over all of its runs
  ledger  s3://<ledger bucket>/ledger/v1/<seq>.json
          append-only, write-once (If-None-Match), hash-chained records. A run reserves its whole
          per-run allowance before any archive request; the reservation counts in full whether or
          not it is used, so re-running or running in parallel cannot exceed the caps. Two runs that
          race for the same sequence number: one gets 412, re-reads and re-checks.

Fail closed: the ledger cannot be listed, read, parsed or verified (gap, broken chain, unknown
policy) -> stop before any archive request. A cap would be exceeded -> stop before that request.

Every request goes through Meter (botocore event hooks):
  - only GetObject, HeadObject, PutObject, ListObjectsV2; only the job's buckets and the ledger
  - Get/Head/Put only for keys in the job's pinned listings; Put only with exactly the pinned bytes
  - no storage class other than Standard (Infrequent Access has retrieval and minimum-duration fees)
  - counts every HTTP attempt as a billable request (Class A: Put, List; Class B: Get, Head),
    request bytes, response bytes, retries and wall time against the reservation
"""
import datetime as dt
import hashlib
import json
import os
import signal
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PREFIX = "ledger/v1/"
DIMENSIONS = ("put_bytes", "get_bytes", "class_a", "class_b", "retries", "seconds")
CLASS_A = {"PutObject", "ListObjectsV2"}
CLASS_B = {"GetObject", "HeadObject"}
ALLOWED_OPS = CLASS_A | CLASS_B
MONTHLY = ("get_bytes", "class_a", "class_b", "retries", "seconds")  # put_bytes is all-time (storage)
SETTLEMENT_WRITE_BYTES = 4096  # upper bound for one ledger record
LEDGER_CLASS_A = 4  # reserve: list + put; settle: list + put


class BudgetError(SystemExit):
    """Stops the run. Exit code 4: limit reached or ledger not verifiable."""

    def __init__(self, msg):
        super().__init__(f"budget: {msg}")
        self.code = 4


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def month_of(ts):
    return ts[:7]  # "YYYY-MM" from an ISO timestamp


def load_policy(path=ROOT / "infra/r2/budget_policy.json"):
    p = Path(path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    for k in ("ledger_bucket", "caps", "per_request"):
        if k not in doc:
            raise BudgetError(f"policy {p} lacks {k}")
    for d in DIMENSIONS:
        if not isinstance(doc["caps"].get(d), int) or doc["caps"][d] < 0:
            raise BudgetError(f"policy cap {d} must be a non-negative integer")
    doc["_sha256"] = sha256_file(p)
    doc["_accepted_sha256"] = {doc["_sha256"], *doc.get("previous_policy_sha256", [])}
    return doc


def load_job(spec):
    """spec = path[#profile]; the profile picks the per-run reservation (default: verify)."""
    path, _, profile = str(spec).partition("#")
    profile = profile or "verify"
    p = Path(path)
    job = json.loads(p.read_text(encoding="utf-8"))
    for k in ("job_id", "buckets", "job_caps", "run_profiles"):
        if k not in job:
            raise BudgetError(f"job {p} lacks {k}")
    if profile not in job["run_profiles"]:
        raise BudgetError(f"job {p} has no run profile {profile!r} (has {sorted(job['run_profiles'])})")
    job["per_run"] = job["run_profiles"][profile]
    job["_profile"] = profile
    for d in DIMENSIONS:
        for part in ("job_caps", "per_run"):
            if not isinstance(job[part].get(d), int) or job[part][d] < 0:
                raise BudgetError(f"job {part}.{d} must be a non-negative integer")
        if job["per_run"][d] > job["job_caps"][d]:
            raise BudgetError(f"job per_run.{d} exceeds job_caps.{d}")
    # every run lists and writes the ledger twice (reserve, settle); a profile that cannot pay for
    # that loses its settlement and keeps its whole reservation (found with the status profile)
    if job["per_run"]["class_a"] < LEDGER_CLASS_A or job["per_run"]["put_bytes"] < 2 * SETTLEMENT_WRITE_BYTES:
        raise BudgetError(f"run profile {profile!r} cannot pay for its own ledger records "
                          f"(needs class_a >= {LEDGER_CLASS_A}, put_bytes >= {2 * SETTLEMENT_WRITE_BYTES})")
    allowed = {}
    for bucket, spec in job["buckets"].items():
        listing = json.loads((ROOT / spec["listing"]).read_text(encoding="utf-8"))
        if listing.get("listing_rule") != "key-sha256-v1":
            raise BudgetError(f"{spec['listing']}: unknown listing rule")
        if spec.get("listing_sha256") != sha256_file(ROOT / spec["listing"]):
            raise BudgetError(f"{spec['listing']}: listing changed since the job was pinned")
        allowed[bucket] = listing["objects"]
    job["_allowed"] = allowed
    job["_sha256"] = sha256_file(p)
    return job


def request_size(request):
    """Bytes this HTTP attempt sends. botocore may wrap the body in a stream, so the declared
    Content-Length is authoritative; an unknown size is refused rather than counted as zero."""
    length = (request.headers or {}).get("Content-Length")
    if length is not None:
        return int(length)
    if isinstance(request.body, (bytes, bytearray)):
        return len(request.body)
    if request.body is None:
        return 0
    raise BudgetError("upload size unknown (no Content-Length); refusing to send")


class Meter:
    """Counts and limits every S3 API request of one run. Attach with meter.attach(client, bucket_role)."""

    def __init__(self, policy, job, limits, deadline_s):
        self.policy, self.job = policy, job
        self.limits = dict(limits)
        self.used = {d: 0 for d in DIMENSIONS}
        self.start = time.monotonic()
        self.deadline_s = deadline_s
        self.calls = 0
        self.attempts_in_call = 0
        self.current_op = None
        self.max_object = policy["per_request"]["max_object_bytes"]

    # -- limits ---------------------------------------------------------------------------
    def _charge(self, dim, n):
        if self.used[dim] + n > self.limits[dim]:
            raise BudgetError(f"{dim} would reach {self.used[dim] + n} > limit {self.limits[dim]} "
                              f"(job {self.job['job_id']}); stopped before the request")
        self.used[dim] += n

    def _check_time(self):
        elapsed = int(time.monotonic() - self.start)
        if elapsed > self.deadline_s:
            raise BudgetError(f"run time {elapsed}s exceeds limit {self.deadline_s}s")
        self.used["seconds"] = elapsed

    def charge_get_bytes(self, n):
        self._charge("get_bytes", int(n))

    # -- request checks (before the request is built) ---------------------------------------
    def check_call(self, op, params, role):
        self._check_time()
        if op not in ALLOWED_OPS:
            raise BudgetError(f"operation {op} is not allowed")
        bucket = params.get("Bucket")
        if role == "ledger":
            if bucket != self.policy["ledger_bucket"]:
                raise BudgetError(f"ledger client used for bucket {bucket}")
            key = params.get("Key", params.get("Prefix", ""))
            if not key.startswith(LEDGER_PREFIX) or op == "HeadObject":
                raise BudgetError(f"ledger access outside {LEDGER_PREFIX}: {op} {key}")
        else:
            allowed = self.job["_allowed"].get(bucket)
            if allowed is None:
                raise BudgetError(f"bucket {bucket} is not in job {self.job['job_id']}")
            if op in ("GetObject", "HeadObject", "PutObject"):
                key = params.get("Key")
                if key not in allowed:
                    raise BudgetError(f"key {key} is not in the pinned listing of job {self.job['job_id']}")
                if op == "PutObject":
                    body = params.get("Body", b"")
                    if not isinstance(body, (bytes, bytearray)):
                        raise BudgetError("PutObject body must be bytes (no streaming uploads)")
                    if hashlib.sha256(body).hexdigest() != allowed[key]:
                        raise BudgetError(f"{key}: bytes differ from the pinned SHA-256")
        if op == "PutObject":
            if params.get("StorageClass") not in (None, "STANDARD"):
                raise BudgetError(f"storage class {params.get('StorageClass')} is not allowed")
            if len(params.get("Body", b"")) > self.max_object:
                raise BudgetError(f"object larger than {self.max_object} bytes")
        self.current_op = op
        self.calls += 1
        self.attempts_in_call = 0

    def on_send(self, request):
        """Every HTTP attempt, including botocore retries, is a billable request."""
        self._check_time()
        op = self.current_op
        if op is None:
            raise BudgetError("request without a checked operation")
        self.attempts_in_call += 1
        if self.attempts_in_call > 1:
            self._charge("retries", 1)
        self._charge("class_a" if op in CLASS_A else "class_b", 1)
        if op == "PutObject":
            self._charge("put_bytes", request_size(request))

    def attach(self, client, role):
        events = client.meta.events

        def provide(params, model, **kw):
            self.check_call(model.name, params, role)

        events.register("provide-client-params.s3.*", provide, unique_id=f"onjeon-meter-provide-{id(self)}")
        events.register("before-send.s3.*", lambda request, **kw: self.on_send(request),
                        unique_id=f"onjeon-meter-send-{id(self)}")

    def snapshot(self):
        self._check_time()
        return dict(self.used)


class Ledger:
    """Append-only reservation records in a write-once store (S3Store or LocalStore)."""

    def __init__(self, st, policy):
        self.st, self.policy = st, policy

    def read(self):
        import source_archive as sa
        try:
            keys = self.st.list(LEDGER_PREFIX)
        except Exception as e:  # cannot see the records -> cannot know what is left
            raise BudgetError(f"ledger list failed ({type(e).__name__}); not running")
        limit = self.policy["per_request"]["max_ledger_records"]
        if len(keys) > limit:
            raise BudgetError(f"ledger has {len(keys)} records > {limit}; compact before running")
        records, prev = [], None
        for i, key in enumerate(sorted(keys), start=1):
            if key != f"{LEDGER_PREFIX}{i:010d}.json":
                raise BudgetError(f"ledger gap or foreign key at {key} (expected seq {i})")
            try:
                raw = self.st.get(key)
                rec = json.loads(raw)
            except Exception as e:
                raise BudgetError(f"ledger record {key} unreadable ({type(e).__name__})")
            if rec.get("seq") != i or rec.get("prev_sha256") != prev:
                raise BudgetError(f"ledger chain broken at {key}")
            if rec.get("policy_sha256") not in self.policy["_accepted_sha256"]:
                raise BudgetError(f"ledger record {key} was written under an unknown policy")
            prev = sa.sha256_bytes(raw)
            if i == 1:
                genesis = prev
            records.append(rec)
        pin = self.policy.get("ledger_genesis_sha256")
        if pin and (not records or genesis != pin):  # an emptied or replaced ledger would reset the caps
            raise BudgetError("ledger does not start with the genesis record pinned in the policy "
                              f"({'empty' if not records else 'different first record'}); not running")
        return records, prev

    @staticmethod
    def usage(records, job_id, month):
        """A reservation counts in full until its own run settles it; then it counts what the run
        measured, never more than it reserved. A run that crashes or never settles keeps its whole
        reservation, so re-running or running in parallel cannot exceed a cap."""
        settled = {}
        for r in records:
            if r.get("kind") == "settlement":
                key = (r.get("reservation_seq"), r.get("run_id"))
                prev = settled.get(key, {})
                settled[key] = {d: max(int(r["amounts"].get(d, 0)), prev.get(d, 0)) for d in DIMENSIONS}
        glob = {d: 0 for d in DIMENSIONS}
        job = {d: 0 for d in DIMENSIONS}
        for r in records:
            if r.get("kind") not in ("reservation", "pre_ledger_usage"):
                continue
            actual = settled.get((r["seq"], r.get("run_id"))) if r["kind"] == "reservation" else None
            for d in DIMENSIONS:
                n = int(r["amounts"].get(d, 0))
                if actual is not None:
                    n = min(n, actual[d])
                if d not in MONTHLY or month_of(r["at"]) == month:
                    glob[d] += n
                if r.get("job_id") == job_id:
                    job[d] += n
        return glob, job

    def append(self, record_body, records, prev):
        """Write the next record; Exists -> another run won the race."""
        import source_archive as sa
        seq = len(records) + 1
        rec = dict(record_body, seq=seq, prev_sha256=prev, policy_sha256=self.policy["_sha256"])
        body = json.dumps(rec, ensure_ascii=False, sort_keys=True, indent=1).encode() + b"\n"
        self.st.put_new(f"{LEDGER_PREFIX}{seq:010d}.json", body, "application/json")
        return rec, sa.sha256_bytes(body)


def reserve(ledger, policy, job, run_id, attempts=None):
    """Reserve the job's per-run allowance; raises BudgetError if any cap would be exceeded."""
    import source_archive as sa
    attempts = attempts or policy["per_request"]["reserve_attempts"]
    month = now_utc().strftime("%Y-%m")
    for _ in range(attempts):
        records, prev = ledger.read()
        glob, used_job = Ledger.usage(records, job["job_id"], month)
        want = job["per_run"]
        for d in DIMENSIONS:
            if glob[d] + want[d] > policy["caps"][d]:
                raise BudgetError(f"global {d}: used {glob[d]} + reservation {want[d]} > cap {policy['caps'][d]}"
                                  + (f" this month ({month})" if d in MONTHLY else " (all time)"))
            if used_job[d] + want[d] > job["job_caps"][d]:
                raise BudgetError(f"job {job['job_id']} {d}: used {used_job[d]} + reservation {want[d]} "
                                  f"> job cap {job['job_caps'][d]}")
        body = {"format": "onjeon-budget-ledger-v1", "kind": "reservation", "job_id": job["job_id"],
                "job_sha256": job["_sha256"], "profile": job["_profile"], "run_id": run_id,
                "at": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "amounts": dict(want)}
        try:
            rec, rec_sha = ledger.append(body, records, prev)
            return rec, rec_sha, {d: policy["caps"][d] - glob[d] - want[d] for d in DIMENSIONS}
        except sa.Exists:
            continue  # lost the race: re-read and re-check
        except BudgetError:
            raise
        except Exception as e:
            raise BudgetError(f"ledger write failed ({type(e).__name__}); not running")
    raise BudgetError(f"could not reserve after {attempts} attempts (concurrent runs)")


class Session:
    """One budgeted run: load policy and job, reserve, meter every client, settle at the end."""

    def __init__(self, job_path, endpoint_url=None, ledger_store=None, policy_path=None):
        self.policy = load_policy(policy_path) if policy_path else load_policy()
        self.job = load_job(job_path)
        self.run_id = f"{now_utc().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        self.meter = Meter(self.policy, self.job, self.job["per_run"], self.job["per_run"]["seconds"])
        self.endpoint_url = endpoint_url
        self._ledger_store = ledger_store
        self.reservation = None

    def open(self):
        import source_archive as sa
        st = self._ledger_store
        if st is None:
            st = sa.S3Store(f"s3://{self.policy['ledger_bucket']}", self.endpoint_url, ledger=True)
        if isinstance(st, sa.S3Store):
            self.meter.attach(st.s3, "ledger")
        self.ledger = Ledger(st, self.policy)
        rec, _sha, remaining = reserve(self.ledger, self.policy, self.job, self.run_id)
        self.reservation = rec
        if hasattr(signal, "SIGALRM"):  # wall clock limit even while no request is in flight
            def alarm(signum, frame):
                raise BudgetError(f"run time limit {self.job['per_run']['seconds']}s reached")
            signal.signal(signal.SIGALRM, alarm)
            signal.alarm(self.job["per_run"]["seconds"])
        return remaining

    def settle(self, outcome):
        """Record what the run measured (plus this record's own write), capped at the reservation.
        If this fails the reservation simply keeps counting in full."""
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
        if self.reservation is None:
            return None
        try:
            records, prev = self.ledger.read()
            used = self.meter.snapshot()
            used["class_a"] += 1  # the settlement PutObject itself
            used["put_bytes"] += SETTLEMENT_WRITE_BYTES
            used = {d: min(used[d], self.job["per_run"][d]) for d in DIMENSIONS}
            body = {"format": "onjeon-budget-ledger-v1", "kind": "settlement", "job_id": self.job["job_id"],
                    "run_id": self.run_id, "reservation_seq": self.reservation["seq"], "outcome": outcome,
                    "at": now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"), "amounts": used}
            rec, _ = self.ledger.append(body, records, prev)
            return rec
        except BaseException as e:  # the reservation already counts in full; a lost settlement costs nothing
            return {"settlement_failed": type(e).__name__}

    def summary(self):
        return {"job_id": self.job["job_id"], "run_id": self.run_id,
                "reservation_seq": self.reservation and self.reservation["seq"],
                "limits": self.meter.limits, "used": self.meter.snapshot(), "requests": self.meter.calls}


ACTIVE = None  # the Session of this process; source_archive.store() refuses R2/AWS without it


def start(job_path, endpoint_url=None, ledger_store=None, policy_path=None):
    global ACTIVE
    if ACTIVE is not None:
        raise BudgetError("a budget session is already open in this process")
    s = Session(job_path, endpoint_url, ledger_store, policy_path)
    s.open()
    ACTIVE = s
    return s


def finish(outcome):
    global ACTIVE
    s, ACTIVE = ACTIVE, None
    if s is None:
        return None
    settled = s.settle(outcome)
    return {**s.summary(), "settlement": settled and settled.get("seq", settled)}


def _cli():
    """status: what is left. init-pre-ledger: record usage made before the ledger existed (seq 1 only)."""
    import argparse
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import source_archive as sa
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint-url")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--job", required=True)
    s = sub.add_parser("init-pre-ledger")
    s.add_argument("--job", required=True)
    s.add_argument("--amounts", required=True, help="JSON file: amounts per dimension and a note")
    a = ap.parse_args()
    if a.cmd == "status":  # reading the ledger costs requests too, so status is a reserved run
        path = a.job.partition("#")[0]
        s = start(f"{path}#status", a.endpoint_url)
        try:
            records, _ = s.ledger.read()
            month = now_utc().strftime("%Y-%m")
            glob, used_job = Ledger.usage(records, s.job["job_id"], month)
            verify = load_job(f"{path}#verify")["per_run"]
            print(json.dumps({"records": len(records), "month": month,
                              "global_used": glob, "global_caps": s.policy["caps"],
                              "job_used_including_this_status": used_job, "job_caps": s.job["job_caps"],
                              "verify_runs_left": min((s.job["job_caps"][d] - used_job[d]) // verify[d]
                                                      for d in DIMENSIONS if verify[d])}, indent=1))
        finally:
            print("budget " + json.dumps(finish("ok")), file=sys.stderr)
        return 0
    policy, job = load_policy(), load_job(a.job)
    small = {"put_bytes": 1 << 20, "get_bytes": 1 << 24, "class_a": 3,
             "class_b": policy["per_request"]["max_ledger_records"] + 1, "retries": 3, "seconds": 300}
    meter = Meter(policy, job, small, small["seconds"])
    st = sa.S3Store(f"s3://{policy['ledger_bucket']}", a.endpoint_url, ledger=True)
    meter.attach(st.s3, "ledger")
    ledger = Ledger(st, policy)
    records, prev = ledger.read()
    if records:
        raise BudgetError("pre-ledger usage can only be the first record")
    spec = json.loads(Path(a.amounts).read_text(encoding="utf-8"))
    body = {"format": "onjeon-budget-ledger-v1", "kind": "pre_ledger_usage", "job_id": job["job_id"],
            "job_sha256": job["_sha256"], "run_id": "pre-ledger", "at": spec["at"],
            "amounts": {d: int(spec["amounts"][d]) for d in DIMENSIONS}, "note": spec["note"]}
    rec, rec_sha = ledger.append(body, records, prev)
    print(json.dumps({"written_seq": rec["seq"], "record_sha256": rec_sha, "requests": meter.snapshot()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
