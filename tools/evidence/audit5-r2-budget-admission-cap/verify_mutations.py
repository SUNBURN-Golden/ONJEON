"""Verify both boundary regressions against in-memory mutants; never edit production source."""
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/tests")]
import r2_budget as budget
import test_r2_budget as tests

path = ROOT / "tools/r2_budget.py"
source = path.read_text()
cases = (
    ("monthly closure waits for N+1", "Session", "_close_if_exhausted",
     ((">= self.policy[\"admission\"][\"per_month_global\"]:",
       "> self.policy[\"admission\"][\"per_month_global\"]:"),
      (">= self.job[\"admissions_per_month\"]:", "> self.job[\"admissions_per_month\"]:")),
     tests.EndToEnd, "test_successful_last_admission_closes_before_reserving"),
    ("append permits record 101", "Ledger", "append",
     (("if count - self.base_seq >= limit:", "if count - self.base_seq > limit:"),),
     tests.LedgerRecordCap, "test_append_cap_is_checkpoint_relative_even_for_recovery"),
)

for name, cls_name, method, changes, test_class, test_name in cases:
    mutant = source
    for old, new in changes:
        assert mutant.count(old) == 1, old
        mutant = mutant.replace(old, new)
    namespace = {"__file__": str(path), "__name__": "budget_cap_mutant"}
    exec(compile(mutant, str(path), "exec"), namespace)
    namespace["BudgetError"] = budget.BudgetError
    output = io.StringIO()
    with mock.patch.object(getattr(budget, cls_name), method, getattr(namespace[cls_name], method)):
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(
            unittest.TestSuite([test_class(test_name)]))
    print(f"MUTANT: {name}\n{output.getvalue()}")
    assert result.failures and not result.errors and not result.skipped, name
    print("Detected as expected; production source unchanged.\n")
