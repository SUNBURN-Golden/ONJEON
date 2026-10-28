#!/usr/bin/env python3
"""Prove the Audit 3 pair regressions reject eager error propagation, offline.

Only a temporary crate inside this evidence directory is mutated. The real
evaluator and fixtures are never changed. Run with python3 -I <this file>.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"


def run(crate, label, test_filter=""):
    command = [
        "cargo", "test", "--offline", "--manifest-path", str(crate / "Cargo.toml"),
        "--test", "all_any_errors",
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
        assert "7 passed; 0 failed" in baseline.stdout, baseline.stdout

        evaluator = crate / "src/eval.rs"
        source = evaluator.read_text(encoding="utf-8")
        old = '''                let out = eval_deferred(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)
                    .and_then(|e| Ok((to_tri(&e, &format!("{path}[{i}]"))?, e)));'''
        eager = '''                let e = eval_deferred(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)?;
                let out = to_tri(&e, &format!("{path}[{i}]")).map(|t| (t, e));'''
        assert source.count(old) == 1, "all/any evaluation changed; update the negative control"
        evaluator.write_text(source.replace(old, eager), encoding="utf-8")
        mutant = run(crate, "control-eager-error", "absorbs_runtime_errors_in_both_versions")
        assert mutant.returncode == 101, mutant.stdout
        assert "0 passed; 2 failed" in mutant.stdout, mutant.stdout
        assert "DateOutOfRange" in mutant.stdout, mutant.stdout
        print("PASS: unchanged evaluator passes all 7 tests; eager `?` fails both pair regressions.")


if __name__ == "__main__":
    main()
