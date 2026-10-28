#!/usr/bin/env python3
"""Guard 09 product-purpose rows against tasks.json (static checks only).

Complements spec_check G12:
  PURPOSE-G12   all nine product-purpose test IDs from 09 section 6 are registered
  PURPOSE-OWNER each test is registered on every task assigned by 09 sections 4/6
  PURPOSE-TASK  each P row's implementation tasks are a subset of tasks.json IDs
  PURPOSE-ROWS  P01..P19 occur exactly once with a nonempty, parseable task list

Registration is not execution or product completion evidence.
Usage: python3 -I tools/ci/check_product_purpose.py [--root DIR] [--tasks FILE] [--purpose FILE]
       python3 -I tools/ci/check_product_purpose.py --selftest
Exit: 0 clean, 1 findings, 2 usage or unreadable/invalid input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_common as C  # noqa: E402

BUNDLE = Path("docs/blueprint/proposals/설계검토_결과")
DEFAULT_TASKS = BUNDLE / "tasks.json"
DEFAULT_PURPOSE = BUNDLE / "09_제품목적_대응표.md"
REQUIRED_TEST_IDS = frozenset({
    "purpose-rows-all-closed",
    "acquisition-reason-not-counted",
    "coverage-status-counts-acquired-only",
    "label-kinds-complete",
    "switch-diff-evidence-trace",
    "multi-contract-relation-trace",
    "first-view-priority",
    "decisive-conditions-not-hidden",
    "no-composite-score",
})
EXPECTED_ROWS = {f"P{i:02}" for i in range(1, 20)}
TASK_ID = re.compile(r"T-[A-Z]{2}-\d{2}")
# 09 §6 assigns all three UX IDs to T-MB-03/T-MB-04/T-AP-07.
# P16 additionally assigns non-hidden conditions to the API/detail/event tasks.
# These are minimum owners: other tasks may also register the same test ID.
REQUIRED_TEST_OWNERS = {
    "acquisition-reason-not-counted": {"T-DT-04"},
    "coverage-status-counts-acquired-only": {"T-AP-04"},
    "label-kinds-complete": {"T-KN-08"},
    "switch-diff-evidence-trace": {"T-TW-05"},
    "multi-contract-relation-trace": {"T-TW-05"},
    "first-view-priority": {"T-MB-03", "T-MB-04", "T-AP-07"},
    "decisive-conditions-not-hidden": {
        "T-MB-03", "T-MB-04", "T-AP-07", "T-AP-02", "T-MB-02", "T-AP-08",
    },
    "no-composite-score": {"T-MB-03", "T-MB-04", "T-AP-07"},
    "purpose-rows-all-closed": {"T-OP-08"},
}


def check(tasks_path, purpose_path):
    data = json.loads(Path(tasks_path).read_text(encoding="utf-8"))
    purpose = Path(purpose_path).read_text(encoding="utf-8")
    tasks = data["tasks"]
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    task_ids, have, registered = set(), set(), {}
    for task in tasks:
        tid, tests = task["id"], task.get("required_test_ids", [])
        if not isinstance(tid, str) or not TASK_ID.fullmatch(tid) or tid in task_ids:
            raise ValueError(f"invalid or duplicate task ID: {tid!r}")
        if not isinstance(tests, list) or any(not isinstance(test, str) for test in tests):
            raise ValueError(f"{tid}: required_test_ids must be a list of strings")
        task_ids.add(tid)
        have.update(tests)
        registered[tid] = set(tests)

    out = [C.Finding("PURPOSE-G12", str(tasks_path), 0,
                     f"required product-purpose test ID {test!r} is not registered")
           for test in sorted(REQUIRED_TEST_IDS - have)]
    for test, owners in sorted(REQUIRED_TEST_OWNERS.items()):
        for owner in sorted(owners):
            if test not in registered.get(owner, set()):
                out.append(C.Finding("PURPOSE-OWNER", str(tasks_path), 0,
                                     f"{owner}: required product-purpose test ID {test!r} is not registered on its assigned task"))
    seen = set()
    task_column = None
    for line_no, line in enumerate(purpose.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            task_column = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "#":
            columns = [i for i, cell in enumerate(cells) if cell.startswith("구현 작업")]
            task_column = columns[0] if len(columns) == 1 else None
            continue
        if not re.fullmatch(r"P\d+", cells[0]):
            continue
        row = cells[0]
        if row not in EXPECTED_ROWS or row in seen:
            out.append(C.Finding("PURPOSE-ROWS", str(purpose_path), line_no,
                                 f"unexpected or duplicate purpose row {row}"))
        seen.add(row)
        if task_column is None or task_column >= len(cells):
            out.append(C.Finding("PURPOSE-ROWS", str(purpose_path), line_no,
                                 f"{row}: missing implementation task column"))
            continue
        refs = [ref.strip().strip("`") for ref in cells[task_column].split(",")]
        if not refs or any(not TASK_ID.fullmatch(ref) for ref in refs):
            out.append(C.Finding("PURPOSE-ROWS", str(purpose_path), line_no,
                                 f"{row}: invalid or empty implementation task list"))
            continue
        unknown = set(refs) - task_ids
        if unknown:
            out.append(C.Finding("PURPOSE-TASK", str(purpose_path), line_no,
                                 f"{row}: implementation tasks absent from tasks.json: {', '.join(sorted(unknown))}"))
    missing = EXPECTED_ROWS - seen
    if missing:
        out.append(C.Finding("PURPOSE-ROWS", str(purpose_path), 0,
                             f"missing purpose rows: {', '.join(sorted(missing))}"))
    return out


def selftest():
    owners = set().union(*REQUIRED_TEST_OWNERS.values())
    rows = [{"id": owner, "required_test_ids": sorted(
        test for test, assigned in REQUIRED_TEST_OWNERS.items() if owner in assigned)}
        for owner in sorted(owners)]
    rows.append({"id": "T-AA-01", "required_test_ids": []})
    tasks = json.dumps({"tasks": rows})
    missing_test = json.loads(tasks)
    next(t for t in missing_test["tasks"] if t["id"] == "T-OP-08")["required_test_ids"] = []
    purpose = "| # | 구현 작업 |\n|---|---|\n" + "".join(
        f"| P{i:02} | T-AA-01 |\n" for i in range(1, 20))
    files = {"tasks.json": tasks, "purpose.md": purpose}
    cases = [
        ("registered and linked", files, None),
        ("missing purpose test", dict(files, **{"tasks.json": json.dumps(missing_test)}), "PURPOSE-G12"),
        ("missing assigned owner", dict(files, **{"tasks.json": tasks.replace('"first-view-priority",', "", 1)}), "PURPOSE-OWNER"),
        ("unknown row task", dict(files, **{"purpose.md": purpose.replace("T-AA-01", "T-AA-99", 1)}), "PURPOSE-TASK"),
        ("missing rows", dict(files, **{"purpose.md": ""}), "PURPOSE-ROWS"),
    ]
    return C.run_selftest("check_product_purpose", cases,
                          lambda root: check(root / "tasks.json", root / "purpose.md"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=C.ROOT)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--purpose", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        findings = check(args.tasks or args.root / DEFAULT_TASKS,
                         args.purpose or args.root / DEFAULT_PURPOSE)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return C.usage_error(f"cannot read product-purpose inputs: {exc}")
    return C.report(findings, "09 P01..P19 task links and all nine G12 product-purpose test IDs registered on assigned tasks (static only)",
                    "product-purpose")


if __name__ == "__main__":
    sys.exit(main())
