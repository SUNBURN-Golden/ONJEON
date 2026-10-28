"""T-OP-00 registrations must cover the canonical IDs, not merely declare them in tasks.json.

Source mutations use temporary copies. Inventory is static; passing behavior is checked
by test_daemon_dry_run and its --require-all regressions.
"""
import ast
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import warnings
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
SPEC = importlib.util.spec_from_file_location("coverage_spec_check", BUNDLE / "검증/spec_check.py")
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)
TASKS = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
REQUIRED = next(t["required_test_ids"] for t in TASKS["tasks"] if t["id"] == "T-OP-00")


class RequiredTestInventory(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.daemon = self.root / "tools/daemon"
        self.daemon.mkdir(parents=True)
        for name in ("scenarios.py", "scenarios_flow.py", "mock_tasks.json"):
            shutil.copyfile(ROOT / "tools/daemon" / name, self.daemon / name)

    def coverage(self, required=None):
        return sc.daemon_test_coverage(str(self.root), REQUIRED if required is None else required)

    def registry(self, filename):
        tree = ast.parse((self.daemon / filename).read_text(encoding="utf-8"))
        name = "CORE_SCENARIOS" if filename == "scenarios.py" else "FLOW_SCENARIOS"
        value = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
        return tree, value

    def write(self, filename, tree):
        (self.daemon / filename).write_text(ast.unparse(tree), encoding="utf-8")

    def test_inventory_matches_runtime_registry_and_canonical_33_ids(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        self.addCleanup(sys.path.remove, str(ROOT / "tools"))
        from daemon import scenarios
        entries, errors = sc.daemon_test_inventory(str(self.root))
        self.assertEqual(errors, [])
        self.assertCountEqual(entries, [(e[0], e[1]) for e in scenarios.SCENARIOS])
        cov = self.coverage()
        self.assertEqual((cov["required_count"], cov["registered_count"]), (33, 33))
        self.assertTrue(cov.pop("fixture_matches"))
        cov.pop("required_count")
        cov.pop("registered_count")
        self.assertFalse(any(cov.values()), cov)

    def test_removing_each_required_registration_is_detected(self):
        checked = []
        for filename in ("scenarios.py", "scenarios_flow.py"):
            original = (self.daemon / filename).read_text(encoding="utf-8")
            tree, registry = self.registry(filename)
            rows = list(registry.elts)
            for row in rows:
                tid = ast.literal_eval(row.elts[1])
                if tid not in REQUIRED:
                    continue
                with self.subTest(test_id=tid):
                    registry.elts = [e for e in rows if e is not row]
                    self.write(filename, tree)
                    self.assertEqual(self.coverage()["missing"], [tid])
                    checked.append(tid)
            (self.daemon / filename).write_text(original, encoding="utf-8")
        self.assertCountEqual(checked, REQUIRED)

    def test_registered_name_without_function_is_detected_for_every_required_id(self):
        checked = []
        for filename in ("scenarios.py", "scenarios_flow.py"):
            original = (self.daemon / filename).read_text(encoding="utf-8")
            tree, registry = self.registry(filename)
            body = list(tree.body)
            for row in registry.elts:
                tid = ast.literal_eval(row.elts[1])
                if tid not in REQUIRED:
                    continue
                with self.subTest(test_id=tid):
                    tree.body = [n for n in body if not (isinstance(n, ast.FunctionDef) and n.name == row.elts[3].id)]
                    self.write(filename, tree)
                    self.assertTrue(self.coverage()["errors"])
                    checked.append(tid)
            (self.daemon / filename).write_text(original, encoding="utf-8")
        self.assertCountEqual(checked, REQUIRED)

    def test_unknown_duplicate_and_sentinel_ids_cannot_hide_missing_tests(self):
        filename = "scenarios_flow.py"
        tree, registry = self.registry(filename)
        row = next(r for r in registry.elts if ast.literal_eval(r.elts[1]) in REQUIRED)
        tid = ast.literal_eval(row.elts[1])
        for replacement in ("unknown-test", "-", ""):
            with self.subTest(replacement=replacement):
                row.elts[1] = ast.Constant(replacement)
                self.write(filename, tree)
                cov = self.coverage()
                self.assertIn(tid, cov["missing"])
                if replacement == "unknown-test":
                    self.assertEqual(cov["unlisted"], [replacement])
                if replacement == "":
                    self.assertTrue(cov["errors"])
        row.elts[1] = ast.Constant(tid)
        registry.elts.append(copy.deepcopy(row))
        self.write(filename, tree)
        cov = self.coverage()
        self.assertEqual(cov["repeated"], [tid])
        self.assertEqual(cov["repeated_scenarios"], [ast.literal_eval(row.elts[0])])

    def test_empty_duplicate_or_drifted_canonical_and_fixture_lists(self):
        self.assertEqual(self.coverage([])["required_count"], 0)
        self.assertEqual(self.coverage(REQUIRED + [REQUIRED[0]])["repeated_required"], [REQUIRED[0]])
        self.assertEqual(self.coverage(REQUIRED + ["new-test"])["missing"], ["new-test"])
        fixture = self.daemon / "mock_tasks.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        data["t_op_00_required_test_ids"].pop()
        fixture.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(self.coverage()["fixture_matches"])
        fixture.write_text("{", encoding="utf-8")
        self.assertTrue(self.coverage()["errors"])
        fixture.unlink()
        self.assertTrue(self.coverage()["errors"])

    def test_missing_malformed_or_nonliteral_registry_fails_closed(self):
        path = self.daemon / "scenarios_flow.py"
        for source in ("", "FLOW_SCENARIOS = []", "FLOW_SCENARIOS = build()", "syntax error!",
                       'FLOW_SCENARIOS = [("M1", "tid")]',
                       'FLOW_SCENARIOS = [("M1", "tid", "title", lambda *args: None)]'):
            with self.subTest(source=source):
                path.write_text(source, encoding="utf-8")
                self.assertTrue(self.coverage()["errors"])
        path.unlink()
        self.assertTrue(self.coverage()["errors"])

    def test_g12b_fails_cli_when_task_ids_still_exist_but_tests_do_not(self):
        sc.RESULTS.clear()
        self.addCleanup(sc.RESULTS.clear)
        out = io.StringIO()
        with mock.patch.object(sc, "daemon_test_inventory", return_value=([], [])), \
                mock.patch("sys.argv", ["spec_check.py", "--repo", str(ROOT)]), \
                contextlib.redirect_stdout(out), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            with self.assertRaises(SystemExit) as code:
                sc.main()
        self.assertEqual(code.exception.code, 1)
        self.assertTrue(all(r["ok"] for r in sc.RESULTS if r["check"].startswith("G12 ")))
        [gate] = [r for r in sc.RESULTS if r["check"].startswith("G12b ")]
        self.assertFalse(gate["ok"])
        self.assertEqual(gate["detail"]["missing"], sorted(REQUIRED))
        self.assertIn("G12b", out.getvalue())


if __name__ == "__main__":
    unittest.main()
