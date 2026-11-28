#!/usr/bin/env python3
"""Two separate checks of the V1 validation samples (ADR-0015). Never mix their results.

reproduce  보관본 재현 검사 — with the originals preserved at the time:
           byte SHA-256 against samples.csv, every quoted line on its cited page in a fresh
           extraction (HTML: every quoted cell in the visible text), the scanned sample re-OCRed
           with --ocr, and archived extraction outputs regenerated with the same tool version.
           Status codes: vocabulary axis `archive_reproduction`.

detect     현재 출처 변경 감지 — fetch permitted recorded URLs and compare with the last observation:
           a different document is a new version candidate to archive and review. It never
           replaces the past original and never turns a past reproduction into a failure.
           Status codes: vocabulary axis `source_change`. For HTML the content hash
           (tools/html_content_hash.py, rule html-visible-text-v3) is an auxiliary signal; equal
           content with different bytes is `bytes_changed_content_same`, never byte identity.
           Survey-recorded robots disallows are held without a request, reported as
           `fetch_failed` with detail `robots_disallow`, and keep the run nonzero.
           Other sources must pass a live robots.txt check before a document request.

Originals come from the raw archive (tools/source_archive.py layout; file:// or s3://) or from a
cache directory laid out by samples.csv `cache_path`. Detect uses the shared crawler transport:
HTTPS-only, exact hosts in data/registry/source_fetch_hosts.json, no redirects, and an honest UA.
The document response URL and HTTP status are recorded separately from change status.
MIME/signature and known HTML block-page checks run before any write. Redirect response bodies
are closed unread. Final bodies over MAX_FETCH_BYTES are refused
(streaming stops at cap + 1 byte). TLS verification stays on; only network errors are retried.
Each fetch has one wall-clock deadline across crawl delays, robots.txt, body reads and retries.
Rejections are `fetch_failed`. Crawl delays and holds apply across samples on the same host in the current run.
Reproduction bounds extractor subprocesses and removes its temporary files.

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
import urllib.parse
from contextlib import ExitStack, contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import html_content_hash as hch  # noqa: E402
import source_archive as sa  # noqa: E402
import source_metadata as sm  # noqa: E402
from crawler.config import ConfigError, CrawlerConfig, HARD_OBJECT_CAP_BYTES  # noqa: E402
from crawler.robots import DAY_S, RobotsCache  # noqa: E402
from crawler.transport import (  # noqa: E402
    BodyFramingError, BodyTooLargeError, NetworkDisabledError, RefusedRequestError, TransportError, UrllibTransport,
    retry_after_until,
)
from crawler.useragent import UserAgentError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "docs/blueprint/validation"
EXTRACT_OF = {"klia_pub_cancer_criteria": "klia_pub_cancer_compare"}
PAIRED_HTML = {"klia_pub_cancer_compare": "klia_pub_cancer_criteria", "klia_pub_cancer_criteria": "klia_pub_cancer_compare"}
TOOL_VERSION_TIMEOUT_SECONDS = 10
EXTRACT_TIMEOUT_SECONDS = 120


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
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TOOL_VERSION_TIMEOUT_SECONDS)
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", r.stdout + r.stderr)
        return m.group(1) if m else None
    except FileNotFoundError:
        return None


def pdf_page_texts(pdf, page, cache):
    key = (str(pdf), page)
    if key not in cache:
        outs = []
        for args in (["-layout"], []):
            r = subprocess.run(["pdftotext", *args, "-f", str(page), "-l", str(page), str(pdf), "-"],
                               capture_output=True, text=True, timeout=EXTRACT_TIMEOUT_SECONDS)
            outs.append(norm(r.stdout))
        import pdfplumber  # required: some quotes (HWP-converted PDFs) were taken from pdfplumber output
        with pdfplumber.open(pdf) as d:
            outs.append(norm(d.pages[page - 1].extract_text(x_tolerance=1.5, y_tolerance=3) or ""))
        cache[key] = outs
    return cache[key]


def ocr_page(pdf, page):
    with tempfile.TemporaryDirectory(prefix="onjeon-ocr-") as temp:
        workdir = Path(temp)
        stem = workdir / f"p{page}"
        subprocess.run(["pdftoppm", "-r", "300", "-gray", "-f", str(page), "-l", str(page), "-png", str(pdf), str(stem)],
                       check=True, capture_output=True, timeout=EXTRACT_TIMEOUT_SECONDS)
        png = sorted(workdir.glob(f"p{page}*.png"))[0]
        return subprocess.run(["tesseract", str(png), "-", "-l", "kor", "--psm", "3"],
                              capture_output=True, text=True, timeout=EXTRACT_TIMEOUT_SECONDS).stdout


def rows():
    with (VAL / "samples.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@contextmanager
def materialize(args, sample_rows):
    """Keep local originals available for the duration of reproduction."""
    paths = {}
    with ExitStack() as stack:
        if args.raw:
            raw = sa.store(args.raw, args.endpoint_url)
            work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="onjeon-reproduce-")))
            for r in sample_rows:
                key = sa.object_key(r["sha256"])
                if raw.exists(key):
                    p = work / r["sha256"]
                    p.write_bytes(raw.get(key))
                    paths[r["sample_id"]] = p
        else:
            for r in sample_rows:
                try:
                    p = sa.confined_path(args.cache, r["cache_path"])
                except sa.UnsafeCachePath:
                    continue  # a cache_path outside the cache is treated as absent
                if p.exists():
                    paths[r["sample_id"]] = p
        yield paths


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
        pages = {}
        for page, line in quotes(md):
            if page not in pages:
                pages[page] = ocr_page(p, page)
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
                self.cache[tool_name] = subprocess.run(["pdftotext", *args, str(self.pdf), "-"],
                                                       capture_output=True, timeout=EXTRACT_TIMEOUT_SECONDS).stdout
            return self.cache[tool_name]
        m = re.match(r"ocr__p-(\d+)\.txt$", name)
        if kind == "ocr" and tool_name == "tesseract" and m:
            if not version.startswith(tool_version(["tesseract", "--version"]) or "?"):
                return "tool_version_differs"
            if not self.ocr_enabled:
                return "not_rerun"
            page = int(m.group(1))
            if page not in self.ocr_pages:
                self.ocr_pages[page] = ocr_page(self.pdf, page)
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
    results = []
    with materialize(args, sample_rows) as paths:
        derived = sa.store(args.derived, args.endpoint_url) if args.derived else None
        for r in sample_rows:
            try:
                results.append(reproduce_one(r, paths, args, derived))
            except subprocess.TimeoutExpired as e:
                print(f"tool_timeout: {r['sample_id']}: {e.cmd[0]} exceeded {e.timeout:g}s", file=sys.stderr)
                return 1
    unverified = {"ocr_not_rerun", "derived_unverified"} if args.allow_unverified else set()
    return report("reproduce", args, results, ok={"reproduced"} | unverified)


MAX_FETCH_BYTES = HARD_OBJECT_CAP_BYTES
FETCH_DEADLINE_SECONDS = 120
FETCH_SOCKET_TIMEOUT_SECONDS = 30
CONTACT_ENV = "ONJEON_CRAWLER_CONTACT"
SOURCE_HOST_REGISTRY = ROOT / "data/registry/source_fetch_hosts.json"
# Conservative hold from the 2026-10-10 survey, not a live robots.txt observation.
# Removing a hold requires reviewing the recorded policy; detect never overrides it.
ROBOTS_DISALLOWED_HOSTS = frozenset({"pub.insure.or.kr"})
ROBOTS_POLICY_SOURCE = "docs/research/2026-10-10_source_survey/A_klia.md#6-접근-제한과-실패"


class FetchRejected(Exception):
    """A source could not be admitted. Carry document response metadata when available."""

    def __init__(self, detail, *, final_url=None, http_status=None, deferred_until=None):
        super().__init__(detail)
        self.final_url = final_url
        self.http_status = http_status
        self.deferred_until = deferred_until


class RobotsDisallowed(FetchRejected):
    """A source is held by a survey-recorded robots.txt disallow; no request is sent."""


def check_recorded_robots_policy(url):
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return  # URL admission reports malformed URLs separately.
    if host in ROBOTS_DISALLOWED_HOSTS:
        raise RobotsDisallowed(f"robots_disallow: {host}: User-agent: *; Disallow: /; {ROBOTS_POLICY_SOURCE}")


def registered_source_hosts():
    """Read the explicit host registry; missing/invalid policy never permits a request."""
    try:
        hosts = json.loads(SOURCE_HOST_REGISTRY.read_text(encoding="utf-8"))["hosts"]
        label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        if (not isinstance(hosts, list) or not hosts
                or any(not isinstance(host, str) or len(host) > 253
                       or re.fullmatch(rf"{label}(?:\.{label})*", host) is None for host in hosts)
                or len(hosts) != len(set(hosts))):
            raise ValueError("invalid hosts")
        return frozenset(hosts)
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise FetchRejected("url_disallowed: source host registry unavailable or invalid") from e


def source_origin(url):
    """Only registered HTTPS hosts without credentials; default ports compare equally."""
    try:
        origin = sm.https_origin(url)
    except ValueError as e:
        raise FetchRejected("url_disallowed: invalid source URL") from e
    if origin[1] not in registered_source_hosts():
        raise FetchRejected("url_disallowed: host is not in the source host registry")
    return origin


SOURCE_MIMES = {
    "pdf": {"application/pdf", "application/octet-stream", "binary/octet-stream"},
    "html": {"text/html", "application/xhtml+xml"},
}
# Specific denial/challenge phrases, not bare "login" links in ordinary site navigation.
BLOCK_PAGE_MARKERS = (
    "access denied", "request rejected", "verify you are human", "unusual traffic",
    "you have been blocked", "your ip has been blocked", "captcha", "bot detected",
    "automated requests", "the requested url was rejected", "enable javascript and cookies to continue",
    "login required", "please log in", "sign in to continue",
    "로그인이 필요", "접근이 차단", "접근 차단", "비정상적인 접근", "자동화된 접근",
    "서비스 점검", "service unavailable", "internal server error",
)


def check_source_body(body, kind):
    if not body:
        raise FetchRejected("empty_body: source returned no document")
    if kind == "pdf":
        if not body.startswith(b"%PDF-"):
            raise FetchRejected("wrong_signature: expected PDF")
        return
    if not body.lstrip().startswith(b"<"):
        raise FetchRejected("wrong_signature: expected HTML markup")
    text, _ = hch.decode(body[:64 * 1024])
    text = text.lower()
    # Check challenge markup before removing scripts; visible text catches split tags/entities.
    challenge = any(marker in text for marker in (
        "cf-chl-", "/cdn-cgi/challenge-platform/", "g-recaptcha", "hcaptcha", "_incapsula_resource",
    )) or re.search(r"<title\b[^>]*>\s*(?:just a moment[.!…\s]*|attention required!\s*\|\s*cloudflare)\s*</title", text)
    password = re.search(r"<input\b[^>]*\btype\s*=\s*['\"]?password\b", text)
    text = re.sub(r"<!--.*?-->|<script\b.*?</script\s*>|<style\b.*?</style\s*>", " ", text, flags=re.S)
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
    if challenge or password or any(marker in text for marker in BLOCK_PAGE_MARKERS):
        raise FetchRejected("block_page: challenge, login or denial HTML")


def _validate_fetch_request(url, attempts, max_bytes, expected_format):
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_FETCH_BYTES:
        raise ValueError("max_bytes must be between 1 and MAX_FETCH_BYTES")
    if type(attempts) is not int or attempts < 1:
        raise ValueError("attempts must be positive")
    check_recorded_robots_policy(url)
    source_origin(url)
    kind = "pdf" if expected_format in {"pdf", "text_pdf", "scanned_pdf"} else expected_format
    if kind not in SOURCE_MIMES:
        raise FetchRejected("unsupported_format: expected PDF or HTML")
    return kind


def fetch(url, attempts=3, max_bytes=MAX_FETCH_BYTES, *, expected_format="pdf",
          robots_deferrals=None, host_pacing=None):
    """Return (bytes, MIME, final URL, HTTP status), sharing holds and crawl delays by host."""
    kind = _validate_fetch_request(url, attempts, max_bytes, expected_format)
    if robots_deferrals is None:
        robots_deferrals = {}
    host = urllib.parse.urlsplit(url).hostname
    deferred = robots_deferrals.get(host)
    if deferred is not None:
        until, reason = deferred
        if time.time() < until:
            raise FetchRejected(reason, deferred_until=until)
    command = [sys.executable, "-I", str(Path(__file__).resolve()), "--fetch-worker"]
    pacing = host_pacing.get(host, (0, 0)) if host_pacing is not None else (0, 0)
    request = json.dumps([url, attempts, max_bytes, kind, pacing]).encode()
    # A socket timeout only caps individual operations. A separate process can be
    # killed and reaped even during DNS resolution or a slowly streamed response.
    # Its temporary output contains response metadata as soon as headers arrive,
    # then the terminal result and any admitted document bytes.
    with tempfile.TemporaryFile() as output:
        deadline = None
        try:
            subprocess.run(command, input=request, stdout=output, check=True, timeout=FETCH_DEADLINE_SECONDS)
        except subprocess.TimeoutExpired as e:
            deadline = e
        stopped_at = time.monotonic()
        output.seek(0)
        observed = {}
        result = None
        for line in output:
            try:
                event = json.loads(line)
            except ValueError:
                if deadline is None:
                    raise
                break  # The worker may have been killed mid-write.
            if "crawl_delay" in event:
                if host_pacing is not None:
                    delay = event["crawl_delay"]
                    # A killed worker may have been in flight. Measure from its exit.
                    host_pacing[host] = (delay, stopped_at + delay)
                continue
            if "response" not in event:
                result = event
                break
            observed = event["response"]
            if "deferral" in event:
                robots_deferrals[host] = tuple(event["deferral"])
        if deadline is not None:
            raise FetchRejected(f"deadline_exceeded: source fetch exceeded {FETCH_DEADLINE_SECONDS:g}s",
                                **observed) from deadline
        if result is None:
            raise FetchRejected("worker_failed: missing fetch result", **observed)
        if "error" in result:
            deferred_until = result.get("deferred_until")
            if deferred_until is not None:
                robots_deferrals[host] = (deferred_until, result["detail"])
            raise FetchRejected(result["detail"], final_url=result.get("final_url", observed.get("final_url")),
                                http_status=result.get("http_status", observed.get("http_status")),
                                deferred_until=deferred_until)
        return output.read(), result["content_type"], result["final_url"], result["http_status"]


def _fetch_worker(input_stream, output_stream):
    url, attempts, max_bytes, kind, pacing = json.load(input_stream)

    def record_progress(**metadata):
        output_stream.write(json.dumps(metadata).encode() + b"\n")
        output_stream.flush()

    body = b""
    try:
        body, ctype, final_url, http_status = _fetch_https(url, attempts, max_bytes, expected_format=kind,
                                                          pacing=pacing, record_progress=record_progress)
        result = {"content_type": ctype, "final_url": final_url, "http_status": http_status}
    except FetchRejected as e:
        result = {"error": "FetchRejected", "detail": str(e),
                  "final_url": e.final_url, "http_status": e.http_status, "deferred_until": e.deferred_until}
    except Exception as e:
        result = {"error": "FetchRejected", "detail": f"{type(e).__name__}: {e}"}
    output_stream.write(json.dumps(result).encode() + b"\n")
    output_stream.write(body)


def _fetch_https(url, attempts=3, max_bytes=MAX_FETCH_BYTES, *, expected_format="pdf",
                 pacing=(0, 0), record_progress=None):
    kind = _validate_fetch_request(url, attempts, max_bytes, expected_format)
    url, _ = urllib.parse.urldefrag(url)  # fragments are client-side and are never sent on the wire
    try:
        # The explicit detect command opts into networking in this config. The transport
        # also requires its environment opt-in for every non-loopback request.
        config = CrawlerConfig(contact=os.environ.get(CONTACT_ENV, ""), network_enabled=True)
        transport = UrllibTransport(config)
        transport.check_destination(url)
    except (NetworkDisabledError, RefusedRequestError) as e:
        raise FetchRejected(str(e)) from e
    except (ConfigError, UserAgentError) as e:
        raise FetchRejected(f"crawler_contact: set {CONTACT_ENV} to a valid public email or URL") from e

    crawl_delay, ready_at = pacing
    wait = ready_at - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    if crawl_delay and record_progress is not None:
        record_progress(crawl_delay=crawl_delay)
    robots = RobotsCache(transport, transport.user_agent, follow_redirects=False).check(url)
    if (robots.crawl_delay or 0) > crawl_delay:
        crawl_delay = robots.crawl_delay
        if record_progress is not None:
            record_progress(crawl_delay=crawl_delay)
    if not robots.allowed:
        raise FetchRejected(robots.reason, deferred_until=robots.deferred_until)
    if crawl_delay:
        time.sleep(crawl_delay)

    final_url = http_status = None
    for i in range(attempts):
        try:
            with transport.request(url, None, FETCH_SOCKET_TIMEOUT_SECONDS, max_bytes) as response:
                final_url, http_status = url, response.status
                retry_after = response.headers.get("retry-after")
                deferral = None
                if http_status == 429 or (http_status == 503 and retry_after is not None):
                    received_at = time.time()
                    until = retry_after_until(retry_after, received_at)
                    if until is None or until <= received_at:
                        until = (int(received_at // DAY_S) + 1) * DAY_S
                    deferral = (until, f"rate_limited: {http_status}")
                if record_progress is not None:
                    metadata = {"response": {"final_url": final_url, "http_status": http_status}}
                    if deferral is not None:
                        metadata["deferral"] = deferral
                    record_progress(**metadata)
                if deferral is not None:
                    until, detail = deferral
                    raise FetchRejected(detail, deferred_until=until)
                if 300 <= http_status < 400:
                    raise FetchRejected(f"redirect_disallowed: {http_status}")
                if http_status != 200:
                    raise FetchRejected(f"unexpected_status: {http_status}")
                ctype = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if ctype not in SOURCE_MIMES[kind]:
                    raise FetchRejected(f"content_type_mismatch: expected {kind}, received {ctype or 'missing'}")
                body = b"".join(response.body_iter)
                check_source_body(body, kind)
                return body, ctype, final_url, http_status
        except BodyFramingError as e:
            raise FetchRejected(f"length_mismatch: {e}", final_url=final_url, http_status=http_status) from e
        except BodyTooLargeError as e:
            raise FetchRejected(f"too_large: {e}", final_url=final_url, http_status=http_status) from e
        except FetchRejected as e:
            e.final_url, e.http_status = final_url, http_status
            raise
        except (NetworkDisabledError, RefusedRequestError) as e:
            raise FetchRejected(str(e), final_url=final_url, http_status=http_status) from e
        except TransportError as e:
            if i == attempts - 1:
                raise FetchRejected(f"transport_error: {e}", final_url=final_url, http_status=http_status) from e
            time.sleep(max(2 * 2**i, crawl_delay))


def cmd_detect(args):
    raw = sa.store(args.raw, args.endpoint_url) if args.raw else None
    out = Path(args.out)
    results = []
    host_deferrals = {}  # Host-wide decisions survive each sample's deadline-bounded worker.
    host_pacing = {}
    for r in rows():
        sid = r["sample_id"]
        res = {"sample_id": sid, "url": r["url"], "requested_url": r["url"], "final_url": None, "http_status": None,
               "baseline_sha256": r["sha256"], "observed_at": now()}
        try:
            check_recorded_robots_policy(r["url"])
        except RobotsDisallowed as e:
            res.update(status="fetch_failed", detail=str(e))
            results.append(res)
            continue
        try:
            dest = sa.confined_path(out, r["cache_path"])
        except sa.UnsafeCachePath as e:
            res.update(status="unsafe_cache_path", detail=str(e)[:200])  # not fetched, not written; exit 1
            results.append(res)
            continue
        try:
            body, ctype, final_url, http_status = fetch(r["url"], expected_format=r["format"],
                                                      robots_deferrals=host_deferrals, host_pacing=host_pacing)
        except FetchRejected as e:
            res.update(status="fetch_failed", detail=str(e)[:200], http_status=e.http_status, final_url=e.final_url)
            if e.final_url is not None:
                res["url"] = e.final_url
            results.append(res)
            continue
        except Exception as e:
            res.update(status="fetch_failed", detail=f"{type(e).__name__}: {e}"[:200])
            results.append(res)
            continue
        res.update(url=final_url, final_url=final_url, http_status=http_status, content_type=ctype)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        digest = sa.sha256_bytes(body)
        res["sha256_now"] = digest
        if digest == r["sha256"]:
            res["status"] = "unchanged_bytes"
        elif r["format"] == "html" and r.get("content_sha256") and r.get("content_hash_rule") == hch.RULE:
            host = urllib.parse.urlsplit(final_url).hostname
            now_content = hch.content_sha256(body, host)
            res["content_hash_rule"] = hch.RULE
            res["status"] = "bytes_changed_content_same" if now_content == r["content_sha256"] else "changed"
        else:
            res["status"] = "changed"
        if raw is not None and args.archive_new:
            _, state = sa.put_raw(raw, body, ctype or "application/octet-stream")
            okey, _ = sa.put_observation(raw, sid, final_url, res["observed_at"], digest, len(body), ctype,
                                         {"detect_status": res["status"], "requested_url": r["url"],
                                          "final_url": final_url, "http_status": http_status})
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
    env = {}
    for name, flag in (("pdftotext", "-v"), ("tesseract", "--version")):
        try:
            env[name] = tool_version([name, flag])
        except subprocess.TimeoutExpired:
            env[name] = None  # version metadata is optional once the checks have finished
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
    ap.add_argument("--endpoint-url", help="S3 API endpoint (HTTPS R2 or localhost/127.0.0.1 emulator); "
                    "required for s3:// targets unless ONJEON_S3_ENDPOINT is set")
    ap.add_argument("--job", help="budget job (infra/r2/jobs/*.json); required for R2 targets")
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
    if args.cmd == "reproduce":
        try:
            import pdfplumber  # noqa: F401
        except ImportError:
            # a missing extractor must stop reproduction, not turn into a false quote_mismatch
            print("pdfplumber is required (pip install pdfplumber==0.11.10)")
            return 2
    args.endpoint_url = getattr(args, "endpoint_url", None)
    return sa.with_budget(args.job, args.endpoint_url,
                          lambda: cmd_reproduce(args) if args.cmd == "reproduce" else cmd_detect(args))


if __name__ == "__main__":
    if sys.argv[1:] == ["--fetch-worker"]:
        _fetch_worker(sys.stdin.buffer, sys.stdout.buffer)
    else:
        sys.exit(main())
