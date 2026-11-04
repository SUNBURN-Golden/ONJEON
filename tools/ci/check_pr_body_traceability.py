#!/usr/bin/env python3
"""PR body traceability guard (Audit 4).

A PR must be traceable to the work contract or to the product completion standard.
The PR body or its head branch may name any one of:
  - a `tasks.json` task ID (`T-XX-NN`), which must exist in tasks.json;
  - an out-of-list node ID: labelled, or a bare (not necessarily inline-code)
    `` auditN-some-node `` slug; the orchestrator emits it in prose and paths;
  - an 09_제품목적_대응표 P row (`P01`..`P19`).

The PR template is the usual place to record this, but this guard reads the body
itself so a missing or edited template cannot leave a PR untraceable. The head
branch is a second accepted source because the orchestrator derives every branch
name from the node slug (`grokbot/onjeon-audit4-example-node`) while an
auto-generated body may omit it. Registration is not completion evidence: a P row
here does not close the row.

  PR-TRACE-MISSING  body and head branch name no task ID, node ID, or P row
  PR-TRACE-TASK     a `T-XX-NN` task ID is not present in tasks.json

Usage: python3 -I tools/ci/check_pr_body_traceability.py --body-file FILE
       python3 -I tools/ci/check_pr_body_traceability.py --body TEXT --head-ref BRANCH
       PR_BODY='...' PR_HEAD_REF='...' python3 -I tools/ci/check_pr_body_traceability.py
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
TASK_ID = re.compile(r"(?<![A-Za-z0-9])(T-[A-Z]{2}-\d{2})(?![0-9])")
# A labelled node ID. Bare hyphenated words other than audit slugs are too easy to hit
# by accident, so only `auditN-...` is accepted unlabelled: the orchestrator writes the
# audit node slug in plain prose and filesystem paths without backticks.
NODE_ID = re.compile(r"(?:노드(?:\s*ID)?|Node|node)\s*[:：]?\s*`([a-z0-9]+(?:-[a-z0-9]+)+)`")
AUDIT_NODE_ID = re.compile(r"(?<![A-Za-z0-9])(audit\d+(?:-[a-z0-9]+)+)(?![A-Za-z0-9])")
P_ROW = re.compile(r"(?<![A-Za-z0-9])(P(?:0[1-9]|1[0-9]))(?![0-9])")


def handles(text):
    """Return the task IDs, node IDs and P rows named in text."""
    return (set(TASK_ID.findall(text)),
            set(NODE_ID.findall(text)) | set(AUDIT_NODE_ID.findall(text)),
            set(P_ROW.findall(text)))


def check(body, tasks_path, head_ref=None):
    """Return findings for a PR body and optional head branch against tasks.json."""
    task_ids, node_ids, p_rows = handles(body)
    ref_task_ids, ref_node_ids, ref_p_rows = handles(head_ref or "")
    task_ids |= ref_task_ids
    node_ids |= ref_node_ids
    p_rows |= ref_p_rows
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
            "PR-TRACE-MISSING", "<pull request body or head branch>", 0,
            "no tasks.json task ID, node ID, or 09 P row (P01..P19)"))
    return findings


def selftest():
    tasks = {"tasks.json": json.dumps({"tasks": [{"id": "T-AA-01"}]})}
    cases = [
        # (name, body, head_ref, expected rule)
        ("task ID and P row", "T-AA-01 P03", None, None),
        ("single P row", "Closes P19 evidence.", None, None),
        ("labelled node ID", "Node `audit4-example-node`", None, None),
        ("inline-code audit node ID", "`audit4-example-node`", None, None),
        ("bare audit node ID in prose", "Node audit4-example-node — in scope fix", None, None),
        ("bare audit node ID in a path", "/wt/audit4-example-node/tools/ci", None, None),
        ("Korean node label", "노드 ID: `audit4-example-node`", None, None),
        ("node slug only in head branch", "", "grokbot/onjeon-audit4-example-node", None),
        ("task ID only in head branch", "Fixes a typo.", "feature/T-AA-01", None),
        ("P row only in head branch", "", "pr/P04", None),
        ("empty body", "", None, "PR-TRACE-MISSING"),
        ("no trace handle", "Fixes a typo in the README.", None, "PR-TRACE-MISSING"),
        ("unrelated head branch", "Fixes a typo.", "feature/typo", "PR-TRACE-MISSING"),
        ("unknown task ID", "T-ZZ-99", None, "PR-TRACE-TASK"),
        ("unknown task ID in head branch", "", "feature/T-ZZ-99", "PR-TRACE-TASK"),
        ("unknown task ID beside a valid P row", "T-ZZ-99 P01", None, "PR-TRACE-TASK"),
        ("out-of-range P row", "P20", None, "PR-TRACE-MISSING"),
        ("unlabelled non-audit slug", "example-node", None, "PR-TRACE-MISSING"),
    ]

    def run(root):
        head_file = root / "head.txt"
        head_ref = head_file.read_text(encoding="utf-8") if head_file.exists() else None
        return check((root / "body.txt").read_text(encoding="utf-8"),
                     root / "tasks.json", head_ref)

    return C.run_selftest(
        "check_pr_body_traceability",
        [(name, dict(tasks, **{"body.txt": body}, **({"head.txt": head} if head else {})), rule)
         for name, body, head, rule in cases],
        run)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=C.ROOT)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--body")
    parser.add_argument("--head-ref")
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
    head_ref = args.head_ref if args.head_ref is not None else os.environ.get("PR_HEAD_REF")
    try:
        findings = check(body, args.tasks or args.root / DEFAULT_TASKS, head_ref)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return C.usage_error(f"cannot read traceability inputs: {exc}")
    return C.report(
        findings,
        "PR body or head branch names a tasks.json task ID, node ID, or 09 P row "
        "(traceability only)",
        "pr-traceability")


if __name__ == "__main__":
    sys.exit(main())
