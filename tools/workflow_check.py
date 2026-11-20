#!/usr/bin/env python3
"""Check the repository's block-style workflows for read-only token permissions.

Any job-level policy must grant the same permissions, and every actions/checkout
step must disable credential persistence in its inputs. Uses only the Python
standard library.

    python3 tools/workflow_check.py [workflow.yml ...]   # default: .github/workflows/ci.yml
"""
import os
import re
import sys

DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".github", "workflows", "ci.yml")
CHECKOUT = re.compile(r"^\s*- uses:\s*actions/checkout@")
PERMISSIONS = re.compile(r"""(?:permissions|'permissions'|"permissions")\s*:""")
JOBS = re.compile(r"""(?:jobs|'jobs'|"jobs")\s*:""")


def _code(line):
    return line.split("#", 1)[0].rstrip()


def _indent(line):
    return len(line) - len(line.lstrip())


def _block(lines, start):
    """Yield indices of nonempty lines indented below the starting line."""
    indent = _indent(lines[start])
    for i in range(start + 1, len(lines)):
        if lines[i]:
            if _indent(lines[i]) <= indent:
                break
            yield i


def _children(lines, start):
    """Yield indices of direct children in a block mapping."""
    block = _block(lines, start)
    first = next(block, None)
    if first is not None:
        indent = _indent(lines[first])
        yield first
        yield from (i for i in block if _indent(lines[i]) == indent)


def _read_only_permissions(lines, start):
    body = [lines[i].strip() for i in _block(lines, start)]
    return PERMISSIONS.fullmatch(lines[start].strip()) is not None and body == ["contents: read"]


def check(text):
    """Return a list of problems (empty = hardened)."""
    lines = [_code(l) for l in text.splitlines()]
    problems = []

    perm = [i for i, line in enumerate(lines) if PERMISSIONS.match(line)]
    if not perm:
        problems.append("no top-level `permissions:` block (GITHUB_TOKEN gets the repo default)")
    elif len(perm) != 1:
        problems.append("multiple top-level `permissions:` declarations")
    elif not _read_only_permissions(lines, perm[0]):
        problems.append("top-level `permissions:` must be exactly `contents: read`")

    for i, line in enumerate(lines):
        if JOBS.fullmatch(line):
            for job in _children(lines, i):
                for field in _children(lines, job):
                    if PERMISSIONS.match(lines[field].lstrip()) and not _read_only_permissions(lines, field):
                        problems.append(f"line {field + 1}: job-level `permissions:` overrides the workflow policy")

    found = 0
    for i, line in enumerate(lines):
        if not CHECKOUT.match(line):
            continue
        found += 1
        inputs = [
            lines[field].strip()
            for child in _children(lines, i)
            if lines[child].strip() == "with:"
            for field in _children(lines, child)
            if lines[field].lstrip().startswith("persist-credentials:")
        ]
        if inputs != ["persist-credentials: false"]:
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
