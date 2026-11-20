"""Execute ci.yml's early security gate against real workflow mutations, offline.

The gate uses only stdlib Python, so it must run before dependency installation or
Rust builds. Copies and mutations stay in a temporary repository, never .github/.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
CI = WORKFLOWS / "ci.yml"
CHECKED_WORKFLOWS = (
    CI, WORKFLOWS / "sources.yml", WORKFLOWS / "pr-traceability.yml",
    WORKFLOWS / "runner-verify.yml",
)


class CiWorkflowSecurity(unittest.TestCase):
    def setUp(self):
        self.workflow = CI.read_text(encoding="utf-8")
        gates = re.findall(
            r"^      - name: Workflow token permissions and immutable action refs\n"
            r"        run: \|\n((?:          [^\n]*\n)+)",
            self.workflow, re.MULTILINE,
        )
        self.assertEqual(len(gates), 1, "ci.yml must declare one early security gate")
        self.command = "\n".join(line[10:] for line in gates[0].splitlines())

    def run_gate(self, workflow, expect_success, path=CI):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / ".github", root / ".github")
            (root / path.relative_to(ROOT)).write_text(workflow, encoding="utf-8")
            (root / "tools/tests").mkdir(parents=True)
            shutil.copy2(ROOT / "tools/workflow_check.py", root / "tools/workflow_check.py")
            shutil.copy2(ROOT / "tools/tests/test_workflow_pins.py",
                         root / "tools/tests/test_workflow_pins.py")
            # Allow scheduler contention in full-suite/shared-worktree runs. This
            # remains bounded; the commands and all negative assertions are unchanged.
            # GitHub's default Linux run shell stops on the first failing command.
            result = subprocess.run(["bash", "-e", "-c", self.command], cwd=root,
                                    capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        if expect_success:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def test_live_workflows_pass_declared_gate(self):
        self.run_gate(self.workflow, expect_success=True)

    def test_missing_or_nonminimal_permissions_fail_declared_gate(self):
        # Exercise the declared CI gate, including values that would prevent checkout
        # or grant permissions beyond this workflow's required contents read access.
        for replacement in (
            "",
            "permissions: {}\n",
            "permissions: read-all\n",
            "permissions:\n  contents: none\n",
            "permissions:\n  contents: write\n",
            "permissions:\n  contents: read\n  pull-requests: write\n",
            "permissions:\n  contents: read\npermissions: write-all\n",
        ):
            with self.subTest(replacement=replacement):
                changed = self.workflow.replace("permissions:\n  contents: read\n", replacement, 1)
                self.assertNotEqual(changed, self.workflow)
                self.assertIn("permissions", self.run_gate(changed, expect_success=False))

    def test_each_workflow_rejects_job_permission_overrides(self):
        for path in CHECKED_WORKFLOWS:
            workflow = path.read_text(encoding="utf-8")
            for override in ('"permissions": write-all', "permissions:\n      contents: write"):
                with self.subTest(workflow=path.name, override=override):
                    changed = workflow.replace("    runs-on:", f"    {override}\n    runs-on:", 1)
                    self.assertNotEqual(changed, workflow)
                    output = self.run_gate(changed, expect_success=False, path=path)
                    self.assertIn("job-level `permissions:` overrides the workflow policy", output)

    def test_each_action_rejects_mutable_or_short_refs(self):
        for path in CHECKED_WORKFLOWS:
            workflow = path.read_text(encoding="utf-8")
            refs = list(re.finditer(r"(?m)^      - uses: ([^@\s]+)@([0-9a-f]{40})", workflow))
            self.assertEqual(len(refs), workflow.count("      - uses:"))
            self.assertTrue(refs, f"{path.name} must contain pinned actions")
            for ref in refs:
                for replacement in ("v4", "main", ref[2][:12]):
                    with self.subTest(workflow=path.name, action=ref[1], line=ref.start(),
                                      replacement=replacement):
                        changed = workflow[:ref.start(2)] + replacement + workflow[ref.end(2):]
                        output = self.run_gate(changed, expect_success=False, path=path)
                        self.assertIn("third-party actions must be pinned", output)
                        self.assertIn(ref[1] + "@" + replacement, output)

    def test_each_checkout_rejects_missing_or_persisted_credentials(self):
        # Mutate each real checkout independently: another hardened checkout must
        # not hide the affected job's default (true) or explicitly enabled storage.
        for path in CHECKED_WORKFLOWS:
            workflow = path.read_text(encoding="utf-8")
            checkouts = list(re.finditer(
                r"(?m)^      - uses: actions/checkout@[^\n]+\n"
                r"        with:\n(?P<setting>          persist-credentials: false\n)",
                workflow,
            ))
            self.assertEqual(len(checkouts), workflow.count("uses: actions/checkout@"), path.name)
            self.assertTrue(checkouts, f"{path.name} must contain checkout steps")
            for checkout in checkouts:
                for replacement in ("", "          persist-credentials: true\n"):
                    with self.subTest(workflow=path.name, line=checkout.start(), replacement=replacement):
                        changed = (workflow[:checkout.start("setting")] + replacement
                                   + workflow[checkout.end("setting"):])
                        output = self.run_gate(changed, expect_success=False, path=path)
                        self.assertIn("actions/checkout without `persist-credentials: false`", output)

    def test_same_step_env_cannot_supply_checkout_credential_setting(self):
        changed = self.workflow.replace(
            "          persist-credentials: false\n",
            "          persist-credentials: true\n"
            "        env:\n"
            "          persist-credentials: false\n",
            1,
        )
        self.assertNotEqual(changed, self.workflow)
        output = self.run_gate(changed, expect_success=False)
        self.assertIn("actions/checkout without `persist-credentials: false`", output)

    def test_other_step_cannot_supply_checkout_credential_setting(self):
        changed = self.workflow.replace(
            "        with:\n          persist-credentials: false\n",
            "      - run: echo unrelated\n"
            "        env:\n          persist-credentials: false\n",
            1,
        )
        self.assertNotEqual(changed, self.workflow)
        output = self.run_gate(changed, expect_success=False)
        self.assertIn("actions/checkout without `persist-credentials: false`", output)


if __name__ == "__main__":
    unittest.main()
