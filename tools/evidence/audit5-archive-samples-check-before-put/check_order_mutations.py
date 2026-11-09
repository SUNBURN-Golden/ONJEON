"""Reject upload-before-check and cache-reread mutations without editing source.

Run from the worktree root with Python 3. Exit 0 requires every selected test
to reject its mutant, with no skips. Unittest failures below are intentional.
"""
import inspect
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_source_archive_commands as tests

sa = tests.sa
source = inspect.getsource(sa.cmd_archive_samples)
validation = '''        digest = sha256_bytes(body)
        if digest != r["sha256"]:
            results.append({"sample_id": r["sample_id"], "status": "hash_differs_from_samples_csv", "sha256": digest})
            continue
'''
upload = '''        digest, state = put_raw(raw, body, ctype)
'''
assert source.count(validation) == source.count(upload) == 1, "archive implementation changed"
mutations = (
    ("upload-before-check", source.replace(validation, "").replace(upload, upload + validation), (
        "test_hash_mismatch_writes_no_raw_observation_or_derived_objects",
        "test_hash_mismatch_preserves_existing_archive_without_calling_put_raw",
        "test_repaired_cache_archives_and_reruns_without_retaining_rejected_bytes",
    )),
    ("reread-cache-after-check", source.replace(upload, upload.replace("body", "p.read_bytes()")), (
        "test_archive_uses_verified_snapshot_when_cache_changes_before_put",
    )),
)
all_rejected = True
for name, mutated, methods in mutations:
    namespace = dict(vars(sa))
    exec(compile(mutated, f"<{name} mutation>", "exec"), namespace)
    mutant = types.FunctionType(namespace["cmd_archive_samples"].__code__, vars(sa))
    suite = unittest.TestSuite(tests.ArchiveCommands(method) for method in methods)
    print(f"Mutation: {name} (in memory only)", flush=True)
    with mock.patch.object(sa, "cmd_archive_samples", mutant):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    rejected = (result.testsRun == len(methods) and not result.skipped
                and {case.id().split(" (", 1)[0] for case, _ in result.failures + result.errors}
                == {f"test_source_archive_commands.ArchiveCommands.{method}" for method in methods})
    print(f"{name}: {'MUTATION REJECTED' if rejected else 'MUTATION CHECK FAILED'}", flush=True)
    all_rejected = all_rejected and rejected
sys.exit(0 if all_rejected else 1)
