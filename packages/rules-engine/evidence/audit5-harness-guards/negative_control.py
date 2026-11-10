#!/usr/bin/env python3
"""Verify that the harness regressions detect each missing guard in isolated crates."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"


def run(crate, label, passed, failed):
    command = ["cargo", "test", "--locked", "--offline", "--manifest-path",
               str(crate / "Cargo.toml"), "--test", "harness_guards"]
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=180,
        env={**os.environ, "CARGO_TARGET_DIR": str(ROOT / "target/harness-control-build")},
    )
    (EVIDENCE / f"{label}.log").write_text(
        f"Command: {' '.join(command)}\n{result.stdout}\nExit: {result.returncode}\n",
        encoding="utf-8",
    )
    assert result.returncode == (101 if failed else 0), result.stdout
    assert f"{passed} passed; {failed} failed" in result.stdout, result.stdout
    return result.stdout


def main():
    source = (PACKAGE / "tests/common/mod.rs").read_text(encoding="utf-8")
    filename_guard = '''            assert_eq!(
                p.file_stem().and_then(|s| s.to_str()),
                Some(rule.rule_id()),
                "{}: file name must equal rule_id `{}` plus .json",
                p.display(),
                rule.rule_id()
            );
'''
    case_guards = [
        "    validate_case_keys(&file, uses_base, &shared_path);\n",
        "        validate_case_keys(&extra, uses_base, &supplement);\n",
    ]
    for guard in [filename_guard, *case_guards]:
        assert source.count(guard) == 1, "update mutation anchor"
    (ROOT / "target").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="harness-control-", dir=ROOT / "target") as tmp:
        scratch = Path(tmp)
        crate = scratch / "packages/rules-engine"
        shutil.copytree(PACKAGE / "src", crate / "src")
        shutil.copytree(PACKAGE / "tests/common", crate / "tests/common")
        shutil.copy2(PACKAGE / "tests/harness_guards.rs", crate / "tests")
        shutil.copytree(ROOT / "packages/fixtures/rules", scratch / "packages/fixtures/rules")
        (crate / "Cargo.toml").write_text(
            (PACKAGE / "Cargo.toml").read_text(encoding="utf-8") + "\n[workspace]\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        harness = crate / "tests/common/mod.rs"
        harness.write_text(source, encoding="utf-8")
        run(crate, "control-baseline", 7, 0)

        harness.write_text(source.replace(filename_guard, ""), encoding="utf-8")
        output = run(crate, "control-missing-filename-guard", 5, 2)
        for name in ["rule_filename_must_match_its_id_even_without_a_collision",
                     "duplicate_rule_ids_are_rejected_in_either_filename_order"]:
            assert f"test {name} ... FAILED" in output, output

        mutant = source
        for guard in case_guards:
            mutant = mutant.replace(guard, "")
        harness.write_text(mutant, encoding="utf-8")
        output = run(crate, "control-missing-case-guards", 4, 3)
        for name in ["unknown_real_case_keys_are_rejected_in_shared_files_and_supplements",
                     "unknown_synthetic_case_keys_are_rejected_in_shared_files_and_supplements",
                     "malformed_overrides_cannot_silently_use_base_inputs"]:
            assert f"test {name} ... FAILED" in output, output
    assert (PACKAGE / "tests/common/mod.rs").read_text(encoding="utf-8") == source
    print("PASS: baseline 7/7; missing filename guard detected by 2 tests; missing case guards by 3.")
    print("PASS: repository harness unchanged; isolated crates removed.")


if __name__ == "__main__":
    main()
