#!/usr/bin/env python3
"""Reject eager errors and error priority using an isolated crate in this worktree."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"
TEST = "reversed_days_between_errors_are_absorbed_only_by_input_decisions"


def run(crate, label, test_filter=None):
    command = [
        "cargo", "test", "--locked", "--offline", "--manifest-path",
        str(crate / "Cargo.toml"), "--test", "all_any_errors",
    ]
    if test_filter:
        command.append(test_filter)
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=180,
        env={**os.environ, "CARGO_TARGET_DIR": str(EVIDENCE / "target")},
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
        shutil.copy2(PACKAGE / "tests/all_any_errors.rs", crate / "tests/all_any_errors.rs")
        (crate / "Cargo.toml").write_text(
            (PACKAGE / "Cargo.toml").read_text(encoding="utf-8") + "\n[workspace]\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        baseline = run(crate, "control-baseline")
        assert baseline.returncode == 0, baseline.stdout
        assert "11 passed; 0 failed" in baseline.stdout, baseline.stdout

        evaluator = crate / "src/eval.rs"
        source = evaluator.read_text(encoding="utf-8")
        deferred = '''                let out = eval_deferred(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)
                    .and_then(|e| Ok((to_tri(&e, &format!("{path}[{i}]"))?, e)));'''
        eager = '''                let e = eval_deferred(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)?;
                let out = to_tri(&e, &format!("{path}[{i}]")).map(|t| (t, e));'''
        guard = "            if acc != decisive {"
        for label, original, replacement in [
            ("control-eager-error", deferred, eager),
            ("control-error-priority", guard, "            if true {"),
        ]:
            assert source.count(original) == 1, "evaluator changed; update the control"
            evaluator.write_text(source.replace(original, replacement), encoding="utf-8")
            mutant = run(crate, label, TEST)
            assert mutant.returncode == 101, mutant.stdout
            assert "0 passed; 1 failed" in mutant.stdout, mutant.stdout
            assert "Type {" in mutant.stdout, mutant.stdout
            assert "first date on or before the second" in mutant.stdout, mutant.stdout
            print(f"PASS: {label} rejected by {TEST} (reversed-date Type error, exit 101)")
        print("PASS: unchanged evaluator passes all 11 regressions; both mutations rejected.")


if __name__ == "__main__":
    main()
