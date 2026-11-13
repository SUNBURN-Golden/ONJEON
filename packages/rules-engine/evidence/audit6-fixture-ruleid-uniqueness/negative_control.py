#!/usr/bin/env python3
"""Exercise missing harness guards in isolated crates inside this worktree."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"


def run(crate, label, failed_names):
    command = ["cargo", "test", "--locked", "--offline", "--manifest-path",
               str(crate / "Cargo.toml"), "--test", "harness_guards"]
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=180,
        env={**os.environ, "CARGO_TARGET_DIR": str(ROOT / "target/audit6-harness-control-build")},
    )
    (EVIDENCE / f"{label}.log").write_text(
        f"Command: {' '.join(command)}\n{result.stdout}\nExit: {result.returncode}\n",
        encoding="utf-8",
    )
    assert result.returncode == (101 if failed_names else 0), result.stdout
    actual_failures = {
        line.split()[1] for line in result.stdout.splitlines()
        if line.startswith("test ") and line.endswith(" ... FAILED")
    }
    assert actual_failures == set(failed_names), result.stdout
    print(f"PASS: {label}: {len(failed_names)} expected failures detected")


def main():
    source = (PACKAGE / "tests/common/mod.rs").read_text(encoding="utf-8")
    duplicate_guard = '''            let entry = match out.entry(rule.rule_id().to_string()) {
                Entry::Vacant(entry) => entry,
                Entry::Occupied(entry) => {
                    panic!("{}: duplicate rule_id `{}`", p.display(), entry.key())
                }
            };
'''
    filename_guard = '''            assert_eq!(
                p.file_stem().and_then(|s| s.to_str()),
                Some(rule.rule_id()),
                "{}: file name must equal rule_id `{}` plus .json",
                p.display(),
                rule.rule_id()
            );
'''
    inventory_guards = [
        '    validate_rule_ids(&file, &shared_path, file["rule_id"].as_str());\n',
        '        validate_rule_ids(&extra, &supplement, file["rule_id"].as_str());\n',
        '        validate_rule_ids(&file, &supplement, file["rule_id"].as_str());\n',
    ]
    for guard in [duplicate_guard, filename_guard, *inventory_guards]:
        assert source.count(guard) == 1, "update mutation anchor"
    mutants = {
        "missing-duplicate-guard": (
            source.replace(duplicate_guard, "").replace(
                "            entry.insert(rule);",
                "            out.insert(rule.rule_id().to_string(), rule);"),
            ["duplicate_rule_id_is_reported_before_any_overwrite"],
        ),
        "missing-filename-guard": (
            source.replace(filename_guard, ""),
            ["rule_filename_must_match_its_id_even_without_a_collision",
             "duplicate_rule_ids_are_rejected_in_either_filename_order"],
        ),
        "missing-shared-inventory-guard": (
            source.replace(inventory_guards[0], ""),
            ["malformed_rule_inventories_are_rejected_in_shared_files_and_supplements",
             "rule_inventory_must_equal_case_selections_in_each_source_file",
             "supplements_cannot_hide_unexercised_shared_inventory_entries"],
        ),
        "missing-supplement-inventory-guard": (
            source.replace(inventory_guards[1], ""),
            ["malformed_rule_inventories_are_rejected_in_shared_files_and_supplements",
             "rule_inventory_must_equal_case_selections_in_each_source_file"],
        ),
        "missing-merged-inventory-guard": (
            source.replace(inventory_guards[2], ""),
            ["supplements_cannot_select_rules_outside_the_shared_inventory"],
        ),
    }
    (ROOT / "target").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audit6-harness-", dir=ROOT / "target") as tmp:
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
        run(crate, "baseline", [])
        for label, (mutant, failures) in mutants.items():
            harness.write_text(mutant, encoding="utf-8")
            run(crate, label, failures)
    assert (PACKAGE / "tests/common/mod.rs").read_text(encoding="utf-8") == source
    print("PASS: repository harness unchanged; isolated crates removed.")


if __name__ == "__main__":
    main()
