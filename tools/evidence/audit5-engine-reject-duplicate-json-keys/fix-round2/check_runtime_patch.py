"""Prepare and execute the runtime patch without modifying out-of-scope files."""
import difflib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUNTIME = ROOT / "packages/twin-runtime"
source = RUNTIME / "src/input_stage.rs"
old_source = source.read_text(encoding="utf-8")
new_source = old_source.replace(
    "use onjeon_rules_engine::Rule;",
    "use onjeon_rules_engine::{parse_rule_json, Rule};",
).replace(
    "/// without the key declares no outside inputs.",
    "/// without the key declares no outside inputs. Duplicate JSON keys anywhere in the\n"
    "/// artifact are rejected before extracting the declaration or hashing the DSL.",
).replace(
    'let mut v: Value = serde_json::from_slice(bytes).map_err(|e| format!("invalid JSON: {e}"))?;',
    "let mut v = parse_rule_json(bytes).map_err(|e| e.to_string())?;",
)
assert new_source != old_source, "expected the unfixed runtime loader"
test = RUNTIME / "tests/input_stage.rs"
old_test = test.read_text(encoding="utf-8")
new_test = old_test + "\n" + (HERE / "runtime-regressions.rs").read_text(encoding="utf-8")
env = dict(os.environ, CARGO_TARGET_DIR=str(ROOT / "target/audit5-runtime-control"))
with tempfile.TemporaryDirectory(prefix="runtime-control-", dir=HERE) as temporary:
    mirror = Path(temporary)
    crate = mirror / "packages/twin-runtime"
    shutil.copytree(RUNTIME / "src", crate / "src")
    shutil.copytree(RUNTIME / "tests", crate / "tests")
    # copy2 preserves old mtimes; a reused target directory must rebuild the
    # baseline library after the preceding run compiled the patched version.
    for rust_file in (crate / "src").rglob("*.rs"):
        rust_file.touch()
    shutil.copytree(ROOT / "packages/ontology/tests/golden", mirror / "packages/ontology/tests/golden")
    manifest = (RUNTIME / "Cargo.toml").read_text(encoding="utf-8")
    for dependency in ["schemas", "ontology", "rules-engine"]:
        manifest = manifest.replace(f'"../{dependency}"', f'"{ROOT / "packages" / dependency}"')
    (crate / "Cargo.toml").write_text(manifest + "\n[workspace]\n", encoding="utf-8")
    shutil.copy2(ROOT / "Cargo.lock", crate / "Cargo.lock")
    subprocess.run(["cargo", "generate-lockfile", "--manifest-path", str(crate / "Cargo.toml"),
                    "--offline"], env=env, check=True)
    (crate / "tests/input_stage.rs").write_text(new_test, encoding="utf-8")
    command = ["cargo", "test", "--manifest-path", str(crate / "Cargo.toml"),
               "--locked", "--offline", "--test", "input_stage", "artifact_"]
    baseline = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
    (HERE / "runtime-unfixed.log").write_text(baseline.stdout, encoding="utf-8")
    assert baseline.returncode == 101, baseline.stdout
    assert "2 passed; 2 failed" in baseline.stdout, baseline.stdout
    (crate / "src/input_stage.rs").write_text(new_source, encoding="utf-8")
    subprocess.run(["rustfmt", "--edition", "2021", str(crate / "tests/input_stage.rs")], check=True)
    new_test = (crate / "tests/input_stage.rs").read_text(encoding="utf-8")
    fixed = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True)
    (HERE / "runtime-fixed.log").write_text(fixed.stdout, encoding="utf-8")
    assert fixed.returncode == 0, fixed.stdout
    assert "4 passed; 0 failed" in fixed.stdout, fixed.stdout
    full = subprocess.run(command[:command.index("--test")], env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    (HERE / "runtime-full.log").write_text(full.stdout, encoding="utf-8")
    assert full.returncode == 0, full.stdout

patch = ""
for path, before, after in [(source, old_source, new_source), (test, old_test, new_test)]:
    relative = path.relative_to(ROOT)
    patch += f"diff --git a/{relative} b/{relative}\n"
    patch += "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile=f"a/{relative}", tofile=f"b/{relative}"))
(HERE / "runtime.patch").write_text(patch, encoding="utf-8")
print("PASS: unfixed runtime: 2 expected failures, 2 controls passed; patched runtime: 4 passed")
