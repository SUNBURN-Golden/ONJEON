"""Re-run spec_check's shell validator on the exact commands Audit 5 reported.

The strings below are the pre-fix values from `tasks.json` (T-OP-09:1536, T-CT-01:1676,
trailing prose at :2046/:3126/:3127/:3328, and the two-filter `cargo test` lines in tasks and
`feature_registry`). Every one must be rejected; the commands now in `tasks.json` for the same
task IDs must pass. Exit 0 only then. This reads the live bundle; it does not write it.
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
_spec = importlib.util.spec_from_file_location("spec_check", BUNDLE / "검증/spec_check.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

OLD_SHELL = {
    "T-OP-09": "bash tools/daemon/runner_verify/run.sh --remote <시험용 원격> --report docs/vm_check/<날짜>/runner_verify.json",
    "T-CT-01": "bash packages/schemas/codegen/check_compat.sh <prev_tag>",
    "T-CT-05": "bash infra/db/test.sh (Compose Postgres에서 제약 시험)",
    "T-KN-04": "cargo test -p onjeon-knowledge fixture_rejection(service_conformance 프로필: 픽스처 A-box 적재 시 fixture_assumption·origin=fixture accepted 전부 거부)",
    "T-KN-06": "cargo test -p onjeon-ai-review review (모의 제공자 2계열)",
    "T-OP-03": "(측정 작업. 자동 시험 없음)",
    "T-OP-06": "(점검 작업)",
    "T-UX-01": "(사용자 시험)",
    "T-OP-07": "(운영 기록)",
}

OLD_TASK_CARGO = {
    "T-AP-02": "cargo test -p onjeon-api coverage evidence",
    "T-PS-03": "cargo test -p onjeon-personal consent deletion export",
    "T-TW-05": "cargo test -p onjeon-twin-runtime multi plan_diff",
}

OLD_REGISTRY_CARGO = {
    "me": "cargo test -p onjeon-personal consent deletion export",
    "collect": "cargo test -p onjeon-collect archive schedule",
    "labeling": "cargo test -p onjeon-knowledge store structures",
    "multi-contract": "cargo test -p onjeon-twin-runtime multi dependency",
    "twin-multi": "cargo test -p onjeon-twin-runtime multi dependency",
    "consent-deletion": "cargo test -p onjeon-personal consent deletion",
    "no-denominator-signal": "cargo test -p onjeon-personal leak denominator_signal",
}

FIXED_TASK_IDS = ("T-OP-09", "T-CT-01", "T-CT-05", "T-KN-04", "T-KN-06", "T-AP-02", "T-PS-03", "T-TW-05")
FIXED_REGISTRY_IDS = ("me", "collect", "labeling", "multi-contract", "twin-multi", "consent-deletion",
                      "no-denominator-signal")

data = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
tasks = {t["id"]: t for t in data["tasks"]}
registry = {f["id"]: f for f in data["feature_registry"]}
failures = 0


def detect(ok, label):
    """A pre-fix command is good here only when the checker flags it."""
    global failures
    if not ok:
        failures += 1
    print(("DETECTED" if ok else "MISSED  ") + " " + label)


def accept(ok, label):
    """A current command is good here only when the checker accepts it."""
    global failures
    if not ok:
        failures += 1
    print(("OK      " if ok else "BAD     ") + " " + label)


print("== pre-fix commands must be rejected ==")
for tid, command in OLD_SHELL.items():
    problems = sc.shell_command_problems(command)
    detect(bool(problems), f"{tid}: {problems or 'no problem found'} :: {command}")

print("\n== pre-fix two-filter cargo test must be rejected ==")
for scope, old in (("task", OLD_TASK_CARGO), ("feature_registry", OLD_REGISTRY_CARGO)):
    for tid, command in old.items():
        filters = sc.cargo_test_filters(command)
        detect(bool(filters and len(filters) > 1), f"{scope} {tid}: filters={filters} :: {command}")

print("\n== current commands for the same tasks must pass ==")
for tid in FIXED_TASK_IDS:
    for command in tasks[tid]["tests"]:
        if command.startswith("시험 "):
            continue
        problems = sc.shell_command_problems(command)
        filters = sc.cargo_test_filters(command)
        accept(not problems and not (filters and len(filters) > 1), f"{tid}: {command}")

print("\n== current commands for the same features must pass ==")
for fid in FIXED_REGISTRY_IDS:
    for command in registry[fid]["acceptance_tests"]:
        if not isinstance(command, str):
            continue
        problems = sc.shell_command_problems(command)
        filters = sc.cargo_test_filters(command)
        accept(not problems and not (filters and len(filters) > 1), f"{fid}: {command}")

print(f"\n{'PASS' if not failures else f'{failures} FAILURE(S)'}")
sys.exit(0 if not failures else 1)
