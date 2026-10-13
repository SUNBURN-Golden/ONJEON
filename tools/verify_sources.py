#!/usr/bin/env python3
"""Two separate checks of the V1 validation samples (ADR-0015). Never mix their results.

reproduce  보관본 재현 검사 — with the originals preserved at the time:
           byte SHA-256 against samples.csv, every quoted line on its cited page in a fresh
           extraction (HTML: every quoted cell in the visible text), the scanned sample re-OCRed
           with --ocr, and archived extraction outputs regenerated with the same tool version.
           Status codes: vocabulary axis `archive_reproduction`.

detect     현재 출처 변경 감지 — fetch each recorded URL now and compare with the last observation:
           a different document is a new version candidate to archive and review. It never
           replaces the past original and never turns a past reproduction into a failure.
           Status codes: vocabulary axis `source_change`. For HTML the content hash
           (tools/html_content_hash.py, rule html-visible-text-v1) is an auxiliary signal; equal
           content with different bytes is `bytes_changed_content_same`, never byte identity.

Originals come from the raw archive (tools/source_archive.py layout; file:// or s3://) or from a
cache directory laid out by samples.csv `cache_path`. Downloads are untrusted input: hashed and
parsed only. TLS verification stays on; only network errors are retried.

Usage:
  verify_sources.py reproduce --raw file:///archive/raw [--derived file:///archive/derived] [--ocr] --report r.json
  verify_sources.py reproduce --cache DIR ...
  verify_sources.py detect --out NEW_DIR [--raw T] [--archive-new] --report d.json
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import html_content_hash as hch  # noqa: E402
import source_archive as sa  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "docs/blueprint/validation"
EXTRACT_OF = {"klia_pub_cancer_criteria": "klia_pub_cancer_compare"}
PAIRED_HTML = {"klia_pub_cancer_compare": "klia_pub_cancer_criteria", "klia_pub_cancer_criteria": "klia_pub_cancer_compare"}


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(s):
    return re.sub(r"\s+", "", s)


def quotes(md):
    """(page or None, line) for every quoted line, skipping markers and omission lines."""
    out = []
    for block in re.findall(r"```text\n(.*?)```", md, re.S):
        page = None
        for line in block.splitlines():
            m = re.match(r"\s*\[PDF p\.(\d+)\]\s*$", line)
            if m:
                page = int(m.group(1))
            elif line.strip() and line.strip() != "..." and not line.startswith("### "):
                out.append((page, line))
    return out


def cells(line):
    """Cell texts of a serialized HTML table line `th|td[...]:text | ...`."""
    out = []
    line = re.sub(r"^\[caption\]\s*", "", line)  # serializer marker for <caption>, not source text
    for part in line.split(" | "):
        m = re.match(r"\s*(?:th|td)(?:\[[^\]]*\])?:(.*)$", part)
        text = (m.group(1) if m else part).strip()
        if text:
            out.append(text)
    return out


def visible_text(raw):
    text, _ = hch.decode(raw)
    text = re.sub(r"<!--.*?-->|<script\b.*?</script\s*>|<style\b.*?</style\s*>", " ", text, flags=re.S | re.I)
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", text)))


def tool_version(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", r.stdout + r.stderr)
        return m.group(1) if m else None
    except FileNotFoundError:
        return None


def pdf_page_texts(pdf, page, cache):
    key = (str(pdf), page)
    if key not in cache:
        outs = []
        for args in (["-layout"], []):
            r = subprocess.run(["pdftotext", *args, "-f", str(page), "-l", str(page), str(pdf), "-"], capture_output=True, text=True)
            outs.append(norm(r.stdout))
        import pdfplumber  # required: some quotes (HWP-converted PDFs) were taken from pdfplumber output
        with pdfplumber.open(pdf) as d:
            outs.append(norm(d.pages[page - 1].extract_text(x_tolerance=1.5, y_tolerance=3) or ""))
        cache[key] = outs
    return cache[key]


def ocr_page(pdf, page, workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    stem = workdir / f"p{page}"
    subprocess.run(["pdftoppm", "-r", "300", "-gray", "-f", str(page), "-l", str(page), "-png", str(pdf), str(stem)],
                   check=True, capture_output=True)
    png = sorted(workdir.glob(f"p{page}*.png"))[0]
    return subprocess.run(["tesseract", str(png), "-", "-l", "kor", "--psm", "3"], capture_output=True, text=True).stdout


def rows():
    return list(csv.DictReader((VAL / "samples.csv").open(encoding="utf-8")))


def materialize(args, sample_rows):
    """Return {sample_id: local path of the original}, pulling from the raw archive if given."""
    paths = {}
    if args.raw:
        raw = sa.store(args.raw, args.endpoint_url)
        work = Path(tempfile.mkdtemp(prefix="onjeon-reproduce-"))
        for r in sample_rows:
            key = sa.object_key(r["sha256"])
            if raw.exists(key):
                p = work / r["sha256"]
                p.write_bytes(raw.get(key))
                paths[r["sample_id"]] = p
    else:
        for r in sample_rows:
            p = Path(args.cache) / r["cache_path"]
            if p.exists():
                paths[r["sample_id"]] = p
    return paths


def reproduce_one(r, paths, args, derived):
    sid = r["sample_id"]
    res = {"sample_id": sid, "sha256_recorded": r["sha256"]}
    p = paths.get(sid)
    if p is None:
        res["status"] = "missing"
        return res
    digest = sa.sha256_bytes(p.read_bytes())
    res["sha256_archived_bytes"] = digest
    if digest != r["sha256"]:
        res["status"] = "hash_mismatch"
        return res
    md = (VAL / "extracts" / f"{EXTRACT_OF.get(sid, sid)}.md").read_text(encoding="utf-8")
    missing, checked = [], 0
    if r["format"] == "html":
        text = visible_text(p.read_bytes())
        sib = PAIRED_HTML.get(sid)
        if sib and sib in paths:  # one extract quotes both KLIA pages
            text += visible_text(paths[sib].read_bytes())
            res["note"] = f"cells checked against this page plus {sib}"
        for _, line in quotes(md):
            for c in cells(line):
                checked += 1
                if norm(c) not in text:
                    missing.append(c[:80])
    elif r["format"] == "scanned_pdf":
        if not args.ocr:
            res["status"] = "ocr_not_rerun"
            return res
        work = Path(tempfile.mkdtemp(prefix="onjeon-ocr-"))
        pages = {}
        for page, line in quotes(md):
            if page not in pages:
                pages[page] = ocr_page(p, page, work)
            checked += 1
            if norm(line) not in norm(pages[page]):
                missing.append(f"p{page}: {line.strip()[:80]}")
        res["_ocr_pages"] = pages
    else:
        texts = {}
        for page, line in quotes(md):
            checked += 1
            if page is None or not any(norm(line) in t for t in pdf_page_texts(p, page, texts)):
                missing.append(f"p{page}: {line.strip()[:80]}")
    res.update(quoted_units=checked, not_found=len(missing), examples=missing[:5])
    if derived is None:
        res["derived"] = None
    else:
        ocr_cache = res.pop("_ocr_pages", {}) if args.ocr else None
        res["derived"] = verify_derived(derived, r["sha256"], r.get("derived_manifest_sha256") or None,
                                        sid, Regenerator(p, ocr_cache, args.ocr))
    res.pop("_ocr_pages", None)
    res["status"] = decide(bool(missing), res["derived"])
    return res


DERIVED_OK = "byte_identical"
DERIVED_STATES = {"byte_identical", "differs", "tool_version_differs", "no_regenerator", "not_rerun"}


def decide(quote_missing, derived):
    """Final archive_reproduction status.

    `derived` is the result of verify_derived() (or None when no derived store was given).
    Full reproduction needs: the pinned manifest found and hash-equal to its pin, linked to this
    raw object, every listed output present with the listed hash, no unlisted outputs, and every
    listed output regenerated byte-identically. A broken record (missing file, tampered or
    missing manifest) is derived_record_invalid; a differing regeneration is derived_mismatch;
    anything not comparable or no pinned manifest is derived_unverified. None of these is success."""
    if quote_missing:
        return "quote_mismatch"
    if derived is None:
        return "derived_unverified"
    if derived.get("record_errors"):
        return "derived_record_invalid"
    if derived.get("manifest") is None:
        return "derived_unverified"
    states = [o["state"] for o in derived.get("outputs", [])]
    if any(s == "differs" for s in states):
        return "derived_mismatch"
    if not states or any(s != DERIVED_OK for s in states):
        return "derived_unverified"
    return "reproduced"


class Regenerator:
    """Regenerates archived derived outputs with tools in this repository. Returns bytes, or a
    state string when it cannot (no_regenerator / tool_version_differs / not_rerun)."""

    def __init__(self, pdf, ocr_pages, ocr_enabled):
        self.pdf, self.ocr_pages, self.ocr_enabled = pdf, ocr_pages or {}, ocr_enabled
        self.cache = {}

    def __call__(self, kind, tool, name):
        tool_name, _, version = tool.partition("@")
        if kind == "text" and tool_name in ("poppler-pdftotext-layout", "poppler-pdftotext-reading-order"):
            if version != tool_version(["pdftotext", "-v"]):
                return "tool_version_differs"
            args = ["-layout"] if tool_name.endswith("layout") else []
            if tool_name not in self.cache:
                self.cache[tool_name] = subprocess.run(["pdftotext", *args, str(self.pdf), "-"], capture_output=True).stdout
            return self.cache[tool_name]
        m = re.match(r"ocr__p-(\d+)\.txt$", name)
        if kind == "ocr" and tool_name == "tesseract" and m:
            if not version.startswith(tool_version(["tesseract", "--version"]) or "?"):
                return "tool_version_differs"
            if not self.ocr_enabled:
                return "not_rerun"
            page = int(m.group(1))
            if page not in self.ocr_pages:
                self.ocr_pages[page] = ocr_page(self.pdf, page, Path(tempfile.mkdtemp(prefix="onjeon-ocr-")))
            return self.ocr_pages[page].encode("utf-8")
        return "no_regenerator"


def manifest_key(raw_digest, manifest_sha256):
    return f"derived/{raw_digest}/manifests/{manifest_sha256}.json"


def verify_derived(derived, raw_digest, pin, sample_id, regen):
    """Check the derived record against the pinned manifest, then regenerate.

    The manifest to verify is fixed by its SHA-256 (samples.csv `derived_manifest_sha256`), never
    discovered by listing the store. Listing is used only to find outputs the manifest does not
    name. Regeneration is compared only after the record itself checks out."""
    result = {"manifest": pin, "record_errors": [], "outputs": []}
    if pin is None:
        return result  # decide(): derived_unverified (nothing pinned to verify against)
    key = manifest_key(raw_digest, pin)
    if not derived.exists(key):
        result["record_errors"].append(f"pinned manifest missing: {key}")
        return result
    body = derived.get(key)
    if sa.sha256_bytes(body) != pin:
        result["record_errors"].append(f"manifest bytes do not hash to the pin: {key}")
        return result
    try:
        manifest = json.loads(body)
    except ValueError:
        result["record_errors"].append("manifest is not valid JSON")
        return result
    if manifest.get("raw_sha256") != raw_digest:
        result["record_errors"].append(f"manifest links raw {manifest.get('raw_sha256')!r}, not {raw_digest}")
    if manifest.get("sample_id") not in (None, sample_id):
        result["record_errors"].append(f"manifest sample_id {manifest.get('sample_id')!r} is not {sample_id}")
    listed = manifest.get("outputs") or []
    if not listed:
        result["record_errors"].append("manifest lists no outputs")
    prefix = f"derived/{raw_digest}/"
    for o in listed:
        k, want = o.get("key", ""), o.get("sha256")
        if not k.startswith(prefix) or len(k.split("/")) != 5:
            result["record_errors"].append(f"listed output outside this raw object: {k}")
        elif not derived.exists(k):
            result["record_errors"].append(f"listed output missing: {k}")
        elif sa.sha256_bytes(derived.get(k)) != want:
            result["record_errors"].append(f"listed output hash differs from manifest: {k}")
    listed_keys = {o.get("key") for o in listed}
    for k in derived.list(prefix):
        parts = k.split("/")
        if len(parts) == 5 and parts[2] != "manifests" and k not in listed_keys:
            result["record_errors"].append(f"output not in the pinned manifest: {k}")
    if result["record_errors"]:
        return result
    for o in sorted(listed, key=lambda x: x["key"]):
        _, _, kind, tool, name = o["key"].split("/")
        got = regen(kind, tool, name)
        if isinstance(got, str):
            state = got
        else:
            state = DERIVED_OK if sa.sha256_bytes(got) == o["sha256"] else "differs"
        assert state in DERIVED_STATES, state
        result["outputs"].append({"key": o["key"], "state": state})
    return result


def cmd_reproduce(args):
    sample_rows = rows()
    paths = materialize(args, sample_rows)
    derived = sa.store(args.derived, args.endpoint_url) if args.derived else None
    results = [reproduce_one(r, paths, args, derived) for r in sample_rows]
    unverified = {"ocr_not_rerun", "derived_unverified"} if args.allow_unverified else set()
    return report("reproduce", args, results, ok={"reproduced"} | unverified)


def fetch(url, attempts=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (onjeon source change detection)"})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), r.headers.get_content_type()
        except urllib.error.HTTPError:
            raise  # an HTTP status is an answer, not a network error
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == attempts - 1:
                raise
            time.sleep(2 * 2**i)


def cmd_detect(args):
    raw = sa.store(args.raw, args.endpoint_url) if args.raw else None
    out = Path(args.out)
    results = []
    for r in rows():
        sid = r["sample_id"]
        res = {"sample_id": sid, "url": r["url"], "baseline_sha256": r["sha256"], "observed_at": now()}
        try:
            body, ctype = fetch(r["url"])
        except Exception as e:
            res.update(status="fetch_failed", detail=f"{type(e).__name__}: {e}"[:200])
            results.append(res)
            continue
        dest = out / r["cache_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        digest = sa.sha256_bytes(body)
        res["sha256_now"] = digest
        if digest == r["sha256"]:
            res["status"] = "unchanged_bytes"
        elif r["format"] == "html" and r.get("content_sha256") and r.get("content_hash_rule") == hch.RULE:
            host = re.sub(r"^https?://([^/]+).*$", r"\1", r["url"])
            now_content = hch.content_sha256(body, host)
            res["content_hash_rule"] = hch.RULE
            res["status"] = "bytes_changed_content_same" if now_content == r["content_sha256"] else "changed"
        else:
            res["status"] = "changed"
        if raw is not None and args.archive_new:
            _, state = sa.put_raw(raw, body, ctype or "application/octet-stream")
            okey, _ = sa.put_observation(raw, sid, r["url"], res["observed_at"], digest, len(body), ctype or "",
                                         {"detect_status": res["status"]})
            res.update(archived_object=state, observation=okey)
        results.append(res)
    # a source that could not be fetched is a failed collection, not a green run (exit 1); a changed
    # source is a successful observation of a new version candidate
    return report("detect", args, results, ok={"unchanged_bytes", "bytes_changed_content_same", "changed"})


def target_label(target, args):
    """file, or provider:bucket for an S3 API store (never the endpoint, which names the account)."""
    if not target:
        return None
    if target.startswith("s3://"):
        endpoint = getattr(args, "endpoint_url", None) or os.environ.get("ONJEON_S3_ENDPOINT")
        return f"{sa.provider_of(endpoint)}:{target[len('s3://'):]}"
    return target.split("://")[0]


def report(kind, args, results, ok):
    counts = {}
    for x in results:
        counts[x["status"]] = counts.get(x["status"], 0) + 1
    env = {"pdftotext": tool_version(["pdftotext", "-v"]), "tesseract": tool_version(["tesseract", "--version"])}
    try:
        import pdfplumber
        env["pdfplumber"] = pdfplumber.__version__
    except Exception:
        env["pdfplumber"] = None
    doc = {"check": kind, "ran_at": now(), "source": target_label(args.raw, args) or ("cache" if getattr(args, "cache", None) else "network"),
           "ocr_rerun": bool(getattr(args, "ocr", False)), "tools": env, "summary": counts, "results": results}
    if getattr(args, "derived", None):
        doc["derived_source"] = target_label(args.derived, args)
    if kind == "detect":
        doc["meaning"] = "change detection only: a changed source is a new version candidate; the recorded originals and past reproductions are untouched"
    if args.report:
        Path(args.report).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for x in results:
        print(f"  {x['status']:<27} {x['sample_id']}" + (f"  {x['quoted_units']} units" if "quoted_units" in x else ""))
    print(f"{kind}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f" (of {len(results)})")
    return 0 if all(x["status"] in ok for x in results) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint-url", help="S3 API endpoint (R2 or an emulator); default $ONJEON_S3_ENDPOINT, else AWS")
    ap.add_argument("--job", help="budget job (infra/r2/jobs/*.json); required for R2/AWS targets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("reproduce")
    src = s.add_mutually_exclusive_group(required=True)
    src.add_argument("--raw")
    src.add_argument("--cache")
    s.add_argument("--derived")
    s.add_argument("--ocr", action="store_true")
    s.add_argument("--allow-unverified", "--allow-ocr-skip", dest="allow_unverified", action="store_true",
                   help="exit 0 on ocr_not_rerun / derived_unverified (never on derived_mismatch)")
    s.add_argument("--report")
    s = sub.add_parser("detect")
    s.add_argument("--out", required=True)
    s.add_argument("--raw")
    s.add_argument("--archive-new", action="store_true")
    s.add_argument("--report")
    args = ap.parse_args()
    if not shutil.which("pdftotext"):
        print("pdftotext (poppler-utils) is required")
        return 2
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        # a missing extractor must stop the run, not turn into a false quote_mismatch
        print("pdfplumber is required (pip install pdfplumber==0.11.10)")
        return 2
    args.endpoint_url = getattr(args, "endpoint_url", None)
    return sa.with_budget(args.job, args.endpoint_url,
                          lambda: cmd_reproduce(args) if args.cmd == "reproduce" else cmd_detect(args))


if __name__ == "__main__":
    sys.exit(main())
