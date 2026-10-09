#!/usr/bin/env python3
"""Re-verify the V1 validation samples against their original bytes.

For every row of docs/blueprint/validation/samples.csv:
1. find the original under the cache root (<cache>/<cache_path>) or, with --download, fetch it
   from the recorded URL into the cache (TLS verification stays on; nothing is retried around
   access blocks)
2. compute the SHA-256 of the bytes and compare with samples.csv
3. re-extract and check every quoted line of the sample's extract:
   - text PDF: the line must appear on its cited [PDF p.N] page in a fresh pdftotext (-layout or
     reading order) or pdfplumber extraction
   - HTML: each quoted cell text must appear in the tag-stripped document
   - scanned PDF: re-OCR only with --ocr (tesseract kor, 300 dpi); otherwise reported as
     `ocr_not_reverified`, never as verified

Downloaded files are untrusted input: they are only hashed and parsed, never executed.

Usage:
  python3 tools/verify_sources.py --cache DIR [--download] [--ocr] [--report out.json]
  ONJEON_SAMPLE_CACHE=DIR python3 tools/verify_sources.py
  python3 tools/verify_sources.py --cache DIR --record-content-hash   # fill content_sha256 for HTML
Exit 0 only if every sample is verified (or ocr_not_reverified when --ocr is not given and
--allow-ocr-skip is set).
"""
import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "docs/blueprint/validation"
EXTRACT_OF = {"klia_pub_cancer_criteria": "klia_pub_cancer_compare"}
PAIRED_HTML = {
    "klia_pub_cancer_compare": "klia_pub_cancer_compare/info_popup.html",
    "klia_pub_cancer_criteria": "klia_pub_cancer_compare/list.html",
}


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


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dest, attempts=3):
    """Fetch with TLS verification on. Retries only network errors (reset, timeout), with backoff."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (onjeon source verification)"})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            dest.write_bytes(body)
            return
        except urllib.error.HTTPError:
            raise  # an HTTP status is an answer, not a network error: do not retry around it
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == attempts - 1:
                raise
            time.sleep(2 * 2**i)


def pdf_page_texts(pdf, page, cache):
    key = (str(pdf), page)
    if key not in cache:
        outs = []
        for args in (["-layout"], []):
            r = subprocess.run(["pdftotext", *args, "-f", str(page), "-l", str(page), str(pdf), "-"],
                               capture_output=True, text=True)
            outs.append(norm(r.stdout))
        try:
            import pdfplumber  # optional second extractor
            with pdfplumber.open(pdf) as d:
                outs.append(norm(d.pages[page - 1].extract_text(x_tolerance=1.5, y_tolerance=3) or ""))
        except Exception:
            pass
        cache[key] = outs
    return cache[key]


def ocr_page(pdf, page, workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    stem = workdir / f"p{page}"
    subprocess.run(["pdftoppm", "-r", "300", "-gray", "-f", str(page), "-l", str(page), "-png", str(pdf), str(stem)],
                   check=True, capture_output=True)
    png = sorted(workdir.glob(f"p{page}*.png"))[0]
    r = subprocess.run(["tesseract", str(png), "-", "-l", "kor", "--psm", "3"], capture_output=True, text=True)
    return norm(r.stdout)


def html_text(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<title.*?</title>", " ", text, flags=re.S | re.I)
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", text)))


def content_sha256(path):
    """Hash of the visible text without scripts, styles and title.

    Disclosure pages embed a session id and a server node marker that change on every request,
    so their byte hash is never stable. Change detection uses this content hash; the raw bytes
    are still archived and their own hash kept.
    """
    return hashlib.sha256(html_text(path).encode("utf-8")).hexdigest()


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


def verify(row, cache_root, args):
    sid = row["sample_id"]
    path = cache_root / row["cache_path"]
    result = {"sample_id": sid, "cache_path": row["cache_path"]}
    if row["cache_path"] in args.failed_downloads:
        result.update(status="download_failed", detail=args.failed_downloads[row["cache_path"]])
        return result
    if not path.exists():
        result["status"] = "missing"
        return result
    digest = sha256(path)
    result["sha256"] = digest
    content_ok = False
    if digest != row["sha256"]:
        if row["format"] == "html" and row.get("content_sha256") and content_sha256(path) == row["content_sha256"]:
            content_ok = True  # only volatile parts (session id, node marker) changed
        else:
            result["status"] = "hash_mismatch"
            result["detail"] = "the bytes differ from the recorded sample (source changed or wrong file)"
            return result
    md = (VAL / "extracts" / f"{EXTRACT_OF.get(sid, sid)}.md").read_text(encoding="utf-8")
    missing, checked = [], 0
    if row["format"] == "html":
        text = html_text(path)
        sibling = PAIRED_HTML.get(sid)
        if sibling:
            # one extract quotes both KLIA pages: a cell must be in this page or its recorded sibling
            sib = cache_root / sibling
            text += html_text(sib) if sib.exists() else ""
            result["note"] = f"cells checked against this page plus {sibling}"
        for _, line in quotes(md):
            for c in cells(line):
                checked += 1
                if norm(c) not in text:
                    missing.append(c[:80])
    elif row["format"] == "scanned_pdf":
        if not args.ocr:
            result["status"] = "ocr_not_reverified"
            return result
        work = Path(args.workdir) / sid
        pages = {}
        for page, line in quotes(md):
            if page not in pages:
                pages[page] = ocr_page(path, page, work)
            checked += 1
            if norm(line) not in pages[page]:
                missing.append(f"p{page}: {line.strip()[:80]}")
    else:
        texts = {}
        for page, line in quotes(md):
            checked += 1
            if page is None or not any(norm(line) in t for t in pdf_page_texts(path, page, texts)):
                missing.append(f"p{page}: {line.strip()[:80]}")
    result.update(quoted_units=checked, not_found=len(missing), examples=missing[:5])
    if missing:
        result["status"] = "quote_mismatch"
    else:
        result["status"] = "content_verified" if content_ok else "verified"
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("ONJEON_SAMPLE_CACHE"))
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--allow-ocr-skip", action="store_true")
    ap.add_argument("--workdir", default="/tmp/onjeon-verify-ocr")
    ap.add_argument("--report")
    ap.add_argument("--record-content-hash", action="store_true")
    args = ap.parse_args()
    if not args.cache:
        print("need --cache DIR or ONJEON_SAMPLE_CACHE (originals are not stored in the repository)")
        return 2
    if not shutil.which("pdftotext"):
        print("pdftotext (poppler-utils) is required")
        return 2
    cache_root = Path(args.cache)
    rows = list(csv.DictReader((VAL / "samples.csv").open(encoding="utf-8")))
    if args.record_content_hash:
        for row in rows:
            path = cache_root / row["cache_path"]
            if row["format"] == "html" and path.exists() and sha256(path) == row["sha256"]:
                row["content_sha256"] = content_sha256(path)
        fields = list(rows[0].keys()) + (["content_sha256"] if "content_sha256" not in rows[0] else [])
        with (VAL / "samples.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows({k: r.get(k, "") for k in fields} for r in rows)
        print("recorded content_sha256 for HTML samples whose bytes match the recorded hash")
        return 0
    args.failed_downloads = {}
    if args.download:  # fetch everything first: one extract can quote two files
        for row in rows:
            path = cache_root / row["cache_path"]
            if not path.exists():
                try:
                    download(row["url"], path)
                except Exception as e:
                    args.failed_downloads[row["cache_path"]] = f"{type(e).__name__}: {e}"
    results = [verify(r, cache_root, args) for r in rows]
    for r in results:
        extra = f" {r.get('quoted_units', '')} units" if "quoted_units" in r else ""
        print(f"  {r['status']:<20} {r['sample_id']}{extra}" + (f"  e.g. {r['examples'][0]}" if r.get("examples") else ""))
    if args.report:
        Path(args.report).write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = {"verified", "content_verified"} | ({"ocr_not_reverified"} if args.allow_ocr_skip else set())
    bad = [r for r in results if r["status"] not in ok]
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f" (of {len(results)})")
    print("content_verified = HTML whose bytes differ only in volatile parts (session id, node marker)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
