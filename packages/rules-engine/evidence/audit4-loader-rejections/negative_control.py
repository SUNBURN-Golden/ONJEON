#!/usr/bin/env python3
"""Run the Audit 4 loader regressions against isolated, weakened guards.

Only temporary copies inside this worktree are changed. Each mutant starts from
the original loader and must compile, then fail the named regression test.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"

# label, test, exact original guard, weaker guard
MUTATIONS = [
    ("calendar", "metadata_values_do_not_silently_default",
     'if cal.as_str() != Some("Asia/Seoul") {', 'if false {'),
    ("blank-release", "metadata_values_do_not_silently_default",
     'Some(J::String(r)) if !r.trim().is_empty() => Some(r.clone()),',
     'Some(J::String(r)) => Some(r.clone()),'),
    ("rounding-extra-key", "every_rounding_operator_rejects_invalid_parameters_and_accepts_all_allowed_pairs",
     'if params.len() != 2 {\n        return Err(RuleError::at(p, "only rounding and unit are allowed"));',
     'if false {\n        return Err(RuleError::at(p, "only rounding and unit are allowed"));'),
    ("rounding-unit", "every_rounding_operator_rejects_invalid_parameters_and_accepts_all_allowed_pairs",
     'Some(u @ (1 | 10 | 100 | 1000)) => u,',
     'Some(u @ (1 | 2 | 10 | 100 | 1000)) => u,'),
    ("inclusivity-extra-key", "days_between_requires_boolean_inclusivity_and_a_closed_parameter_object",
     'if params.len() != 2 {\n                        return Err(RuleError::at(&p, "only inclusive_start and inclusive_end are allowed"));',
     'if false {\n                        return Err(RuleError::at(&p, "only inclusive_start and inclusive_end are allowed"));'),
    ("arity-upper-bound", "array_operator_arity_and_container_guards_reject_both_sides_of_the_bounds",
     'if a.len() < min || a.len() > max {', 'if a.len() < min {'),
    ("band-upper-bound", "anniversary_band_rejects_malformed_tables_and_boundary_containers",
     'if table.is_empty() || table.len() > 64 {', 'if table.is_empty() {'),
    ("operator-extra-key", "expression_objects_and_if_objects_have_exact_shapes",
     'if map.len() != 1 {', 'if map.is_empty() {'),
    ("version-gate", "every_rule_02_operator_is_gated_independently_of_input_declarations",
     '"max_over" if !inputs.v02 => {', '"max_over" if false => {'),
]


def run(crate, label, test=None):
    command = [
        "cargo", "test", "--locked", "--offline", "--manifest-path",
        str(crate / "Cargo.toml"), "--test", "loader_rejections",
    ]
    if test:
        command += [test, "--", "--exact"]
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=180,
        # A fresh target per temporary crate prevents reusing a prior run's
        # mutant when copy2 preserves the original source timestamps.
        env={**os.environ, "CARGO_TARGET_DIR": str(crate / "target")},
    )
    (EVIDENCE / f"control-{label}.log").write_text(
        f"Command: {' '.join(command)}\n{result.stdout}\nExit: {result.returncode}\n",
        encoding="utf-8",
    )
    return result


def main():
    source = (PACKAGE / "src/rule.rs").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="loader-control-", dir=ROOT / "target") as tmp:
        crate = Path(tmp)
        shutil.copytree(PACKAGE / "src", crate / "src")
        (crate / "tests").mkdir()
        shutil.copy2(PACKAGE / "tests/loader_rejections.rs", crate / "tests/loader_rejections.rs")
        (crate / "Cargo.toml").write_text(
            (PACKAGE / "Cargo.toml").read_text(encoding="utf-8") + "\n[workspace]\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        baseline = run(crate, "baseline")
        assert baseline.returncode == 0, baseline.stdout
        assert "13 passed; 0 failed" in baseline.stdout, baseline.stdout
        print("PASS: unchanged loader passes all 13 tests", flush=True)
        for label, test, old, new in MUTATIONS:
            assert source.count(old) == 1, f"{label}: loader changed; update the exact mutation"
            (crate / "src/rule.rs").write_text(source.replace(old, new), encoding="utf-8")
            mutant = run(crate, label, test)
            assert mutant.returncode == 101, mutant.stdout
            assert f"test {test} ... FAILED" in mutant.stdout, mutant.stdout
            assert "0 passed; 1 failed" in mutant.stdout, mutant.stdout
            print(f"PASS: {label} compiled and failed {test}", flush=True)
    assert (PACKAGE / "src/rule.rs").read_text(encoding="utf-8") == source
    print("PASS: all 9 weakened guards detected; repository loader unchanged")


if __name__ == "__main__":
    main()
