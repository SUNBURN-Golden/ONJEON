#!/usr/bin/env python3
"""PR body traceability guard (Audit 4).

A PR must be traceable to the work contract or to the product completion standard.
The body may name any one of:
  - a `tasks.json` task ID (`T-XX-NN`), which must exist in tasks.json;
  - an out-of-list node ID: labelled, or a bare (not necessarily inline-code)
    `` auditN-some-node `` slug; the orchestrator emits it in prose and paths;
  - an 09_제품목적_대응표 P row (`P01`..`P19`).

The PR template is the usual place to record this, but this guard reads the body
itself so a missing or edited template cannot leave a PR untraceable. Registration
is not completion evidence: a P row here does not close the row.

  PR-TRACE-MISSING  body names no task ID, node ID, or P row
  PR-TRACE-TASK     a `T-XX-NN` task ID is not present in tasks.json

Usage: python3 -I tools/ci/check_pr_body_traceability.py --body-file FILE
       python3 -I tools/ci/check_pr_body_traceability.py --body TEXT
       PR_BODY='...' python3 -I tools/ci/check_pr_body_traceability.py
       python3 -I tools/ci/check_pr_body_traceability.py --selftest
Exit: 0 clean, 1 findings, 2 usage or unreadable/invalid input.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_common as C  # noqa: E402

DEFAULT_TASKS = Path("docs/blueprint/proposals/설계검토_결과/tasks.json")
# Hyphens are part of the token boundary: DEC-CANON-T-CT-02 contains "T-CT-02"
# as a suffix, not as a tasks.json task ID.
TASK_ID = re.compile(r"(?<![A-Za-z0-9-])(T-[A-Z]{2}-\d{2})(?![A-Za-z0-9-])")
# A labelled node ID. Bare hyphenated words other than audit slugs are too easy to hit
# by accident, so only `auditN-...` is accepted unlabelled: the orchestrator writes the
# audit node slug in plain prose and filesystem paths without backticks.
NODE_ID = re.compile(r"(?:노드(?:\s*ID)?|Node|node)\s*[:：]?\s*`([a-z0-9]+(?:-[a-z0-9]+)+)`")
AUDIT_NODE_ID = re.compile(r"(?<![A-Za-z0-9])(audit\d+(?:-[a-z0-9]+)+)(?![A-Za-z0-9])")
P_ROW = re.compile(r"(?<![A-Za-z0-9])(P(?:0[1-9]|1[0-9]))(?![0-9])")


def check(body, tasks_path):
    """Return findings for a PR body against a tasks.json file."""
    task_ids = set(TASK_ID.findall(body))
    node_ids = set(NODE_ID.findall(body)) | set(AUDIT_NODE_ID.findall(body))
    p_rows = set(P_ROW.findall(body))
    findings = []

    if task_ids:
        data = json.loads(Path(tasks_path).read_text(encoding="utf-8"))
        known = {task["id"] for task in data["tasks"]}
        for task_id in sorted(task_ids - known):
            findings.append(C.Finding(
                "PR-TRACE-TASK", str(tasks_path), 0,
                f"{task_id} is not a task ID in tasks.json"))
    if not task_ids and not node_ids and not p_rows:
        findings.append(C.Finding(
            "PR-TRACE-MISSING", "<pull request body>", 0,
            "no tasks.json task ID, node ID, or 09 P row (P01..P19)"))
    return findings


def selftest():
    files = {"tasks.json": json.dumps({"tasks": [{"id": "T-AA-01"}]})}
    cases = [
        ("task ID and P row", "T-AA-01 P03", None),
        ("single P row", "Closes P19 evidence.", None),
        ("labelled node ID", "Node `audit4-example-node`", None),
        ("inline-code audit node ID", "`audit4-example-node`", None),
        ("bare audit node ID in prose", "Node audit4-example-node — in scope fix", None),
        ("bare audit node ID in a path", "/wt/audit4-example-node/tools/ci", None),
        ("Korean node label", "노드 ID: `audit4-example-node`", None),
        ("DEC id suffix is not a task ID", "Node `audit4-example-node` DEC-CANON-T-CT-02", None),
        ("empty body", "", "PR-TRACE-MISSING"),
        ("no trace handle", "Fixes a typo in the README.", "PR-TRACE-MISSING"),
        ("unknown task ID", "T-ZZ-99", "PR-TRACE-TASK"),
        ("unknown task ID beside a valid P row", "T-ZZ-99 P01", "PR-TRACE-TASK"),
        ("out-of-range P row", "P20", "PR-TRACE-MISSING"),
        ("unlabelled non-audit slug", "example-node", "PR-TRACE-MISSING"),
    ]
    return C.run_selftest(
        "check_pr_body_traceability",
        [(name, dict(files, **{"body.txt": body}), rule) for name, body, rule in cases],
        lambda root: check((root / "body.txt").read_text(encoding="utf-8"), root / "tasks.json"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=C.ROOT)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--body")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.body_file is not None:
        try:
            body = args.body_file.read_text(encoding="utf-8")
        except OSError as exc:
            return C.usage_error(f"cannot read PR body file: {exc}")
    elif args.body is not None:
        body = args.body
    elif "PR_BODY" in os.environ:
        body = os.environ["PR_BODY"]
    else:
        return C.usage_error("no PR body: pass --body-file/--body or set PR_BODY")
    try:
        findings = check(body, args.tasks or args.root / DEFAULT_TASKS)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return C.usage_error(f"cannot read traceability inputs: {exc}")
    return C.report(
        findings,
        "PR body names a tasks.json task ID, node ID, or 09 P row (traceability only)",
        "pr-traceability")


if __name__ == "__main__":
    sys.exit(main())
