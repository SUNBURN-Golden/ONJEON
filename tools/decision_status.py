#!/usr/bin/env python3
"""Generate or check the decision index and its Markdown projections."""
import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = Path("docs")
BUNDLE = DOCS / "blueprint/proposals/설계검토_결과"
LEDGER = DOCS / "blueprint/DECISIONS.md"
REGISTRY = BUNDLE / "tasks.json"
PURPOSE = BUNDLE / "09_제품목적_대응표.md"
GATE_TABLES = (BUNDLE / "README.md", BUNDLE / "03_작업명세.md")
PHASES = ("start", "real_data", "merge", "release")
STATUS_LABELS = {
    "scope_resolved": "기록 범위 해결",
    "provisional_scope_resolved": "기록 범위 해결(잠정 기준)",
    "provisional": "잠정 개발 기준",
    "delegated": "위임 결정",
    "conditional": "조건부 승인",
    "awaiting_audit": "감리 대기·미승인",
    "scope_only": "범위만 기록·내용 미정",
    "partially_superseded": "부분 대체",
    "open": "미정",
}
SOURCE = ("<!-- decision-status-source:start -->", "<!-- decision-status-source:end -->")
GENERATED = ("<!-- decision-status-table:start -->", "<!-- decision-status-table:end -->")
PURPOSE_COLUMN = "결정 상태(작업·범위)"
GATE_ID = r"(?:D-\d{2}|O\d{2})"


def region(text, markers):
    start, end = markers
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) >= text.index(end):
        raise ValueError(f"expected one ordered region for {start}")
    before, rest = text.split(start)
    body, after = rest.split(end)
    return before, body, after


def table_cells(line):
    return [cell.strip() for cell in line.strip("|").split("|")]


def table_row(cells):
    return "| " + " | ".join(cells) + " |"


def ledger_metadata(ledger, record_names):
    _, source, _ = region(ledger, SOURCE)
    index, seen = {}, set()
    rows = [line for line in source.splitlines() if line.startswith("|")]
    for line in rows[2:]:
        label, _, _, _, status, decided_by = table_cells(line)
        status = status.strip("`")
        link = re.fullmatch(r"\[(DEC-[A-Z0-9-]+|O\d{2})\]\(\.\./decisions/(DEC-[A-Z0-9-]+)\.md\)", label)
        if link:
            name, target = link.groups()
            if target not in record_names or (name.startswith("DEC-") and name != target):
                raise ValueError(f"invalid DEC reference: {label}")
            if name.startswith("DEC-"):
                seen.add(name)
            gate = name.removeprefix("DEC-")
        elif re.fullmatch(rf"`{GATE_ID}`", label):
            gate, target = label.strip("`"), None
        else:
            raise ValueError(f"invalid decision entry: {label}")
        if gate in index or status not in STATUS_LABELS or not decided_by:
            raise ValueError(f"duplicate decision or invalid metadata: {gate}")
        if (status == "open") != (target is None):
            raise ValueError(f"{gate}: only open entries lack a DEC record")
        if (status in {"open", "awaiting_audit", "scope_only"}) != (decided_by == "—"):
            raise ValueError(f"{gate}: decided_by must reflect the decision status")
        index[gate] = {
            "status": status,
            "decided_by": None if decided_by == "—" else decided_by,
            "record_ref": f"docs/decisions/{target}.md" if target else None,
        }
    if seen != record_names:
        raise ValueError(f"missing DEC rows in ledger: {', '.join(sorted(record_names - seen))}")
    return index


def build_index(metadata, tasks):
    index = {
        gate: {**entry, **{phase: [] for phase in PHASES}}
        for gate, entry in sorted(metadata.items())
    }
    for task in tasks:
        for phase in PHASES:
            for gate in task["decision_gates"][phase]:
                if gate not in index:
                    raise ValueError(f"{task['id']} {phase}: {gate} is missing from the decision ledger")
                index[gate][phase].append(task["id"])
    return index


def record_link(gate, entry):
    ref = entry["record_ref"]
    return f"[{gate}](../../../{ref.removeprefix('docs/')})" if ref else gate


def render_gate_table(index):
    columns = ["결정·기록", "상태", "결정자", "시작(start)", "실데이터(real_data)",
               "병합(merge)", "출시·서비스 적용(release)"]
    rows = [table_row(columns), table_row(["---"] * len(columns))]
    for gate, entry in index.items():
        rows.append(table_row([
            record_link(gate, entry), STATUS_LABELS[entry["status"]], entry["decided_by"] or "—",
            *[", ".join(entry[phase]) or "—" for phase in PHASES],
        ]))
    return "\n".join(rows)


def render_purpose(text, index, tasks):
    task_gates = {
        task["id"]: set().union(*(task["decision_gates"][phase] for phase in PHASES))
        for task in tasks
    }
    lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("| # |") and table_cells(line.rstrip())[-2] != PURPOSE_COLUMN:
            raise ValueError(f"missing purpose column: {PURPOSE_COLUMN}")
        if re.match(r"^\| P\d{2} \|", line):
            cells = line.split("|")
            purpose_id, task_refs = cells[1].strip(), cells[7]
            if len(cells) != 13:
                raise ValueError(f"{purpose_id}: expected 11 purpose columns")
            refs = [ref.strip().strip("`") for ref in task_refs.split(",")]
            if set(refs) - task_gates.keys():
                raise ValueError(f"{purpose_id}: unknown implementation task")
            gates = set().union(*(task_gates[ref] for ref in refs))
            scope_gates = re.findall(rf"(?<!BP-)\b{GATE_ID}\b", cells[-2], re.ASCII)
            gates.update(set(scope_gates) & index.keys())
            entries = [f"{record_link(gate, index[gate])} ‒ {STATUS_LABELS[index[gate]['status']]}"
                       for gate in sorted(gates)]
            cells[-3] = f" {'<br>'.join(entries) or '—'} "
            line = "|".join(cells)
        lines.append(line)
    return "".join(lines)


def projections(root):
    ledger = (root / LEDGER).read_text(encoding="utf-8")
    record_names = {path.stem for path in (root / DOCS / "decisions").glob("DEC-*.md") if path.is_file()}
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    index = build_index(ledger_metadata(ledger, record_names), registry["tasks"])
    registry["decision_index"] = index
    yield REGISTRY, json.dumps(registry, ensure_ascii=False, indent=2) + "\n"
    for path in GATE_TABLES:
        before, _, after = region((root / path).read_text(encoding="utf-8"), GENERATED)
        yield path, f"{before}{GENERATED[0]}\n{render_gate_table(index)}\n{GENERATED[1]}{after}"
    yield PURPOSE, render_purpose((root / PURPOSE).read_text(encoding="utf-8"), index, registry["tasks"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the committed projections")
    args = parser.parse_args()
    try:
        outputs = list(projections(ROOT))
        stale = [(path, content) for path, content in outputs
                 if (ROOT / path).read_text(encoding="utf-8") != content]
        for path, content in stale:
            if args.write:
                (ROOT / path).write_text(content, encoding="utf-8")
                print(f"Updated {path}")
            else:
                print(f"Stale decision status: {path}", file=sys.stderr)
        if stale and not args.write:
            print("Run python3 tools/decision_status.py --write", file=sys.stderr)
            return 1
        print("Decision index and tables are synchronized")
        return 0
    except (KeyError, OSError, ValueError) as exc:
        print(f"Cannot synchronize decision status: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
