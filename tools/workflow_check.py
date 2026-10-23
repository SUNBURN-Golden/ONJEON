#!/usr/bin/env python3
"""ci.yml token hardening check (Audit 1): top-level `permissions: {contents: read}` and
`persist-credentials: false` on every actions/checkout step. Stdlib only, line-based on purpose
(no YAML dependency in CI); it understands only the layout this repo's workflows use.

    python3 tools/workflow_check.py [workflow.yml ...]   # default: .github/workflows/ci.yml
"""
import os
import re
import sys

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".github", "workflows", "ci.yml")
CHECKOUT = re.compile(r"^(\s*)- uses:\s*actions/checkout@")


def _code(line):
    return line.split("#", 1)[0].rstrip()


def check(text):
    """Return a list of problems (empty = hardened)."""
    lines = [_code(l) for l in text.splitlines()]
    problems = []

    perm = [i for i, l in enumerate(lines) if re.match(r"^permissions:\s*$", l)]
    if not perm:
        problems.append("no top-level `permissions:` block (GITHUB_TOKEN gets the repo default)")
    else:
        body = []
        for l in lines[perm[0] + 1:]:
            if l.strip() and not l.startswith(" "):
                break
            if l.strip():
                body.append(l.strip())
        if body != ["contents: read"]:
            problems.append(f"top-level `permissions:` must be exactly `contents: read`, found {body}")

    found = 0
    for i, l in enumerate(lines):
        m = CHECKOUT.match(l)
        if not m:
            continue
        found += 1
        indent = len(m.group(1))
        step = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            step.append(nxt.strip())
        if "persist-credentials: false" not in step:
            problems.append(f"line {i + 1}: actions/checkout without `persist-credentials: false`")
    if not found:
        problems.append("no actions/checkout step found (check is looking at the wrong file?)")
    return problems


def main(argv):
    paths = argv or [DEFAULT]
    bad = 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            problems = check(f.read())
        for msg in problems:
            print(f"FAIL {os.path.normpath(p)}: {msg}")
        bad += len(problems)
        if not problems:
            print(f"ok   {os.path.normpath(p)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
