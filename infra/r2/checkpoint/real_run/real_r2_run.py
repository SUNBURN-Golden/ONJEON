"""Real-R2 verification harness for T-OP-04 (run by hand, see VERIFICATION.md).

Secrets come from the environment only and are never printed. The test ledger and test archive are
separate buckets; the production ledger and archive are not written by this script.
usage: ONJEON_REPO=<repo> real_r2_run.py <workdir> <step>
"""
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(os.environ["ONJEON_REPO"])
sys.path.insert(0, str(REPO / "tools"))
import r2_budget as b  # noqa: E402
import source_archive as sa  # noqa: E402

W = Path(sys.argv[1])
STEP = sys.argv[2]
EP = os.environ["R2_ENDPOINT"]
# Test buckets only; the names can be overridden so a supplementary run can use a second test
# ledger (the first is month-closed and stays untouched). Production buckets are never named here.
LEDGER_B = os.environ.get("ONJEON_TEST_LEDGER_BUCKET", "onjeon-t-op-04-test-ledger")
ARCH_B = os.environ.get("ONJEON_TEST_ARCHIVE_BUCKET", "onjeon-t-op-04-test-archive")
BODY = b"t-op-04 real r2 conditional write probe\n"
KEY = sa.object_key(hashlib.sha256(BODY).hexdigest())
POLICY, JOB, GATE = W / "policy.json", W / "job.json", W / "gate"
PREV = W / "previous_policy_sha256.txt"
PROD = json.loads((REPO / "infra/r2/budget_policy.json").read_text())
PJOB = json.loads((REPO / "infra/r2/jobs/initial-119.json").read_text())
TEST_JOB_ID = "t-op-04-real-r2-test"


def out(**kw):
    print(json.dumps(kw, sort_keys=True))
    sys.stdout.flush()


def raw_s3():
    import boto3
    return boto3.client("s3", region_name="auto", endpoint_url=EP,
                        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])


def write_files(genesis=None, per_month_global=100):
    p = copy.deepcopy(PROD)
    p["ledger_bucket"] = LEDGER_B
    p["previous_policy_sha256"] = [x for x in PREV.read_text().split()] if PREV.exists() else []
    p["admission"]["per_month_global"] = per_month_global
    p.pop("ledger_genesis_sha256", None)
    p.pop("ledger_genesis_note", None)
    if genesis:
        p["ledger_genesis_sha256"] = genesis
    POLICY.write_text(json.dumps(p, indent=1))
    lst = W / "listing.json"
    lst.write_text(json.dumps({"listing_rule": "key-sha256-v1", "keys": 1,
                               "objects": {KEY: hashlib.sha256(BODY).hexdigest()}}))
    j = copy.deepcopy(PJOB)
    j["job_id"] = TEST_JOB_ID
    j["buckets"] = {ARCH_B: {"listing": str(lst), "listing_sha256": b.sha256_file(lst)}}
    j["admissions_per_month"] = 20
    JOB.write_text(json.dumps(j, indent=1))


def run(profile, fn):
    """One budgeted run: admission, reservation, fn(session), settlement."""
    s = b.start(f"{JOB}#{profile}", EP, policy_path=POLICY, gate_dir=GATE)
    try:
        r = fn(s)
    finally:
        summ = b.finish("ok")
    return r, summ


def counts(summ):
    return {"requests": summ["requests"], "used": summ["used"], "settlement": summ["settlement"]}



def main():
    if STEP == "setup":
        s3 = raw_s3()
        res = {}
        for name in (LEDGER_B, ARCH_B):
            try:
                s3.create_bucket(Bucket=name)
                res[name] = "created"
            except Exception as e:
                res[name] = type(e).__name__ + ":" + str(getattr(e, "response", {}).get("Error", {}).get("Code"))
        out(buckets=res)
    elif STEP == "genesis":
        write_files()
        pol = b.load_policy(POLICY)
        job = b.load_job(f"{JOB}#status")
        meter = b.Meter(pol, job, pol["admission"]["limits"], 120)
        st = sa.S3Store(f"s3://{LEDGER_B}", EP, ledger=True)
        meter.attach(st.s3, "ledger")
        body = {"format": "onjeon-budget-ledger-v1", "kind": "pre_ledger_usage", "job_id": job["job_id"],
                "job_sha256": job["_sha256"], "run_id": "pre-ledger", "at": b.stamp(),
                "amounts": {d: 0 for d in b.DIMENSIONS}, "note": "test ledger genesis (T-OP-04 real R2 run)"}
        rec, sha = b.Ledger(st, pol).append(body, 0, None)
        PREV.write_text(b.sha256_file(POLICY) + "\n")
        write_files(genesis=sha)
        out(genesis_seq=rec["seq"], requests=meter.snapshot())
    elif STEP == "fixpolicy":  # re-derive the policy chain after the genesis record was written
        g = json.loads(POLICY.read_text())["ledger_genesis_sha256"]
        PREV.unlink(missing_ok=True)
        write_files()
        PREV.write_text(b.sha256_file(POLICY) + "\n")
        write_files(genesis=g)
        out(fixed=True)
    elif STEP == "closedcheck":  # a machine that has not seen the closure: how many requests until it stops
        import tempfile
        s = b.Session(f"{JOB}#status", EP, None, POLICY, Path(tempfile.mkdtemp()))
        try:
            s.open()
            res = "RAN"
        except b.BudgetError as e:
            res = str(e)[:120]
        out(step=STEP, result=res, requests=s.meter.snapshot())
    elif STEP == "limit":
        with PREV.open("a") as f:  # records so far were written under the current policy file
            f.write(b.sha256_file(POLICY) + "\n")  # shrink the monthly admission limit of the TEST policy (arg 3)
        write_files(genesis=json.loads(POLICY.read_text())["ledger_genesis_sha256"],
                    per_month_global=int(sys.argv[3]))
        out(per_month_global=int(sys.argv[3]))
    elif STEP in ("status", "checkpoint", "audit"):
        def fn(s):
            if STEP == "checkpoint":
                return b.write_checkpoint(s.ledger)
            if STEP == "audit":
                return b.audit_checkpoints(s.ledger)
            recs, _ = s.ledger.read()
            return {"records_after_checkpoint": len(recs), "base_seq": s.ledger.base_seq}
        r, summ = run("verify" if STEP == "audit" else "status", fn)
        out(step=STEP, result=r, **counts(summ))
    elif STEP == "race":  # lose the reservation race on purpose: a rival writes the same seq first
        pol = b.load_policy(POLICY)
        rival = b.Ledger(sa.S3Store(f"s3://{LEDGER_B}", EP, ledger=True), pol)
        orig, fired = b.Ledger.read, []

        def read(self, known=None):
            res = orig(self, known)
            if not fired and self is not rival:
                fired.append(1)
                recs, prev = res
                rival.append({"format": "onjeon-budget-ledger-v1", "kind": "reservation", "job_id": TEST_JOB_ID,
                              "job_sha256": "0" * 64, "profile": "status", "run_id": "rival", "at": b.stamp(),
                              "amounts": {d: 0 for d in b.DIMENSIONS}}, self.base_seq + len(recs), prev)
            return res
        b.Ledger.read = read
        r, summ = run("status", lambda s: len(s.ledger.read()[0]))
        out(step=STEP, rival_wrote_first=bool(fired), **counts(summ))
    elif STEP == "gate":  # a second concurrent run on this computer is refused before any request
        s = b.start(f"{JOB}#status", EP, policy_path=POLICY, gate_dir=GATE)
        first = b.ACTIVE
        try:
            calls = s.meter.calls
            try:
                b.ACTIVE = None
                b.Session(f"{JOB}#status", EP, None, POLICY, GATE).open()
                res = "NOT REFUSED"
            except BaseException as e:
                res = f"refused: {type(e).__name__}: {str(e)[:100]}"
            b.ACTIVE = first
            out(step=STEP, second_run=res, first_run_request_count_unchanged=(s.meter.calls == calls))
        finally:
            summ = b.finish("ok")
        out(step=STEP, **counts(summ))
    elif STEP == "conditional":
        def fn(s):
            st = sa.store(f"s3://{ARCH_B}", EP)
            first = sa.put_once(st, KEY, BODY, "text/plain")  # stores, or already_present (HEAD only)
            try:
                st.put_new(KEY, BODY, "text/plain")  # same key, same bytes: the PUT reaches R2
                second = "WRITTEN (overwrote!)"
            except sa.Exists:
                second = "412 -> Exists"
            try:
                st.put_new(KEY, b"different bytes", "text/plain")
                guard = "SENT"
            except b.BudgetError as e:
                guard = "refused before sending: " + str(e)[-40:]
            same = hashlib.sha256(st.get(KEY)).hexdigest() == hashlib.sha256(BODY).hexdigest()
            return {"first": first, "tool_put_same_key": second, "tool_put_other_bytes": guard,
                    "bytes_unchanged": same}
        r, summ = run("upload", fn)
        out(step=STEP, result=r, **counts(summ))
    elif STEP == "rawconditional":  # outside the tool: R2 itself must refuse a different-bytes conditional PUT
        from botocore.exceptions import ClientError
        s3 = raw_s3()
        try:
            s3.put_object(Bucket=ARCH_B, Key=KEY, Body=b"different bytes", IfNoneMatch="*")
            res = "WRITTEN (overwrote!)"
        except ClientError as e:
            res = f"HTTP {e.response['ResponseMetadata']['HTTPStatusCode']} {e.response['Error']['Code']}"
        body = s3.get_object(Bucket=ARCH_B, Key=KEY)["Body"].read()
        out(step=STEP, put=res, bytes_unchanged=(body == BODY), requests=3)
    elif STEP == "cprewrite":  # a second write to the newest checkpoint key must be refused
        def fn(s):
            k = s.ledger.checkpoints()[-1]
            body = s.ledger.st.get(k)
            try:
                s.ledger.st.put_new(k, body + b" ", "application/json")
                res = "WRITTEN (overwrote!)"
            except sa.Exists:
                res = "412 -> Exists"
            return {"rewrite": res, "bytes_unchanged": s.ledger.st.get(k) == body}
        r, summ = run("status", fn)
        out(step=STEP, result=r, **counts(summ))
    else:
        sys.exit("unknown step")



try:
    main()
except b.BudgetError as e:
    out(refused_or_failed="BudgetError", code=e.code if not isinstance(e.code,str) else 4, message=str(e)[:300])
    sys.exit(4)
