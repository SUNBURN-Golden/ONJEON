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
CI = ROOT / ".github/workflows/ci.yml"


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

    def run_gate(self, workflow, expect_success):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / ".github", root / ".github")
            (root / ".github/workflows/ci.yml").write_text(workflow, encoding="utf-8")
            (root / "tools/tests").mkdir(parents=True)
            shutil.copy2(ROOT / "tools/workflow_check.py", root / "tools/workflow_check.py")
            shutil.copy2(ROOT / "tools/tests/test_workflow_pins.py",
                         root / "tools/tests/test_workflow_pins.py")
            # GitHub's default Linux run shell stops on the first failing command.
            result = subprocess.run(["bash", "-e", "-c", self.command], cwd=root,
                                    capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        if expect_success:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def test_live_workflows_pass_declared_gate(self):
        self.run_gate(self.workflow, expect_success=True)

    def test_missing_or_write_permissions_fail_declared_gate(self):
        for replacement in ("", "permissions:\n  contents: write\n"):
            with self.subTest(replacement=replacement):
                changed = self.workflow.replace("permissions:\n  contents: read\n", replacement, 1)
                self.assertNotEqual(changed, self.workflow)
                self.assertIn("permissions", self.run_gate(changed, expect_success=False))

    def test_each_ci_action_rejects_mutable_or_short_refs(self):
        refs = list(re.finditer(r"(?m)^      - uses: ([^@\s]+)@([0-9a-f]{40})", self.workflow))
        self.assertTrue(refs, "ci.yml must contain pinned actions")
        for ref in refs:
            for replacement in ("v4", "main", ref[2][:12]):
                with self.subTest(action=ref[1], line=ref.start(), replacement=replacement):
                    changed = self.workflow[:ref.start(2)] + replacement + self.workflow[ref.end(2):]
                    output = self.run_gate(changed, expect_success=False)
                    self.assertIn("third-party actions must be pinned", output)
                    self.assertIn(ref[1] + "@" + replacement, output)


if __name__ == "__main__":
    unittest.main()
