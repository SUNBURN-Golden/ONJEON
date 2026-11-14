#!/usr/bin/env python3
"""Require the CLI lifecycle regression to reject missing/late integrity guards.

Only in-memory functions change; tests use temporary local stores and no network.
"""
import ast
import inspect
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_source_archive_commands as tests


def mutate(function, mode):
    tree = ast.parse(inspect.getsource(function))
    loop = next(node for node in tree.body[0].body if isinstance(node, ast.For))
    guards = [node for node in loop.body if isinstance(node, ast.If)
              and ast.unparse(node.test) == "digest != r['sha256']"]
    assert len(guards) == 1, "expected exactly one sample hash guard"
    guard = guards[0]
    loop.body.remove(guard)
    if mode == "after_write":
        write = "digest, state = put_raw(raw, body, ctype)" if function is tests.sa.cmd_archive_samples \
            else "dest.write_bytes(body)"
        writes = [i for i, node in enumerate(loop.body) if ast.unparse(node) == write]
        assert len(writes) == 1, "expected exactly one archive/restore write"
        loop.body.insert(writes[0] + 1, guard)
    else:
        assert mode == "removed"
    namespace = dict(vars(tests.sa))
    exec(compile(ast.fix_missing_locations(tree), f"<{function.__name__}-{mode}>", "exec"), namespace)
    # Keep each test's temporary manifest and real LocalStore patches effective.
    return types.FunctionType(namespace[function.__name__].__code__, vars(tests.sa))


def main():
    method = "test_cli_rejects_bad_cache_and_corrupt_store_through_archive_restore_lifecycle"
    for name in ("cmd_archive_samples", "cmd_fetch"):
        for mode in ("removed", "after_write"):
            mutant = mutate(getattr(tests.sa, name), mode)
            print(f"Mutation: {name}/{mode} (in memory only)", flush=True)
            with mock.patch.object(tests.sa, name, mutant):
                suite = unittest.TestSuite([tests.ArchiveCommands(method)])
                result = unittest.TextTestRunner(verbosity=2).run(suite)
            # Assertion failures must detect the defect; unrelated errors/skips do not count.
            if result.testsRun != 1 or not result.failures or result.errors or result.skipped:
                raise SystemExit(f"{name}/{mode}: mutation escaped or regression did not run")
            print(f"MUTATION REJECTED: {name}/{mode}", flush=True)


if __name__ == "__main__":
    main()
