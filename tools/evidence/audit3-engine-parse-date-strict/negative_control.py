#!/usr/bin/env python3
"""Verify the date regressions detect the old permissive parser, offline.

Mutates only a temporary crate inside this worktree, never the real parser.
Run with python3 -I tools/evidence/audit3-engine-parse-date-strict/negative_control.py.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[2]
PACKAGE = ROOT / "packages/rules-engine"


def run(crate, label):
    command = [
        "cargo", "test", "--offline", "--manifest-path", str(crate / "Cargo.toml"),
        "--test", "date_format",
    ]
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=180,
        # Each control needs fresh artifacts: copy2 preserves source timestamps,
        # so Cargo can otherwise reuse a previous run's permissive parser even
        # for the strict baseline. Keep both targets inside the temporary crate.
        env={**os.environ, "CARGO_TARGET_DIR": str(crate / "target" / label)},
    )
    (EVIDENCE / f"{label}.log").write_text(
        f"Command: {' '.join(command)}\n{result.stdout}\nExit: {result.returncode}\n",
        encoding="utf-8",
    )
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="negative-control-", dir=EVIDENCE) as tmp:
        crate = Path(tmp)
        shutil.copytree(PACKAGE / "src", crate / "src")
        (crate / "tests").mkdir()
        shutil.copy2(PACKAGE / "tests/date_format.rs", crate / "tests/date_format.rs")
        (crate / "Cargo.toml").write_text(
            (PACKAGE / "Cargo.toml").read_text(encoding="utf-8") + "\n[workspace]\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        baseline = run(crate, "control-baseline")
        assert baseline.returncode == 0, baseline.stdout
        assert "4 passed; 0 failed" in baseline.stdout, baseline.stdout

        parser = crate / "src/date.rs"
        source = parser.read_text(encoding="utf-8")
        digits = '''        || !b[0..4].iter().all(u8::is_ascii_digit)
        || !b[5..7].iter().all(u8::is_ascii_digit)
        || !b[8..10].iter().all(u8::is_ascii_digit)
'''
        assert source.count(digits) == 1, "date parser changed; update the negative control"
        parser.write_text(source.replace(digits, ""), encoding="utf-8")
        mutant = run(crate, "control-permissive")
        assert mutant.returncode == 101, mutant.stdout
        assert "1 passed; 3 failed" in mutant.stdout, mutant.stdout
        for name in [
            "non_canonical_date_literals_are_rejected_at_load",
            "non_canonical_date_inputs_are_rejected_at_evaluation",
            "date_aliases_cannot_produce_alternate_rule_hashes",
        ]:
            assert f"test {name} ... FAILED" in mutant.stdout, mutant.stdout
        assert "2026-+1-+5" in mutant.stdout, mutant.stdout
        print("PASS: strict parser passes 4 tests; removing digit checks fails all 3 rejection regressions.")


if __name__ == "__main__":
    main()
