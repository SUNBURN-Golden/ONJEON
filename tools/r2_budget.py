#!/usr/bin/env python3
"""Spend limits for the S3-API archive (Cloudflare R2; also AWS). ADR-0017, infra/r2/BUDGET.md.

A runaway mitigation for runs of this tool: per-run limits plus the cumulative use recorded in the
ledger. It is not an account-wide spending cap and does not bound requests made outside this tool;
some of this tool's own requests are not recorded either (infra/r2/BUDGET.md section 5). R2 has no
hard spending cap; a Cloudflare budget alert only sends an email. The limits here are enforced by
this client before each request is sent:

  policy     infra/r2/budget_policy.json   global caps (per UTC month; stored bytes for all time),
                                           admission limits, local gate
  job        infra/r2/jobs/<job>.json      what one job may touch (buckets, operations, the exact
                                           keys and their SHA-256), its caps, per-run profiles
  ledger     s3://<ledger>/ledger/v1/<seq>.json      write-once, hash-chained reservations and
                                                     settlements; genesis hash pinned in the policy
  admission  s3://<ledger>/admission/v1/<YYYY-MM>/<job>/<run>.json
                                                     one per run, written before any read
  closed     s3://<ledger>/closed/v1/<YYYY-MM>/<job | _global>.json
                                                     admissions for the month used up

Run control, in this order (each step before any later request):
  1. local gate (no network): one run at a time on this machine, a runs-per-hour limit, and a
     remembered closure. Refused runs send nothing.
  2. closure check: two HEADs. Closed -> stop. These two are the only requests a blocked run sends.
  3. admission: a blind conditional PUT of a unique record. From here until the reservation the
     meter enforces the policy's admission limits, so the record bounds everything the run spends
     before reserving (listing and reading the ledger, the reservation write, retries). An admission
     whose run never settles counts against the caps at those limits, so a refused run that is
     repeated is paid for every time. When the month's admissions for the job (or in total) are
     used up the run writes the closure marker.
  4. reservation: the run's whole per-run profile, only if it fits under the caps after leaving
     room for every admission still allowed this month. Then archive requests may start.
  5. settlement: what the run measured since step 3 plus the worst case of the settlement write
     itself (every attempt, its bytes, its retries, its timeouts), never more than reserved. A run
     that never settles keeps its admission and its whole reservation.

Every request goes through Meter (botocore event hooks): only Get/Head/Put/ListObjectsV2, only the
job's buckets and the ledger prefixes, only pinned keys and pinned bytes, Standard storage only;
every HTTP attempt (retries included) is charged as Class A or B, with request bytes, response
bytes, retries and wall time.
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
ADMISSION_PREFIX = "admission/v1/"
CLOSED_PREFIX = "closed/v1/"
CONTROL_PREFIXES = (LEDGER_PREFIX, ADMISSION_PREFIX, CLOSED_PREFIX)
DIMENSIONS = ("put_bytes", "get_bytes", "class_a", "class_b", "retries", "seconds")
CLASS_A = {"PutObject", "ListObjectsV2"}
CLASS_B = {"GetObject", "HeadObject"}
ALLOWED_OPS = CLASS_A | CLASS_B
MONTHLY = ("get_bytes", "class_a", "class_b", "retries", "seconds")  # put_bytes is all-time (storage)
RECORD_BYTES = 4096  # upper bound for one ledger, admission or closure record
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 120  # also used by source_archive.S3Store


class BudgetError(SystemExit):
    """Stops the run. Exit code 4: limit reached, run refused, or ledger not verifiable."""

    def __init__(self, msg):
        super().__init__(f"budget: {msg}")
        self.code = 4


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def month_of(ts):
    return ts[:7]  # "YYYY-MM" from an ISO timestamp


def stamp():
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def load_policy(path=ROOT / "infra/r2/budget_policy.json"):
    p = Path(path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    for k in ("ledger_bucket", "caps", "per_request", "admission", "local_gate"):
        if k not in doc:
            raise BudgetError(f"policy {p} lacks {k}")
    for part in ("caps", "admission"):
        src = doc[part] if part == "caps" else doc["admission"]["limits"]
        for d in DIMENSIONS:
            if not isinstance(src.get(d), int) or src[d] < 0:
                raise BudgetError(f"policy {part} {d} must be a non-negative integer")
    doc["_sha256"] = sha256_file(p)
    doc["_accepted_sha256"] = {doc["_sha256"], *doc.get("previous_policy_sha256", [])}
    return doc


def settlement_worst_case(policy):
    """The settlement PUT itself, every attempt counted (it happens after the measured snapshot)."""
    n = policy["per_request"]["max_attempts"]
    return {"put_bytes": n * RECORD_BYTES, "get_bytes": 0, "class_a": n, "class_b": 0,
            "retries": n - 1, "seconds": n * (CONNECT_TIMEOUT + READ_TIMEOUT)}


def profile_minimum(policy):
    """What any run needs to get through admission, reserve, and settle (tail read + worst-case PUT)."""
    adm, settle, n = policy["admission"]["limits"], settlement_worst_case(policy), policy["per_request"]["max_attempts"]
    tail = {"put_bytes": 0, "get_bytes": n * RECORD_BYTES, "class_a": n, "class_b": n, "retries": 2 * (n - 1),
            "seconds": 0}
    return {d: adm[d] + tail[d] + settle[d] for d in DIMENSIONS}


def load_job(spec, policy=None):
    """spec = path[#profile]; the profile picks the per-run reservation (default: verify)."""
    path, _, profile = str(spec).partition("#")
    profile = profile or "verify"
    p = Path(path)
    job = json.loads(p.read_text(encoding="utf-8"))
    for k in ("job_id", "buckets", "job_caps", "run_profiles", "admissions_per_month"):
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
    if policy is not None:  # a profile that cannot pay for its own control records would lose them
        need = profile_minimum(policy)
        short = [d for d in DIMENSIONS if job["per_run"][d] < need[d]]
        if short:
            raise BudgetError(f"run profile {profile!r} cannot pay for admission, reservation and settlement: "
                              + ", ".join(f"{d} {job['per_run'][d]} < {need[d]}" for d in short))
    allowed = {}
    for bucket, bspec in job["buckets"].items():
        listing = json.loads((ROOT / bspec["listing"]).read_text(encoding="utf-8"))
        if listing.get("listing_rule") != "key-sha256-v1":
            raise BudgetError(f"{bspec['listing']}: unknown listing rule")
        if bspec.get("listing_sha256") != sha256_file(ROOT / bspec["listing"]):
            raise BudgetError(f"{bspec['listing']}: listing changed since the job was pinned")
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
    """Counts and limits every S3 API request of one run, from its first request to its last."""

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
        self.archive_allowed = True

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

    def check_call(self, op, params, role):
        self._check_time()
        if op not in ALLOWED_OPS:
            raise BudgetError(f"operation {op} is not allowed")
        bucket = params.get("Bucket")
        if role == "ledger":
            if bucket != self.policy["ledger_bucket"]:
                raise BudgetError(f"ledger client used for bucket {bucket}")
            key = params.get("Key", params.get("Prefix", ""))
            if not key.startswith(CONTROL_PREFIXES):
                raise BudgetError(f"ledger access outside {CONTROL_PREFIXES}: {op} {key}")
            if op == "HeadObject" and not key.startswith(CLOSED_PREFIX):
                raise BudgetError(f"ledger HEAD outside {CLOSED_PREFIX}: {key}")
        else:
            if not self.archive_allowed:
                raise BudgetError("archive request before a reservation")
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

        events.register("provide-client-params.s3.*", provide, unique_id=f"onjeon-meter-provide-{id(self)}-{role}")
        events.register("before-send.s3.*", lambda request, **kw: self.on_send(request),
                        unique_id=f"onjeon-meter-send-{id(self)}-{role}")

    def snapshot(self):
        self._check_time()
        return dict(self.used)


class LocalGate:
    """Run control on this machine, before any network request: one run at a time, at most
    max_runs_per_hour starts, and a remembered closure (month, job) once a run has seen one."""

    def __init__(self, policy, job_id, gate_dir=None):
        self.max_per_hour = policy["local_gate"]["max_runs_per_hour"]
        self.job_id = job_id
        d = Path(gate_dir or os.environ.get("ONJEON_GATE_DIR") or Path.home() / ".cache/onjeon")
        d.mkdir(parents=True, exist_ok=True)
        self.state_path = d / "r2_gate.json"
        self.lock_path = d / "r2_gate.lock"
        self._lock = None

    def _state(self):
        if not self.state_path.exists():
            return {"starts": [], "closed": []}
        try:
            s = json.loads(self.state_path.read_text(encoding="utf-8"))
            assert isinstance(s["starts"], list) and isinstance(s["closed"], list)
            return s
        except Exception:
            raise BudgetError(f"local gate state {self.state_path} unreadable; not running")

    def _write(self, s):
        tmp = self.state_path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(s), encoding="utf-8")
        tmp.replace(self.state_path)

    def enter(self):
        import fcntl
        self._lock = open(self.lock_path, "a+")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            self._lock = None
            raise BudgetError("another budgeted run is in progress on this machine")
        try:
            s = self._state()
            month = now_utc().strftime("%Y-%m")
            if f"{month}/{self.job_id}" in s["closed"] or f"{month}/_global" in s["closed"]:
                raise BudgetError(f"admissions for {month} are closed (remembered on this machine); nothing was sent")
            now = time.time()
            s["starts"] = [t for t in s["starts"] if now - t < 3600]
            if len(s["starts"]) >= self.max_per_hour:
                raise BudgetError(f"{self.max_per_hour} budgeted runs started on this machine in the last hour; "
                                  "nothing was sent")
            s["starts"].append(now)
            self._write(s)
        except BaseException:
            self.leave()
            raise

    def remember_closed(self, scope):
        s = self._state()
        tag = f"{now_utc().strftime('%Y-%m')}/{scope}"
        if tag not in s["closed"]:
            s["closed"].append(tag)
            self._write(s)

    def leave(self):
        if self._lock is not None:
            import fcntl
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()
            self._lock = None


class Ledger:
    """Write-once control records in the ledger bucket (S3Store or LocalStore)."""

    def __init__(self, st, policy):
        self.st, self.policy = st, policy

    def _list(self, prefix):
        try:
            return self.st.list(prefix)
        except BudgetError:
            raise
        except Exception as e:  # cannot see the records -> cannot know what is left
            raise BudgetError(f"ledger list failed ({type(e).__name__}); not running")

    def read(self, known=None):
        """All sequence records, verified. With known=(records, prev) only newer records are fetched."""
        import source_archive as sa
        keys = sorted(self._list(LEDGER_PREFIX))
        limit = self.policy["per_request"]["max_ledger_records"]
        if len(keys) > limit:
            raise BudgetError(f"ledger has {len(keys)} records > {limit}; checkpoint before running")
        records, prev = (list(known[0]), known[1]) if known else ([], None)
        for i, key in enumerate(keys, start=1):
            if key != f"{LEDGER_PREFIX}{i:010d}.json":
                raise BudgetError(f"ledger gap or foreign key at {key} (expected seq {i})")
        if len(keys) < len(records):
            raise BudgetError("ledger lost records while this run was reading it")
        for i in range(len(records) + 1, len(keys) + 1):
            key = keys[i - 1]
            try:
                raw = self.st.get(key)
                rec = json.loads(raw)
            except BudgetError:
                raise
            except Exception as e:
                raise BudgetError(f"ledger record {key} unreadable ({type(e).__name__})")
            if rec.get("seq") != i or rec.get("prev_sha256") != prev:
                raise BudgetError(f"ledger chain broken at {key}")
            if rec.get("policy_sha256") not in self.policy["_accepted_sha256"]:
                raise BudgetError(f"ledger record {key} was written under an unknown policy")
            if i == 1 and self.policy.get("ledger_genesis_sha256") not in (None, sa.sha256_bytes(raw)):
                raise BudgetError("ledger does not start with the genesis record pinned in the policy; not running")
            prev = sa.sha256_bytes(raw)
            records.append(rec)
        if self.policy.get("ledger_genesis_sha256") and not records:
            raise BudgetError("ledger is empty but the policy pins a genesis record; not running")
        return records, prev

    def tail(self):
        """Next sequence number and the hash of the last record: one LIST and one GET."""
        import source_archive as sa
        keys = sorted(self._list(LEDGER_PREFIX))
        if not keys or keys[-1] != f"{LEDGER_PREFIX}{len(keys):010d}.json":
            raise BudgetError("ledger tail is not contiguous")
        return len(keys), sa.sha256_bytes(self.st.get(keys[-1]))

    def admissions(self):
        """(month, job_id, run_id) of every admission ever made: LIST only, no GETs. Job caps are
        all-time, so admissions of earlier months still count for the job."""
        out = []
        for key in self._list(ADMISSION_PREFIX):
            parts = key[len(ADMISSION_PREFIX):].split("/")
            if len(parts) != 3 or not parts[2].endswith(".json") or len(parts[0]) != 7:
                raise BudgetError(f"foreign key in admissions: {key}")
            out.append((parts[0], parts[1], parts[2][:-5]))
        return out

    def admit(self, job, run_id, month):
        rec = {"format": "onjeon-budget-admission-v1", "job_id": job["job_id"], "profile": job["_profile"],
               "run_id": run_id, "at": stamp(), "policy_sha256": self.policy["_sha256"],
               "limits": self.policy["admission"]["limits"]}
        body = json.dumps(rec, sort_keys=True).encode()
        self.st.put_new(f"{ADMISSION_PREFIX}{month}/{job['job_id']}/{run_id}.json", body, "application/json")

    def close(self, month, scope, reason):
        import source_archive as sa
        body = json.dumps({"format": "onjeon-budget-closed-v1", "scope": scope, "at": stamp(),
                           "reason": reason}, sort_keys=True).encode()
        try:
            self.st.put_new(f"{CLOSED_PREFIX}{month}/{scope}.json", body, "application/json")
        except sa.Exists:
            pass

    def closed(self, month, job_id):
        for scope in ("_global", job_id):
            if self.st.exists(f"{CLOSED_PREFIX}{month}/{scope}.json"):
                return scope
        return None

    @staticmethod
    def usage(records, job_id, month, admissions=(), admission_limits=None):
        """A reservation counts in full until its own run settles it; then it counts what the run
        measured (never more than reserved). An admission whose run never settled counts at the
        admission limits. Re-running or running in parallel therefore counts against the caps (as far as
        this ledger sees; unrecorded requests are listed in infra/r2/BUDGET.md section 5)."""
        settled = {}
        for r in records:
            if r.get("kind") == "settlement":
                key = (r.get("reservation_seq"), r.get("run_id"))
                prev = settled.get(key, {})
                settled[key] = {d: max(int(r["amounts"].get(d, 0)), prev.get(d, 0)) for d in DIMENSIONS}
        settled_runs = {run for (_seq, run) in settled}
        glob = {d: 0 for d in DIMENSIONS}
        job = {d: 0 for d in DIMENSIONS}

        def add(amounts, at, rec_job):
            for d in DIMENSIONS:
                n = int(amounts.get(d, 0))
                if d not in MONTHLY or month_of(at) == month:
                    glob[d] += n
                if rec_job == job_id:
                    job[d] += n

        for r in records:
            if r.get("kind") not in ("reservation", "pre_ledger_usage"):
                continue
            actual = settled.get((r["seq"], r.get("run_id"))) if r["kind"] == "reservation" else None
            amounts = {d: min(int(r["amounts"].get(d, 0)), actual[d]) if actual else int(r["amounts"].get(d, 0))
                       for d in DIMENSIONS}
            add(amounts, r["at"], r.get("job_id"))
        for adm_month, adm_job, run_id in admissions:
            if run_id not in settled_runs:
                add(admission_limits, f"{adm_month}-01T00:00:00Z", adm_job)
        return glob, job

    def append(self, record_body, count, prev):
        """Write record count+1; Exists -> another run won the race."""
        import source_archive as sa
        seq = count + 1
        rec = dict(record_body, seq=seq, prev_sha256=prev, policy_sha256=self.policy["_sha256"])
        body = json.dumps(rec, ensure_ascii=False, sort_keys=True, indent=1).encode() + b"\n"
        self.st.put_new(f"{LEDGER_PREFIX}{seq:010d}.json", body, "application/json")
        return rec, sa.sha256_bytes(body)


def this_month(admissions, month, job_id=None):
    return sum(1 for m, j, _ in admissions if m == month and (job_id is None or j == job_id))


def headroom(policy, job, admissions, job_id, month):
    """Room that must stay free for the admissions still allowed this month (global and job)."""
    lim = policy["admission"]["limits"]
    left_glob = max(policy["admission"]["per_month_global"] - this_month(admissions, month), 0)
    left_job = max(job["admissions_per_month"] - this_month(admissions, month, job_id), 0)
    return {d: left_glob * lim[d] for d in DIMENSIONS}, {d: left_job * lim[d] for d in DIMENSIONS}


def reserve(ledger, policy, job, run_id, month, admissions, attempts=None):
    """Reserve the job's per-run allowance; raises BudgetError if any cap would be exceeded."""
    import source_archive as sa
    attempts = attempts or policy["per_request"]["reserve_attempts"]
    known = None
    for _ in range(attempts):
        records, prev = ledger.read(known)
        known = (records, prev)
        glob, used_job = Ledger.usage(records, job["job_id"], month, admissions, policy["admission"]["limits"])
        room_glob, room_job = headroom(policy, job, admissions, job["job_id"], month)
        want = job["per_run"]
        for d in DIMENSIONS:
            if glob[d] + want[d] + room_glob[d] > policy["caps"][d]:
                raise BudgetError(f"global {d}: used {glob[d]} + reservation {want[d]} + admission room "
                                  f"{room_glob[d]} > cap {policy['caps'][d]}"
                                  + (f" this month ({month})" if d in MONTHLY else " (all time)"))
            if used_job[d] + want[d] + room_job[d] > job["job_caps"][d]:
                raise BudgetError(f"job {job['job_id']} {d}: used {used_job[d]} + reservation {want[d]} + "
                                  f"admission room {room_job[d]} > job cap {job['job_caps'][d]}")
        body = {"format": "onjeon-budget-ledger-v1", "kind": "reservation", "job_id": job["job_id"],
                "job_sha256": job["_sha256"], "profile": job["_profile"], "run_id": run_id,
                "at": stamp(), "amounts": dict(want)}
        try:
            rec, rec_sha = ledger.append(body, len(records), prev)
            return rec, rec_sha, {d: policy["caps"][d] - glob[d] - want[d] for d in DIMENSIONS}
        except sa.Exists:
            continue  # lost the race: read only the newer records and re-check
        except BudgetError:
            raise
        except Exception as e:
            raise BudgetError(f"ledger write failed ({type(e).__name__}); not running")
    raise BudgetError(f"could not reserve after {attempts} attempts (concurrent runs)")


class Session:
    """One budgeted run: run control, admission, reservation, metered requests, settlement."""

    def __init__(self, job_path, endpoint_url=None, ledger_store=None, policy_path=None, gate_dir=None):
        self.policy = load_policy(policy_path) if policy_path else load_policy()
        self.job = load_job(job_path, self.policy)
        self.run_id = f"{now_utc().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        adm = self.policy["admission"]["limits"]
        self.meter = Meter(self.policy, self.job, adm, adm["seconds"])  # admission limits until reserved
        self.meter.archive_allowed = False
        self.endpoint_url = endpoint_url
        self._ledger_store = ledger_store
        self.gate = LocalGate(self.policy, self.job["job_id"], gate_dir)
        self.reservation = None
        self.admitted = False

    def _refuse_and_maybe_close(self, month, admissions, err):
        job_n = this_month(admissions, month, self.job["job_id"])
        if this_month(admissions, month) >= self.policy["admission"]["per_month_global"]:
            self.ledger.close(month, "_global", "global admissions for the month used up")
            self.gate.remember_closed("_global")
        elif job_n >= self.job["admissions_per_month"]:
            self.ledger.close(month, self.job["job_id"], "job admissions for the month used up")
            self.gate.remember_closed(self.job["job_id"])
        raise err

    def open(self):
        import source_archive as sa
        self.gate.enter()
        try:
            st = self._ledger_store
            if st is None:
                st = sa.S3Store(f"s3://{self.policy['ledger_bucket']}", self.endpoint_url, ledger=True)
            if isinstance(st, sa.S3Store):
                self.meter.attach(st.s3, "ledger")
            self.ledger = Ledger(st, self.policy)
            month = now_utc().strftime("%Y-%m")
            scope = self.ledger.closed(month, self.job["job_id"])
            if scope:
                self.gate.remember_closed(scope)
                raise BudgetError(f"admissions for {month} are closed ({scope}); no further request was sent")
            try:
                self.ledger.admit(self.job, self.run_id, month)
            except BudgetError:
                raise
            except Exception as e:
                raise BudgetError(f"admission write failed ({type(e).__name__}); not running")
            self.admitted = True
            admissions = self.ledger.admissions()
            if (this_month(admissions, month) > self.policy["admission"]["per_month_global"]
                    or this_month(admissions, month, self.job["job_id"]) > self.job["admissions_per_month"]):
                self._refuse_and_maybe_close(month, admissions, BudgetError(
                    f"admissions for {month} used up; this run is recorded and refused"))
            try:
                rec, _sha, remaining = reserve(self.ledger, self.policy, self.job, self.run_id, month, admissions)
            except BudgetError as e:
                self._refuse_and_maybe_close(month, admissions, e)
            self.reservation = rec
            self.meter.limits = dict(self.job["per_run"])  # counters keep everything since admission
            self.meter.deadline_s = self.job["per_run"]["seconds"]
            self.meter.archive_allowed = True
        except BaseException:
            self.gate.leave()
            raise
        if hasattr(signal, "SIGALRM"):  # wall clock limit even while no request is in flight
            def alarm(signum, frame):
                raise BudgetError(f"run time limit {self.job['per_run']['seconds']}s reached")
            signal.signal(signal.SIGALRM, alarm)
            signal.alarm(self.job["per_run"]["seconds"])
        return remaining

    def settle(self, outcome):
        """Record the measured use plus the worst case of this very write, capped at the reservation.
        If this fails the admission and the reservation simply keep counting in full."""
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
        try:
            if self.reservation is None:
                return None
            count, prev = self.ledger.tail()
            used = self.meter.snapshot()
            worst = settlement_worst_case(self.policy)
            used = {d: min(used[d] + worst[d], self.job["per_run"][d]) for d in DIMENSIONS}
            body = {"format": "onjeon-budget-ledger-v1", "kind": "settlement", "job_id": self.job["job_id"],
                    "run_id": self.run_id, "reservation_seq": self.reservation["seq"], "outcome": outcome,
                    "at": stamp(), "amounts": used, "includes_settlement_worst_case": worst}
            rec, _ = self.ledger.append(body, count, prev)
            return rec
        except BaseException as e:
            return {"settlement_failed": type(e).__name__}
        finally:
            self.gate.leave()

    def summary(self):
        return {"job_id": self.job["job_id"], "run_id": self.run_id,
                "reservation_seq": self.reservation and self.reservation["seq"],
                "limits": self.meter.limits, "used": self.meter.snapshot(), "requests": self.meter.calls}


ACTIVE = None  # the Session of this process; source_archive.store() refuses R2/AWS without it


def start(job_path, endpoint_url=None, ledger_store=None, policy_path=None, gate_dir=None):
    global ACTIVE
    if ACTIVE is not None:
        raise BudgetError("a budget session is already open in this process")
    s = Session(job_path, endpoint_url, ledger_store, policy_path, gate_dir)
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
    """status: what is left (a budgeted run itself). init-pre-ledger: first record of a new ledger."""
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
    if a.cmd == "status":  # reading the ledger costs requests too, so status is an admitted, reserved run
        path = a.job.partition("#")[0]
        s = start(f"{path}#status", a.endpoint_url)
        try:
            month = now_utc().strftime("%Y-%m")
            records, _ = s.ledger.read()
            admissions = s.ledger.admissions()
            lim = s.policy["admission"]["limits"]
            glob, used_job = Ledger.usage(records, s.job["job_id"], month, admissions, lim)
            verify = load_job(f"{path}#verify", s.policy)["per_run"]
            room_glob, room_job = headroom(s.policy, s.job, admissions, s.job["job_id"], month)
            print(json.dumps({"records": len(records), "month": month,
                              "admissions_this_month": this_month(admissions, month),
                              "global_used": glob, "global_caps": s.policy["caps"],
                              "job_used_including_this_status": used_job, "job_caps": s.job["job_caps"],
                              "admission_room_job": room_job,
                              "verify_runs_left": min((s.job["job_caps"][d] - used_job[d] - room_job[d]) // verify[d]
                                                      for d in DIMENSIONS if verify[d])}, indent=1))
        finally:
            print("budget " + json.dumps(finish("ok")), file=sys.stderr)
        return 0
    policy = load_policy()
    if policy.get("ledger_genesis_sha256"):  # decided without any request
        raise BudgetError("the ledger is initialised (genesis pinned in the policy); nothing was sent")
    job = load_job(a.job)
    meter = Meter(policy, job, policy["admission"]["limits"], policy["admission"]["limits"]["seconds"])
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
    rec, rec_sha = ledger.append(body, 0, None)
    print(json.dumps({"written_seq": rec["seq"], "record_sha256": rec_sha, "requests": meter.snapshot()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
