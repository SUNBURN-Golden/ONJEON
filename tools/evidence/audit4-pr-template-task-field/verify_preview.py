"""Validate the reviewable patch without writing outside the node's allowed paths.

This checks a proposed template, not the installed GitHub PR template.
"""
import difflib
import importlib.util
import subprocess
import unittest
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = next(parent for parent in EVIDENCE.parents if (parent / ".git").exists())
TEMPLATE_PATH = ".github/pull_request_template.md"
TEST_PATH = "tools/tests/test_pr_template_traceability.py"


def main():
    original = (ROOT / TEMPLATE_PATH).read_text(encoding="utf-8")
    preview = (EVIDENCE / "pull_request_template.preview.md").read_text(encoding="utf-8")
    regression = EVIDENCE / "test_pr_template_traceability.py"
    expected_patch = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), preview.splitlines(keepends=True),
        fromfile="a/" + TEMPLATE_PATH, tofile="b/" + TEMPLATE_PATH))
    expected_patch += "".join(difflib.unified_diff(
        [], regression.read_text(encoding="utf-8").splitlines(keepends=True),
        fromfile="/dev/null", tofile="b/" + TEST_PATH))
    # Git accepts an empty context line without a whitespace-only prefix.
    expected_patch = "".join("\n" if line == " \n" else line
                             for line in expected_patch.splitlines(keepends=True))
    patch = EVIDENCE / "pull_request_template.patch"
    if patch.read_text(encoding="utf-8") != expected_patch:
        raise SystemExit("patch differs from the proposed template/regression test")
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=ROOT, check=True)

    spec = importlib.util.spec_from_file_location("test_pr_template_traceability", regression)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TEMPLATE = EVIDENCE / "pull_request_template.preview.md"
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    print("Proposed-template tests only; the installed PR template is unchanged.", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
