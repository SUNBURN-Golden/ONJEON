#!/usr/bin/env python3
"""Content-addressed archive of public source originals and their derived outputs (ADR-0015).

Two stores, never mixed:
  raw     public disclosure originals (PDF, HTML, price tables) exactly as fetched
  derived extraction and OCR outputs computed from a raw object

Raw store layout:
  objects/sha256/<h0h1>/<h2h3>/<sha256>        the bytes; the key is the SHA-256 of the bytes
  observations/<source_id>/<observed_at>_<sha256[:16]>.json
                                               one record per fetch: url, time, hash, size, type
Derived store layout:
  derived/<raw sha256>/<kind>/<tool>@<version>/<name>
  derived/<raw sha256>/manifests/<sha256 of manifest>.json   (outputs: key + sha256)

Rules enforced here (on AWS also by the bucket policy in infra/s3/; R2 has no bucket policy, see infra/r2/):
- a key is written once; an existing key is never overwritten (S3: If-None-Match: *;
  local: refuse). Re-archiving identical bytes is a no-op that is verified, not a rewrite.
- a changed document at the same URL is a new object plus a new observation; the old object and
  its observations stay.
- there is no delete command.
- personal policy, health, family history or DNA data never enter these stores
  (only rows from docs/blueprint/validation/samples.csv or explicit public-source arguments).

Targets: file:///abs/dir  or  s3://bucket[/prefix]. The S3 API endpoint comes from --endpoint-url or
ONJEON_S3_ENDPOINT (unset = AWS S3, ap-northeast-2). An endpoint on *.r2.cloudflarestorage.com selects
Cloudflare R2 (infra/r2/): region "auto", credentials from R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY,
no SSE header (R2 encrypts every object at rest). Otherwise credentials come from the standard AWS chain.
Never pass keys on the command line, never print them.

Usage:
  source_archive.py archive-samples --cache DIR --raw T --derived T [--derived-src DIR]
  source_archive.py add-observation --file F --source-id ID --url U --observed-at TS --raw T
  source_archive.py fetch --raw T --out DIR          # restore samples.csv originals by hash
  source_archive.py copy --src file:///bundle/raw --dst s3://bucket   # no overwrite, conflicts abort
  source_archive.py verify --raw T [--report out.json]
  source_archive.py listing --src T --out listing.json   # key -> sha256 of every object (no content)
  source_archive.py verify-copy (--src T | --expected listing.json) --dst s3://bucket [--report out.json]
                                                     # download every key back and compare bytes
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))  # r2_budget; -I leaves the script directory off sys.path
SAMPLES = ROOT / "docs/blueprint/validation/samples.csv"
SAFE_ID = re.compile(r"^[a-z0-9_]+$")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def object_key(digest):
    return f"objects/sha256/{digest[0:2]}/{digest[2:4]}/{digest}"


class Exists(Exception):
    pass


ABSENT = object()  # stored_sha256(): the key does not exist


class Conflict(Exception):
    """A key already holds different bytes. Nothing was overwritten; the run must stop."""


def put_once(st, key, body, content_type):
    """Write a key once. Same bytes already there: 'already_present'. Different bytes: Conflict.

    Every write in this module goes through here, so a re-run can never silently keep an old
    object while reporting the hash of a new input.
    """
    stored = st.stored_sha256(key) if hasattr(st, "stored_sha256") else ABSENT
    if stored is not ABSENT:  # S3: the key exists; decide without uploading the bytes again
        if stored is None:  # no checksum recorded: compare by downloading
            stored = sha256_bytes(st.get(key))
        if stored != sha256_bytes(body):
            raise Conflict(f"{key}: stored sha256 {stored[:16]}… differs from new input "
                           f"{sha256_bytes(body)[:16]}…; not overwritten")
        return "already_present"
    try:
        st.put_new(key, body, content_type)
        return "stored"
    except Exists:
        existing = st.get(key)
        if sha256_bytes(existing) != sha256_bytes(body):
            raise Conflict(f"{key}: stored sha256 {sha256_bytes(existing)[:16]}… differs from new input "
                           f"{sha256_bytes(body)[:16]}…; not overwritten")
        return "already_present"


class LocalStore:
    def __init__(self, root):
        self.root = Path(root)

    def put_new(self, key, body, content_type):
        p = self.root / key
        if p.exists():
            raise Exists(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.{id(body)}.partial")
        tmp.write_bytes(body)
        try:
            os.link(tmp, p)  # atomic create-if-absent: a concurrent writer gets Exists, never an overwrite
        except FileExistsError:
            raise Exists(key)
        finally:
            tmp.unlink()

    def get(self, key):
        return (self.root / key).read_bytes()

    def exists(self, key):
        return (self.root / key).exists()

    def list(self, prefix):
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file() and not p.name.endswith(".partial"))


R2_HOST_SUFFIX = ".r2.cloudflarestorage.com"


def provider_of(endpoint_url):
    """aws (no endpoint), r2 (Cloudflare R2 S3 API) or emulator (any other endpoint, tests only)."""
    if not endpoint_url:
        return "aws"
    from urllib.parse import urlparse
    u = urlparse(endpoint_url)
    if (u.hostname or "").endswith(R2_HOST_SUFFIX):
        if u.scheme != "https":
            raise SystemExit("R2 endpoint must be https")
        return "r2"
    return "emulator"


class S3Store:
    def __init__(self, url, endpoint_url=None, ledger=False):
        import boto3  # only needed for s3:// targets
        from botocore.config import Config
        rest = url[len("s3://"):]
        self.bucket, _, prefix = rest.partition("/")
        self.prefix = prefix.strip("/")
        endpoint_url = endpoint_url or os.environ.get("ONJEON_S3_ENDPOINT") or None
        self.provider = provider_of(endpoint_url)
        import r2_budget
        budget = r2_budget.ACTIVE
        if self.provider in ("aws", "r2") and budget is None and not ledger:
            raise SystemExit(f"{self.provider} access needs a budget job (--job infra/r2/jobs/<job>.json); "
                             "nothing was sent")
        kw = {}
        if self.provider == "r2":
            key, secret = os.environ.get("R2_ACCESS_KEY_ID"), os.environ.get("R2_SECRET_ACCESS_KEY")
            if ledger and os.environ.get("R2_LEDGER_ACCESS_KEY_ID"):
                key, secret = os.environ.get("R2_LEDGER_ACCESS_KEY_ID"), os.environ.get("R2_LEDGER_SECRET_ACCESS_KEY")
            if not (key and secret):  # never fall back to the AWS chain for R2
                raise SystemExit("R2 endpoint selected but R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY are not set")
            kw = {"aws_access_key_id": key, "aws_secret_access_key": secret}
        # checksums only when we send one ourselves (SHA-256 below); keeps S3-compatible stores working
        attempts = budget.policy["per_request"]["max_attempts"] if budget else 3
        base = {"signature_version": "s3v4", "retries": {"max_attempts": attempts, "mode": "standard"},
                "connect_timeout": r2_budget.CONNECT_TIMEOUT, "read_timeout": r2_budget.READ_TIMEOUT}
        try:  # botocore >= 1.36 adds default CRC checksums; older versions have neither the default nor the option
            cfg = Config(**base, request_checksum_calculation="when_required",
                         response_checksum_validation="when_required")
        except TypeError:
            cfg = Config(**base)
        self.s3 = boto3.client("s3", region_name="auto" if self.provider == "r2" else "ap-northeast-2",
                               endpoint_url=endpoint_url, config=cfg, **kw)
        put = self.s3.meta.service_model.operation_model("PutObject").input_shape.members
        if "IfNoneMatch" not in put:  # botocore before 1.35 cannot send a conditional put: never write unguarded
            import botocore
            raise SystemExit(f"botocore {botocore.__version__} cannot send If-None-Match on PutObject; "
                             "install boto3>=1.35 (tested with 1.43.100)")
        self.meter = budget.meter if budget else None
        if self.meter and not ledger:
            self.meter.attach(self.s3, "archive")

    def _k(self, key):
        return f"{self.prefix}/{key}" if self.prefix else key

    def put_new(self, key, body, content_type):
        from botocore.exceptions import ClientError
        kw = {}
        if self.provider == "aws":
            kw["ServerSideEncryption"] = "AES256"  # R2 encrypts at rest itself and rejects this header
        try:
            self.s3.put_object(
                Bucket=self.bucket, Key=self._k(key), Body=body, ContentType=content_type,
                IfNoneMatch="*",  # never overwrite (AWS: the bucket policy also denies writes without it)
                ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode(),
                **kw,
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict") \
                    or e.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412:
                raise Exists(key)
            raise

    def get(self, key):
        r = self.s3.get_object(Bucket=self.bucket, Key=self._k(key))
        if self.meter:  # refuse to read a body that would exceed the byte limit
            try:
                self.meter.charge_get_bytes(r.get("ContentLength") or 0)
            except BaseException:
                r["Body"].close()
                raise
        return r["Body"].read()

    def stored_sha256(self, key):
        """HEAD (Class B): ABSENT, the SHA-256 recorded at upload, or None if it exists without one."""
        from botocore.exceptions import ClientError
        try:
            h = self.s3.head_object(Bucket=self.bucket, Key=self._k(key), ChecksumMode="ENABLED")
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return ABSENT
            raise
        c = h.get("ChecksumSHA256")
        return base64.b64decode(c).hex() if c and "-" not in c else None

    def exists(self, key):
        from botocore.exceptions import ClientError
        try:
            self.s3.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def list(self, prefix):
        out, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": self._k(prefix)}
            if token:
                kw["ContinuationToken"] = token
            r = self.s3.list_objects_v2(**kw)
            out += [o["Key"][len(self.prefix) + 1:] if self.prefix else o["Key"] for o in r.get("Contents", [])]
            if not r.get("IsTruncated"):
                return sorted(out)
            token = r["NextContinuationToken"]


def describe(st, target):
    """Store label for reports: file, or provider plus bucket (never the endpoint, which names the account)."""
    if isinstance(st, S3Store):
        return f"{st.provider}:{st.bucket}" + (f"/{st.prefix}" if st.prefix else "")
    return target.split("://")[0]


def store(target, endpoint_url=None):
    if target.startswith("file://"):
        return LocalStore(target[len("file://"):])
    if target.startswith("s3://"):
        return S3Store(target, endpoint_url)
    raise SystemExit(f"target must be file:///dir or s3://bucket[/prefix], got {target}")


def put_raw(raw, body, content_type):
    """Write the bytes under their own hash. Returns (digest, 'stored'|'already_present')."""
    digest = sha256_bytes(body)
    return digest, put_once(raw, object_key(digest), body, content_type)


def put_observation(raw, source_id, url, observed_at, digest, size, content_type, extra=None):
    if not SAFE_ID.match(source_id):
        raise SystemExit(f"source_id must be lower snake_case: {source_id}")
    stamp = re.sub(r"[^0-9TZ]", "", observed_at)
    key = f"observations/{source_id}/{stamp}_{digest[:16]}.json"
    rec = {"source_id": source_id, "url": url, "observed_at": observed_at, "sha256": digest,
           "bytes": size, "content_type": content_type, "object_key": object_key(digest)}
    rec.update(extra or {})
    body = (json.dumps(rec, ensure_ascii=False, indent=2) + "\n").encode()
    return key, put_once(raw, key, body, "application/json")


def content_type_of(path, fmt):
    if fmt == "html":
        return "text/html"
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def cmd_archive_samples(a):
    raw = store(a.raw, a.endpoint_url)
    derived = store(a.derived, a.endpoint_url) if a.derived else None
    rows = list(csv.DictReader(SAMPLES.open(encoding="utf-8")))
    results = []
    for r in rows:
        p = Path(a.cache) / r["cache_path"]
        if not p.exists():
            results.append({"sample_id": r["sample_id"], "status": "missing_in_cache"})
            continue
        body = p.read_bytes()
        ctype = content_type_of(p, r["format"])
        digest, state = put_raw(raw, body, ctype)
        if digest != r["sha256"]:
            results.append({"sample_id": r["sample_id"], "status": "hash_differs_from_samples_csv", "sha256": digest})
            continue
        extra = {"sample_id": r["sample_id"], "doc_role": r["doc_role"], "format": r["format"]}
        okey, ostate = put_observation(raw, r["sample_id"], r["url"], r["retrieved_at"], digest, len(body), ctype, extra)
        results.append({"sample_id": r["sample_id"], "sha256": digest, "object": state, "observation": ostate})
        if derived and a.derived_src:
            results[-1]["derived"] = put_derived_for(derived, Path(a.derived_src) / Path(r["cache_path"]).parent, digest, r)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(x.get("object") in ("stored", "already_present") for x in results) else 1


# Extraction outputs produced in the V1 session, with the tool that produced them.
DERIVED_FILES = [
    (r".*\.layout\.txt$", "text", "poppler-pdftotext-layout@24.02.0"),
    (r".*\.raw\.txt$", "text", "poppler-pdftotext-reading-order@24.02.0"),
    (r".*\.plumber_selected\.txt$", "text", "pdfplumber@0.11.10-x1.5-y3-selected-pages"),
    (r".*\.tables\.txt$", "text", "html-table-serializer@v1-session"),
    (r".*page\.text\.txt$", "text", "html-text@v1-session"),
    (r"ocr_all\.txt$", "ocr", "tesseract@5.3.4-kor-psm3-300dpi-gray"),
    (r"ocr/.*\.txt$", "ocr", "tesseract@5.3.4-kor-psm3-300dpi-gray"),
]


def belongs_to(rel, row):
    """Is this derived file an output of this sample's original? Two samples can share a
    directory (the two KLIA pages), so the file name must start with the original's stem."""
    stem = Path(row["cache_path"]).name.split(".")[0]
    if row.get("format") == "scanned_pdf" and (rel.startswith("ocr/") or rel == "ocr_all.txt"):
        return True
    return Path(rel).name.split(".")[0] == stem


def put_derived_for(derived, src_dir, digest, row):
    done = []
    if not src_dir.exists():
        return {"outputs": 0, "manifest_sha256": None}
    for f in sorted(src_dir.rglob("*.txt")):
        rel = str(f.relative_to(src_dir))
        if not belongs_to(rel, row):
            continue
        for pat, kind, tool in DERIVED_FILES:
            if re.search(pat, rel):
                key = f"derived/{digest}/{kind}/{tool}/{rel.replace('/', '__')}"
                body = f.read_bytes()
                state = put_once(derived, key, body, "text/plain; charset=utf-8")
                done.append({"key": key, "sha256": sha256_bytes(body), "state": state})
                break
    if done:
        # content-addressed manifest: outputs (key, sha256) only, no per-run state or time
        manifest = {"raw_sha256": digest, "sample_id": row["sample_id"],
                    "outputs": sorted(({"key": x["key"], "sha256": x["sha256"]} for x in done), key=lambda x: x["key"])}
        body = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        put_once(derived, f"derived/{digest}/manifests/{sha256_bytes(body)}.json", body, "application/json")
        return {"outputs": len(done), "manifest_sha256": sha256_bytes(body)}
    return {"outputs": 0, "manifest_sha256": None}


def cmd_add_observation(a):
    raw = store(a.raw, a.endpoint_url)
    body = Path(a.file).read_bytes()
    ctype = a.content_type or content_type_of(Path(a.file), "html" if a.file.endswith(".html") else "")
    digest, state = put_raw(raw, body, ctype)
    extra = json.loads(a.extra) if a.extra else {}
    okey, ostate = put_observation(raw, a.source_id, a.url, a.observed_at, digest, len(body), ctype, extra)
    print(json.dumps({"sha256": digest, "object": state, "observation": okey, "observation_state": ostate}, indent=2))
    return 0


def cmd_fetch(a):
    raw = store(a.raw, a.endpoint_url)
    out = Path(a.out)
    for r in csv.DictReader(SAMPLES.open(encoding="utf-8")):
        dest = out / r["cache_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        body = raw.get(object_key(r["sha256"]))
        dest.write_bytes(body)
    print(f"restored originals into {out}")
    return 0


def cmd_verify(a):
    raw = store(a.raw, a.endpoint_url)
    results = []
    for r in csv.DictReader(SAMPLES.open(encoding="utf-8")):
        key = object_key(r["sha256"])
        try:
            body = raw.get(key)
        except Exception as e:  # missing object or access error: report, never treat as verified
            results.append({"sample_id": r["sample_id"], "status": "not_retrievable", "detail": type(e).__name__})
            continue
        got = sha256_bytes(body)
        obs = raw.list(f"observations/{r['sample_id']}/")
        results.append({"sample_id": r["sample_id"], "status": "byte_identical" if got == r["sha256"] else "hash_mismatch",
                        "sha256_recorded": r["sha256"], "sha256_downloaded": got, "bytes": len(body),
                        "observations": len(obs)})
    summary = {}
    for x in results:
        summary[x["status"]] = summary.get(x["status"], 0) + 1
    report = {"checked_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "store": describe(raw, a.raw), "summary": summary, "results": results}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if a.report:
        Path(a.report).write_text(text, encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary.get("byte_identical") == len(results) else 1


def cmd_copy(a):
    """Copy every key of one store into another without overwriting (local bundle -> S3)."""
    src, dst = store(a.src, a.endpoint_url), store(a.dst, a.endpoint_url)
    counts = {"stored": 0, "already_present": 0}
    for key in src.list(""):
        body = src.get(key)
        if key.startswith("objects/sha256/") and sha256_bytes(body) != key.rsplit("/", 1)[1]:
            raise SystemExit(f"source store corruption: {key}")
        ctype = "application/json" if key.endswith(".json") else ("text/plain; charset=utf-8" if key.endswith(".txt") else "application/octet-stream")
        counts[put_once(dst, key, body, ctype)] += 1
    print(json.dumps(counts))
    return 0


def listing_of(st):
    return {key: sha256_bytes(st.get(key)) for key in st.list("")}


def cmd_listing(a):
    """Write every key of a store with the SHA-256 of its bytes (no content), to pin a store in Git."""
    src = store(a.src, a.endpoint_url)
    keys = listing_of(src)
    doc = {"listing_rule": "key-sha256-v1", "keys": len(keys), "objects": keys}
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"keys": len(keys)}))
    return 0


def cmd_verify_copy(a):
    """Download every key of the destination back and compare it with the source, byte for byte.
    Covers what verify does not: extra originals, every observation, derived outputs and manifests.
    The source is a store (--src) or a pinned listing (--expected, from the listing command)."""
    dst = store(a.dst, a.endpoint_url)
    if getattr(a, "expected", None):
        expected = json.loads(Path(a.expected).read_text(encoding="utf-8"))["objects"]
        src_label = "listing"
    else:
        src = store(a.src, a.endpoint_url)
        expected, src_label = listing_of(src), describe(src, a.src)
    src_keys, dst_keys = sorted(expected), set(dst.list(""))
    results, summary = [], {}
    for key in src_keys:
        want = expected[key]
        if key not in dst_keys:
            st, got = "missing", None
        else:
            got = sha256_bytes(dst.get(key))
            st = "byte_identical" if got == want else "hash_mismatch"
        if st == "byte_identical" and key.startswith("objects/sha256/") and got != key.rsplit("/", 1)[1]:
            st = "hash_mismatch"
        results.append({"key": key, "status": st, "sha256_source": want, "sha256_downloaded": got})
        summary[st] = summary.get(st, 0) + 1
    extra = sorted(dst_keys - set(src_keys))
    if extra:
        summary["extra_in_destination"] = len(extra)
    report = {"checked_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "source": src_label, "destination": describe(dst, a.dst),
              "summary": summary, "extra_in_destination": extra, "results": results}
    if a.report:
        Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary.get("byte_identical", 0) == len(src_keys) and src_keys else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint-url", help="S3 API endpoint (R2 or an emulator); default $ONJEON_S3_ENDPOINT, else AWS")
    ap.add_argument("--job", help="budget job (infra/r2/jobs/*.json); required for R2/AWS targets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("archive-samples")
    s.add_argument("--cache", required=True)
    s.add_argument("--raw", required=True)
    s.add_argument("--derived")
    s.add_argument("--derived-src")
    s = sub.add_parser("add-observation")
    for k in ("--file", "--source-id", "--url", "--observed-at", "--raw"):
        s.add_argument(k, required=True)
    s.add_argument("--content-type")
    s.add_argument("--extra")
    s = sub.add_parser("fetch")
    s.add_argument("--raw", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("copy")
    s.add_argument("--src", required=True)
    s.add_argument("--dst", required=True)
    s = sub.add_parser("verify")
    s.add_argument("--raw", required=True)
    s.add_argument("--report")
    s = sub.add_parser("listing")
    s.add_argument("--src", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("verify-copy")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--src")
    g.add_argument("--expected", help="pinned listing JSON (key -> sha256) instead of a source store")
    s.add_argument("--dst", required=True)
    s.add_argument("--report")
    a = ap.parse_args()
    return with_budget(a.job, a.endpoint_url, lambda: run(a))


def with_budget(job, endpoint_url, fn):
    """Run fn inside a budget session when a job is given; always settle; print the usage."""
    import r2_budget
    outcome, code = "error", 1
    try:
        if job:
            r2_budget.start(job, endpoint_url)
        code = fn()
        outcome = "ok" if code == 0 else f"exit_{code}"
        return code
    except Conflict as e:
        print(f"conflict: {e}", file=sys.stderr)
        outcome, code = "conflict", 3
        return 3
    except r2_budget.BudgetError as e:
        print(str(e), file=sys.stderr)
        outcome, code = "budget_stop", 4
        return 4
    finally:
        if job:
            summary = r2_budget.finish(outcome)
            print("budget " + (json.dumps(summary) if summary else "no reservation made; no archive request was sent"),
                  file=sys.stderr)


def run(a):
    return {"archive-samples": cmd_archive_samples, "add-observation": cmd_add_observation,
            "fetch": cmd_fetch, "copy": cmd_copy, "verify": cmd_verify,
            "verify-copy": cmd_verify_copy, "listing": cmd_listing}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
