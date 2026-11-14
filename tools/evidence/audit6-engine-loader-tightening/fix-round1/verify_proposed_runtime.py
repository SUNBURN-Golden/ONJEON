#!/usr/bin/env python3
"""Verify the proposed runtime patch in a disposable crate; never edit runtime sources."""
import difflib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUNTIME = ROOT / 'packages/twin-runtime'
SOURCE = RUNTIME / 'src/input_stage.rs'
OLD = 'let mut v: Value = serde_json::from_slice(bytes).map_err(|e| format!("invalid JSON: {e}"))?;'
NEW = '''let mut v = onjeon_rules_engine::strict_json::from_slice(bytes)
        .map_err(|e| format!("invalid JSON: {e}"))?;'''
original = SOURCE.read_text()
assert original.count(OLD) == 1
proposed = original.replace(OLD, NEW).replace(
    '/// without the key declares no outside inputs.',
    '/// without the key declares no outside inputs. Duplicate keys are rejected throughout\n'
    '/// the artifact before any declaration is extracted or any rule is evaluated.'
)
tests = (HERE / 'runtime_tests.rs').read_text()
patch = ''.join(difflib.unified_diff(original.splitlines(True), proposed.splitlines(True),
    fromfile='a/packages/twin-runtime/src/input_stage.rs', tofile='b/packages/twin-runtime/src/input_stage.rs'))
patch += ''.join(difflib.unified_diff([], tests.splitlines(True),
    fromfile='/dev/null', tofile='b/packages/twin-runtime/tests/artifact_strict_json.rs'))
(HERE / 'proposed-runtime.patch').write_text(patch)


def run(crate, label, expected_failures):
    command = ['cargo', 'test', '--manifest-path', str(crate / 'Cargo.toml'), '--locked', '--offline', '--test', 'artifact_strict_json']
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, 'CARGO_TARGET_DIR': str(ROOT / 'target/audit6-runtime-proposal')}, timeout=240)
    report = result.stdout.replace(str(ROOT), '<worktree>')
    (HERE / f'{label}.log').write_text(f'Command: {command}\n{report}\nExit: {result.returncode}\n')
    failed = {line.split()[1] for line in report.splitlines() if line.startswith('test ') and line.endswith(' ... FAILED')}
    assert result.returncode == (101 if expected_failures else 0), report
    assert failed == set(expected_failures), report
    print(f'{label}: {len(expected_failures)} expected failures; verified', flush=True)


with tempfile.TemporaryDirectory(prefix='audit6-runtime-', dir=ROOT / 'target') as temp:
    packages = Path(temp) / 'packages'
    packages.mkdir()
    crate = packages / 'twin-runtime'
    shutil.copytree(RUNTIME, crate, ignore=shutil.ignore_patterns('target'))
    for name in ['ontology', 'rules-engine', 'schemas']:
        (packages / name).symlink_to(ROOT / 'packages' / name, target_is_directory=True)
    (crate / 'Cargo.toml').write_text((crate / 'Cargo.toml').read_text() + '\n[workspace]\n')
    shutil.copy2(ROOT / 'Cargo.lock', crate / 'Cargo.lock')
    subprocess.run(['cargo', 'generate-lockfile', '--offline', '--manifest-path', str(crate / 'Cargo.toml')], cwd=ROOT, check=True)
    (crate / 'tests/artifact_strict_json.rs').write_text(tests)
    run(crate, 'before-runtime', [
        'artifact_duplicates_fail_before_declaration_extraction',
        'duplicate_artifacts_stop_requests_before_fill_or_engine',
        'case_runner_rejects_duplicate_artifacts_with_zero_engine_calls',
    ])
    (crate / 'src/input_stage.rs').write_text(proposed)
    run(crate, 'proposed-runtime', [])
assert SOURCE.read_text() == original
print('Runtime sources unchanged; proposed patch verified in disposable crate.', flush=True)
