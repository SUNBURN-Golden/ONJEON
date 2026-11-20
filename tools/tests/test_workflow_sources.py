"""Check source setup and failure handling with no network or credentials."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/sources.yml"
LISTING = "Every archived key matches the pinned listing"
REPRODUCE = "Reproduce from the archive"
DETECT_LOCK = "requirements-sources-detect.txt"
REPRODUCE_LOCK = "requirements-sources-reproduce.txt"


class WorkflowSources(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def step(self, text, name):
        blocks = re.split(r"(?m)^      - ", text)[1:]
        matching = [block for block in blocks if block.startswith(f"name: {name}\n")]
        self.assertEqual(len(matching), 1, name)
        return matching[0]

    def assert_failure_handling(self, text):
        detect, reproduce = text.split("  reproduce:\n", 1)
        self.assertLess(reproduce.index(f"      - name: {LISTING}\n"),
                        reproduce.index(f"      - name: {REPRODUCE}\n"))
        for name in (LISTING, REPRODUCE):
            step = self.step(reproduce, name)
            self.assertNotRegex(step, r"(?m)^        (?:if|continue-on-error):",
                                f"{name} must require success and propagate failure")
        self.assertRegex(self.step(detect, "Per-source result"),
                         r"(?m)^        if: \$\{\{ !cancelled\(\) \}\}$")

        unconditional = re.findall(
            r"(?m)^      - ([^\n]+)\n        if: always\(\)$", text
        )
        self.assertEqual(len(unconditional), 2)
        self.assertTrue(all(step.startswith("uses: actions/upload-artifact@")
                            for step in unconditional))
        code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
        self.assertEqual(sum(len(re.findall(r"\balways\s*\(", line)) for line in code), 2)
        self.assertIn('with: { name: reproduce-report, path: "${{ runner.temp }}/*.json" }',
                      reproduce)

    def test_only_artifact_uploads_run_unconditionally(self):
        self.assert_failure_handling(self.workflow)

    def test_failure_handling_regressions_are_rejected(self):
        self.assert_failure_handling(self.workflow)
        for name, setting in ((REPRODUCE, "if: always()"), (REPRODUCE, "if: failure()"),
                              (LISTING, "continue-on-error: true")):
            with self.subTest(step=name, setting=setting):
                header = f"      - name: {name}\n"
                mutated = self.workflow.replace(header, f"{header}        {setting}\n", 1)
                self.assertNotEqual(mutated, self.workflow)
                with self.assertRaisesRegex(AssertionError, "must require success"):
                    self.assert_failure_handling(mutated)

    def test_listing_shell_propagates_budget_stop_from_either_tool_call(self):
        listing = self.step(self.workflow, LISTING)
        self.assertIn("        shell: bash\n", listing)
        body = re.search(r"(?m)^        run: \|\n((?:          [^\n]*\n)+)", listing)
        self.assertIsNotNone(body)
        script = "\n".join(line[10:] for line in body[1].splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python = root / "python3"
            python.write_text(
                f"#!{sys.executable}\n"
                "import os, sys\n"
                "from pathlib import Path\n"
                "report = Path(sys.argv[sys.argv.index('--report') + 1])\n"
                "with Path(os.environ['CALLS']).open('a') as out:\n"
                "    print(report.name, file=out)\n"
                "if report.name == os.environ['BUDGET_STOP']:\n"
                "    sys.exit(4)\n"
                "report.write_text('{}')\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            reports = ["listing_raw.json", "listing_derived.json"]
            for index, stop in enumerate(reports):
                with self.subTest(stop=stop):
                    runner = root / str(index)
                    runner.mkdir()
                    calls = runner / "calls"
                    result = subprocess.run(
                        ["/bin/bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
                        cwd=root, text=True, capture_output=True, timeout=10,
                        env={"PATH": str(root), "RUNNER_TEMP": str(runner), "CALLS": str(calls),
                             "BUDGET_STOP": stop, "JOB": "job.json", "ONJEON_RAW_BUCKET": "raw",
                             "ONJEON_DERIVED_BUCKET": "derived"},
                    )
                    self.assertEqual(result.returncode, 4, result.stderr)
                    self.assertEqual(calls.read_text().splitlines(), reports[:index + 1])
                    self.assertEqual(sorted(path.name for path in runner.glob("*.json")),
                                     reports[:index])

    def test_installers_require_hashes_and_wheels_from_their_lock(self):
        detect, reproduce = self.workflow.split("  reproduce:\n", 1)
        for job, lock in ((detect, DETECT_LOCK), (reproduce, REPRODUCE_LOCK)):
            with self.subTest(lock=lock):
                extractors = self.step(job, "Extractors")
                commands = [line.strip() for line in extractors.splitlines() if "/pip" in line]
                self.assertEqual(commands, [
                    '"$RUNNER_TEMP/venv/bin/pip" install --quiet --require-hashes '
                    f"--only-binary=:all: -r tools/ci/{lock}"
                ])

    def test_lock_files_pin_and_hash_each_requirement(self):
        for name, root_pin, includes in (
            (DETECT_LOCK, "pdfplumber==0.11.10", []),
            (REPRODUCE_LOCK, "boto3==1.43.100", [f"-r {DETECT_LOCK}"]),
        ):
            with self.subTest(lock=name):
                text = (ROOT / "tools/ci" / name).read_text(encoding="utf-8")
                lines = [line.strip() for line in text.replace("\\\n", "").splitlines()
                         if line.strip() and not line.startswith("#")]
                self.assertEqual([line for line in lines if line.startswith("-r ")], includes)
                pins = [line for line in lines if line not in includes]
                self.assertIn(root_pin, [line.split()[0] for line in pins])
                for line in pins:
                    self.assertRegex(line, r"^[\w.-]+==[\w.]+(?:\s+--hash=sha256:[0-9a-f]{64})+$")


if __name__ == "__main__":
    unittest.main()
