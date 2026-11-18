"""Keep the Audit 7 merge record traceable to the task contract and local history."""

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
REPORT = ROOT / "docs/blueprint/audits/2026-11-18_s0_critical_path_merge.md"
TASKS_IN_REVIEW = {
    "T-CT-01", "T-CT-02", "T-CT-03", "T-CT-04", "T-CT-05", "T-CT-06",
    "T-OP-01", "T-OP-09", "T-KN-01", "T-KN-03", "T-DT-01",
}


def read(path):
    return path.read_text(encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


class Audit7CriticalPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = re.findall(r"^\| (T-[A-Z]+-\d+) \| ([^|]+) \| `([a-f0-9]+)` \|$",
                          read(REPORT), re.MULTILINE)
        cls.rows = {task: (set(re.findall(r"T-[A-Z]+-\d+", prerequisites)), sha)
                    for task, prerequisites, sha in rows}
        if len(rows) != len(cls.rows):
            raise AssertionError("Duplicate task in Audit 7 merge record")

    def test_report_covers_both_prerequisites_and_the_named_followups(self):
        tasks = {t["id"]: t for t in json.loads(read(BUNDLE / "tasks.json"))["tasks"]}
        self.assertEqual(set(self.rows), TASKS_IN_REVIEW)
        for task, (prerequisites, _) in self.rows.items():
            with self.subTest(task=task):
                self.assertEqual(prerequisites, set(tasks[task]["prereq_tasks"]))

    def test_status_and_purpose_table_link_to_the_audit_record(self):
        blueprint = ROOT / "docs/BLUEPRINT.md"
        purpose = BUNDLE / "09_제품목적_대응표.md"
        for path, heading in ((blueprint, "## 11. "), (purpose, "## 7. ")):
            with self.subTest(path=path.name):
                section = read(path).split(heading, 1)[1].split("\n## ", 1)[0]
                links = re.findall(r"\]\(([^)]+)\)", section)
                self.assertIn(REPORT, {(path.parent / link).resolve() for link in links})

    def test_merges_are_in_first_parent_history_in_prerequisite_order(self):
        if git("rev-parse", "--is-shallow-repository") == "true":
            self.skipTest("merge ancestry requires full Git history")
        history = git("log", "--first-parent", "--merges", "--format=%H%x09%s", "HEAD")
        merges = {sha: (position, subject) for position, (sha, subject) in enumerate(
            line.split("\t", 1) for line in history.splitlines()
        )}
        positions = {}
        for task, (_, sha) in self.rows.items():
            with self.subTest(task=task, merge=sha):
                position, subject = merges[git("rev-parse", f"{sha}^{{commit}}")]
                self.assertTrue(subject.endswith(f"/onjeon-{task}"), subject)
                positions[task] = position
        for task, (prerequisites, _) in self.rows.items():
            for prerequisite in prerequisites & positions.keys():
                with self.subTest(task=task, prerequisite=prerequisite):
                    self.assertGreater(positions[prerequisite], positions[task])
        for task in ("T-CT-01", "T-OP-01"):
            self.assertGreater(positions["T-OP-09"], positions[task])
