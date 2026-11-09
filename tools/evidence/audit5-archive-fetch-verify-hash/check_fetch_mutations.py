#!/usr/bin/env python3
"""Require fetch regressions to reject missing or late hash checks, in memory only."""
import ast
import inspect
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_source_archive_fetch_r2 as tests


def mutated_fetch(mode):
    tree = ast.parse(inspect.getsource(tests.sa.cmd_fetch))
    loop = next(node for node in tree.body[0].body if isinstance(node, ast.For))
    guards = [node for node in loop.body if isinstance(node, ast.If)
              and ast.unparse(node.test) == "digest != r['sha256']"]
    assert len(guards) == 1, "expected exactly one downloaded hash guard"
    guard = guards[0]
    loop.body.remove(guard)
    if mode == "after_write":
        assert ast.unparse(loop.body[-1]) == "dest.write_bytes(body)"
        loop.body.append(guard)
    else:
        assert mode == "removed"
    namespace = dict(tests.sa.__dict__)
    exec(compile(ast.fix_missing_locations(tree), f"<fetch-hash-{mode}>", "exec"), namespace)
    # Resolve globals through the real module so each test's manifest/store patches apply.
    return types.FunctionType(namespace["cmd_fetch"].__code__, tests.sa.__dict__)


def main():
    names = (
        "test_overwritten_bytes_rejected_even_with_expected_server_checksum",
        "test_corrupt_middle_object_stops_restore_and_preserves_verified_files",
        "test_rerun_rehashes_overwritten_object_and_keeps_last_verified_restore",
        "test_cli_hash_mismatch_returns_failure_and_settles_budget_as_failed",
    )
    for mode in ("removed", "after_write"):
        suite = unittest.TestSuite(tests.R2Fetch(name) for name in names)
        with mock.patch.object(tests.sa, "cmd_fetch", mutated_fetch(mode)):
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        detected = {getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors}
        if result.testsRun != len(names) or result.skipped or len(detected) != len(names):
            raise SystemExit(f"{mode}: mutation escaped or required regressions did not run")
        print(f"MUTATION REJECTED ({mode}): all {len(names)} regression tests detected it", flush=True)


if __name__ == "__main__":
    main()
