"""Audit 6: task completion cannot silently skip required IDs described in prose."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import task_test_coverage as coverage  # noqa: E402

SPEC = importlib.util.spec_from_file_location("product_coverage_spec", ROOT / coverage.REGISTRY.parent / "검증/spec_check.py")
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)
TASKS = json.loads((ROOT / coverage.REGISTRY).read_text(encoding="utf-8"))
PRODUCTS = [t for t in TASKS["tasks"] if t["id"] not in ("T-OP-00", "T-OP-09")]


class ProductCoverageContract(unittest.TestCase):
    def problems(self, tasks):
        return sc.product_test_contract_problems({t["id"]: t for t in tasks})

    def test_every_product_task_has_completion_command_and_writable_suite(self):
        self.assertEqual(len(PRODUCTS), 62)
        self.assertEqual(self.problems(PRODUCTS), [])

    def test_removing_command_completion_or_scope_for_each_product_fails(self):
        for t in PRODUCTS:
            tid = t['id']
            for field, value in (
                ('tests', f'python3 -I tools/task_test_coverage.py --task {tid}'),
                ('done_criteria', f'python3 -I tools/task_test_coverage.py --task {tid}'),
                ('allowed_paths', f'tools/task_tests/{tid}/**'),
                ('conflict_paths', f'tools/task_tests/{tid}/**'),
            ):
                with self.subTest(task=tid, field=field):
                    changed = copy.deepcopy(t)
                    changed[field].remove(value)
                    self.assertTrue(self.problems([changed]))

    def test_command_cannot_be_redirected_to_another_task_or_masked(self):
        for suffix in (' --task T-XX-99', ' || true', '; true', ' --help'):
            t = copy.deepcopy(PRODUCTS[0])
            t['tests'][-1] += suffix
            self.assertTrue(self.problems([t]))
        t['tests'] = [t['done_criteria'][-1]] * 2
        self.assertTrue(self.problems([t]))

    def test_every_prose_id_is_required_even_if_registered_on_another_task(self):
        for task in PRODUCTS:
            for tid in task['required_test_ids']:
                with self.subTest(task=task['id'], required_id=tid):
                    changed = copy.deepcopy(PRODUCTS)
                    next(t for t in changed if t['id'] == task['id'])['required_test_ids'].remove(tid)
                    self.assertTrue(self.problems(changed))

    def test_manual_prose_and_amount_schema_orphan_have_explicit_ids(self):
        for tid in ('T-KN-06', 'T-OP-03', 'T-OP-06', 'T-UX-01', 'T-OP-07', 'T-CT-08'):
            t = next(t for t in PRODUCTS if t['id'] == tid)
            self.assertTrue(t['required_test_ids'])
            self.assertEqual(self.problems([t]), [])

    def test_empty_malformed_duplicate_and_unmapped_prose_fail(self):
        self.assertTrue(self.problems([]))
        for ids in (None, 'some-id', [''], ['some-id', 'some-id'], [{}]):
            t = copy.deepcopy(PRODUCTS[0])
            t['required_test_ids'] = ids
            self.assertTrue(self.problems([t]))
        t = copy.deepcopy(PRODUCTS[0])
        t['tests'].append('시험 수동 확인')
        self.assertTrue(self.problems([t]))

    def test_g12c_is_an_executable_spec_gate(self):
        tasks = copy.deepcopy(TASKS)
        next(t for t in tasks['tasks'] if t['id'] == 'T-AP-02')['tests'].pop()
        # Other spec gates are exercised by their own regression suites.
        sc.RESULTS.clear()
        self.addCleanup(sc.RESULTS.clear)
        with warnings.catch_warnings(), mock.patch.object(sc, 'load', side_effect=lambda name: tasks if name == 'tasks.json' else
                               json.loads((ROOT / coverage.REGISTRY.parent / name).read_text())), \
                mock.patch('sys.argv', ['spec_check.py', '--repo', str(ROOT)]), \
                contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter("ignore", ResourceWarning)
            with self.assertRaises(SystemExit) as result:
                sc.main()
        self.assertEqual(result.exception.code, 1)
        self.assertFalse(next(r for r in sc.RESULTS if r['check'].startswith('G12c '))['ok'])


class TaskCoverageExecution(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.path = self.root / 'tools/task_tests/T-AA-01/coverage.py'
        self.path.parent.mkdir(parents=True)
        self.task = {'id': 'T-AA-01', 'required_test_ids': ['first-id', 'second-id'],
                     'tests': ['시험 first-id: first', '시험 second-id: second']}
        self.source = '''import unittest
TEST_IDS = [("first-id", "Contract.test_first"), ("second-id", "Contract.test_second")]
class Contract(unittest.TestCase):
    def test_first(self):
        self.assertEqual(2 + 2, 4)
    def test_second(self):
        self.assertRaises(ValueError, int, "x")
'''
        self.path.write_text(self.source)

    def run_task(self):
        self.output = io.StringIO()
        return coverage.run_task(self.root, self.task, self.output)

    def cli(self):
        registry = self.root / 'tasks.json'
        registry.write_text(json.dumps({'tasks': [self.task]}))
        return subprocess.run([sys.executable, '-I', str(ROOT / 'tools/task_test_coverage.py'),
                               '--root', str(self.root), '--registry', str(registry), '--task', self.task['id']],
                              capture_output=True, text=True, cwd=self.root)

    def test_runs_every_registered_method_and_reports_exact_counts(self):
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(self.run_task(), 0)
        self.assertIn('required=2, ran=2', self.output.getvalue())

    def test_removing_each_registration_or_method_fails(self):
        for test_id, target in coverage.inventory(self.path, self.task['required_test_ids']):
            with self.subTest(test_id=test_id):
                self.path.write_text(self.source.replace(f'("{test_id}", "{target}")', '("unknown-id", "Contract.test_first")'))
                self.assertNotEqual(self.cli().returncode, 0)
                self.path.write_text(self.source.replace('def '+target.split('.')[1]+'(', 'def removed('))
                self.assertNotEqual(self.cli().returncode, 0)

    def test_missing_malformed_empty_dynamic_duplicate_and_reused_registries_fail(self):
        for source in ('', '{', 'TEST_IDS = []', 'TEST_IDS = make_tests()',
                       self.source.replace('second-id', 'first-id'),
                       self.source.replace('Contract.test_second', 'Contract.test_first'),
                       self.source.replace('Contract.test_second', 'Contract'),
                       self.source + '\nTEST_IDS = []\n',
                       self.source + '\nTEST_IDS.pop()\n'):
            with self.subTest(source=source):
                self.path.write_text(source)
                self.assertNotEqual(self.cli().returncode, 0)
        self.path.unlink()
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertIn('coverage FAIL', result.stderr)

    def test_failure_error_skips_expected_failure_and_zero_run_fail(self):
        for edit in (
            ('self.assertEqual(2 + 2, 4)', 'self.assertEqual(2 + 2, 5)'),
            ('self.assertEqual(2 + 2, 4)', 'raise RuntimeError("failure")'),
            ('self.assertEqual(2 + 2, 4)', 'pass'),
            ('self.assertEqual(2 + 2, 4)', 'self.skipTest("not implemented")'),
            ('    def test_first', '    @unittest.skip("missing evidence")\n    def test_first'),
            ('    def test_first', '    @unittest.expectedFailure\n    def test_first'),
            ('class Contract(unittest.TestCase):', 'class Contract(unittest.TestCase):\n    def run(self, result):\n        return result'),
        ):
            with self.subTest(edit=edit):
                source = self.source.replace(*edit)
                if 'expectedFailure' in source:
                    source = source.replace('self.assertEqual(2 + 2, 4)', 'self.fail("expected")')
                self.path.write_text(source)
                self.assertEqual(self.cli().returncode, 1)

    def test_required_list_empty_drift_duplicate_unknown_and_prose_cannot_pass(self):
        for ids in ([], ['new-id'], ['first-id'], ['first-id', 'first-id'], None, 'first-id'):
            self.task['required_test_ids'] = ids
            self.assertEqual(self.cli().returncode, 1)
        self.task['required_test_ids'] = []
        self.task['tests'] = []
        # A leftover registration must not pass when its IDs were removed.
        self.assertEqual(self.cli().returncode, 1)
        self.path.unlink()
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertIn('required_test_ids=[]', result.stdout)
        self.task['tests'] = ['시험 (수동 측정)']
        self.assertEqual(self.cli().returncode, 1)

    def test_all_current_product_ids_fail_if_task_implementation_is_missing(self):
        for t in PRODUCTS:
            if not t['required_test_ids']:
                continue
            with self.subTest(task=t['id']), self.assertRaises(OSError):
                coverage.run_task(self.root, t, io.StringIO())

    def test_module_and_class_fixture_skips_or_errors_fail(self):
        for fixture in (
            '\ndef setUpModule():\n    raise unittest.SkipTest("missing environment")\n',
            '\ndef setUpModule():\n    raise RuntimeError("missing fixture")\n',
        ):
            with self.subTest(fixture=fixture):
                self.path.write_text(self.source + fixture)
                self.assertEqual(self.cli().returncode, 1)
        self.path.write_text(self.source.replace('class Contract(unittest.TestCase):',
            'class Contract(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        raise unittest.SkipTest("missing evidence")'))
        self.assertEqual(self.cli().returncode, 1)

    def test_task_isolation_does_not_borrow_another_task_registration(self):
        self.task['id'] = 'T-AA-02'
        with self.assertRaises(OSError):
            self.run_task()


if __name__ == '__main__':
    unittest.main()
