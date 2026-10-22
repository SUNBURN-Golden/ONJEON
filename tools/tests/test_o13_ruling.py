"""D-04 correction proposals and the access gates they must preserve.

Protected sources are read only. The daemon uses in-memory mock ports, and only
gate lists from real tasks are copied into a mock task; no R2 access is attempted.
"""
import copy
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from daemon.core.envelope_validator import derive  # noqa: E402
from daemon.mock_env import MockEnv  # noqa: E402

BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
REVIEW = ROOT / "docs/review/2026-10-23_audit1_o13_d04_ruling.md"
MOCK_TASK = "T-MOCK-BASIC"


class RulingDocumentation(unittest.TestCase):
    def test_every_proposal_cites_the_actual_owner_ruling(self):
        source = (ROOT / "docs/decisions/DEC-D-04.md").read_text(encoding="utf-8")
        owner = re.search(r"\| decided_by \| ([^ (]+)", source).group(1)
        decided_at = re.search(r"\| time \(`decided_at`\) \| ([^|]+) \|", source).group(1).strip()
        self.assertIn("폐기하지 않는다", source)
        text = REVIEW.read_text(encoding="utf-8")
        targets = (
            ("O13", "../blueprint/DECISIONS.md"),
            ("§12", "../BLUEPRINT.md"),
            ("VM", "../blueprint/proposals/설계검토_결과/05_VM실행준비.md"),
            ("작업 명세", "../blueprint/proposals/설계검토_결과/03_작업명세.md"),
        )
        sections = re.split(r"\n## \d+\. ", text)[1:5]
        self.assertEqual(4, len(sections))
        for section, (name, target) in zip(sections, targets):
            with self.subTest(target=name):
                self.assertIn(name, section)
                self.assertIn(f"]({target})", section)
                self.assertTrue((REVIEW.parent / target).is_file())
                proposed_rows = [line for line in section.splitlines()
                                 if line.startswith("| ") and "폐기하지 않는다" in line]
                self.assertEqual(1, len(proposed_rows))
                row = proposed_rows[0]
                for required in ("[DEC-D-04](../decisions/DEC-D-04.md)", owner,
                                 decided_at, "2026-10-23"):
                    self.assertIn(required, row)
                self.assertNotIn("폐기 전", row)
                self.assertNotIn("폐기·범위 제한 토큰 재발급", row)

    def test_readme_exposes_pending_correction_without_claiming_closure(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"]({REVIEW.relative_to(ROOT).as_posix()})", readme)
        text = REVIEW.read_text(encoding="utf-8")
        self.assertIn("정본 반영 대기 — finding 미종결", text)
        self.assertIn("실제 수집·R2 대조·제품 완료 증거가 아니며", text)
        patch = REVIEW.with_suffix(".patch")
        self.assertIn(f"]({patch.name})", text)
        # --check validates the proposed change without writing protected files.
        result = subprocess.run(["git", "apply", "--check", str(patch)],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


class RulingAccessGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t["id"]: t for t in json.loads(
            (BUNDLE / "tasks.json").read_text(encoding="utf-8"))["tasks"]}

    def env(self, task_id):
        env = MockEnv(BUNDLE / "daemon_rules.json", ROOT / "tools/daemon/mock_tasks.json")
        env.ports.catalog.tasks[MOCK_TASK]["decision_gates"] = copy.deepcopy(
            self.tasks[task_id]["decision_gates"])
        return env

    def test_record_file_alone_does_not_release_op04_start(self):
        self.assertTrue((ROOT / "docs/decisions/DEC-D-04.md").is_file())
        env = self.env("T-OP-04")
        env.start_task(MOCK_TASK)
        self.assertEqual("blocked", env.state(MOCK_TASK))
        self.assertNotIn("D-04", env.task(MOCK_TASK)["task_state"]["decisions_recorded"])
        self.assertEqual([], env.ports.sender.sent)

    def test_local_paths_queue_but_r2_access_stays_disabled(self):
        for task_id in ("T-DT-01", "T-DT-04", "T-OP-02"):
            with self.subTest(task=task_id):
                env = self.env(task_id)
                env.start_task(MOCK_TASK)
                self.assertEqual("queued", env.state(MOCK_TASK))
                self.assertFalse(derive(env.core, MOCK_TASK, [])["expected.real_data_allowed"])
                # The document reference is not a registered decision ID.
                self.assertFalse(derive(env.core, MOCK_TASK, ["DEC-D-04"])["expected.real_data_allowed"])

    def test_op02_requires_both_registered_decisions(self):
        env = self.env("T-OP-02")
        for decisions in ([], ["D-02"], ["D-04"]):
            with self.subTest(decisions=decisions):
                self.assertFalse(derive(env.core, MOCK_TASK, decisions)["expected.real_data_allowed"])
        # Positive control in memory only: confirms that the gate is evaluated,
        # rather than testing an unconditional denial.
        self.assertTrue(derive(env.core, MOCK_TASK, ["D-02", "D-04"])["expected.real_data_allowed"])

    def test_independent_lock_and_bulk_collection_gates_remain(self):
        self.assertEqual(["D-04"], self.tasks["T-OP-04"]["decision_gates"]["start"])
        self.assertEqual(["O14"], self.tasks["T-OP-04"]["decision_gates"]["merge"])
        self.assertEqual(["O17"], self.tasks["T-DT-05"]["decision_gates"]["release"])


if __name__ == "__main__":
    unittest.main()
