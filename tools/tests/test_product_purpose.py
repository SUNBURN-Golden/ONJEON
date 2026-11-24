"""CI regression guard for 09 -> tasks.json; no release completion is claimed.

Lives in tools/tests because the existing CI workflow discovers this directory.
All mutations use temporary inputs; the live design bundle stays read-only.
"""
import copy
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
            {"id": "T-AA-01", "required_test_ids": []},
            {"id": "T-AA-02", "required_test_ids": []},
        ]}
        owners = set().union(*P.REQUIRED_TEST_OWNERS.values(), *P.REQUIRED_ROW_OWNERS.values())
        self.data["tasks"].extend(
            {"id": owner, "required_test_ids": sorted(
                test for test, assigned in P.REQUIRED_TEST_OWNERS.items() if owner in assigned)}
            for owner in sorted(owners))
        self.text = "| # | 제품 목적 | 구현 작업(tasks.json) | 완료 증거 |\n|---|---|---|---|\n" + "".join(
            f"| P{i:02} | purpose | {', '.join(['T-AA-01', 'T-AA-02', *sorted(P.REQUIRED_ROW_OWNERS.get(f'P{i:02}', set()))])} | T-ZZ-99 is an evidence reference |\n"
            for i in range(1, 21))

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

    def test_required_ids_match_section_six(self):
        text = (P.C.ROOT / P.DEFAULT_PURPOSE).read_text(encoding="utf-8")
        section = text.split("## 6.", 1)[1].split("## 7.", 1)[0]
        ids = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", section))
        self.assertEqual(ids, P.REQUIRED_TEST_IDS)

    def test_registered_ids_and_shared_row_tasks_pass(self):
        self.assertEqual([], self.check())

    def test_additional_registration_on_other_task_passes(self):
        self.data["tasks"][0]["required_test_ids"] = sorted(P.REQUIRED_TEST_IDS)
        self.assertEqual([], self.check())

    def test_each_missing_id_fails_for_g12(self):
        original = copy.deepcopy(self.data)
        for test_id in sorted(P.REQUIRED_TEST_IDS):
            with self.subTest(test_id=test_id):
                self.data = copy.deepcopy(original)
                for task in self.data["tasks"]:
                    task["required_test_ids"] = [t for t in task["required_test_ids"] if t != test_id]
                found = self.check()
                self.assertEqual(1, sum(f.rule == "PURPOSE-G12" for f in found))
                self.assertEqual({"PURPOSE-G12", "PURPOSE-OWNER"}, {f.rule for f in found})
                self.assertIn(test_id, found[0].message)

    def test_id_in_tests_or_done_criteria_is_not_registration(self):
        task = next(t for t in self.data["tasks"] if t["id"] == "T-OP-08")
        task["required_test_ids"].remove("purpose-rows-all-closed")
        task["tests"] = ["purpose-rows-all-closed"]
        task["done_criteria"] = ["purpose-rows-all-closed"]
        self.assertEqual(["PURPOSE-G12", "PURPOSE-OWNER"], [f.rule for f in self.check()])

    def test_every_assigned_owner_is_required_even_if_id_exists_elsewhere(self):
        original = copy.deepcopy(self.data)
        for test_id, owners in P.REQUIRED_TEST_OWNERS.items():
            for owner in sorted(owners):
                with self.subTest(test_id=test_id, owner=owner):
                    self.data = copy.deepcopy(original)
                    task = next(t for t in self.data["tasks"] if t["id"] == owner)
                    task["required_test_ids"].remove(test_id)
                    task["tests"] = [test_id]
                    task["done_criteria"] = [test_id]
                    self.data["tasks"][0]["required_test_ids"] = [test_id]
                    found = self.check()
                    self.assertEqual(["PURPOSE-OWNER"], [f.rule for f in found])
                    self.assertIn(owner, found[0].message)
                    self.assertIn(test_id, found[0].message)

    def test_missing_assigned_task_fails_even_without_p_row_reference(self):
        self.data["tasks"] = [t for t in self.data["tasks"] if t["id"] != "T-AP-07"]
        found = self.check()
        self.assertEqual(["PURPOSE-OWNER"] * 3, [f.rule for f in found])
        self.assertTrue(all("T-AP-07" in f.message for f in found))

    def test_live_ownership_and_task_spec_agree(self):
        bundle = P.C.ROOT / P.BUNDLE
        tasks = {t["id"]: t for t in json.loads((bundle / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
        spec = (bundle / "03_작업명세.md").read_text(encoding="utf-8")
        # Independent acceptance matrix for this finding (not the checker's constant).
        expected = {
            "T-MB-03": {"first-view-priority", "decisive-conditions-not-hidden", "no-composite-score",
                        "mobile-screen-accessibility"},
            "T-MB-04": {"first-view-priority", "decisive-conditions-not-hidden", "no-composite-score"},
            "T-AP-07": {"first-view-priority", "decisive-conditions-not-hidden", "no-composite-score"},
            "T-AP-02": {"decisive-conditions-not-hidden"},
            "T-MB-02": {"decisive-conditions-not-hidden"},
            "T-AP-08": {"decisive-conditions-not-hidden"},
            "T-AP-09": {"no-composite-score"},
            "T-KN-04": {"profile-historical-vs-service"},
            "T-WB-01": {"public-web-accessibility"},
        }
        self.assertLessEqual(P.REQUIRED_TEST_IDS, P.REQUIRED_TEST_OWNERS.keys())
        for owner, required in expected.items():
            with self.subTest(owner=owner):
                task = tasks[owner]
                self.assertLessEqual(required, set(task["required_test_ids"]))
                for test_id in required:
                    self.assertIn(owner, P.REQUIRED_TEST_OWNERS[test_id])
                    self.assertTrue(any(test.startswith(f"시험 {test_id}") for test in task["tests"]))
                rows = [line for line in spec.splitlines()
                        if re.match(rf"^\| {owner} \| (?:path|crate):", line)]
                self.assertEqual(1, len(rows))
                cells = [c.strip() for c in rows[0].strip("|").split("|")]
                self.assertEqual(set(task["required_test_ids"]), set(cells[-1].split(", ")))
                self.assertEqual("; ".join(task["done_criteria"]), cells[-2])

    def test_live_rows_link_the_test_implementations(self):
        bundle = P.C.ROOT / P.BUNDLE
        tasks = {t["id"]: t for t in json.loads((bundle / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
        text = (bundle / "09_제품목적_대응표.md").read_text(encoding="utf-8")
        for row, owner, test_id in (
            ("P02", "T-DT-04", "acquisition-reason-not-counted"),
            ("P02", "T-AP-04", "coverage-status-counts-acquired-only"),
            ("P06", "T-KN-04", "profile-historical-vs-service"),
            ("P16", "T-MB-04", "decisive-conditions-not-hidden"),
            ("P17", "T-AP-09", "no-composite-score"),
            ("P19", "T-MB-03", "mobile-screen-accessibility"),
            ("P19", "T-WB-01", "public-web-accessibility"),
        ):
            with self.subTest(row=row):
                line = next(line for line in text.splitlines() if line.startswith(f"| {row} |"))
                cells = [c.strip() for c in line.strip("|").split("|")]
                self.assertIn(owner, cells[6].split(", "))
                self.assertIn(test_id, cells[7])
                self.assertIn(test_id, tasks[owner]["required_test_ids"])

    def test_live_rows_link_public_releases_and_mobile_scenario_tests(self):
        bundle = P.C.ROOT / P.BUNDLE
        registry = json.loads((bundle / "tasks.json").read_text(encoding="utf-8"))
        features = {feature["id"]: feature for feature in registry["feature_registry"]}
        text = (bundle / "09_제품목적_대응표.md").read_text(encoding="utf-8")
        for row, owner, feature, command in (
            ("P03", "T-WB-01", "web-releases", "npm test -- releases"),
            ("P08", "T-MB-04", "what-if", "integration_test what_if_boundary_days"),
        ):
            with self.subTest(row=row):
                line = next(line for line in text.splitlines() if line.startswith(f"| {row} |"))
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                self.assertIn(owner, cells[6].split(", "))
                self.assertIn(command.removeprefix("integration_test "), cells[7])
                self.assertIn(owner, features[feature]["tasks"])
                self.assertIn(command, features[feature]["acceptance_tests"])

    def test_live_requirement_references_include_anonymous_access_and_privacy(self):
        bundle = P.C.ROOT / P.BUNDLE
        text = (bundle / "09_제품목적_대응표.md").read_text(encoding="utf-8")
        rows = {}
        for line in text.splitlines():
            if re.match(r"^\| P\d+ \|", line):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                rows[cells[0]] = cells
        requirements = (bundle.parents[1] / "REQUIREMENTS.md").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"^\| (R\d{2}) \|", requirements, re.M)),
                         {req for cells in rows.values() for req in re.findall(r"\bR\d{2}\b", cells[8])})

        self.assertIn("R01", rows["P18"][8].split(", "))
        self.assertIn("entry_points", rows["P18"][7])
        self.assertIn("로그인·PDF·가족력·상담 없이", rows["P18"][7])
        privacy = rows["P20"]
        self.assertEqual({"R19", "R20", "R22", "R23"}, set(privacy[8].split(", ")))
        self.assertLessEqual({"T-PS-03", "T-PS-04", "T-OP-05"}, set(privacy[6].split(", ")))
        for evidence in ("consent", "deletion", "export", "family_history", "need-result-reasons",
                         "늦은 쓰기 거부", "백업 복원 시 삭제 표시 재적용", "누출 시험", "롤백 리허설"):
            self.assertIn(evidence, privacy[7])
        for scope in ("첫 출시 기능 구현은 동결", "DEC-D-17", "합성 자료만", "O18 결정 전"):
            self.assertIn(scope, privacy[9])

    def test_row_owner_cannot_be_replaced_by_another_registered_task(self):
        original = self.text
        for row, owners in P.REQUIRED_ROW_OWNERS.items():
            for owner in owners:
                with self.subTest(row=row, owner=owner):
                    self.text = original
                    self.assertEqual([], self.check())
                    line = next(line for line in original.splitlines() if line.startswith(f"| {row} |"))
                    self.text = original.replace(line, line.replace(f", {owner}", ""))
                    found = self.check()
                    self.assertEqual(["PURPOSE-ROW-OWNER"], [f.rule for f in found])
                    self.assertIn(row, found[0].message)
                    self.assertIn(owner, found[0].message)
                    self.assertGreater(found[0].line, 0)

    def test_profile_registration_is_required_beyond_the_g12_ids(self):
        self.assertNotIn("profile-historical-vs-service", P.REQUIRED_TEST_IDS)
        task = next(t for t in self.data["tasks"] if t["id"] == "T-KN-04")
        task["required_test_ids"].remove("profile-historical-vs-service")
        found = self.check()
        self.assertEqual(["PURPOSE-OWNER"], [f.rule for f in found])
        self.assertIn("T-KN-04", found[0].message)
        self.assertIn("profile-historical-vs-service", found[0].message)

    def test_every_row_rejects_unknown_task_with_row_and_line(self):
        original = self.text
        for i in range(1, 21):
            row = f"P{i:02}"
            with self.subTest(row=row):
                self.text = original.replace(f"| {row} | purpose | T-AA-01, T-AA-02",
                                             f"| {row} | purpose | T-AA-01, T-AA-99")
                found = self.check()
                self.assertEqual(["PURPOSE-TASK"], [f.rule for f in found])
                self.assertIn(row, found[0].message)
                self.assertIn("T-AA-99", found[0].message)
                self.assertEqual(i + 2, found[0].line)

    def test_removing_referenced_task_fails_all_rows(self):
        self.data["tasks"].pop(1)
        found = self.check()
        self.assertEqual(20, len(found))
        self.assertEqual({"PURPOSE-TASK"}, {f.rule for f in found})

    def test_repeated_headers_and_inline_code_task_ids_pass(self):
        self.text = self.text.replace("T-AA-01, T-AA-02", "`T-AA-01`, `T-AA-02`")
        self.text = self.text.replace("| P10 |", "\n## Another table\n\n| # | 제품 목적 | 구현 작업 | 완료 증거 |\n|---|---|---|---|\n| P10 |")
        self.assertEqual([], self.check())

    def test_missing_duplicate_unexpected_or_unparseable_rows_fail(self):
        original = self.text
        bad_texts = [
            "",
            original.replace("P20", "P19"),
            original.replace("P20", "P21"),
            original.replace("구현 작업(tasks.json)", "wrong column"),
            original.replace("T-AA-01, T-AA-02", ""),
            original.replace("T-AA-01, T-AA-02", "T-AA-01, typo"),
            re.sub(r"^\| P20 \|.*$", "| P20 | purpose |", original, flags=re.M),
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
        self.assertIn("P20", result.stdout)

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
