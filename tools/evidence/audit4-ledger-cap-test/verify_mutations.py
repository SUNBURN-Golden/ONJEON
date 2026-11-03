"""Run the HTTP boundary regression against in-memory historical cap defects."""
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/tests")]
import r2_budget as budget
import test_r2_checkpoint as tests

source_path = ROOT / "tools/r2_budget.py"
source = source_path.read_text()
read_guard = "not self.over_limit_ok and len(keys) >= limit:"
append_guard = "if count - self.base_seq >= limit:"
assert source.count(read_guard) == source.count(append_guard) == 1

for name, change_read, change_append in (
    ("read allows exactly 100", True, False),
    ("settlement append guard missing", False, True),
    ("historical path allows 101 and 102", True, True),
):
    mutant = source
    if change_read:
        mutant = mutant.replace(read_guard, "not self.over_limit_ok and len(keys) > limit:")
    if change_append:
        mutant = mutant.replace(append_guard, "if False:")
    namespace = {"__file__": str(source_path), "__name__": "cap_mutant"}
    exec(compile(mutant, str(source_path), "exec"), namespace)
    namespace["BudgetError"] = budget.BudgetError
    output = io.StringIO()
    with mock.patch.object(budget.Ledger, "read", namespace["Ledger"].read), \
            mock.patch.object(budget.Ledger, "append", namespace["Ledger"].append):
        suite = unittest.TestSuite([tests.EndToEnd(
            "test_ordinary_sessions_enforce_ledger_cap_before_http_writes")])
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
        if change_read and change_append:
            fixture = tests.EndToEnd()
            fixture.setUp()
            try:
                fixture.seed_full_ledger()
                session = budget.Session(str(fixture.job_path), fixture.stub.endpoint,
                                         policy_path=fixture.policy_path, gate_dir=fixture.gate_dir)
                session.open()
                settled = session.settle("ok")
                assert (session.reservation["seq"], settled["seq"]) == (101, 102)
                print("Historical reproduction: 100 -> reservation 101 -> settlement 102.")
            finally:
                fixture.tearDown()
                fixture.doCleanups()
    print(f"MUTANT: {name}\n{output.getvalue()}")
    assert result.failures and not result.errors and not result.skipped, name
    print("Detected as expected; production source unchanged.\n")
