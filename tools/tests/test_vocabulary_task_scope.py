"""Keep vocabulary task permissions in step with contract generation."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "packages/schemas/codegen")]

import gen
from tools.daemon.core.gate_evaluator import paths_within_scope, patterns_overlap


class VocabularyTaskScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        registry = ROOT / "docs/blueprint/proposals/설계검토_결과/tasks.json"
        cls.tasks = {task["id"]: task for task in json.loads(registry.read_text(encoding="utf-8"))["tasks"]}
        cls.outputs = [path.relative_to(ROOT).as_posix() for path in gen.expected_outputs()]

    def test_regeneration_paths_are_allowed_declared_and_lockable(self):
        for task_id in ("T-CT-02", "T-CT-09"):
            task = self.tasks[task_id]
            for path in self.outputs + ["packages/schemas/README.md"]:
                with self.subTest(task=task_id, path=path):
                    self.assertTrue(paths_within_scope([path], task))
                    self.assertTrue(any(
                        ref.startswith("path:") and patterns_overlap(path, ref.removeprefix("path:"))
                        for ref in task["produces"]
                    ))
                    self.assertTrue(any(patterns_overlap(path, lock) for lock in task["conflict_paths"]))

    def test_canon_approval_is_limited_to_vocabulary_files(self):
        for task_id in ("T-CT-02", "T-CT-09"):
            with self.subTest(task=task_id):
                task = self.tasks[task_id]
                approval = task["canon_change"]
                self.assertIs(approval["required"], True)
                self.assertEqual(set(approval["approval"]["scope_paths"]), {
                    "packages/schemas/vocabulary.json", "docs/blueprint/VOCABULARY.md",
                })
                for path in ("docs/BLUEPRINT.md", "docs/data/PREMIUM_DATA_CONTRACT.md",
                             "packages/schemas/codegen/gen.py", "packages/api-types/src/lib.rs"):
                    self.assertFalse(paths_within_scope([path], task), path)

    def test_contract_version_and_both_lockfiles_can_be_updated_together(self):
        paths = ["packages/schemas/Cargo.toml", "Cargo.lock", "services/scenario-api/Cargo.lock"]
        for task_id in ("T-CT-02", "T-CT-09"):
            with self.subTest(task=task_id):
                task = self.tasks[task_id]
                self.assertTrue(paths_within_scope(paths, task))
                for path in paths:
                    self.assertTrue(any(patterns_overlap(path, lock) for lock in task["conflict_paths"]), path)
                exceptions = {entry["path"] for entry in task["path_policy"]["exceptions"]}
                self.assertTrue(set(paths[1:]) <= exceptions)

    def test_tasks_require_generation_and_workspace_tests(self):
        for task_id in ("T-CT-02", "T-CT-09"):
            with self.subTest(task=task_id):
                commands = self.tasks[task_id]["tests"]
                self.assertIn("python3 -I packages/schemas/codegen/gen.py --check", commands)
                self.assertIn("cargo test --all --locked", commands)
                self.assertIn("cargo test --manifest-path services/scenario-api/Cargo.toml --locked", commands)

    def test_remaining_axis_work_reaches_final_gate(self):
        task = self.tasks["T-CT-09"]
        self.assertTrue({"payment_cycle", "package_binding"} <= set(task["vocabulary_axes"]))
        self.assertIn("T-CT-02", task["prereq_tasks"])
        self.assertIn(task["id"], self.tasks["T-OP-08"]["prereq_tasks"])
