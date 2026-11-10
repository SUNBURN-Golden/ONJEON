#!/usr/bin/env python3
"""Regressions must detect removal of row validation and length-only validation."""
import ast
import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_samples_csv_validation as tests


def mutated_function(module, name, tree):
    namespace = dict(module.__dict__)
    exec(compile(ast.fix_missing_locations(tree), "<hash-validation-mutation>", "exec"), namespace)
    return namespace[name]


def main():
    tree = ast.parse(inspect.getsource(tests.vc.check))
    guards = [node for node in ast.walk(tree) if isinstance(node, ast.Try)
              and isinstance(node.body[0], ast.Expr)
              and ast.unparse(node.body[0].value) == "sm.check_sha256(r.get('sha256'))"]
    assert len(guards) == 1, "expected exactly one sample hash guard"
    guards[0].body = [ast.Pass()]
    removed = mutated_function(tests.vc, "check", tree)

    source = inspect.getsource(tests.sa.sm.check_sha256)
    condition = 're.fullmatch(r"[0-9a-fA-F]{64}", digest) is None'
    assert source.count(condition) == 1
    length_only = mutated_function(tests.sa.sm, "check_sha256",
                                  ast.parse(source.replace(condition, "len(digest) != 64")))
    metadata_tests = [
        "test_bad_hashes_are_metadata_errors_independent_of_encoded_documents",
        "test_each_row_is_checked_even_when_encoded_hashes_match",
        "test_csv_cli_rejects_bad_or_missing_sha256_and_accepts_valid_hex",
    ]
    for label, module, name, replacement, methods in [
        ("row guard removed", tests.vc, "check", removed, metadata_tests),
        ("length-only hash guard", tests.sa.sm, "check_sha256", length_only,
         metadata_tests + ["test_object_key_rejects_bad_hashes_directly",
                           "test_invalid_hash_is_rejected_before_any_store_probe_or_read"]),
    ]:
        suite = unittest.TestSuite(tests.SampleMetadata(method) for method in methods)
        with mock.patch.object(module, name, replacement):
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        detected = {getattr(test, "test_case", test).id()
                    for test, _ in result.failures + result.errors}
        if result.testsRun != len(methods) or result.skipped or len(detected) != len(methods):
            raise SystemExit(f"mutation escaped or required regressions did not run: {label}")
        print(f"MUTATION REJECTED: {label}; all {len(methods)} selected tests detected it", flush=True)


if __name__ == "__main__":
    main()
