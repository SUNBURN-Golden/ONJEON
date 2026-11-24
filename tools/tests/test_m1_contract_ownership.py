"""Regression tests for the M1 shared contract assignment."""

import unittest
from pathlib import Path

from tools.ci.bootstrap_sample.prune import keep_set, load_tasks
from tools.daemon.core.gate_evaluator import paths_within_scope, patterns_overlap
from tools.release_readiness.check import read_contract

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
REGISTRY = BUNDLE / "tasks.json"
OWNER = "T-CT-10"
SCHEMAS = {
    "raw_asset": "raw-asset-content-addressed",
    "source_observation": "source-observation-preserves-history",
    "clause_occurrence": "clause-occurrence-provenance",
    "code_set": "code-set-edition-as-of",
    "parameter_table": "parameter-table-observed-open-range",
}


def schema_path(name):
    return f"packages/schemas/json/{name}.schema.json"


class M1ContractOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = load_tasks(REGISTRY)

    def test_each_schema_has_one_s0_owner_and_a_named_acceptance_test(self):
        task = self.tasks[OWNER]
        self.assertEqual((task["zone"], task["stage"]), ("contracts", "S0"))
        self.assertTrue({"T-CT-01", "T-CT-04"} <= keep_set(self.tasks, OWNER))
        self.assertEqual(set(task["required_test_ids"]), set(SCHEMAS.values()))
        for name, test_id in SCHEMAS.items():
            path = schema_path(name)
            with self.subTest(schema=path):
                exact_owners = [
                    tid for tid, other in self.tasks.items()
                    if f"path:{path}" in other["produces"]
                ]
                self.assertEqual(exact_owners, [OWNER])
                self.assertTrue(any(entry.startswith(f"시험 {test_id}:") for entry in task["tests"]))
                self.assertTrue(any(test_id in entry for entry in task["done_criteria"]))

    def test_scope_supports_versioned_codegen_and_separate_evidence(self):
        task = self.tasks[OWNER]
        locks = {"Cargo.lock", "services/scenario-api/Cargo.lock"}
        evidence = f"docs/release-readiness/evidence/{OWNER}"
        deliverables = locks | {schema_path(name) for name in SCHEMAS} | {
            "packages/schemas/Cargo.toml",
            "packages/schemas/src/generated/types.rs",
            "packages/schemas/codegen/generated/ts/types.ts",
            "packages/schemas/codegen/generated/dart/lib/src/types.dart",
            "packages/schemas/codegen/tests/test_schemas.py",
            f"{evidence}/acceptance.log",
        }
        self.assertEqual({entry["path"] for entry in task["path_policy"]["exceptions"]}, locks)
        self.assertIn(f"path:{evidence}/**", task["produces"])
        for path in sorted(deliverables):
            with self.subTest(path=path):
                self.assertTrue(paths_within_scope([path], task))
                self.assertTrue(any(patterns_overlap(path, lock) for lock in task["conflict_paths"]))
        for path in ("packages/schemas/vocabulary.json", "docs/blueprint/VOCABULARY.md",
                     "docs/data/DATA_PIPELINE_CONTRACT.md", "docs/release-readiness/evidence/readiness.json"):
            self.assertFalse(paths_within_scope([path], task), path)

    def test_consumers_and_gates_have_the_schema_owner_as_a_prerequisite(self):
        consumers = {
            "T-KN-05": ("raw_asset", "source_observation", "clause_occurrence"),
            "T-KN-08": ("code_set", "parameter_table"),
        }
        for tid, names in consumers.items():
            with self.subTest(consumer=tid):
                expected = {f"path:{schema_path(name)}" for name in names}
                self.assertTrue(expected <= set(self.tasks[tid]["consumes"]))
                self.assertIn(OWNER, keep_set(self.tasks, tid))
        for tid in ("T-OP-10", "T-OP-02", "T-OP-08"):
            self.assertIn(OWNER, keep_set(self.tasks, tid), tid)
        for tid in ("T-DT-01", "T-DT-02"):
            self.assertNotIn(OWNER, keep_set(self.tasks, tid), tid)

    def test_release_purpose_contract_tracks_the_owner(self):
        _, rows, _ = read_contract(REGISTRY, BUNDLE / "09_제품목적_대응표.md")
        linked = {row_id for row_id, row in rows.items() if OWNER in row["tasks"]}
        self.assertEqual(linked, {"P02", "P03", "P05", "P08"})
