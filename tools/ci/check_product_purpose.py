#!/usr/bin/env python3
"""Guard 09 product-purpose rows against tasks.json (static checks only).

Complements spec_check G12 without editing the protected design bundle:
  PURPOSE-G12   all nine product-purpose test IDs from 09 section 6 are registered
  PURPOSE-TASK  each P row's implementation tasks are a subset of tasks.json IDs
  PURPOSE-ROWS  P01..P19 occur exactly once with a nonempty, parseable task list
  PURPOSE-OWNER each of those test IDs is registered on a task 09 section 6 names as its owner
  PURPOSE-SCOPE every 축소·후속 cell other than '—' cites at least one basis (ADR-nnnn, DEC-*,
                D-nn, Onn, BLUEPRINT §n) and every basis it cites resolves in the repo under --root
  PURPOSE-GATE  T-OP-08 stays final_gate with purpose-rows-all-closed and the exact closure command
                (python3 -I tools/release_readiness/check.py with exactly --purpose 09, --registry
                tasks.json and --evidence docs/release-readiness/evidence/, compared token by token)

Registration is not execution or product completion evidence. Row closure (post_merge state and
evidence logs) is T-OP-08's tools/release_readiness/check.py, which this guard does not replace.
Usage: python3 -I tools/ci/check_product_purpose.py [--root DIR] [--tasks FILE] [--purpose FILE]
       python3 -I tools/ci/check_product_purpose.py --selftest
Exit: 0 clean, 1 findings, 2 usage or unreadable/invalid input.
"""
import argparse
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_common as C  # noqa: E402

BUNDLE = Path("docs/blueprint/proposals/설계검토_결과")
DEFAULT_TASKS = BUNDLE / "tasks.json"
DEFAULT_PURPOSE = BUNDLE / "09_제품목적_대응표.md"
# 09 section 6: test ID -> tasks allowed to own it (at least one of them must register it).
SCREEN_OWNERS = frozenset({"T-MB-03", "T-MB-04", "T-AP-07"})
TEST_OWNERS = {
    "purpose-rows-all-closed": frozenset({"T-OP-08"}),
    "acquisition-reason-not-counted": frozenset({"T-DT-04"}),
    "coverage-status-counts-acquired-only": frozenset({"T-AP-04"}),
    "label-kinds-complete": frozenset({"T-KN-08"}),
    "switch-diff-evidence-trace": frozenset({"T-TW-05"}),
    "multi-contract-relation-trace": frozenset({"T-TW-05"}),
    "first-view-priority": SCREEN_OWNERS,
    "decisive-conditions-not-hidden": SCREEN_OWNERS,
    "no-composite-score": SCREEN_OWNERS,
}
REQUIRED_TEST_IDS = frozenset(TEST_OWNERS)
GATE_TASK = "T-OP-08"
GATE_TEST = "purpose-rows-all-closed"
# The closure command is compared token by token: exact program argv, each option exactly once with
# its exact value, nothing else (no extra flags, suffixed paths, redirects or shell operators).
GATE_PROGRAM = ("python3", "-I", "tools/release_readiness/check.py")
GATE_OPTIONS = {"--purpose": DEFAULT_PURPOSE.as_posix(), "--registry": DEFAULT_TASKS.as_posix(),
                "--evidence": "docs/release-readiness/evidence/"}
GATE_COMMAND = " ".join([*GATE_PROGRAM, *(f"{k} {v}" for k, v in GATE_OPTIONS.items())])
EXPECTED_ROWS = {f"P{i:02}" for i in range(1, 20)}
TASK_ID = re.compile(r"T-[A-Z]{2}-\d{2}")
NO_SCOPE = "—"
BASIS = re.compile(r"(?<![A-Za-z0-9-])(?:ADR-\d{4}|DEC-[A-Z0-9]+(?:-[A-Z0-9]+)*|D-\d{2}|O\d{2})(?![0-9])"
                   r"|BLUEPRINT §\d+(?:\.\d+)?")


def basis_exists(root, ref):
    root = Path(root)
    if ref.startswith("ADR-"):
        return any((root / "docs/decisions").glob(f"{ref}-*.md"))
    if ref.startswith("DEC-"):
        return (root / "docs/decisions" / f"{ref}.md").is_file()
    if ref.startswith("D-"):
        return (root / "docs/decisions" / f"DEC-{ref}.md").is_file()
    if ref.startswith("O"):
        ledger = root / "docs/blueprint/DECISIONS.md"
        return ledger.is_file() and re.search(rf"^\| {ref} \|", ledger.read_text(encoding="utf-8"), re.M) is not None
    section = ref.split("§", 1)[1]
    blueprint = root / "docs/BLUEPRINT.md"
    return blueprint.is_file() and re.search(rf"^#+ {re.escape(section)}[. ]",
                                             blueprint.read_text(encoding="utf-8"), re.M) is not None


def check_gate(tasks_path, by_id):
    task = by_id.get(GATE_TASK)
    if task is None:
        return [C.Finding("PURPOSE-GATE", str(tasks_path), 0, f"closure gate task {GATE_TASK} is missing")]
    out = []
    if task.get("final_gate") is not True:
        out.append(C.Finding("PURPOSE-GATE", str(tasks_path), 0, f"{GATE_TASK} is no longer final_gate"))
    if GATE_TEST not in task.get("required_test_ids", []):
        out.append(C.Finding("PURPOSE-GATE", str(tasks_path), 0,
                             f"{GATE_TASK} no longer requires {GATE_TEST}"))
    tests = task.get("tests", [])
    if not isinstance(tests, list) or not any(is_gate_command(cmd) for cmd in tests):
        out.append(C.Finding("PURPOSE-GATE", str(tasks_path), 0,
                             f"{GATE_TASK} tests lack the closure command: {GATE_COMMAND}"))
    return out


def is_gate_command(cmd):
    """True only for GATE_PROGRAM followed by every GATE_OPTIONS pair once, in any order, and nothing else."""
    # shlex treats newlines as whitespace, while a shell can use them to end the command.
    if not isinstance(cmd, str) or "\n" in cmd or "\r" in cmd:
        return False
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return False
    n = len(GATE_PROGRAM)
    if tuple(argv[:n]) != GATE_PROGRAM or len(argv) != n + 2 * len(GATE_OPTIONS):
        return False
    pairs = list(zip(argv[n::2], argv[n + 1::2]))
    return dict(pairs) == GATE_OPTIONS and len({key for key, _ in pairs}) == len(pairs)


def check(tasks_path, purpose_path, root=C.ROOT):
    data = json.loads(Path(tasks_path).read_text(encoding="utf-8"))
    purpose = Path(purpose_path).read_text(encoding="utf-8")
    tasks = data["tasks"]
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    task_ids, have, by_id = set(), {}, {}
    for task in tasks:
        tid, tests = task["id"], task.get("required_test_ids", [])
        if not isinstance(tid, str) or not TASK_ID.fullmatch(tid) or tid in task_ids:
            raise ValueError(f"invalid or duplicate task ID: {tid!r}")
        if not isinstance(tests, list) or any(not isinstance(test, str) for test in tests):
            raise ValueError(f"{tid}: required_test_ids must be a list of strings")
        task_ids.add(tid)
        by_id[tid] = task
        for test in tests:
            have.setdefault(test, set()).add(tid)

    out = [C.Finding("PURPOSE-G12", str(tasks_path), 0,
                     f"required product-purpose test ID {test!r} is not registered")
           for test in sorted(REQUIRED_TEST_IDS - have.keys())]
    for test in sorted(REQUIRED_TEST_IDS & have.keys()):
        if not have[test] & TEST_OWNERS[test]:
            out.append(C.Finding("PURPOSE-OWNER", str(tasks_path), 0,
                                 f"{test!r} is registered on {', '.join(sorted(have[test]))}, "
                                 f"not on its 09 section 6 owner {' or '.join(sorted(TEST_OWNERS[test]))}"))
    out += check_gate(tasks_path, by_id)
    seen = set()
    task_column = scope_column = None
    for line_no, line in enumerate(purpose.splitlines(), 1):
        if not line.lstrip().startswith("|"):
            task_column = scope_column = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == "#":
            columns = [i for i, cell in enumerate(cells) if cell.startswith("구현 작업")]
            task_column = columns[0] if len(columns) == 1 else None
            columns = [i for i, cell in enumerate(cells) if cell.startswith("축소·후속")]
            scope_column = columns[0] if len(columns) == 1 else None
            continue
        if not re.fullmatch(r"P\d+", cells[0]):
            continue
        row = cells[0]
        if row not in EXPECTED_ROWS or row in seen:
            out.append(C.Finding("PURPOSE-ROWS", str(purpose_path), line_no,
                                 f"unexpected or duplicate purpose row {row}"))
        seen.add(row)
        if scope_column is None or scope_column >= len(cells):
            out.append(C.Finding("PURPOSE-ROWS", str(purpose_path), line_no,
                                 f"{row}: missing 축소·후속 column"))
        elif cells[scope_column] != NO_SCOPE:
            refs = sorted(set(BASIS.findall(cells[scope_column])))
            missing_refs = [ref for ref in refs if not basis_exists(root, ref)]
            if not refs:
                out.append(C.Finding("PURPOSE-SCOPE", str(purpose_path), line_no,
                                     f"{row}: 축소·후속 cell cites no basis (ADR-nnnn, DEC-*, D-nn, Onn, BLUEPRINT §n)"))
            elif missing_refs:
                out.append(C.Finding("PURPOSE-SCOPE", str(purpose_path), line_no,
                                     f"{row}: 축소·후속 basis not found in repo: {', '.join(missing_refs)}"))
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


def fixture_tasks():
    """Smallest tasks list satisfying every rule: owners, the T-OP-08 gate and row tasks T-AA-01/02."""
    tasks = {}
    for test, owners in sorted(TEST_OWNERS.items()):
        tasks.setdefault(min(owners), {"id": min(owners), "required_test_ids": []})["required_test_ids"].append(test)
    tasks[GATE_TASK].update(final_gate=True, tests=[GATE_COMMAND])
    return list(tasks.values()) + [{"id": "T-AA-01", "required_test_ids": []},
                                   {"id": "T-AA-02", "required_test_ids": []}]


def selftest():
    data = {"tasks": fixture_tasks()}
    tasks = json.dumps(data)
    purpose = "| # | 구현 작업 | 축소·후속(근거) |\n|---|---|---|\n" + "".join(
        f"| P{i:02} | T-AA-01 | — |\n" for i in range(1, 20))
    files = {"tasks.json": tasks, "purpose.md": purpose, "docs/decisions/DEC-D-01.md": "x\n"}
    moved = json.loads(tasks)
    for task in moved["tasks"]:
        if task["id"] == "T-AA-01":
            task["required_test_ids"].append("label-kinds-complete")
        elif "label-kinds-complete" in task["required_test_ids"]:
            task["required_test_ids"].remove("label-kinds-complete")
    no_gate = json.loads(tasks)
    for task in no_gate["tasks"]:
        task.pop("final_gate", None)
    cases = [
        ("registered and linked", files, None),
        ("cited basis exists", dict(files, **{"purpose.md": purpose.replace("| — |", "| D-01 뒤 |", 1)}), None),
        ("missing purpose test", dict(files, **{"tasks.json": tasks.replace('"purpose-rows-all-closed"', '"x"')}),
         "PURPOSE-G12"),
        ("unknown row task", dict(files, **{"purpose.md": purpose.replace("T-AA-01", "T-AA-99", 1)}), "PURPOSE-TASK"),
        ("missing rows", dict(files, **{"purpose.md": ""}), "PURPOSE-ROWS"),
        ("test on non-owner", dict(files, **{"tasks.json": json.dumps(moved)}), "PURPOSE-OWNER"),
        ("scope without basis", dict(files, **{"purpose.md": purpose.replace("| — |", "| 후속 |", 1)}), "PURPOSE-SCOPE"),
        ("scope basis missing", dict(files, **{"purpose.md": purpose.replace("| — |", "| D-99 뒤 |", 1)}),
         "PURPOSE-SCOPE"),
        ("gate not final", dict(files, **{"tasks.json": json.dumps(no_gate)}), "PURPOSE-GATE"),
        ("gate command disabled", dict(files, **{"tasks.json": tasks.replace("check.py", "check.py.disabled")}),
         "PURPOSE-GATE"),
    ]
    return C.run_selftest("check_product_purpose", cases,
                          lambda root: check(root / "tasks.json", root / "purpose.md", root))


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
                         args.purpose or args.root / DEFAULT_PURPOSE, args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return C.usage_error(f"cannot read product-purpose inputs: {exc}")
    return C.report(findings, "09 P01..P19 task links, nine section 6 test IDs on their owner tasks, "
                    "축소·후속 bases and the T-OP-08 closure gate present (static only; 0 rows proven closed)",
                    "product-purpose")


if __name__ == "__main__":
    sys.exit(main())
