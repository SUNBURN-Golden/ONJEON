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
  derived/<raw sha256>/<kind>/<tool>@<version>/manifest.json

Rules enforced here (and by the bucket policy in infra/s3/, which is the real guard):
- a key is written once; an existing key is never overwritten (S3: If-None-Match: *;
  local: refuse). Re-archiving identical bytes is a no-op that is verified, not a rewrite.
- a changed document at the same URL is a new object plus a new observation; the old object and
  its observations stay.
- there is no delete command.
- personal policy, health, family history or DNA data never enter these stores
  (only rows from docs/blueprint/validation/samples.csv or explicit public-source arguments).

Targets: file:///abs/dir  or  s3://bucket[/prefix]  (credentials from the standard AWS chain;
never pass keys on the command line, never print them). --endpoint-url is for an S3 emulator.

Usage:
  source_archive.py archive-samples --cache DIR --raw T --derived T [--derived-src DIR]
  source_archive.py add-observation --file F --source-id ID --url U --observed-at TS --raw T
  source_archive.py fetch --raw T --out DIR          # restore samples.csv originals by hash
  source_archive.py copy --src file:///bundle/raw --dst s3://bucket   # no overwrite, conflicts abort
  source_archive.py verify --raw T [--report out.json]
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import json
import mimetypes
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "docs/blueprint/validation/samples.csv"
SAFE_ID = re.compile(r"^[a-z0-9_]+$")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def object_key(digest):
    return f"objects/sha256/{digest[0:2]}/{digest[2:4]}/{digest}"


class Exists(Exception):
    pass


class LocalStore:
    def __init__(self, root):
        self.root = Path(root)

    def put_new(self, key, body, content_type):
        p = self.root / key
        if p.exists():
            raise Exists(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".partial")
        tmp.write_bytes(body)
        tmp.rename(p)

    def get(self, key):
        return (self.root / key).read_bytes()

    def exists(self, key):
        return (self.root / key).exists()

    def list(self, prefix):
        base = self.root / prefix
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file() and not p.name.endswith(".partial"))


class S3Store:
    def __init__(self, url, endpoint_url=None):
        import boto3  # only needed for s3:// targets
        rest = url[len("s3://"):]
        self.bucket, _, prefix = rest.partition("/")
        self.prefix = prefix.strip("/")
        self.s3 = boto3.client("s3", region_name="ap-northeast-2", endpoint_url=endpoint_url)

    def _k(self, key):
        return f"{self.prefix}/{key}" if self.prefix else key

    def put_new(self, key, body, content_type):
        from botocore.exceptions import ClientError
        try:
            self.s3.put_object(
                Bucket=self.bucket, Key=self._k(key), Body=body, ContentType=content_type,
                IfNoneMatch="*",  # never overwrite; the bucket policy also denies writes without it
                ChecksumAlgorithm="SHA256",
                ChecksumSHA256=base64.b64encode(hashlib.sha256(body).digest()).decode(),
                ServerSideEncryption="AES256",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] in ("PreconditionFailed", "ConditionalRequestConflict"):
                raise Exists(key)
            raise

    def get(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=self._k(key))["Body"].read()

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


def store(target, endpoint_url=None):
    if target.startswith("file://"):
        return LocalStore(target[len("file://"):])
    if target.startswith("s3://"):
        return S3Store(target, endpoint_url)
    raise SystemExit(f"target must be file:///dir or s3://bucket[/prefix], got {target}")


def put_raw(raw, body, content_type):
    """Write the bytes under their own hash. Returns (digest, 'stored'|'already_present')."""
    digest = sha256_bytes(body)
    key = object_key(digest)
    try:
        raw.put_new(key, body, content_type)
        state = "stored"
    except Exists:
        if sha256_bytes(raw.get(key)) != digest:
            raise SystemExit(f"store corruption: {key} does not hash to its key")
        state = "already_present"
    return digest, state


def put_observation(raw, source_id, url, observed_at, digest, size, content_type, extra=None):
    if not SAFE_ID.match(source_id):
        raise SystemExit(f"source_id must be lower snake_case: {source_id}")
    stamp = re.sub(r"[^0-9TZ]", "", observed_at)
    key = f"observations/{source_id}/{stamp}_{digest[:16]}.json"
    rec = {"source_id": source_id, "url": url, "observed_at": observed_at, "sha256": digest,
           "bytes": size, "content_type": content_type, "object_key": object_key(digest)}
    rec.update(extra or {})
    try:
        raw.put_new(key, (json.dumps(rec, ensure_ascii=False, indent=2) + "\n").encode(), "application/json")
        return key, "stored"
    except Exists:
        return key, "already_present"


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


def put_derived_for(derived, src_dir, digest, row):
    done = []
    if not src_dir.exists():
        return done
    for f in sorted(src_dir.rglob("*.txt")):
        rel = str(f.relative_to(src_dir))
        for pat, kind, tool in DERIVED_FILES:
            if re.search(pat, rel):
                key = f"derived/{digest}/{kind}/{tool}/{rel.replace('/', '__')}"
                body = f.read_bytes()
                try:
                    derived.put_new(key, body, "text/plain; charset=utf-8")
                    state = "stored"
                except Exists:
                    state = "already_present"
                done.append({"key": key, "sha256": sha256_bytes(body), "state": state})
                break
    if done:
        manifest = {"raw_sha256": digest, "sample_id": row["sample_id"], "outputs": done,
                    "note": "outputs of the V1 session (2026-10-09); tool versions as recorded in the key"}
        key = f"derived/{digest}/manifest-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        try:
            derived.put_new(key, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(), "application/json")
        except Exists:
            pass
    return len(done)


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
              "store": a.raw.split("://")[0], "summary": summary, "results": results}
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
        try:
            dst.put_new(key, body, ctype)
            counts["stored"] += 1
        except Exists:
            if sha256_bytes(dst.get(key)) != sha256_bytes(body):
                raise SystemExit(f"conflict: {key} exists in the target with different bytes; not overwritten")
            counts["already_present"] += 1
    print(json.dumps(counts))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint-url", help="S3-compatible emulator endpoint for tests only")
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
    a = ap.parse_args()
    return {"archive-samples": cmd_archive_samples, "add-observation": cmd_add_observation,
            "fetch": cmd_fetch, "copy": cmd_copy, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
