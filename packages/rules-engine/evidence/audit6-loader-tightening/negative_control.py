#!/usr/bin/env python3
"""Reintroduce each audit finding in a disposable crate inside this worktree."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"
TESTS = ["loader_tightening", "date_format", "identity_evidence", "immutable_rule_doctests"]


def run(crate, label, failures):
    command = ["cargo", "test", "--locked", "--offline", "--manifest-path", str(crate / "Cargo.toml")]
    for name in TESTS:
        command.extend(["--test", name])
    command.append("--no-fail-fast")
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=240, env={**os.environ, "CARGO_TARGET_DIR": str(ROOT / "target/audit6-loader-control")},
    )
    report = result.stdout.replace(str(ROOT), "<worktree>")
    (EVIDENCE / f"control-{label}.log").write_text(
        f"Command: {' '.join(command).replace(str(ROOT), '<worktree>')}\n{report}\nExit: {result.returncode}\n",
        encoding="utf-8",
    )
    actual = {
        line.split()[1] for line in report.splitlines()
        if line.startswith("test ") and line.endswith(" ... FAILED")
    }
    assert result.returncode == (101 if failures else 0), report
    assert actual == set(failures), report
    print(f"PASS: {label}: {len(failures)} expected failures detected", flush=True)


def main():
    original = {name: (PACKAGE / "src" / name).read_text(encoding="utf-8")
                for name in ["rule.rs", "date.rs"]}
    rule = original["rule.rs"]
    kind_guard = '''        if let Some(kind) = obj.get("example_kind") {
            if !kind.as_str().is_some_and(|s| EXAMPLE_KINDS.contains(&s)) {
                return Err(RuleError::at(
                    "example_kind",
                    format!("must be one of {}", EXAMPLE_KINDS.join("|")),
                ));
            }
        }
'''
    id_guard = '''        if rule_id.trim().is_empty() {
            return Err(RuleError::at("rule_id", "must not be empty"));
        }
'''
    strict_parse = "let crate::strict_json::StrictValue(v) = serde_json::from_str(s)"
    doctest = "/// rule.content_hash = String::new(); // private: does not compile"
    digit_guards = [f"        || !b[{a}..{b}].iter().all(u8::is_ascii_digit)\n"
                    for a, b in [(0, 4), (5, 7), (8, 10)]]
    for anchor in [kind_guard, id_guard, strict_parse, doctest]:
        assert rule.count(anchor) == 1, f"update mutation anchor: {anchor}"
    for anchor in digit_guards:
        assert original["date.rs"].count(anchor) == 1, "update date mutation anchor"
    permissive_date = original["date.rs"]
    for anchor in digit_guards:
        permissive_date = permissive_date.replace(anchor, "")

    mutants = {
        "duplicate-overwrite": ({"rule.rs": rule.replace(strict_parse, "let v: J = serde_json::from_str(s)")}, [
            "duplicate_top_level_members_fail_even_when_identical_or_last_value_is_valid",
            "duplicate_nested_members_fail_in_inputs_expressions_parameters_and_dead_branches",
            "duplicate_keys_are_compared_after_json_string_decoding",
        ]),
        "unchecked-example-kind": ({"rule.rs": rule.replace(kind_guard, "")}, [
            "example_kind_rejects_wrong_types_blank_and_unknown_values",
        ]),
        "blank-rule-id": ({"rule.rs": rule.replace(id_guard, "")}, [
            "blank_rule_ids_are_rejected",
            "json_escaped_whitespace_rule_ids_are_rejected_after_decoding",
        ]),
        "signed-dates": ({"date.rs": permissive_date}, [
            "non_canonical_date_literals_are_rejected_at_load",
            "non_canonical_date_inputs_are_rejected_at_evaluation",
            "date_aliases_cannot_produce_alternate_rule_hashes",
        ]),
        "unrelated-doctest-error": ({"rule.rs": rule.replace(doctest, "/// let _: UnrelatedDoctestType;")}, [
            "immutable_rule_doctests_fail_only_on_private_field_access",
        ]),
    }
    (ROOT / "target").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audit6-loader-", dir=ROOT / "target") as tmp:
        crate = Path(tmp)
        shutil.copytree(PACKAGE / "src", crate / "src")
        (crate / "tests").mkdir()
        for name in TESTS:
            shutil.copy2(PACKAGE / f"tests/{name}.rs", crate / "tests")
        (crate / "Cargo.toml").write_text((PACKAGE / "Cargo.toml").read_text() + "\n[workspace]\n")
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        run(crate, "baseline", [])
        for label, (sources, failures) in mutants.items():
            for name, source in original.items():
                (crate / "src" / name).write_text(sources.get(name, source), encoding="utf-8")
            run(crate, label, failures)
    for name, source in original.items():
        assert (PACKAGE / "src" / name).read_text(encoding="utf-8") == source
    print("PASS: production sources unchanged; disposable crate removed.")


if __name__ == "__main__":
    main()
