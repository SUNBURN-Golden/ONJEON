"""R2 credentials belong only to the two archive-consumer steps (Audit 2).

Stdlib contract test for sources.yml's block-style layout, like workflow_check.py.
This is deliberately not a general YAML parser: changing the guarded step/env layout
requires updating this test. No credentials, network access or extra CI dependency.
Action SHA pins and ci.yml permissions have separate workflow regression tests.
"""
import re
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / ".github/workflows/sources.yml"
CONSUMERS = (
    "Every archived key matches the pinned listing",
    "Reproduce from the archive",
)
BINDINGS = {
    "ONJEON_S3_ENDPOINT": "ONJEON_S3_ENDPOINT",
    "R2_ACCESS_KEY_ID": "R2_VERIFIER_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY": "R2_VERIFIER_SECRET_ACCESS_KEY",
    "R2_LEDGER_ACCESS_KEY_ID": "R2_LEDGER_ACCESS_KEY_ID",
    "R2_LEDGER_SECRET_ACCESS_KEY": "R2_LEDGER_SECRET_ACCESS_KEY",
}
ENV = "        env:\n" + "".join(
    f"          {key}: ${{{{ secrets.{secret} }}}}\n" for key, secret in BINDINGS.items()
)
GOOD = """name: sources
jobs:
  reproduce:
    env:
      JOB: infra/r2/jobs/initial-119.json
    steps:
      - uses: actions/checkout@SHA
      - name: Extractors
        run: pip install example
""" + "".join(
    f"      - name: {name}\n{ENV}        run: python3 -I tools/example.py\n"
    for name in CONSUMERS
) + """      - uses: actions/upload-artifact@SHA
        if: always()
"""


class WorkflowSecretScope(unittest.TestCase):
    def assert_scoped(self, text):
        # Reject credentials outside the exact env block of each named consumer,
        # including workflow/job env, scripts, action inputs and other jobs/steps.
        code = "\n".join(line for line in text.splitlines()
                         if not line.lstrip().startswith("#")) + "\n"
        chunks = re.split(r"(?m)^      - ", code)
        counts = {name: 0 for name in CONSUMERS}
        for chunk in chunks:
            name = chunk.splitlines()[0].removeprefix("name: ")
            if name in counts:
                counts[name] += 1
                envs = re.findall(r"(?m)^        env:\n((?:          [^\n]*\n)+)", chunk)
                self.assertEqual(len(envs), 1, f"{name}: exactly one step env required")
                bindings = envs[0].splitlines()
                self.assertCountEqual(bindings, ENV.splitlines()[1:],
                                      f"{name}: endpoint, verifier and ledger bindings required")
                chunk = chunk.replace("        env:\n" + envs[0], "", 1)
                self.assertIn("        run:", chunk, f"{name}: must be a run step")
                self.assertNotRegex(chunk, r"(?m)^        uses:", "actions cannot receive R2 secrets")
                self.assertNotRegex(chunk, r"\b(?:pip|apt-get)\b", "install before receiving secrets")
            self.assertNotRegex(chunk, r"\bsecrets\s*[.\[]", "secret outside consumer step env")
            for key in BINDINGS:
                self.assertNotRegex(chunk, rf"(?m)^\s*{key}:\s*", "credential env outside consumer")
        self.assertEqual(counts, {name: 1 for name in CONSUMERS})

    def test_live_sources_secrets_are_step_scoped(self):
        self.assert_scoped(SOURCE.read_text(encoding="utf-8"))

    def test_consumers_receive_all_bindings(self):
        self.assert_scoped(GOOD)

    def test_workflow_or_job_env_regression_is_rejected(self):
        for prefix in ("env:\n  ", "    env:\n      "):
            for key, secret in BINDINGS.items():
                with self.subTest(scope=prefix, key=key):
                    text = GOOD.replace("jobs:\n", f"jobs:\n{prefix}{key}: ${{{{ secrets.{secret} }}}}\n")
                    with self.assertRaises(AssertionError):
                        self.assert_scoped(text)

    def test_other_steps_and_jobs_cannot_receive_secrets(self):
        for header in (
            "uses: actions/checkout@SHA", "name: Extractors",
            "uses: actions/upload-artifact@SHA", "name: Detect current source changes",
        ):
            for key, secret in BINDINGS.items():
                with self.subTest(step=header, key=key):
                    extra = f"      - {header}\n        env:\n          {key}: ${{{{ secrets.{secret} }}}}\n"
                    with self.assertRaises(AssertionError):
                        self.assert_scoped(GOOD + "  other:\n    steps:\n" + extra)

    def test_missing_duplicate_or_wrong_binding_is_rejected(self):
        for key, secret in BINDINGS.items():
            binding = f"          {key}: ${{{{ secrets.{secret} }}}}\n"
            for replacement in ("", binding * 2, binding.replace(secret + " }}", "OTHER }}")):
                with self.subTest(key=key, replacement=replacement):
                    with self.assertRaises(AssertionError):
                        self.assert_scoped(GOOD.replace(binding, replacement, 1))

    def test_secret_in_action_input_or_script_is_rejected(self):
        for location in ("        with:\n          token:", "        run: echo"):
            with self.subTest(location=location):
                with self.assertRaises(AssertionError):
                    self.assert_scoped(GOOD + location + " ${{ secrets.R2_LEDGER_SECRET_ACCESS_KEY }}\n")

    def test_install_or_action_in_consumer_is_rejected(self):
        for replacement in ("pip install example", "apt-get install example"):
            with self.subTest(replacement=replacement):
                with self.assertRaises(AssertionError):
                    self.assert_scoped(GOOD.replace("python3 -I tools/example.py", replacement, 1))
        with self.assertRaises(AssertionError):
            self.assert_scoped(GOOD.replace("        run: python3 -I tools/example.py",
                                            "        uses: actions/example@SHA", 1))

    def test_missing_or_duplicate_consumer_is_rejected(self):
        with self.assertRaises(AssertionError):
            self.assert_scoped(GOOD.replace(CONSUMERS[0], "Different step", 1))
        with self.assertRaises(AssertionError):
            self.assert_scoped(GOOD + f"      - name: {CONSUMERS[0]}\n{ENV}        run: echo example\n")


if __name__ == "__main__":
    unittest.main()
