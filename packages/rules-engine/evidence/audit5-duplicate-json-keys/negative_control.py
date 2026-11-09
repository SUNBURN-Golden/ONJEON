"""Run regression tests against fixed and last-wins parsers in an isolated crate."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[1]
ROOT = ENGINE.parents[1]
with tempfile.TemporaryDirectory(prefix="control-", dir=HERE) as temporary:
    crate = Path(temporary)
    # Cargo can reuse the preceding run's mutated library when copytree keeps
    # older source mtimes. Give each control run its own build directory so the
    # baseline always compiles the fixed source, even after a last-wins run.
    env = dict(os.environ, CARGO_TARGET_DIR=str(crate / "target"))
    shutil.copytree(ENGINE / "src", crate / "src")
    (crate / "tests").mkdir()
    shutil.copy2(ENGINE / "tests/duplicate_json_keys.rs", crate / "tests")
    (crate / "Cargo.toml").write_text(
        (ENGINE / "Cargo.toml").read_text() + "\n[workspace]\n", encoding="utf-8"
    )
    shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
    command = ["cargo", "test", "--manifest-path", str(crate / "Cargo.toml"),
               "--locked", "--offline", "--test", "duplicate_json_keys"]
    baseline = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
    (HERE / "control-fixed.log").write_text(baseline.stdout, encoding="utf-8")
    assert baseline.returncode == 0, baseline.stdout
    source = crate / "src/strict_json.rs"
    fixed = "serde_json::from_slice::<UniqueValue>(bytes).map(|v| v.0)"
    text = source.read_text(encoding="utf-8")
    assert text.count(fixed) == 1
    source.write_text(text.replace(fixed, "serde_json::from_slice::<Value>(bytes)"), encoding="utf-8")
    mutant = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    (HERE / "control-last-wins.log").write_text(mutant.stdout, encoding="utf-8")
    assert mutant.returncode == 101, mutant.stdout
    for test in [
        "every_top_level_key_is_unique_in_both_versions_and_all_publication_states",
        "repeated_constructor_keys_cannot_bypass_the_one_key_check",
        "arrays_unselected_branches_and_operator_parameters_are_checked_recursively",
        "input_names_and_escaped_equivalent_keys_are_checked_after_decoding",
    ]:
        assert f"test {test} ... FAILED" in mutant.stdout, mutant.stdout
    assert "2 passed; 4 failed" in mutant.stdout, mutant.stdout
    print("PASS: fixed parser: 6 passed; last-wins mutation: 4 expected failures, 2 controls passed")
