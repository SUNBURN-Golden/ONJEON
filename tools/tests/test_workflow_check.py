import os
import re
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

    def test_job_override_is_detected_in_quoted_jobs_block(self):
        text = GOOD.replace('jobs:\n  a:\n', '"jobs":\n  a:\n    permissions: write-all\n')
        self.assertTrue(any("job-level" in p for p in workflow_check.check(text)))

    def test_job_can_declare_the_same_read_only_permissions(self):
        text = GOOD.replace("  a:\n", "  a:\n    permissions:\n      contents: read\n")
        self.assertEqual(workflow_check.check(text), [])

    def test_step_script_text_does_not_override_job_permissions(self):
        text = GOOD.replace("      - run: echo hi\n", "      - run: |\n          permissions: write-all\n")
        self.assertEqual(workflow_check.check(text), [])

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

    def test_source_checkouts_do_not_persist_credentials(self):
        path = os.path.join(REPO, ".github", "workflows", "sources.yml")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(workflow_check.check(text), [])
        settings = list(re.finditer(
            r"(?m)^      - uses: actions/checkout@[^\n]+\n"
            r"        with:\n(?P<setting>          persist-credentials: false\n)", text
        ))
        self.assertEqual(len(settings), 2)
        for setting in settings:
            for replacement in ("", "          persist-credentials: true\n"):
                with self.subTest(offset=setting.start(), replacement=replacement):
                    mutated = (text[:setting.start("setting")] + replacement
                               + text[setting.end("setting"):])
                    problems = workflow_check.check(mutated)
                    self.assertEqual(len(problems), 1)
                    self.assertIn("persist-credentials: false", problems[0])


if __name__ == "__main__":
    unittest.main()
