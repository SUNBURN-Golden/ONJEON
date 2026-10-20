import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

EDITION = "docproc-text@1.0"
ROLES = {"보통약관", "특약 약관", "별표", "요약서", "공시 목록", "안내 쪽"}
NS = {"h": "http://www.w3.org/1999/xhtml"}


def run(args):
    result = subprocess.run(["pdftotext", *args], capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("PDF extraction failed")
    return result.stdout


def tool_version():
    result = subprocess.run(["pdftotext", "-v"], capture_output=True, timeout=10)
    match = re.search(rb"pdftotext version (\d+\.\d+\.\d+)", result.stderr + result.stdout)
    if not match:
        raise ValueError("Poppler version unavailable")
    return match[1].decode()


def fingerprint(page_texts, version):
    if not version.startswith("24.02."):
        raise ValueError("fp-0.1 requires Poppler 24.02")
    text = unicodedata.normalize("NFC", "".join(page_texts))
    return {"rule": "fp-0.1", "sha256": hashlib.sha256(re.sub(r"\s+", "", text).encode()).hexdigest()}


def page_lines(pdf, page):
    xml = run(["-f", str(page), "-l", str(page), "-bbox-layout", str(pdf), "-"])
    root = ET.fromstring(xml)
    pages = root.findall(".//h:page", NS)
    if len(pages) != 1:
        raise ValueError("Physical page missing")
    out = []
    for line in root.findall(".//h:line", NS):
        words = line.findall("h:word", NS)
        if not words:
            continue
        out.append({"quote": " ".join(w.text or "" for w in words),
                    "bbox": [float(line.attrib[k]) for k in ("xMin", "yMin", "xMax", "yMax")],
                    "words": [{"text": w.text or "", "bbox": [float(w.attrib[k]) for k in ("xMin", "yMin", "xMax", "yMax")]} for w in words]})
    return out


def extract(pdf, specs, edition=EDITION, origin="pipeline"):
    pdf = Path(pdf).resolve(strict=True)
    if pdf.stat().st_size > 256 * 1024 * 1024 or not pdf.read_bytes().startswith(b"%PDF-"):
        raise ValueError("Invalid PDF input")
    if origin not in {"pipeline", "fixture"} or not re.fullmatch(r"docproc-text@[0-9]+\.[0-9]+", edition):
        raise ValueError("Invalid extraction metadata")
    version = tool_version()
    if not version.startswith("24.02."):
        raise ValueError("fp-0.1 requires Poppler 24.02")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    segments, clauses, covered = [], [], set()
    if not isinstance(specs, list) or not specs:
        raise ValueError("Explicit segment specifications required")
    for spec in specs:
        start, end = spec["page_from"], spec["page_to"]
        role, rule = spec["doc_role"], spec["seg_rule_ver"]
        boundary = spec.get("boundary", "unconfirmed")
        if (type(start) is not int or type(end) is not int or start < 1 or end < start
                or end > 10000 or role not in ROLES or boundary not in {"confirmed", "unconfirmed"}
                or not re.fullmatch(r"[a-z][a-z0-9.-]*", rule)):
            raise ValueError("Invalid segment specification")
        if covered.intersection(range(start, end + 1)):
            raise ValueError("Overlapping segment specifications")
        covered.update(range(start, end + 1))
        sid = f"seg:{digest[:12]}:p{start}-{end}:{role}:{rule}"
        texts = []
        for page in range(start, end + 1):
            lines = page_lines(pdf, page)
            if not lines:
                raise ValueError("Textless page requires a separate OCR strategy")
            texts.append(run(["-layout", "-f", str(page), "-l", str(page), str(pdf), "-"]).decode("utf-8"))
            for index, line in enumerate(lines, 1):
                match = re.match(r"^(제\s*(\d+)\s*조|Article\s+(\d+)\b)", line["quote"])
                slug = f"article-{match[2] or match[3]}-line-{index}" if match else f"line-{index}"
                clauses.append({"id": f"clause:{sid}/{slug}#p{page}:{edition}",
                                "segment_id": sid, "raw_asset_id": f"raw:sha256:{digest}",
                                "clause_path": match[1] if match else slug,
                                "clause_path_basis": "printed" if match else "inferred",
                                "page": page, "printed_page": None,
                                "coordinate_system": "pdf-points-top-left-xmin-ymin-xmax-ymax",
                                **line, "parent_headings": [], "table_cell": None,
                                "footnotes": [], "definition_refs": [],
                                "extraction_edition": edition,
                                "extractor": {"tool": "poppler-pdftotext-bbox-layout", "version": version},
                                "review_status": "hold", "hold_reason": "extraction_uncertain", "origin": origin})
        segments.append({"id": sid, "raw_asset_id": f"raw:sha256:{digest}",
                         "page_from": start, "page_to": end, "doc_role": role,
                         "seg_rule_ver": rule, "boundary": boundary,
                         "fingerprint": fingerprint(texts, version), "origin": origin})
    return {"schema_version": "docproc-1.0", "raw_sha256": digest,
            "extraction_edition": edition, "segments": segments, "clauses": clauses}


def verify(pdf, output):
    specs = [{k: s[k] for k in ("page_from", "page_to", "doc_role", "seg_rule_ver", "boundary")} for s in output["segments"]]
    expected = extract(pdf, specs, output["extraction_edition"], output["segments"][0]["origin"])
    if expected != output:
        raise ValueError("Source coordinates, quote or extraction metadata mismatch")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--segments", type=Path)
    group.add_argument("--verify", type=Path)
    parser.add_argument("--origin", choices=("pipeline", "fixture"), default="pipeline")
    args = parser.parse_args()
    try:
        if args.verify:
            verify(args.pdf, json.loads(args.verify.read_text()))
        else:
            print(json.dumps(extract(args.pdf, json.loads(args.segments.read_text()), origin=args.origin), ensure_ascii=False, sort_keys=True))
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired, ET.ParseError):
        parser.exit(1, "docproc: input or extraction validation failed\n")


if __name__ == "__main__":
    main()
