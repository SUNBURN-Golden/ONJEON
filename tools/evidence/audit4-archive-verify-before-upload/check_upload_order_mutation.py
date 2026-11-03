"""Recreate the reported upload-before-compare bug in memory; never edit source.

Run from the worktree root:
  python3 tools/evidence/audit4-archive-verify-before-upload/check_upload_order_mutation.py
Exit 0 means both new regressions rejected the mutation (no skips allowed).
"""
import inspect
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_source_archive_upload_r2 as tests

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
mutated = source.replace(validation, "").replace(upload, upload + validation)
namespace = dict(vars(sa))
exec(compile(mutated, "<upload-before-compare mutation>", "exec"), namespace)
mutant = types.FunctionType(namespace["cmd_archive_samples"].__code__, vars(sa))
suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.R2ArchiveSamples)
print("Mutation: move samples.csv comparison after put_raw (in memory only).", flush=True)
with mock.patch.object(sa, "cmd_archive_samples", mutant):
    result = unittest.TextTestRunner(verbosity=2).run(suite)
rejected = (result.testsRun == 2 and not result.skipped
            and {case.id().split(" (", 1)[0] for case, _ in result.errors + result.failures}
            == {f"test_source_archive_upload_r2.R2ArchiveSamples.{name}" for name in (
                "test_mismatched_cache_makes_no_raw_or_derived_requests",
                "test_bad_row_is_skipped_and_matching_row_uploads_then_reruns_without_put")})
print("MUTATION REJECTED" if rejected else "MUTATION CHECK FAILED")
sys.exit(0 if rejected else 1)
