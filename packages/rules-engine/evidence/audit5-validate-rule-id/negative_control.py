#!/usr/bin/env python3
"""Prove the identity tests detect removal of the existing rule_id guard."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
PACKAGE = ROOT / "packages/rules-engine"


def run(crate, label):
    command = [
        "cargo", "test", "--locked", "--offline", "--manifest-path",
        str(crate / "Cargo.toml"), "--test", "identity_evidence",
    ]
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=180,
        env={**os.environ, "CARGO_TARGET_DIR": str(ROOT / "target/audit5-id-control")},
    )
    (EVIDENCE / f"{label}.log").write_text(
        f"Command: {' '.join(command)}\n{result.stdout}\nExit: {result.returncode}\n",
        encoding="utf-8",
    )
    return result


def main():
    original = (PACKAGE / "src/rule.rs").read_bytes()
    with tempfile.TemporaryDirectory(prefix="negative-control-", dir=EVIDENCE) as tmp:
        crate = Path(tmp)
        shutil.copytree(PACKAGE / "src", crate / "src")
        (crate / "tests").mkdir()
        shutil.copy2(PACKAGE / "tests/identity_evidence.rs", crate / "tests")
        (crate / "Cargo.toml").write_text(
            (PACKAGE / "Cargo.toml").read_text(encoding="utf-8") + "\n[workspace]\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
        baseline = run(crate, "control-baseline")
        assert baseline.returncode == 0, baseline.stdout
        assert "7 passed; 0 failed" in baseline.stdout, baseline.stdout

        loader = crate / "src/rule.rs"
        source = loader.read_text(encoding="utf-8")
        guard = '''        if rule_id.trim().is_empty() {
            return Err(RuleError::at("rule_id", "must not be empty"));
        }
'''
        assert source.count(guard) == 1, "update rule_id guard mutation anchor"
        loader.write_text(source.replace(guard, ""), encoding="utf-8")
        mutant = run(crate, "control-missing-guard")
        assert mutant.returncode == 101, mutant.stdout
        assert "5 passed; 2 failed" in mutant.stdout, mutant.stdout
        for test in [
            "blank_rule_ids_are_rejected",
            "json_escaped_whitespace_rule_ids_are_rejected_after_decoding",
        ]:
            assert f"test {test} ... FAILED" in mutant.stdout, mutant.stdout
    assert (PACKAGE / "src/rule.rs").read_bytes() == original
    print("PASS: baseline 7/7; missing rule_id guard detected by both blank-ID tests.")
    print("PASS: production loader unchanged; temporary crate removed.")


if __name__ == "__main__":
    main()
