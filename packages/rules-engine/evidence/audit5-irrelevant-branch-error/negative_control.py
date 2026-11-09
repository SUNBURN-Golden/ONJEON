#!/usr/bin/env python3
"""Restore each reported defect in an isolated crate inside this worktree."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"


def run(crate, label, test_filter=None):
    command = [
        "cargo", "test", "--locked", "--offline", "--manifest-path",
        str(crate / "Cargo.toml"), "--test", "irrelevant_branch_errors",
    ]
    if test_filter:
        command.append(test_filter)
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=180,
        env={**os.environ, "CARGO_TARGET_DIR": str(ROOT / "target/audit5-control")},
    )
    (EVIDENCE / f"{label}.log").write_text(
        f"Command: {' '.join(command)}\n{result.stdout}\nExit: {result.returncode}\n",
        encoding="utf-8",
    )
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="negative-control-", dir=EVIDENCE) as tmp:
        crate = Path(tmp) / "packages/rules-engine"
        shutil.copytree(PACKAGE / "src", crate / "src")
        (crate / "tests").mkdir()
        shutil.copy2(PACKAGE / "tests/irrelevant_branch_errors.rs", crate / "tests")
        fixture = Path(tmp) / "packages/fixtures/rules/real"
        fixture.mkdir(parents=True)
        shutil.copy2(
            ROOT / "packages/fixtures/rules/real/kyobo-1995-cancer-waiting.json", fixture
        )
        (crate / "Cargo.toml").write_text(
            (PACKAGE / "Cargo.toml").read_text(encoding="utf-8") + "\n[workspace]\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        baseline = run(crate, "control-baseline")
        assert baseline.returncode == 0, baseline.stdout
        assert "2 passed; 0 failed" in baseline.stdout, baseline.stdout

        evaluator = crate / "src/eval.rs"
        source = evaluator.read_text(encoding="utf-8")
        logical_old = '''                let out = eval_deferred(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)
                    .and_then(|e| Ok((to_tri(&e, &format!("{path}[{i}]"))?, e)));'''
        logical_bad = '''                let e = eval_deferred(c, &format!("{path}.{}[{i}]", expr.op_name()), ctx)?;
                let out = to_tri(&e, &format!("{path}[{i}]")).map(|t| (t, e));'''
        amount_old = '''                let amt = eval_deferred(&self.amount, "amount", &mut ctx)
                    .unwrap_or_else(|_| Ev::unknown(BTreeSet::new()));'''
        amount_bad = '''                let amt = eval_deferred(&self.amount, "amount", &mut ctx)?;'''
        for label, old, bad, test_filter, error in [
            ("control-eager-logical", logical_old, logical_bad,
             "kyobo_waiting_exclusion_survives_an_out_of_range_waiting_date", "DateOutOfRange"),
            ("control-eager-amount", amount_old, amount_bad,
             "logical_and_amount_errors_preserve_unknown_eligibility_together", "Overflow"),
        ]:
            assert source.count(old) == 1, f"update mutation anchor: {label}"
            evaluator.write_text(source.replace(old, bad), encoding="utf-8")
            mutant = run(crate, label, test_filter)
            assert mutant.returncode == 101, mutant.stdout
            assert "0 passed; 1 failed" in mutant.stdout, mutant.stdout
            assert error in mutant.stdout, mutant.stdout
            print(f"PASS: {label} rejected by {test_filter} ({error})", flush=True)
        print("PASS: baseline 2/2; both reported defects detected; real evaluator unchanged.")


if __name__ == "__main__":
    main()
