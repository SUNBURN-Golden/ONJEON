"""Regression tests for audit-1 I/O and audit-2 I2 fields/batch errors.

`docs/blueprint/proposals/온톨로지/검증/runner/src/main.rs` used to `expect()` on
`rule_path` and on reading the rule file, so one unreadable or malformed
`rule_path` panicked the process and lost the whole batch. The runner must now
emit a per-case `io_error` object and keep evaluating the remaining jobs, exiting
0 so `subprocess.run(..., check=True)` in `ontology_check.run_engine` still works.

Set ONJEON_ONTOLOGY_RUNNER to use an already-built runner (the design-specs CI
job does this). Otherwise build with `cargo build --offline`; a failed build
fails the tests. Only a missing cargo without a prebuilt runner skips them.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
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


@unittest.skipUnless(os.environ.get("ONJEON_ONTOLOGY_RUNNER") or shutil.which("cargo"), "cargo not installed")
class RunnerIoError(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = os.environ.get("ONJEON_ONTOLOGY_RUNNER", str(RUNNER_BIN))
        if not os.environ.get("ONJEON_ONTOLOGY_RUNNER"):
            subprocess.run(["cargo", "build", "--offline"], cwd=RUNNER_DIR, capture_output=True, text=True, check=True)

    def run_jobs(self, batch):
        p = subprocess.run([self.runner], input=json.dumps(batch), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        rows = json.loads(p.stdout)
        self.assertEqual(len(rows), len(batch))
        return rows

    def write_rule(self, directory, **changes):
        """Synthetic rules only; never change the frozen ontology rule files."""
        rule = {
            "rule_id": "runner-test", "rule_version": "v1", "schema_version": "rule-0.1",
            "publication_state": "fixture_only", "evidence_refs": ["clause:runner-test"],
            "unknown_policy": "use_three_valued_logic_never_default_to_zero",
            "inputs": {"gate": "bool"}, "eligibility": "gate", "amount": {"krw": 1234},
        }
        rule.update(changes)
        path = Path(directory) / "rule.json"
        path.write_text(json.dumps(rule), encoding="utf-8")
        return str(path)

    def assert_batch(self, results):
        self.assertEqual(set(results), {"ok_before", "missing_path", "nonstring_path", "unreadable", "ok_after"})
        for cid in ("missing_path", "nonstring_path", "unreadable"):
            self.assertIn("io_error", results[cid], cid)
            self.assertEqual(results[cid]["case_id"], cid)
        for cid in ("ok_before", "ok_after"):
            self.assertNotIn("io_error", results[cid], cid)
            self.assertEqual(results[cid]["payout"]["kind"], "payable")
            self.assertEqual(results[cid]["payout"]["amount"]["krw"], 5000000)
            self.assertIsNone(results[cid]["release_id"])
            self.assertEqual(results[cid]["schema_version"], "rule-0.1")

    def test_per_case_io_error_and_batch_continues(self):
        """Exit 0; bad rule_path cases get io_error; a case after them still evaluates."""
        self.assert_batch({r["case_id"]: r for r in self.run_jobs(jobs())})

    def test_run_engine_treats_io_error_like_load_error(self):
        """run_engine (check=True) stays up on io_error rows and keys them by case_id."""
        evs = ontology_check.run_engine(self.runner, jobs())
        self.assert_batch(evs)

    def test_release_and_schema_fields_for_every_payout_state(self):
        """Both DSLs, omitted/null fixture releases and distinct synthetic releases."""
        with tempfile.TemporaryDirectory() as directory:
            for schema in ("rule-0.1", "rule-0.2"):
                released_hashes = []
                for release in ("omitted", None, "rel:runner-1", "rel:runner-2"):
                    changes = {"schema_version": schema}
                    if release != "omitted":
                        changes["release_id"] = release
                    if release and release != "omitted":
                        changes["publication_state"] = "released"
                    path = self.write_rule(directory, **changes)
                    batch = [
                        {"case_id": "yes", "rule_path": path, "inputs": {"gate": True}},
                        {"case_id": "no", "rule_path": path, "inputs": {"gate": False}},
                        {"case_id": "unknown", "rule_path": path, "inputs": {}},
                    ]
                    with self.subTest(schema=schema, release=release):
                        rows = self.run_jobs(batch)
                        self.assertEqual(rows, self.run_jobs(batch))
                        self.assertEqual([r["case_id"] for r in rows], ["yes", "no", "unknown"])
                        self.assertEqual([r["eligibility"] for r in rows], ["true", "false", "unknown"])
                        self.assertEqual([r["payout"]["kind"] for r in rows], ["payable", "not_payable", "undetermined"])
                        self.assertEqual(rows[0]["payout"]["amount"], {"kind": "exact", "krw": 1234})
                        self.assertEqual(rows[2]["missing_inputs"], ["gate"])
                        for row in rows:
                            self.assertEqual(row["release_id"], None if release == "omitted" else release)
                            self.assertEqual(row["schema_version"], schema)
                            self.assertEqual(row["rule_id"], "runner-test")
                            self.assertEqual(row["rule_version"], "v1")
                            self.assertEqual(row["publication_state"], changes.get("publication_state", "fixture_only"))
                            self.assertEqual(row["evidence_refs"], ["clause:runner-test"])
                            for key in ("rule_content_hash", "input_snapshot_hash"):
                                self.assertRegex(row[key], r"^[0-9a-f]{64}$")
                            self.assertTrue(row["engine_version"])
                            self.assertGreater(row["trace_len"], 0)
                            self.assertTrue(row["trace_head"])
                        if changes.get("publication_state") == "released":
                            released_hashes.append(rows[0]["rule_content_hash"])
                self.assertEqual(released_hashes[0], released_hashes[1])

    def test_load_and_eval_errors_preserve_order_and_later_success(self):
        with tempfile.TemporaryDirectory() as directory:
            good = {"case_id": "before", "rule_path": str(RULE), "inputs": INPUTS}
            bad_json = Path(directory) / "broken.json"
            bad_json.write_text("{", encoding="utf-8")
            bad_utf8 = Path(directory) / "bad-utf8.json"
            bad_utf8.write_bytes(b"\xff")
            bad_rule = self.write_rule(directory, schema_version="unsupported")
            overflow_dir = Path(directory) / "overflow"
            overflow_dir.mkdir()
            overflow = self.write_rule(overflow_dir, amount={"add": [{"krw": 9223372036854775807}, {"krw": 1}]})
            errors = [
                ("json", str(bad_json), {}, "load_error", "invalid JSON:"),
                ("schema", bad_rule, {}, "load_error", "schema_version"),
                ("utf8", str(bad_utf8), {}, "io_error", str(bad_utf8)),
                ("missing_inputs", str(RULE), None, "eval_error", "InputsNotObject"),
                ("array_inputs", str(RULE), [], "eval_error", "InputsNotObject"),
                ("bad_type", str(RULE), {**INPUTS, "dx_in_category": "yes"}, "eval_error", "BadInput"),
                ("unknown_input", str(RULE), {"typo": True}, "eval_error", "UnknownInput"),
                ("overflow", overflow, {"gate": True}, "eval_error", "Overflow"),
            ]
            batch = [good]
            for cid, path, inputs, _, _ in errors:
                job = {"case_id": cid, "rule_path": path, "inputs": inputs}
                if cid == "missing_inputs":
                    del job["inputs"]
                batch.append(job)
            batch.append({**good, "case_id": "after"})
            rows = self.run_jobs(batch)
            self.assertEqual([r["case_id"] for r in rows], [j["case_id"] for j in batch])
            for row, (cid, _, _, key, detail) in zip(rows[1:-1], errors):
                with self.subTest(case=cid):
                    self.assertEqual(set(row), {"case_id", key})
                    self.assertIn(detail, row[key])
            self.assertEqual(rows[0]["payout"], rows[-1]["payout"])
            self.assertEqual(rows[-1]["payout"]["kind"], "payable")
            self.assertEqual(ontology_check.run_engine(self.runner, batch), {r["case_id"]: r for r in rows})

    def test_nonobject_jobs_are_per_job_errors(self):
        batch = [None, 42, "bad job", [], {"case_id": "after", "rule_path": str(RULE), "inputs": INPUTS}]
        rows = self.run_jobs(batch)
        for row in rows[:-1]:
            self.assertEqual(row, {"case_id": None, "io_error": "rule_path missing or not a string"})
        self.assertEqual(rows[-1]["case_id"], "after")
        self.assertEqual(rows[-1]["payout"]["kind"], "payable")

    def test_invalid_batch_is_reported_without_panic(self):
        for raw in ("", "[", '[{"case_id":"incomplete"}', '{}', 'null', '"string"', '1', '[] trailing'):
            with self.subTest(raw=raw):
                p = subprocess.run([self.runner], input=raw, capture_output=True, text=True)
                self.assertEqual(p.returncode, 1)
                self.assertEqual(p.stdout, "")
                self.assertIn("ontology-case-runner: jobs json:", p.stderr)
                self.assertNotIn("panicked", p.stderr)

    def test_empty_batch_is_valid(self):
        self.assertEqual(self.run_jobs([]), [])


if __name__ == "__main__":
    unittest.main()
