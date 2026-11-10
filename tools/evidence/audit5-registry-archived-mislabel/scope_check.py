#!/usr/bin/env python3
"""Verify this audit's changed paths, document links, parsing and untouched inputs.

Writes registry-snapshot.json beside this script and exits nonzero on any
violation. Read-only with respect to tracked files.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
AUDIT_DOC = ROOT / "docs/blueprint/audits/2026-11-10_registry_archived_mislabel.md"
EVIDENCE_README = HERE / "README.md"
SNAPSHOT = HERE / "registry-snapshot.json"

ALLOWED = (
    "docs/BLUEPRINT.md", "docs/blueprint/", "docs/decisions/", "packages/schemas/",
    "packages/rules-engine/", ".github/workflows/", "tools/", "services/", "apps/",
    "data/", "infra/", "README.md",
)
PROTECTED = (
    "docs/PRINCIPLES.md", "docs/data/",
    "docs/design/CONSUMER_FLOW_SPEC.md", "DECISION_REQUIRED.md",
)
UNCHANGED = (
    "tools/registry_normalize.py",
    "data/registry/insurers.csv",
    "data/registry/cooperatives_and_others.csv",
    "data/registry/excluded_or_historical.csv",
    "data/registry/access_log.csv",
)
PYTHON = (
    "tools/tests/test_registry_normalize.py",
    "tools/evidence/audit5-registry-archived-mislabel/mutation_check.py",
    "tools/evidence/audit5-registry-archived-mislabel/scope_check.py",
)

failures = []


def fail(message):
    failures.append(message)
    print(f"FAIL {message}")


def git_bytes(*args):
    return subprocess.run(("git", *args), cwd=ROOT,
                          capture_output=True, check=True).stdout


def changed_paths():
    status = git_bytes("-c", "core.quotepath=false", "status", "--porcelain").decode()
    return [line[3:] for line in status.splitlines() if line.strip()]


def check_paths():
    for path in changed_paths():
        if any(path == p or path.startswith(p) for p in PROTECTED):
            fail(f"PROTECTED {path}")
        elif any(path == p or path.startswith(p) for p in ALLOWED):
            print(f"ALLOWED {path}")
        else:
            fail(f"OUTSIDE_ALLOWED {path}")


def check_python():
    for path in PYTHON:
        compile((ROOT / path).read_text(encoding="utf-8"), path, "exec")
        print(f"PYTHON_PARSE_OK {path}")


def check_links():
    for document in (AUDIT_DOC, EVIDENCE_README):
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (document.parent / target.split("#")[0]).resolve()
            if resolved.exists():
                continue
            fail(f"BROKEN_LINK {document.relative_to(ROOT)} -> {target}")
        print(f"LOCAL_LINKS_OK {document.relative_to(ROOT)}")


def check_unchanged():
    snapshot = {}
    for path in UNCHANGED:
        working = (ROOT / path).read_bytes()
        head = git_bytes("show", f"HEAD:{path}")
        digest = hashlib.sha256(working).hexdigest()
        matches = working == head
        snapshot[path] = {"sha256": digest, "matches_HEAD": matches}
        if not matches:
            fail(f"CHANGED_AGAINST_HEAD {path}")
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    if not failures:
        print("REPOSITORY_NORMALIZER_AND_REGISTRY_UNCHANGED")
    print(f"SNAPSHOT_WRITTEN {SNAPSHOT.relative_to(ROOT)}")


def check_whitespace():
    output = git_bytes("diff", "--check").decode()
    if output.strip():
        fail(f"DIFF_CHECK\n{output}")
    else:
        print("DIFF_CHECK_OK")


if __name__ == "__main__":
    check_paths()
    check_python()
    check_links()
    check_unchanged()
    check_whitespace()
    if failures:
        print(f"FAILED {len(failures)} check(s)")
        sys.exit(1)
    print("PASS")
