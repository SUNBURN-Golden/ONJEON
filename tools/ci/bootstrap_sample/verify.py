#!/usr/bin/env python3
"""Record the bootstrap sample and existing safety checks without hiding failures."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
COMMANDS = [
    ["bash", "-n", "tools/ci/bootstrap_sample/run.sh"],
    ["python3", "-I", "-m", "unittest", "discover", "-s", "tools/ci/bootstrap_sample", "-p", "test_*.py", "-v"],
    ["python3", "-I", "tools/ci/bootstrap_sample/prune.py", "--selftest"],
    ["python3", "-I", "tools/ci/check_bootstrap.py"],
    ["python3", "-I", "tools/ci/check_leak.py"],
    ["python3", "-I", "tools/ci/check_skeleton.py"],
    ["python3", "-I", "tools/ci/check_deps.py"],
    ["python3", "-I", "-m", "unittest", "discover", "-s", "tools/ci/tests", "-v"],
    ["bash", "tools/ci/bootstrap_sample/run.sh", "--task", "T-TW-01"],
]


def main():
    reports = HERE / "reports"
    reports.mkdir(exist_ok=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    failed = 0
    with (reports / "verification.log").open("w", encoding="utf-8") as log:
        def record(text):
            print(text, end="", flush=True)
            log.write(text)
            log.flush()
        record(f"T-CT-07 verification; worktree HEAD: {sha}\n")
        record("author role: implementation agent; execution path: CLI; independent review: pending\n")
        for command in COMMANDS:
            record("\n$ " + " ".join(command) + "\n")
            result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            record(result.stdout)
            record(f"exit: {result.returncode}\n")
            failed += result.returncode != 0
        record(f"\nverification: {'FAIL' if failed else 'PASS'}; failed commands: {failed}\n")
    return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main())
