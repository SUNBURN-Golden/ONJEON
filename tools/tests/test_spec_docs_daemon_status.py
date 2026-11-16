"""Audit 6: design summaries must match daemon tools and their evidence limits."""
import json
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
REPORT = ROOT / "docs/vm_check/2026-10-16/runner_verify.json"


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


class SpecDocsDaemonStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = json.loads(read(BUNDLE / "tasks.json"))["tasks"]
        cls.rules = json.loads(read(BUNDLE / "daemon_rules.json"))
        cls.report = json.loads(read(REPORT))

    def test_task_counts_match_unique_live_tasks(self):
        ids = [task["id"] for task in self.tasks]
        self.assertEqual(len(ids), len(set(ids)))
        for filename, pattern in (
            ("README.md", r"과제 (\d+)개"),
            ("그록봇_인계/README.md", r"과제 (\d+)개"),
            ("06_검토사항_점검.md", r"(\d+)개 과제"),
        ):
            with self.subTest(file=filename):
                stated = re.search(pattern, read(BUNDLE / filename))
                self.assertIsNotNone(stated)
                self.assertEqual(int(stated[1]), len(ids), filename)

    def test_r2_handoff_order_matches_rules(self):
        text = read(BUNDLE / "05_VM실행준비.md")
        row = next(line for line in text.splitlines() if line.startswith("| R2 |"))
        order = re.search(r"인계 순서\(([^)]+)\)", row)
        self.assertIsNotNone(order)
        self.assertEqual(order[1].split(" → "), self.rules["handoff_sequence"])
        self.assertEqual(self.rules["handoff_sequence"],
                         self.rules["switch_policy"]["handoff_sequence"])

    def test_checklist_covers_every_runner_scenario(self):
        text = read(BUNDLE / "05_VM실행준비.md")
        scenario_numbers = [int(n) for n in re.findall(r"^\| R(\d+) \|", text, re.M)]
        self.assertEqual(scenario_numbers, list(range(1, max(scenario_numbers) + 1)))
        checklist = section(text, "## 7.", "## 8.")
        stated = re.search(r"T-OP-09 R(\d+)~R(\d+) 보고서", checklist)
        self.assertIsNotNone(stated)
        self.assertEqual(list(range(int(stated[1]), int(stated[2]) + 1)), scenario_numbers)
        self.assertEqual({f"R{n}" for n in scenario_numbers},
                         {result["r"] for result in self.report["results"]})
        self.assertNotIn("[x] T-OP-09", checklist)

    def test_inventory_describes_implemented_tools_and_limits(self):
        text = read(BUNDLE / "README.md")
        summary = section(text, "## 7.", "## 8.")
        contract = section(read(BUNDLE / "02_구현계약.md"), "## 10.", "## 11.")
        row = next(line for line in contract.splitlines()
                   if line.startswith("| 데몬 상태 기계"))
        for current in (summary, row):
            with self.subTest(section=current[:60]):
                self.assertIn("구현됨", current)
                for path in ("tools/daemon/core/", "tools/daemon/runner_verify/"):
                    self.assertIn(path, current)
                    self.assertTrue((ROOT / path).is_dir())
                self.assertIn("개발 도구", current)
                self.assertIn("상주 데몬", current)
        self.assertNotIn("둘 다 아직 없다", text)
        self.assertNotIn("T-OP-00·T-OP-09 없음", text)
        self.assertNotIn("규칙 파일만 있음", row)
        handoff = read(BUNDLE / "그록봇_인계/README.md")
        self.assertNotIn("실제 실행기(T-OP-09)는 없다", handoff)

    def test_each_status_summary_links_results_and_preserves_partial_results(self):
        counts = Counter(result["status"] for result in self.report["results"])
        partial = {result["r"] for result in self.report["results"]
                   if result["status"] == "PARTIAL"}
        for filename in ("README.md", "02_구현계약.md", "05_VM실행준비.md",
                         "그록봇_인계/README.md"):
            with self.subTest(file=filename):
                path = BUNDLE / filename
                text = read(path)
                self.assertIn(f"PASS {counts['PASS']}·PARTIAL {counts['PARTIAL']}", text)
                self.assertIn(f"FAIL {counts['FAIL']}", text)
                self.assertTrue(partial <= set(re.findall(r"(?<![A-Za-z0-9])R\d+(?![A-Za-z0-9])", text)))
                links = re.findall(r"\]\(([^)]+/RESULTS\.md)\)", text)
                self.assertTrue(links, "historical runner results must be linked")
                self.assertTrue(REPORT.with_name("RESULTS.md").is_file())
                self.assertTrue(any((path.parent / link).resolve() == REPORT.with_name("RESULTS.md")
                                    for link in links))
                self.assertIn("가동 승인", text)
                self.assertIn("첫 출시", text)


if __name__ == "__main__":
    unittest.main()
