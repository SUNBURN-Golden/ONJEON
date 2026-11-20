"""Keep the full real-adapter suite wired to changes in its inputs."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/runner-verify.yml"
BUNDLE = "docs/blueprint/proposals/설계검토_결과"
RUN_SUITE = "python3 -m unittest discover -s tools/daemon/runner_verify/tests -v"


def block(lines, heading):
    """Return the lines indented below a heading in the workflow's block layout."""
    start = lines.index(heading) + 1
    indent = len(heading) - len(heading.lstrip())
    end = next((i for i in range(start, len(lines))
                if len(lines[i]) - len(lines[i].lstrip()) <= indent), len(lines))
    return lines[start:end]


class RunnerVerifyWorkflow(unittest.TestCase):
    def setUp(self):
        self.lines = [line for line in (ROOT / WORKFLOW).read_text(encoding="utf-8").splitlines()
                      if line.strip() and not line.lstrip().startswith("#")]

    def test_push_and_pull_request_filter_on_runner_inputs(self):
        triggers = block(self.lines, "on:")
        expected_paths = {
            WORKFLOW,
            "tools/daemon/**",  # Shared Ports, real adapters, fixtures and tests.
            f"{BUNDLE}/daemon_rules.json",
            f"{BUNDLE}/tasks.json",
            "docs/vm_check/**",
        }
        for event, filters in (("push", ['    branches: [main, "claude/**"]']), ("pull_request", [])):
            with self.subTest(event=event):
                event_lines = block(triggers, f"  {event}:")
                paths = block(event_lines, "    paths:")
                self.assertEqual({line.strip().removeprefix("- ").strip("'\"") for line in paths},
                                 expected_paths)
                self.assertEqual(event_lines, filters + ["    paths:"] + paths)

    def test_runner_job_uses_full_discovery_and_blocks_on_failures(self):
        job = block(block(self.lines, "jobs:"), "  runner-verify:")
        self.assertIn("    runs-on: ubuntu-latest", job)
        self.assertEqual([line.strip() for line in job if line.lstrip().startswith("run:")],
                         [f"run: {RUN_SUITE}"])
        self.assertNotRegex("\n".join(job), r"(?m)^ +(?:- )?(?:if|continue-on-error|needs|working-directory):")


if __name__ == "__main__":
    unittest.main()
