#!/usr/bin/env python3
"""Require archive regressions to detect weakened LocalStore key checks in memory."""
import ast
import inspect
import sys
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_source_archive_paths as tests


def main():
    source = textwrap.dedent(inspect.getsource(tests.sa.LocalStore._path))
    mutations = [
        ("key type guard removed", "store key must be a string",
         "test_non_string_keys_fail_with_the_store_validation_error"),
        ("canonical key guard removed", "noncanonical key:",
         "test_traversal_absolute_and_noncanonical_keys_are_rejected"),
        ("resolved containment guard removed", "key leaves local store:",
         "test_resolved_sibling_with_matching_root_prefix_is_outside"),
    ]
    for label, message, method in mutations:
        tree = ast.parse(source)
        guards = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                  and isinstance(node.body[0], ast.Raise) and message in ast.unparse(node.body[0])]
        assert len(guards) == 1, f"guard not found: {label}"
        guards[0].test = ast.Constant(False)
        namespace = dict(tests.sa.__dict__)
        exec(compile(ast.fix_missing_locations(tree), "<local-key-mutation>", "exec"), namespace)
        suite = unittest.TestSuite([tests.LocalStorePaths(method)])
        with mock.patch.object(tests.sa.LocalStore, "_path", namespace["_path"]):
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        if result.testsRun != 1 or result.skipped or result.wasSuccessful():
            raise SystemExit(f"mutation escaped: {label}")
        print(f"MUTATION REJECTED: {label}", flush=True)


if __name__ == "__main__":
    main()
