"""Audit 4: a pull request must be traceable without editing the PR template.

The template is outside this node's allowed paths, so the guard reads the PR body.
These tests cover the check, its CI wiring and the canonical BLUEPRINT policy.
Registration is not completion evidence.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "tools/ci"
sys.path.insert(0, str(CI))
import check_pr_body_traceability as T  # noqa: E402


class BodyCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tasks = Path(self.tmp.name) / "tasks.json"
        self.tasks.write_text(json.dumps({"tasks": [
            {"id": "T-AA-01"}, {"id": "T-OP-08"},
        ]}), encoding="utf-8")

    def rules(self, body):
        return [f.rule for f in T.check(body, self.tasks)]

    def test_accepts_an_existing_task_id(self):
        self.assertEqual([], self.rules("Agent node: `audit4-x`. Task T-AA-01."))

    def test_accepts_every_p_row_in_range(self):
        for n in range(1, 20):
            with self.subTest(row=f"P{n:02}"):
                self.assertEqual([], self.rules(f"Closes P{n:02} evidence."))
                self.assertEqual([], self.rules(f"Closes P{n:02}."))

    def test_accepts_a_labelled_out_of_list_node_id(self):
        for body in ("Node `audit4-pr-template-task-field` — in scope fix",
                     "노드 ID: `audit4-pr-template-task-field`",
                     "노드 `audit4-pr-template-task-field`",
                     "`audit4-pr-template-task-field` — in scope fix"):
            with self.subTest(body=body):
                self.assertEqual([], self.rules(body))

    def test_accepts_a_bare_audit_slug_as_the_orchestrator_emits_it(self):
        # The builder PR body names the node in prose and in an evidence path, with no
        # backticks; CI must still recognise it (round 3 regression).
        for body in ("Node audit4-pr-template-task-field — in scope fix",
                     "Builder node: audit4-pr-template-task-field.",
                     "[evidence](/workspace/onjeon-run/wt/audit4-pr-template-task-field/"
                     "tools/evidence/audit4-pr-template-task-field/README.md)"):
            with self.subTest(body=body):
                self.assertEqual([], self.rules(body))

    def test_accepts_the_round_2_builder_pr_body_snapshot(self):
        # Snapshot of the body that failed CI run 41771859128: the slug appears only
        # un-backticked in prose and in an evidence path.
        body = (ROOT / "tools/evidence/audit4-pr-template-task-field"
                / "actual-pr-body.md").read_text(encoding="utf-8")
        self.assertEqual([], self.rules(body))

    def test_rejects_an_empty_or_unlabelled_body(self):
        for body in ("", "Fixes a typo in the README.",
                     "example-node",
                     "audit4",
                     "Xaudit4-example-node",
                     "P00 P20", "T-aa-01"):
            with self.subTest(body=body):
                self.assertIn("PR-TRACE-MISSING", self.rules(body))

    def test_rejects_a_task_id_that_is_not_in_tasks_json(self):
        self.assertEqual(["PR-TRACE-TASK"], self.rules("T-ZZ-99"))
        # A valid P row does not excuse a named task ID that does not exist.
        self.assertEqual(["PR-TRACE-TASK"], self.rules("T-ZZ-99 P01"))

    def test_task_id_must_stand_on_token_boundaries(self):
        self.assertEqual([], self.rules("T-AA-01."))
        self.assertIn("PR-TRACE-MISSING", self.rules("XT-AA-01"))
        self.assertIn("PR-TRACE-MISSING", self.rules("T-AA-001"))


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "tasks.json").write_text(
            json.dumps({"tasks": [{"id": "T-AA-01"}]}), encoding="utf-8")

    def run_check(self, *args, env=None):
        base = {k: v for k, v in os.environ.items() if k != "PR_BODY"}
        base.update(env or {})
        return subprocess.run(
            [sys.executable, "-I", str(CI / "check_pr_body_traceability.py"),
             "--tasks", str(self.root / "tasks.json"), *args],
            capture_output=True, text=True, env=base, timeout=30)

    def test_body_file_and_exit_codes(self):
        body = self.root / "body.md"
        body.write_text("Node `audit4-example`", encoding="utf-8")
        self.assertEqual(0, self.run_check("--body-file", str(body)).returncode)
        body.write_text("no trace handle", encoding="utf-8")
        failed = self.run_check("--body-file", str(body))
        self.assertEqual(1, failed.returncode)
        self.assertIn("PR-TRACE-MISSING", failed.stdout)

    def test_env_body_and_missing_body_usage_error(self):
        self.assertEqual(0, self.run_check(env={"PR_BODY": "P07"}).returncode)
        self.assertEqual(2, self.run_check().returncode)

    def test_decision_node_body_requires_the_missing_trace_handle(self):
        # Runs 41795807949 and 41804857097 supplied the same body without a node.
        # Exercise PR_BODY as CI does and the supervisor's --body-file preflight.
        evidence = ROOT / "tools/evidence/audit4-decision-id-collision/fix-round2"
        before = (evidence / "pr-body-before.txt").read_text(encoding="utf-8")
        after = (evidence / "pr-body.txt").read_text(encoding="utf-8")
        trace = "Node `audit4-decision-id-collision`\n\n"
        self.assertEqual(trace + before, after)
        failed = self.run_check(env={"PR_BODY": before})
        self.assertEqual(1, failed.returncode)
        self.assertIn("PR-TRACE-MISSING", failed.stdout)
        for round_name in ("fix-round2", "fix-round3"):
            body_file = evidence.parent / round_name / "pr-body.txt"
            body = body_file.read_text(encoding="utf-8")
            with self.subTest(round=round_name):
                self.assertTrue(body.startswith(trace))
                for passed in (self.run_check(env={"PR_BODY": body}),
                               self.run_check("--body-file", str(body_file))):
                    self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
                # The node handle is essential: decision IDs and Refs #418 alone
                # must not accidentally become an accepted traceability fallback.
                removed = self.run_check(env={"PR_BODY": body[len(trace):]})
                self.assertEqual(1, removed.returncode)
                self.assertIn("PR-TRACE-MISSING", removed.stdout)

    def test_bad_tasks_file_is_a_usage_error(self):
        (self.root / "tasks.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(2, self.run_check("--body", "T-AA-01").returncode)


class CiWiring(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    def test_pr_body_is_passed_to_the_check_on_pull_requests_only(self):
        self.assertIn("python3 -I tools/ci/check_pr_body_traceability.py", self.workflow)
        self.assertIn("PR_BODY: ${{ github.event.pull_request.body }}", self.workflow)
        self.assertIn("if: github.event_name == 'pull_request'", self.workflow)

    def test_selftest_runs_on_every_ci_event(self):
        self.assertIn("check_pr_body_traceability.py --selftest", self.workflow)


class CanonicalPolicy(unittest.TestCase):
    def test_blueprint_requires_a_traceability_handle_in_the_pr_body(self):
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        rules = blueprint.split("## 10. 드리프트 방지 규칙", 1)[1].split("## 11.", 1)[0]
        for text in ("`tasks.json` 과제 ID", "노드 ID와 사유", "09 P행",
                     "`P01`~`P19`", "tools/ci/check_pr_body_traceability.py"):
            with self.subTest(text=text):
                self.assertIn(text, rules)

    def test_bundle_states_are_honest_about_the_template(self):
        bundle = ROOT / "docs/blueprint/proposals/설계검토_결과"
        tasks = json.loads((bundle / "tasks.json").read_text(encoding="utf-8"))
        readme = (bundle / "README.md").read_text(encoding="utf-8")
        work_spec = (bundle / "03_작업명세.md").read_text(encoding="utf-8")
        policies = {
            "tasks.json": tasks["_common_done_criteria_note"],
            "README §0.1": readme.split("## 0.1 ", 1)[1].split("## 1.", 1)[0],
            "03 §2": work_spec.split("## 2.", 1)[1].split("## 3.", 1)[0],
        }
        self.assertEqual("non_binding_until_adopted",
                         tasks["_common_done_criteria_status"])
        for name, policy in policies.items():
            with self.subTest(document=name):
                self.assertIn("check_pr_body_traceability.py", policy)
                self.assertIn("PR 템플릿은 이 노드의 허용 경로 밖이라 변경하지 않았", policy)
                self.assertNotIn("입력란을 추가했으나", policy)


if __name__ == "__main__":
    unittest.main()
