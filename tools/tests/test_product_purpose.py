"""CI regression guard for 09 -> tasks.json; no release completion is claimed.

Lives in tools/tests because the existing CI workflow discovers this directory.
All mutations use temporary inputs; the protected design bundle stays read-only.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CI = Path(__file__).resolve().parents[1] / "ci"
sys.path.insert(0, str(CI))
import check_product_purpose as P  # noqa: E402


class ProductPurposeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tasks = self.root / "tasks.json"
        self.purpose = self.root / "purpose.md"
        self.data = {"tasks": [
            {"id": "T-AA-01", "required_test_ids": sorted(P.REQUIRED_TEST_IDS)},
            {"id": "T-AA-02", "required_test_ids": []},
        ]}
        self.text = "| # | 제품 목적 | 구현 작업(tasks.json) | 완료 증거 |\n|---|---|---|---|\n" + "".join(
            f"| P{i:02} | purpose | T-AA-01, T-AA-02 | T-ZZ-99 is an evidence reference |\n"
            for i in range(1, 20))

    def write(self):
        self.tasks.write_text(json.dumps(self.data), encoding="utf-8")
        self.purpose.write_text(self.text, encoding="utf-8")

    def check(self):
        self.write()
        return P.check(self.tasks, self.purpose)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(CI / "check_product_purpose.py"), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True)

    def test_real_repo_product_purpose_links(self):
        # This is the live CI guard: removing an ID or adding a dangling P-row task fails CI.
        self.assertEqual([], P.check(P.C.ROOT / P.DEFAULT_TASKS, P.C.ROOT / P.DEFAULT_PURPOSE))

    def test_required_ids_match_all_nine_in_section_six(self):
        text = (P.C.ROOT / P.DEFAULT_PURPOSE).read_text(encoding="utf-8")
        section = text.split("## 6.", 1)[1].split("## 7.", 1)[0]
        ids = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", section))
        self.assertEqual(9, len(ids))
        self.assertEqual(ids, P.REQUIRED_TEST_IDS)

    def test_registered_ids_and_shared_row_tasks_pass(self):
        self.assertEqual([], self.check())

    def test_required_id_on_any_task_passes(self):
        tests = self.data["tasks"][0]["required_test_ids"]
        self.data["tasks"][0]["required_test_ids"] = tests[:4]
        self.data["tasks"][1]["required_test_ids"] = tests[4:]
        self.assertEqual([], self.check())

    def test_each_of_nine_missing_ids_fails_for_g12(self):
        for test_id in sorted(P.REQUIRED_TEST_IDS):
            with self.subTest(test_id=test_id):
                self.data["tasks"][0]["required_test_ids"] = sorted(P.REQUIRED_TEST_IDS - {test_id})
                found = self.check()
                self.assertEqual(["PURPOSE-G12"], [f.rule for f in found])
                self.assertIn(test_id, found[0].message)

    def test_id_in_tests_or_done_criteria_is_not_registration(self):
        task = self.data["tasks"][0]
        task["required_test_ids"].remove("purpose-rows-all-closed")
        task["tests"] = ["purpose-rows-all-closed"]
        task["done_criteria"] = ["purpose-rows-all-closed"]
        self.assertEqual(["PURPOSE-G12"], [f.rule for f in self.check()])

    def test_every_row_rejects_unknown_task_with_row_and_line(self):
        original = self.text
        for i in range(1, 20):
            row = f"P{i:02}"
            with self.subTest(row=row):
                self.text = original.replace(f"| {row} | purpose | T-AA-01, T-AA-02 |",
                                             f"| {row} | purpose | T-AA-01, T-AA-99 |")
                found = self.check()
                self.assertEqual(["PURPOSE-TASK"], [f.rule for f in found])
                self.assertIn(row, found[0].message)
                self.assertIn("T-AA-99", found[0].message)
                self.assertEqual(i + 2, found[0].line)

    def test_removing_referenced_task_fails_all_rows(self):
        self.data["tasks"].pop()
        found = self.check()
        self.assertEqual(19, len(found))
        self.assertEqual({"PURPOSE-TASK"}, {f.rule for f in found})

    def test_repeated_headers_and_inline_code_task_ids_pass(self):
        self.text = self.text.replace("T-AA-01, T-AA-02", "`T-AA-01`, `T-AA-02`")
        self.text = self.text.replace("| P10 |", "\n## Another table\n\n| # | 제품 목적 | 구현 작업 | 완료 증거 |\n|---|---|---|---|\n| P10 |")
        self.assertEqual([], self.check())

    def test_missing_duplicate_unexpected_or_unparseable_rows_fail(self):
        original = self.text
        bad_texts = [
            "",
            original.replace("P19", "P18"),
            original.replace("P19", "P20"),
            original.replace("구현 작업(tasks.json)", "wrong column"),
            original.replace("T-AA-01, T-AA-02", ""),
            original.replace("T-AA-01, T-AA-02", "T-AA-01, typo"),
            original.replace("| P19 | purpose | T-AA-01, T-AA-02 | T-ZZ-99 is an evidence reference |",
                             "| P19 | purpose |"),
        ]
        for text in bad_texts:
            with self.subTest(text=text[:100]):
                self.text = text
                self.assertIn("PURPOSE-ROWS", {f.rule for f in self.check()})

    def test_cli_passes_from_other_cwd_and_reports_findings(self):
        self.write()
        args = ("--tasks", self.tasks, "--purpose", self.purpose)
        result = self.cli(*args)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("static only", result.stdout)
        self.text = self.text.replace("T-AA-02", "T-AA-99")
        self.write()
        result = self.cli(*args)
        self.assertEqual(1, result.returncode)
        self.assertIn("PURPOSE-TASK", result.stdout)
        self.assertIn("P19", result.stdout)

    def test_cli_root_selects_bundle(self):
        self.write()
        (self.root / P.BUNDLE).mkdir(parents=True)
        self.tasks.rename(self.root / P.DEFAULT_TASKS)
        self.purpose.rename(self.root / P.DEFAULT_PURPOSE)
        result = self.cli("--root", self.root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_cli_bad_input_is_error(self):
        for content in ("not json", "{}", '{"tasks": {}}',
                        '{"tasks": [{"id": "T-AA-01", "required_test_ids": "wrong"}]}',
                        '{"tasks": [{"id": "bad"}]}',
                        '{"tasks": [{"id": "T-AA-01"}, {"id": "T-AA-01"}]}'):
            with self.subTest(content=content):
                self.write()
                self.tasks.write_text(content, encoding="utf-8")
                result = self.cli("--tasks", self.tasks, "--purpose", self.purpose)
                self.assertEqual(2, result.returncode)
                self.assertIn("cannot read product-purpose inputs", result.stderr)
        self.assertEqual(2, self.cli("--root", self.root / "missing").returncode)
        self.assertEqual(2, self.cli("--unknown").returncode)

    def test_selftest(self):
        result = self.cli("--selftest")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
