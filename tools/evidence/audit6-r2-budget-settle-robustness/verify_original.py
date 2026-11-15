"""Run five regressions against a pinned original revision, without editing source files."""
import subprocess
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_r2_budget_settlement as tests  # noqa: E402

b = tests.b
original = types.ModuleType("audit6_original_budget")
original.__file__ = b.__file__
revision = sys.argv[1] if len(sys.argv) > 1 else "b79cfa3eeac1e3cb0178e35637eaf1c241fded54"
print("Original revision:", revision, flush=True)
source = subprocess.check_output(["git", "show", f"{revision}:tools/r2_budget.py"], cwd=ROOT, text=True)
exec(compile(source, b.__file__, "exec"), original.__dict__)
original.BudgetError = b.BudgetError
b.Ledger.append = original.Ledger.append
b.Session.settle = original.Session.settle
b.settlement_worst_case = original.settlement_worst_case
b.profile_minimum = original.profile_minimum
names = [
    "test_settlement_retries_sequence_race_with_fresh_hash_and_usage",
    "test_committed_reservation_followed_by_412_is_reconciled_without_duplicate",
    "test_committed_settlement_followed_by_412_is_reconciled_and_confirmation_metered",
    "test_confirmation_get_retries_are_in_recorded_worst_case",
    "test_paginated_http_reads_and_race_retry_charge_every_page_and_body",
]
suite = unittest.TestSuite(tests.SettlementRobustness(name) for name in names)
result = unittest.TextTestRunner(verbosity=2).run(suite)
expected = (len(result.failures) == 4 and len(result.errors) == 1
            and result.errors[0][0].id().endswith(names[1])
            and "class_a would reach 9 > limit 8" in result.errors[0][1])
print("Original implementation detected by all five regressions (four assertions, one admission refusal):", expected)
raise SystemExit(0 if expected else 1)
