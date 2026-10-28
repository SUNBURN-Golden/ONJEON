"""Run invariant negative controls in disposable copies inside this worktree.

Usage: python3 -I tools/evidence/audit3-engine-invariant-tests-strengthen/negative_controls.py
The real fixtures/pins are never edited. Cargo needs its normal local cache.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    with tempfile.TemporaryDirectory(prefix="invariant-controls-", dir=ROOT / "tools") as tmp:
        sandbox = Path(tmp)
        engine = sandbox / "packages/rules-engine"
        engine.mkdir(parents=True)
        for name in ["Cargo.toml", "README.md"]:
            shutil.copy2(ROOT / "packages/rules-engine" / name, engine / name)
        for name in ["src", "tests"]:
            shutil.copytree(ROOT / "packages/rules-engine" / name, engine / name)
        fixtures = sandbox / "packages/fixtures/rules"
        shutil.copytree(ROOT / "packages/fixtures/rules", fixtures)
        (sandbox / "Cargo.toml").write_text(
            '[workspace]\nresolver = "2"\nmembers = ["packages/rules-engine"]\n'
        )
        shutil.copy2(ROOT / "Cargo.lock", sandbox / "Cargo.lock")
        env = dict(os.environ, CARGO_TARGET_DIR=str(sandbox / "target"))

        def run(label, suites, test_filter, expected_code, diagnostic=None):
            cmd = ["cargo", "test", "--offline", "-p", "onjeon-rules-engine"]
            for suite in suites:
                cmd.extend(["--test", suite])
            cmd.extend([test_filter, "--", "--exact"])
            result = subprocess.run(cmd, cwd=sandbox, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode != expected_code or (
                diagnostic is not None and diagnostic not in result.stdout
            ):
                raise AssertionError(f"{label}: unexpected result\n{result.stdout}")
            print(f"{label}: exit {result.returncode}, expected {expected_code}", flush=True)

        pins_path = fixtures / "real.content_hashes.json"
        original = pins_path.read_bytes()
        pins = json.loads(original)
        run("baseline pins", ["golden"], "real_rule_content_hashes_are_pinned", 0)
        for rule_id in pins["hashes"]:
            altered = json.loads(original)
            altered["hashes"][rule_id] = "0" * 64
            pins_path.write_text(json.dumps(altered))
            run(f"changed pin {rule_id}", ["golden"],
                "real_rule_content_hashes_are_pinned", 101, f"{rule_id}: rule_content_hash changed")
            del altered["hashes"][rule_id]
            pins_path.write_text(json.dumps(altered))
            run(f"missing pin {rule_id}", ["golden"],
                "real_rule_content_hashes_are_pinned", 101, "pinned set must equal")
        pins_path.write_bytes(original)

        # Removing both a rule and its pin must not make the audited inventory shrink.
        for rule_id in pins["hashes"]:
            rule_path = fixtures / "real" / f"{rule_id}.json"
            rule_bytes = rule_path.read_bytes()
            rule_path.unlink()
            altered = json.loads(original)
            del altered["hashes"][rule_id]
            pins_path.write_text(json.dumps(altered))
            for suite, test in [
                ("golden", "real_rule_content_hashes_are_pinned"),
                ("golden", "real_results_are_byte_identical_after_disk_reload_and_key_permutation"),
                ("soundness", "hiding_an_input_never_changes_a_definite_answer_on_real_rules"),
            ]:
                run(f"dropped rule {rule_id} / {test}", [suite], test, 101,
                    "real rule inventory must stay at seven audited rules")
            rule_path.write_bytes(rule_bytes)
        pins_path.write_bytes(original)
        print("PASS: baseline + 14 pin mutations + 21 rule-inventory checks")


if __name__ == "__main__":
    main()
