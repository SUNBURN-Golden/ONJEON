#!/usr/bin/env python3
"""Reintroduce the permissive emulator fallback in memory; regressions must catch it."""
import ast
import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_store_provider as tests


def main():
    tree = ast.parse(inspect.getsource(tests.sa.provider_of))
    function = tree.body[0]
    assert isinstance(function.body[-1], ast.Raise)
    function.body[-1] = ast.Return(value=ast.Constant(value="emulator"))
    namespace = dict(tests.sa.__dict__)
    exec(compile(ast.fix_missing_locations(tree), "<permissive-emulator-mutation>", "exec"), namespace)
    suite = unittest.TestSuite([
        tests.Provider("test_explicit_aws_and_other_remote_endpoints_are_refused"),
        tests.Provider("test_lookalike_host_is_not_r2"),
        tests.EndpointGate("test_remote_endpoint_is_refused_before_client_creation"),
    ])
    with mock.patch.object(tests.sa, "provider_of", namespace["provider_of"]):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    detected = {getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors}
    if result.testsRun != 3 or result.skipped or len(detected) != 3:
        raise SystemExit("mutation escaped or required regressions did not run")
    print("MUTATION REJECTED: all three regression tests detected the permissive fallback")


if __name__ == "__main__":
    main()
