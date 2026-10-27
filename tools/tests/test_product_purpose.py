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
        self.data = {"tasks": P.fixture_tasks()}
        self.text = "| # | 제품 목적 | 구현 작업(tasks.json) | 완료 증거 | 축소·후속(근거) |\n|---|---|---|---|---|\n" + "".join(
            f"| P{i:02} | purpose | T-AA-01, T-AA-02 | T-ZZ-99 is an evidence reference | — |\n"
            for i in range(1, 20))

    def task(self, tid):
        return next(task for task in self.data["tasks"] if task["id"] == tid)

    def move_test(self, test_id, to):
        for task in self.data["tasks"]:
            if test_id in task["required_test_ids"]:
                task["required_test_ids"].remove(test_id)
        self.task(to)["required_test_ids"].append(test_id)

    def plant(self, rel, text="x\n"):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def scope(self, row, cell):
        self.text = self.text.replace(f"| {row} | purpose | T-AA-01, T-AA-02 | T-ZZ-99 is an evidence reference | — |",
                                      f"| {row} | purpose | T-AA-01, T-AA-02 | T-ZZ-99 is an evidence reference | {cell} |")

    def check_in_root(self):
        self.write()
        return P.check(self.tasks, self.purpose, self.root)

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

    def test_owner_map_matches_section_six(self):
        text = (P.C.ROOT / P.DEFAULT_PURPOSE).read_text(encoding="utf-8")
        section = text.split("## 6.", 1)[1].split("## 7.", 1)[0]
        owners = {}
        for group, tasks in re.findall(r"((?:`[a-z-]+`·?)+)\(([^)]*)\)", section):
            for test_id in re.findall(r"`([a-z-]+)`", group):
                owners[test_id] = frozenset(re.findall(r"T-[A-Z]{2}-\d{2}", tasks))
        self.assertEqual(P.TEST_OWNERS, owners)

    def test_real_repo_registers_each_id_on_an_owner(self):
        tasks = json.loads((P.C.ROOT / P.DEFAULT_TASKS).read_text(encoding="utf-8"))["tasks"]
        for test_id, owners in P.TEST_OWNERS.items():
            with self.subTest(test_id=test_id):
                self.assertTrue(any(test_id in t.get("required_test_ids", []) for t in tasks if t["id"] in owners))

    def test_ids_split_across_owners_and_extra_non_owner_copy_pass(self):
        self.data["tasks"] += [{"id": tid, "required_test_ids": []} for tid in ("T-MB-03", "T-MB-04")]
        self.move_test("first-view-priority", "T-MB-03")
        self.move_test("no-composite-score", "T-MB-04")
        self.task("T-AA-01")["required_test_ids"].append("label-kinds-complete")
        self.assertEqual([], self.check())

    def test_each_id_moved_to_non_owner_fails_for_owner(self):
        original = json.dumps(self.data)
        for test_id in sorted(P.REQUIRED_TEST_IDS):
            with self.subTest(test_id=test_id):
                self.data = json.loads(original)
                self.move_test(test_id, "T-AA-01")
                found = [f for f in self.check() if f.rule == "PURPOSE-OWNER"]
                self.assertEqual(1, len(found))
                self.assertIn(test_id, found[0].message)
                self.assertIn("T-AA-01", found[0].message)
                expected = {"PURPOSE-OWNER", "PURPOSE-GATE"} if test_id == P.GATE_TEST else {"PURPOSE-OWNER"}
                self.assertEqual(expected, {f.rule for f in self.check()})

    def test_each_of_nine_missing_ids_fails_for_g12(self):
        for test_id in sorted(P.REQUIRED_TEST_IDS):
            with self.subTest(test_id=test_id):
                self.data = {"tasks": P.fixture_tasks()}
                for task in self.data["tasks"]:
                    task["required_test_ids"] = [t for t in task["required_test_ids"] if t != test_id]
                found = [f for f in self.check() if f.rule != "PURPOSE-GATE"]
                self.assertEqual(["PURPOSE-G12"], [f.rule for f in found])
                self.assertIn(test_id, found[0].message)

    def test_id_in_tests_or_done_criteria_is_not_registration(self):
        task = self.task("T-OP-08")
        task["required_test_ids"].remove("purpose-rows-all-closed")
        task["tests"].append("purpose-rows-all-closed")
        task["done_criteria"] = ["purpose-rows-all-closed"]
        self.assertEqual(["PURPOSE-G12", "PURPOSE-GATE"], [f.rule for f in self.check()])

    def test_gate_removed_or_weakened_fails(self):
        def drop_task(data):
            data["tasks"] = [t for t in data["tasks"] if t["id"] != "T-OP-08"]
        mutations = {
            "not final_gate": lambda data: self.task("T-OP-08").update(final_gate=False),
            "final_gate missing": lambda data: self.task("T-OP-08").pop("final_gate"),
            "command removed": lambda data: self.task("T-OP-08").update(tests=["시험 purpose-rows-all-closed"]),
            "no --purpose": lambda data: self.task("T-OP-08").update(
                tests=["python3 -I tools/release_readiness/check.py --evidence docs/release-readiness/evidence/"]),
            "other evidence dir": lambda data: self.task("T-OP-08").update(
                tests=[" ".join(P.GATE_COMMAND).replace("docs/release-readiness/evidence/", "/tmp/")]),
            "other checker": lambda data: self.task("T-OP-08").update(
                tests=[" ".join(P.GATE_COMMAND).replace("release_readiness/check.py", "noop.py")]),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                self.data = {"tasks": P.fixture_tasks()}
                mutate(self.data)
                found = self.check()
                self.assertEqual(["PURPOSE-GATE"], [f.rule for f in found])
                self.assertIn("T-OP-08", found[0].message)
        self.data = {"tasks": P.fixture_tasks()}
        drop_task(self.data)
        self.assertIn("PURPOSE-GATE", {f.rule for f in self.check()})
        self.assertIn("missing", [f for f in self.check() if f.rule == "PURPOSE-GATE"][0].message)

    def test_real_gate_command_shape(self):
        tasks = json.loads((P.C.ROOT / P.DEFAULT_TASKS).read_text(encoding="utf-8"))["tasks"]
        gate = next(t for t in tasks if t["id"] == "T-OP-08")
        self.assertEqual([], P.check_gate("tasks.json", {"T-OP-08": gate}))
        self.assertEqual(["T-OP-08"], [t["id"] for t in tasks if t.get("final_gate")])

    def test_scope_cell_needs_resolvable_basis(self):
        self.plant("docs/decisions/ADR-0018-범위.md")
        self.plant("docs/decisions/DEC-O04.md")
        self.plant("docs/decisions/DEC-D-12.md")
        self.plant("docs/blueprint/DECISIONS.md", "| # | 항목 |\n|---|---|\n| O04 | 가격 |\n")
        self.plant("docs/BLUEPRINT.md", "# 설계\n\n## 1. 북극성\n\n### 7.1 범위\n")
        cases = {
            "ADR-0018 확정": None,
            "가격은 DEC-O04 뒤": None,
            "원문은 D-12 뒤": None,
            "가격 열은 O04 뒤(결정 대기)": None,
            "정본 BLUEPRINT §1 A7이 후속": None,
            "BLUEPRINT §7.1과 D-12": None,
            "후속": "cites no basis",
            "D12 뒤": "cites no basis",
            "DEC-D-12의 D-120": None,  # D-120 is not a D-nn reference
            "ADR-0099 확정": "ADR-0099",
            "D-18 뒤": "D-18",
            "DEC-D-99 뒤": "DEC-D-99",
            "O05 뒤": "O05",
            "BLUEPRINT §9 뒤": "BLUEPRINT §9",
            "D-12와 D-77": "D-77",
        }
        original = self.text
        for cell, problem in cases.items():
            with self.subTest(cell=cell):
                self.text = original
                self.scope("P07", cell)
                found = self.check_in_root()
                if problem is None:
                    self.assertEqual([], found)
                else:
                    self.assertEqual(["PURPOSE-SCOPE"], [f.rule for f in found])
                    self.assertIn("P07", found[0].message)
                    self.assertIn(problem, found[0].message)
                    self.assertEqual(9, found[0].line)

    def test_every_real_scope_cell_cites_a_basis(self):
        text = (P.C.ROOT / P.DEFAULT_PURPOSE).read_text(encoding="utf-8")
        cited = {}
        for line in text.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if re.fullmatch(r"P\d+", cells[0]) and cells[-1] != P.NO_SCOPE:
                cited[cells[0]] = set(P.BASIS.findall(cells[-1]))
        self.assertEqual({"P01", "P02", "P03", "P06", "P09", "P11", "P14", "P17", "P18", "P19"}, set(cited))
        self.assertTrue(all(cited.values()), cited)
        self.assertIn("BLUEPRINT §1", cited["P18"])

    def test_missing_scope_column_fails(self):
        self.text = self.text.replace("축소·후속(근거)", "비고")
        found = self.check()
        self.assertEqual(19, len(found))
        self.assertEqual({"PURPOSE-ROWS"}, {f.rule for f in found})
        self.assertIn("축소·후속", found[0].message)

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
        self.text = self.text.replace("| P10 |", "\n## Another table\n\n| # | 제품 목적 | 구현 작업 | 완료 증거 | 축소·후속 |\n|---|---|---|---|---|\n| P10 |")
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
            original.replace("| P19 | purpose | T-AA-01, T-AA-02 | T-ZZ-99 is an evidence reference | — |",
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
        for content in ("not json", "{}", '{"tasks": {}}', '{"tasks": [{"id": "T-OP-08", "required_test_ids": [1]}]}',
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
