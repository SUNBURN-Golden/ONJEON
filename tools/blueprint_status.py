#!/usr/bin/env python3
"""Check §11 against every ADR/DEC; --write stamps and refreshes its decision index.

Status rows still require human review. Only the §11 heading and the generated
index are written; a matching index is not milestone or release evidence.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- blueprint-decisions:start -->"
END = "<!-- blueprint-decisions:end -->"
HEADING = re.compile(r"^## 11\. 현재 위치 \((\d{4}-\d{2}-\d{2})\)$", re.MULTILINE)


def decision_records(root):
    """Hash paths as well as bytes, so removals and renames also invalidate §11."""
    directory = root / "docs/decisions"
    records = sorted([*directory.glob("ADR-*.md"), *directory.glob("DEC-*.md")])
    if not any(p.name.startswith("ADR-") for p in records):
        raise ValueError("no ADR records found")
    if not any(p.name.startswith("DEC-") for p in records):
        raise ValueError("no DEC records found")
    return [(p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in records]


def render_index(records, stamp):
    digest = hashlib.sha256(json.dumps(records, ensure_ascii=False,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    lines = [START, f"결정 기록 대조일: {stamp} | SHA-256(파일명·내용): `{digest}`",
             "", "| 기록 | 전체 파일 색인(상태·조건은 각 원문 참조) |", "|---|---|"]
    for kind in ("ADR", "DEC"):
        names = [name for name, _ in records if name.startswith(kind + "-")]
        links = [f"[{Path(name).stem}](decisions/{name})" for name in names]
        lines.append(f"| {kind} ({len(names)}) | " + ", ".join(links) + " |")
    return "\n".join([*lines, END])


def section(text):
    headings = list(HEADING.finditer(text))
    if len(headings) != 1:
        raise ValueError("expected exactly one dated §11 heading")
    heading = headings[0]
    end = text.find("\n## ", heading.end())
    body = text[heading.end():end if end != -1 else len(text)]
    if any(text.count(marker) != body.count(marker) for marker in (START, END)):
        raise ValueError("decision index markers must be inside §11")
    return heading, body


def index_bounds(body):
    if body.count(START) != 1 or body.count(END) != 1:
        raise ValueError("§11 needs exactly one generated decision index")
    start, end = body.index(START), body.index(END)
    if end < start:
        raise ValueError("decision index markers are reversed")
    return start, end + len(END)


def check(text, records, today):
    try:
        heading, body = section(text)
        stamp = heading.group(1)
        if dt.date.fromisoformat(stamp) > today:
            raise ValueError("§11 date is in the future")
        start, end = index_bounds(body)
        if body[start:end] != render_index(records, stamp):
            raise ValueError("ADR/DEC files or §11 date changed; decision index is stale")
    except ValueError as exc:
        return [str(exc)]
    return []


def refresh(text, records, today):
    heading, body = section(text)
    stamp = today.isoformat()
    index = render_index(records, stamp)
    if START not in body and END not in body:
        updated_body = body.rstrip() + "\n\n" + index + "\n"
    else:
        start, end = index_bounds(body)
        updated_body = body[:start] + index + body[end:]
    return (text[:heading.start()] + f"## 11. 현재 위치 ({stamp})" + updated_body
            + text[heading.end() + len(body):])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="after reviewing §11 status rows, stamp and regenerate its index")
    args = parser.parse_args()
    today = dt.datetime.now(dt.timezone.utc).date()
    path = ROOT / "docs/BLUEPRINT.md"
    try:
        records = decision_records(ROOT)
        text = path.read_text(encoding="utf-8")
        if args.write:
            text = refresh(text, records, today)
            path.write_text(text, encoding="utf-8")
        problems = check(text, records, today)
    except (OSError, ValueError) as exc:
        print(f"BLUEPRINT-S11: {exc}")
        return 2
    if problems:
        for problem in problems:
            print(f"BLUEPRINT-S11: {problem}")
        print("Review §11 status rows, then run: python3 -I tools/blueprint_status.py --write")
        return 1
    print(f"BLUEPRINT-S11: current decision index ({len(records)} ADR/DEC files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
