#!/usr/bin/env python3
"""Prove the range comparison tests catch the original money type erasure.

Run with python3 -I from any directory. Only a temporary crate inside this
worktree is mutated; the real engine and its fixtures are never rewritten.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
ENGINE = ROOT / "packages/rules-engine"


def main():
    original = (ENGINE / "src/rule.rs").read_text(encoding="utf-8")
    needle = "self.with_range(rounding == Rounding::Unspecified)"
    assert original.count(needle) == 1, "range inference implementation changed"
    with tempfile.TemporaryDirectory(prefix="negative-", dir=EVIDENCE) as directory:
        crate = Path(directory)
        shutil.copytree(ENGINE / "src", crate / "src")
        (crate / "tests").mkdir()
        shutil.copy2(ENGINE / "tests/range_comparisons.rs", crate / "tests")
        manifest = (ENGINE / "Cargo.toml").read_text(encoding="utf-8")
        (crate / "Cargo.toml").write_text(manifest + "\n[workspace]\n", encoding="utf-8")
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        environment = dict(os.environ, CARGO_TARGET_DIR=str(crate / "target"))

        def run():
            result = subprocess.run(
                ["cargo", "test", "--manifest-path", str(crate / "Cargo.toml"),
                 "--offline", "--test", "range_comparisons"],
                cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
            )
            print(result.stdout + result.stderr, flush=True)
            return result

        print("Unmodified temporary copy: all 10 tests must pass.", flush=True)
        baseline = run()
        assert baseline.returncode == 0 and "10 passed; 0 failed" in baseline.stdout
        # Recreate the finding: unspecified rounding is typed as exact money,
        # so a range-producing expression is admitted into comparisons.
        mutant = original.replace(needle, "{ let _ = rounding; self }")
        (crate / "src/rule.rs").write_text(mutant, encoding="utf-8")
        print("Money range inference removed: load rejection tests must fail.", flush=True)
        result = run()
        assert result.returncode == 101, "mutant unexpectedly passed"
        assert "range comparison must fail at load" in result.stdout
        assert "nested_and_unreachable_comparisons_fail_at_both_load_boundaries ... FAILED" in result.stdout
        assert "audit_p201_is_rejected_before_input_dependent_failure ... FAILED" in result.stdout
        assert "exact_money_threshold_comparisons_preserve_order_and_missing_inputs ... ok" in result.stdout
    assert (ENGINE / "src/rule.rs").read_text(encoding="utf-8") == original
    print("PASS: original type-erasure bug detected; real engine unchanged.")


if __name__ == "__main__":
    main()
