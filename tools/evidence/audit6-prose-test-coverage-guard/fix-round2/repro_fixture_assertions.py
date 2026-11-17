"""audit6 fix round 2: fixture assertions must not satisfy empty required-ID tests.

    python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round2/repro_fixture_assertions.py <repository root>

Runs the reviewer's setUp-assertion reproduction (one required ID, pass body)
plus tearDown/cleanup/mixed variants and positive controls through the given
tree's task_test_coverage.run_task in temporary directories. Nothing is written
to the given tree. Exit 0 only if every empty method is rejected (exit 1) and
every real method passes (exit 0).
"""
import io
from pathlib import Path
import sys
import tempfile

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "tools"))
import task_test_coverage as coverage  # noqa: E402

TWO = '''import unittest
TEST_IDS = [("first-id", "Contract.test_first"), ("second-id", "Contract.test_second")]
class Contract(unittest.TestCase):
{fixture}    def test_first(self):
        {body1}
    def test_second(self):
        {body2}
'''
ONE = '''import unittest
TEST_IDS = [("first-id", "EmptyRequiredTest.test_missing_product_behavior")]
class EmptyRequiredTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(True)
    def test_missing_product_behavior(self):
        pass
'''
TASK_TWO = {'id': 'T-AA-01', 'required_test_ids': ['first-id', 'second-id'],
            'tests': ['시험 first-id: first', '시험 second-id: second']}
TASK_ONE = {'id': 'T-AA-01', 'required_test_ids': ['first-id'], 'tests': ['시험 first-id: first']}
SETUP = '    def setUp(self):\n        self.assertTrue(True)\n'
TEARDOWN = '    def tearDown(self):\n        self.assertTrue(True)\n'
CLEANUP = '    def setUp(self):\n        self.addCleanup(self.assertTrue, True)\n'
HELPER = '    def helper(self):\n        self.assertEqual(1, 1)\n'
REAL1, REAL2 = 'self.assertEqual(2 + 2, 4)', 'self.assertRaises(ValueError, int, "x")'

cases = [
    ('reviewer repro: setUp assertion, pass body', ONE, TASK_ONE, 1),
    ('setUp only, both bodies empty', TWO.format(fixture=SETUP, body1='pass', body2='pass'), TASK_TWO, 1),
    ('tearDown only, both bodies empty', TWO.format(fixture=TEARDOWN, body1='pass', body2='pass'), TASK_TWO, 1),
    ('setUp+tearDown, both bodies empty', TWO.format(fixture=SETUP + TEARDOWN, body1='pass', body2='pass'), TASK_TWO, 1),
    ('cleanup only, both bodies empty', TWO.format(fixture=CLEANUP, body1='pass', body2='pass'), TASK_TWO, 1),
    ('one real method, one empty, setUp asserts', TWO.format(fixture=SETUP, body1=REAL1, body2='pass'), TASK_TWO, 1),
    ('positive: fixture assertions + real bodies', TWO.format(fixture=SETUP + TEARDOWN, body1=REAL1, body2=REAL2), TASK_TWO, 0),
    ('positive: helper + subTest assertions', TWO.format(fixture=HELPER, body1='self.helper()\n        with self.subTest(x=1):\n            self.assertTrue(True)', body2=REAL2), TASK_TWO, 0),
]

failed = False
for name, source, task, want in cases:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'tools/task_tests/T-AA-01/coverage.py'
        path.parent.mkdir(parents=True)
        path.write_text(source, encoding='utf-8')
        out = io.StringIO()
        code = coverage.run_task(Path(tmp), task, out)
    ok = code == want
    failed |= not ok
    print(f"{'OK ' if ok else 'BAD'} {name}: exit {code} (want {want})")
    if not ok:
        print(out.getvalue())
print('PASS: fixture assertions cannot satisfy empty required-ID methods' if not failed
      else 'FAIL: an empty required-ID method was not rejected')
sys.exit(1 if failed else 0)
