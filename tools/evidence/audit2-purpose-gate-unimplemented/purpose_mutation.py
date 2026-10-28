#!/usr/bin/env python3
"""Plant the audit's gaps into temp copies of tasks.json and 09, then run a check_product_purpose.py.

Usage: python3 -I purpose_mutation.py CHECKER_DIR [--timeout SECONDS]
CHECKER_DIR holds check_product_purpose.py and ci_common.py (the HEAD copy for before.log, tools/ci
for after.log). The repo files are never edited. Prints each mutation and the checker exit code/output.
Each checker has a 10-second deadline; a timeout exits 2 and names the running case.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
TASKS = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
PURPOSE = (BUNDLE / "09_제품목적_대응표.md").read_text(encoding="utf-8")


def task(data, tid):
    return next(t for t in data["tasks"] if t["id"] == tid)


def move(test_id, src, dst):
    def mutate(data, text):
        task(data, src)["required_test_ids"].remove(test_id)
        task(data, dst)["required_test_ids"].append(test_id)
        return text
    return mutate


def weaken_gate(data, text):
    task(data, "T-OP-08")["final_gate"] = False
    return text


def drop_gate_command(data, text):
    gate = task(data, "T-OP-08")
    gate["tests"] = [t for t in gate["tests"] if "--purpose" not in t]
    return text


def edit_gate_command(old, new):
    def mutate(data, text):
        gate = task(data, "T-OP-08")
        index = next(i for i, cmd in enumerate(gate["tests"]) if "--purpose" in cmd)
        assert old in gate["tests"][index], old
        gate["tests"][index] = gate["tests"][index].replace(old, new, 1)
        return text
    return mutate


def scope(row_id, new):
    def mutate(data, text):
        lines = text.splitlines(keepends=True)
        scope_column = None
        matches = []
        for index, line in enumerate(lines):
            if not line.lstrip().startswith("|"):
                scope_column = None
                continue
            cells = line.split("|")
            if cells[1].strip() == "#":
                columns = [i for i, cell in enumerate(cells) if cell.strip().startswith("축소·후속")]
                scope_column = columns[0] if len(columns) == 1 else None
            elif cells[1].strip() == row_id:
                assert scope_column is not None and scope_column < len(cells) - 1, row_id
                cells[scope_column] = f" {new} "
                matches.append((index, "|".join(cells)))
        assert len(matches) == 1, row_id
        index, line = matches[0]
        lines[index] = line
        return "".join(lines)
    return mutate


MUTATIONS = [
    ("none (live repo copy)", lambda data, text: text),
    ("acquisition-reason-not-counted moved T-DT-04 -> T-OP-01", move("acquisition-reason-not-counted", "T-DT-04", "T-OP-01")),
    ("purpose-rows-all-closed moved T-OP-08 -> T-OP-07", move("purpose-rows-all-closed", "T-OP-08", "T-OP-07")),
    ("P09 scope cell loses its basis", scope("P09", "가격 열 노출은 나중(결정 대기, 축소 아님)")),
    ("P19 scope cell cites unknown D-61", scope("P19", "시험 과제·표본·수락 수치는 D-61(결정 대기)")),
    ("T-OP-08 final_gate false", weaken_gate),
    ("T-OP-08 --purpose closure command removed", drop_gate_command),
    ("closure checker renamed check.py.disabled", edit_gate_command("check.py", "check.py.disabled")),
    ("closure --purpose file renamed .md.bak", edit_gate_command(".md ", ".md.bak ")),
    ("closure --evidence redirected to evidence/old/", edit_gate_command("evidence/", "evidence/old/")),
    ("closure --registry file renamed tasks.json.bak", edit_gate_command("tasks.json ", "tasks.json.bak ")),
    ("closure command followed by || true", edit_gate_command("evidence/", "evidence/ || true")),
]


def positive_seconds(value):
    seconds = float(value)
    if not 0 < seconds < float("inf"):
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return seconds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checker_dir", type=Path)
    parser.add_argument("--timeout", type=positive_seconds, default=10,
                        help="maximum seconds per checker invocation (default: 10)")
    args = parser.parse_args(argv)
    checker = args.checker_dir.resolve() / "check_product_purpose.py"
    failures = 0
    for name, mutate in MUTATIONS:
        print(f"== mutation: {name}", flush=True)
        data = json.loads(json.dumps(TASKS))
        text = mutate(data, PURPOSE)
        with tempfile.TemporaryDirectory() as tmp:
            tasks, purpose = Path(tmp) / "tasks.json", Path(tmp) / "09.md"
            tasks.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            purpose.write_text(text, encoding="utf-8")
            try:
                result = subprocess.run(
                    [sys.executable, "-I", str(checker), "--root", str(ROOT),
                     "--tasks", str(tasks), "--purpose", str(purpose)],
                    capture_output=True, text=True, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                print(f"TIMEOUT: checker exceeded {args.timeout:g}s for {name}", flush=True)
                return 2
            out = (result.stdout + result.stderr).replace(tmp, "<tmp>").replace(str(ROOT), "<repo>")
        print(f"exit={result.returncode}\n{out.rstrip()}\n", flush=True)
        failures += result.returncode != 0
    print(f"{failures}/{len(MUTATIONS)} runs exited nonzero")
    return 0


if __name__ == "__main__":
    sys.exit(main())
