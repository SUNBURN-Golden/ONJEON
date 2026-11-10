#!/usr/bin/env python3
"""Reject tracked local credentials and virtual environments (Audit 5).

The finding asks for `.env*`, `*.pem`, `*.key` and `.venv/` ignore rules. The
repository-root `.gitignore` is outside this node's allowed_paths, so the same
outcome is enforced for tracked content at any depth: this gate fails CI when a
tracked path has one of those names, wherever it lives. The per-tree
`.gitignore` files (apps/, data/, infra/, packages/schemas/, packages/rules-engine/,
services/, tools/) keep locally generated files out of `git add` in those trees.

`infra/compose/.env.example` is the only allowed tracked `.env*` path. It is a
placeholder template whose password and key fields are empty, and
`infra/compose/tests/test_compose_static.py` keeps them empty.

Tracked paths are read from `git ls-files`, so this checks what a commit would
contain, not what happens to be untracked in one working copy.

Usage:
  python3 -I tools/check_tracked_secrets.py [--root DIR]
  python3 -I tools/check_tracked_secrets.py --selftest

Exit: 0 clean, 1 tracked sensitive paths, 2 usage or Git failure.
"""
import os
import subprocess
import sys
from pathlib import PurePosixPath

# The placeholder template is tracked on purpose; every other env-like path is not.
ALLOWED_TRACKED = {"infra/compose/.env.example"}


def kind(path):
    """Return the credential/virtual-environment kind for a repository-relative path."""
    parts = PurePosixPath(path.replace("\\", "/")).parts
    for part in parts:
        name = part.casefold()
        if name.startswith(".env"):
            return "environment file"
        if name.endswith(".pem"):
            return "PEM file"
        if name.endswith(".key"):
            return "key file"
        if name == ".venv":
            return "virtual environment"
    return None


def violations(paths):
    """Return (path, kind) for every tracked path that must not be committed."""
    found = []
    for raw in paths:
        path = raw.replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        if not path or path in ALLOWED_TRACKED:
            continue
        found_kind = kind(path)
        if found_kind:
            found.append((path, found_kind))
    return found


def tracked_paths(root):
    result = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"],
        capture_output=True, timeout=60,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip() or "git ls-files failed"
        raise OSError(detail)
    text = result.stdout.decode("utf-8", "surrogateescape")
    return [path for path in text.split("\0") if path]


def selftest():
    cases = [
        (".env", True),
        (".env.local", True),
        (".envrc", True),
        ("services/collect/.env.production", True),
        ("certificate.pem", True),
        ("infra/compose/server.pem", True),
        ("private.key", True),
        ("services/app/config/private.key", True),
        (".venv/pyvenv.cfg", True),
        ("services/app/.venv/bin/python", True),
        ("infra/compose/.env.example", False),
        ("README.md", False),
        ("services/app/env.example", False),
        ("services/app/certificate.pem.txt", False),
        ("services/app/private.key.example", False),
        ("services/app/.venv-notes/README.md", False),
    ]
    failed = 0
    for path, expected in cases:
        actual = bool(violations([path]))
        if actual != expected:
            print(f"FAIL selftest {path}: expected flagged={expected}, got {actual}")
            failed += 1
    if failed:
        return 1
    print(f"ok   selftest {len(cases)} paths")
    return 0


def usage(message=None):
    if message:
        print(f"check_tracked_secrets: {message}", file=sys.stderr)
    print("usage: check_tracked_secrets.py [--root DIR] [--selftest]", file=sys.stderr)
    return 2


def main(argv):
    root = os.getcwd()
    args = list(argv)
    if args[:1] == ["--selftest"]:
        return selftest() if len(args) == 1 else usage("--selftest takes no other arguments")
    if args[:1] == ["--root"]:
        if len(args) < 2:
            return usage("--root needs a directory")
        root = args[1]
        args = args[2:]
    if args:
        return usage(f"unexpected arguments: {' '.join(args)}")
    try:
        paths = tracked_paths(root)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"check_tracked_secrets: {exc}", file=sys.stderr)
        return 2
    found = violations(paths)
    for path, found_kind in found:
        print(f"FAIL {path}: tracked {found_kind} (Audit 5)")
    if not found:
        print("ok   no tracked credential or virtual-environment paths")
        return 0
    print(f"{len(found)} tracked path(s) must be removed or ignored before merge")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
