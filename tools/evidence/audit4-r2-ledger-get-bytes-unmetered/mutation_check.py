#!/usr/bin/env python3
"""Verify that removing only the ledger body-meter binding breaks the regressions.

The mutation lives in this process only; repository implementation files are unchanged.
"""
import ast
import inspect
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools/tests"), str(ROOT / "tools")]
import r2_budget as budget  # noqa: E402
import test_r2_budget as tests  # noqa: E402


def main():
    if not tests.HAVE_BOTO:
        raise SystemExit("boto3 >= 1.35 is required; mutation verification must not skip")
    tree = ast.parse(textwrap.dedent(inspect.getsource(budget.Session.open)))
    bindings = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Attribute) and target.attr == "meter"
                        and isinstance(target.value, ast.Name) and target.value.id == "st"
                        for target in node.targets)]
    if len(bindings) != 1:
        raise SystemExit(f"expected one ledger body-meter binding, found {len(bindings)}")

    class RemoveBinding(ast.NodeTransformer):
        def visit_Assign(self, node):
            return None if node is bindings[0] else node

    tree = ast.fix_missing_locations(RemoveBinding().visit(tree))
    namespace = {}
    exec(compile(tree, "<Session.open without st.meter binding>", "exec"), budget.__dict__, namespace)
    budget.Session.open = namespace["open"]
    names = ["test_ledger_get_exhausts_admission_before_reservation",
             "test_settlement_get_exhausts_remaining_bytes_after_active_is_cleared"]
    suite = unittest.TestSuite(tests.EndToEnd(name) for name in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failed = {case.id().split(" (")[0] for case, _ in result.failures}
    expected = {tests.EndToEnd(name).id() for name in names}
    if result.errors or result.skipped or failed != expected:
        raise SystemExit("mutation was not rejected by both regressions through assertion failures")
    print("PASS: both regressions reject the missing body-meter binding; request hooks remain intact.")


if __name__ == "__main__":
    main()
