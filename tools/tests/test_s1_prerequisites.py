"""Regression tests for S1 scheduling with the adopted task catalog."""
import unittest
from pathlib import Path

from tools.ci.bootstrap_sample.prune import keep_set, load_tasks
from tools.daemon.bench import BASIC
from tools.daemon.mock_env import MockEnv
from tools.daemon.scenarios_flow import approve_to_wait, land, pr_of

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
MOCK_S1 = "T-OP-10"
REAL_S1 = "T-OP-02"
FOLLOWUPS = ("T-DT-03", "T-KN-08", "T-PS-01")
DATA_PATH = {"T-DT-01", "T-DT-02", "T-KN-03", "T-KN-05", "T-KN-06"}


class S1Prerequisites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = load_tasks(BUNDLE / "tasks.json")

    def env(self):
        env = MockEnv(BUNDLE / "daemon_rules.json", ROOT / "tools/daemon/mock_tasks.json")
        # The mock envelope builder takes its runtime limits from the fixture catalog.
        limits = env.ports.catalog.task(BASIC)["limits"]
        for tid, task in self.tasks.items():
            env.ports.catalog.add(dict(task, task_id=tid, limits=limits))
        return env

    def test_real_gate_and_followups_include_the_actual_data_pipeline(self):
        required = DATA_PATH | {"T-MB-02", "T-KN-07"}
        for tid in (MOCK_S1, REAL_S1):
            with self.subTest(task=tid):
                self.assertEqual(required - keep_set(self.tasks, tid), set())
        for tid in (*FOLLOWUPS, "T-OP-08"):
            with self.subTest(task=tid):
                self.assertIn(REAL_S1, keep_set(self.tasks, tid))
        self.assertIn(MOCK_S1, keep_set(self.tasks, REAL_S1))

    def test_remaining_vocabulary_work_is_required_for_release_without_holding_s1(self):
        for tid in (MOCK_S1, REAL_S1):
            with self.subTest(task=tid):
                self.assertNotIn("T-CT-09", keep_set(self.tasks, tid))
        self.assertTrue({REAL_S1, "T-CT-09"} <= keep_set(self.tasks, "T-OP-08"))

    def test_s1_waits_for_review_implementation_and_mock_merge(self):
        env = self.env()
        for tid in ("T-MB-02", "T-KN-07"):
            env.core.register_task(tid, "done")
        env.core.register_task("T-KN-06", "merge_wait")
        env.start_task(MOCK_S1)
        env.start_task(REAL_S1)
        self.assertEqual(env.state(MOCK_S1), "blocked")
        self.assertEqual(env.state(REAL_S1), "blocked")

        env.core.register_task("T-KN-06", "audit_queued")
        env.core.evaluate_prereqs(MOCK_S1)
        env.core.evaluate_prereqs(REAL_S1)
        self.assertEqual(env.state(MOCK_S1), "queued")
        self.assertEqual(env.state(REAL_S1), "blocked")

    def test_mock_merge_leaves_followups_blocked_until_real_gate_merges(self):
        env = self.env()
        earlier = set().union(*(keep_set(self.tasks, tid) for tid in FOLLOWUPS))
        for tid in earlier - {MOCK_S1, REAL_S1, *FOLLOWUPS}:
            env.core.register_task(tid, "done")
        for tid in (REAL_S1, *FOLLOWUPS):
            env.start_task(tid)

        # Synthetic CI, audit and landing observations exercise scheduling only.
        approve_to_wait(env, MOCK_S1)
        env.observe(MOCK_S1, "audit_result", verdict="pass", sha=pr_of(env, MOCK_S1)["head_sha"])
        self.assertEqual(pr_of(env, MOCK_S1)["merge_wait_reason"], "ready")
        land(env, MOCK_S1)
        self.assertIn(env.state(MOCK_S1), env.rules.outside("post_merge_states"))
        self.assertEqual(env.state(REAL_S1), "queued")
        for tid in FOLLOWUPS:
            self.assertEqual(env.state(tid), "blocked", tid)

        approve_to_wait(env, REAL_S1)
        self.assertFalse(env.instr(REAL_S1)["real_data_allowed"])
        self.assertEqual(env.state(REAL_S1), "audit_pending")
        env.observe(REAL_S1, "audit_result", verdict="pass", sha=pr_of(env, REAL_S1)["head_sha"])
        self.assertEqual(pr_of(env, REAL_S1)["merge_wait_reason"], "decision_pending")
        env.observe(None, "decision_record", decision_id="D-02", recorded_at=env.clock.now(),
                    recorded_by="mock-owner", source_ref="mock://decision/s1")
        self.assertEqual(pr_of(env, REAL_S1)["merge_wait_reason"], "ready")
        for tid in FOLLOWUPS:
            self.assertEqual(env.state(tid), "blocked", tid)

        land(env, REAL_S1)
        self.assertIn(env.state(REAL_S1), env.rules.outside("post_merge_states"))
        self.assertEqual(env.state("T-DT-03"), "queued")
        for tid in ("T-KN-08", "T-PS-01"):
            self.assertEqual(env.state(tid), "blocked")

        env.core.register_task("T-DT-03", "done")
        for tid in ("T-KN-08", "T-PS-01"):
            env.core.evaluate_prereqs(tid)
            self.assertEqual(env.state(tid), "queued")
