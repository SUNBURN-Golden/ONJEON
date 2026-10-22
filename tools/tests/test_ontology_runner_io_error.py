"""Regression tests for the audit-1 finding on the ontology case runner.

`docs/blueprint/proposals/온톨로지/검증/runner/src/main.rs` used to `expect()` on
`rule_path` and on reading the rule file, so one unreadable or malformed
`rule_path` panicked the process and lost the whole batch. The runner must now
emit a per-case `io_error` object and keep evaluating the remaining jobs, exiting
0 so `subprocess.run(..., check=True)` in `ontology_check.run_engine` still works.

The tests build the runner crate with `cargo build --offline` and are skipped
when cargo or the offline registry is unavailable.
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO / "docs/blueprint/proposals/온톨로지/검증/runner"
RUNNER_BIN = RUNNER_DIR / "target/debug/ontology-case-runner"
RULE = REPO / "docs/blueprint/proposals/온톨로지/규칙/hana-2601-3d-cancer-dx.json"
CHECK_DIR = REPO / "docs/blueprint/proposals/온톨로지/검증"

sys.path.insert(0, str(CHECK_DIR))
import ontology_check  # noqa: E402

INPUTS = {
    "contract_date": "2026-08-20",
    "is_initial_contract": True,
    "renewal_date": None,
    "diagnosis_date": "2027-04-20",
    "policy_end_date": "2046-08-20",
    "dx_in_category": True,
    "already_paid": False,
    "insured_amount_krw": 10000000,
}


def jobs():
    return [
        {"case_id": "ok_before", "rule_path": str(RULE), "inputs": INPUTS},
        {"case_id": "missing_path", "inputs": INPUTS},
        {"case_id": "nonstring_path", "rule_path": 42, "inputs": INPUTS},
        {"case_id": "unreadable", "rule_path": str(RUNNER_DIR / "no-such-rule.json"), "inputs": INPUTS},
        {"case_id": "ok_after", "rule_path": str(RULE), "inputs": INPUTS},
    ]


@unittest.skipUnless(shutil.which("cargo"), "cargo not installed")
class RunnerIoError(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = subprocess.run(["cargo", "build", "--offline"], cwd=RUNNER_DIR, capture_output=True, text=True)
        if p.returncode != 0:
            raise unittest.SkipTest("offline runner build failed: " + p.stderr.strip().splitlines()[-1])

    def assert_batch(self, results):
        self.assertEqual(set(results), {"ok_before", "missing_path", "nonstring_path", "unreadable", "ok_after"})
        for cid in ("missing_path", "nonstring_path", "unreadable"):
            self.assertIn("io_error", results[cid], cid)
            self.assertEqual(results[cid]["case_id"], cid)
        for cid in ("ok_before", "ok_after"):
            self.assertNotIn("io_error", results[cid], cid)
            self.assertEqual(results[cid]["payout"]["kind"], "payable")
            self.assertEqual(results[cid]["payout"]["amount"]["krw"], 5000000)

    def test_per_case_io_error_and_batch_continues(self):
        """Exit 0; bad rule_path cases get io_error; a case after them still evaluates."""
        p = subprocess.run([str(RUNNER_BIN)], input=json.dumps(jobs()), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assert_batch({r["case_id"]: r for r in json.loads(p.stdout)})

    def test_run_engine_treats_io_error_like_load_error(self):
        """run_engine (check=True) stays up on io_error rows and keys them by case_id."""
        evs = ontology_check.run_engine(str(RUNNER_BIN), jobs())
        self.assert_batch(evs)


if __name__ == "__main__":
    unittest.main()
