import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import workflow_check  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..", "..")

GOOD = """name: ci
on:
  pull_request:

permissions:
  contents: read

jobs:
  a:
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - run: echo hi
  b:
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false  # no token for PR-head code
"""


class WorkflowCheckTest(unittest.TestCase):
    def test_hardened_passes(self):
        self.assertEqual(workflow_check.check(GOOD), [])

    def test_missing_permissions(self):
        text = GOOD.replace("permissions:\n  contents: read\n", "")
        self.assertTrue(any("permissions" in p for p in workflow_check.check(text)))

    def test_too_broad_permissions(self):
        text = GOOD.replace("contents: read", "contents: write")
        self.assertTrue(any("exactly" in p for p in workflow_check.check(text)))
        text = GOOD.replace("contents: read", "contents: read\n  pull-requests: write")
        self.assertTrue(any("exactly" in p for p in workflow_check.check(text)))

    def test_job_level_permissions_do_not_count(self):
        text = GOOD.replace("\npermissions:\n  contents: read\n", "").replace(
            "  a:\n", "  a:\n    permissions:\n      contents: read\n"
        )
        self.assertTrue(any("top-level" in p for p in workflow_check.check(text)))

    def test_checkout_without_with(self):
        text = GOOD.replace("        with:\n          persist-credentials: false\n", "", 1)
        probs = workflow_check.check(text)
        self.assertEqual(len(probs), 1)
        self.assertIn("persist-credentials", probs[0])

    def test_checkout_persist_true(self):
        text = GOOD.replace("persist-credentials: false", "persist-credentials: true", 1)
        self.assertEqual(len(workflow_check.check(text)), 1)

    def test_persist_false_of_a_later_step_does_not_count(self):
        text = GOOD.replace("        with:\n          persist-credentials: false\n", "", 1).replace(
            "      - run: echo hi\n", "      - run: echo hi\n        with:\n          persist-credentials: false\n"
        )
        self.assertEqual(len(workflow_check.check(text)), 1)

    def test_no_checkout_is_an_error(self):
        self.assertTrue(workflow_check.check("permissions:\n  contents: read\njobs: {}\n"))

    def test_repo_ci_yml_is_hardened(self):
        path = os.path.join(REPO, ".github", "workflows", "ci.yml")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(workflow_check.check(f.read()), [])


if __name__ == "__main__":
    unittest.main()
