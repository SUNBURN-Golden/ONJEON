#!/usr/bin/env python3
"""Plant the audit's gaps into temp copies of tasks.json and 09, then run a check_product_purpose.py.

Usage: python3 -I purpose_mutation.py CHECKER_DIR
CHECKER_DIR holds check_product_purpose.py and ci_common.py (the HEAD copy for before.log, tools/ci
for after.log). The repo files are never edited. Prints each mutation and the checker exit code/output.
"""
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


def scope(old, new):
    def mutate(data, text):
        assert text.count(old) == 1, old
        return text.replace(old, new)
    return mutate


MUTATIONS = [
    ("none (live repo copy)", lambda data, text: text),
    ("acquisition-reason-not-counted moved T-DT-04 -> T-OP-01", move("acquisition-reason-not-counted", "T-DT-04", "T-OP-01")),
    ("purpose-rows-all-closed moved T-OP-08 -> T-OP-07", move("purpose-rows-all-closed", "T-OP-08", "T-OP-07")),
    ("P09 scope cell loses its basis", scope("| 가격 열 노출은 O04·D-18 뒤(결정 대기, 축소 아님) |", "| 가격 열 노출은 나중(결정 대기, 축소 아님) |")),
    ("P19 scope cell cites unknown D-61", scope("| 시험 과제·표본·수락 수치는 D-16(결정 대기) |", "| 시험 과제·표본·수락 수치는 D-61(결정 대기) |")),
    ("T-OP-08 final_gate false", weaken_gate),
    ("T-OP-08 --purpose closure command removed", drop_gate_command),
]


def main():
    checker = Path(sys.argv[1]).resolve() / "check_product_purpose.py"
    failures = 0
    for name, mutate in MUTATIONS:
        data = json.loads(json.dumps(TASKS))
        text = mutate(data, PURPOSE)
        with tempfile.TemporaryDirectory() as tmp:
            tasks, purpose = Path(tmp) / "tasks.json", Path(tmp) / "09.md"
            tasks.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            purpose.write_text(text, encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(checker), "--root", str(ROOT),
                                     "--tasks", str(tasks), "--purpose", str(purpose)],
                                    capture_output=True, text=True)
            out = (result.stdout + result.stderr).replace(tmp, "<tmp>").replace(str(ROOT), "<repo>")
        print(f"== mutation: {name}\nexit={result.returncode}\n{out.rstrip()}\n")
        failures += result.returncode != 0
    print(f"{failures}/{len(MUTATIONS)} runs exited nonzero")


if __name__ == "__main__":
    main()
