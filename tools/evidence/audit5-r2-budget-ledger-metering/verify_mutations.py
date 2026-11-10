#!/usr/bin/env python3
"""Run each regression against an in-memory mutant; never edit production files."""
import inspect
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/tests")]
import r2_budget as budget  # noqa: E402
import source_archive as archive  # noqa: E402
import test_r2_budget as tests  # noqa: E402


def check(owner, name, old, new, cases):
    original = getattr(owner, name)
    source = textwrap.dedent(inspect.getsource(original))
    if source.count(old) != 1:
        raise SystemExit(f"expected exactly one {old!r} in {name}")
    namespace = {}
    exec(compile(source.replace(old, new), f"<mutant {old}>", "exec"),
         original.__globals__, namespace)
    try:
        setattr(owner, name, namespace[name])
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.TestSuite(tests.EndToEnd(case) for case in cases))
        rejected = {case.id().split(" (")[0] for case, _ in result.failures + result.errors}
        expected = {tests.EndToEnd(case).id() for case in cases}
        if result.skipped or rejected != expected:
            raise SystemExit(f"mutant escaped regression: {old}")
        print(f"PASS: rejected {old!r} -> {new!r}", flush=True)
    finally:
        setattr(owner, name, original)


if __name__ == "__main__":
    if not tests.HAVE_BOTO:
        raise SystemExit("boto3 with conditional PUT support is required; no skips allowed")
    check(budget.Session, "open", "st.meter = self.meter", "st.meter = None",
          ["test_ledger_get_exhausts_admission_before_reservation",
           "test_settlement_get_exhausts_remaining_bytes_after_active_is_cleared"])
    check(budget.Session, "open", "ledger=True, budget=self", "ledger=True",
          ["test_ledger_get_uses_policy_total_attempts_before_active_is_set"])
    check(archive.S3Store, "__init__", '"total_max_attempts": attempts', '"max_attempts": attempts',
          ["test_ledger_get_uses_policy_total_attempts_before_active_is_set",
           "test_policy_attempts_cover_archive_and_settlement_after_active_is_cleared"])
