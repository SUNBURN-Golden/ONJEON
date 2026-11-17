"""audit6 fix round 3: method aliases must not share one required-ID implementation.

    python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round3/repro_method_alias.py <repository root>

Runs the reviewer's alias reproduction (two distinct target strings resolving to
one method via `test_second = test_first`) plus assignment/cross-class/inherited
variants and positive controls through the given tree's task_test_coverage.run_task
in temporary directories. ValueError/OSError from run_task count as rejection
(exit 1), matching the CLI. Nothing is written to the given tree. Exit 0 only if
every alias registration is rejected and every distinct implementation passes.
"""
import io
from pathlib import Path
import sys
import tempfile

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "tools"))
import task_test_coverage as coverage  # noqa: E402

HEAD = '''import unittest
TEST_IDS = [("first-id", "Contract.test_first"), ("second-id", "{second}")]
class Contract(unittest.TestCase):
    def test_first(self):
        self.assertEqual(2 + 2, 4)
'''
TASK = {'id': 'T-AA-01', 'required_test_ids': ['first-id', 'second-id'],
        'tests': ['시험 first-id: first', '시험 second-id: second']}
DISTINCT = '''import unittest
TEST_IDS = [("first-id", "Contract.test_check"), ("second-id", "Other.test_check")]
class Contract(unittest.TestCase):
    def test_check(self):
        self.assertEqual(2 + 2, 4)
class Other(unittest.TestCase):
    def test_check(self):
        self.assertRaises(ValueError, int, "x")
'''

cases = [
    ('reviewer repro: in-class alias test_second = test_first',
     HEAD.format(second='Contract.test_second') + '    test_second = test_first\n', 1),
    ('assignment after class creation',
     HEAD.format(second='Contract.test_second') + '\nContract.test_second = Contract.test_first\n', 1),
    ('alias through another local TestCase class',
     HEAD.format(second='Second.test_second') + '\nclass Second(unittest.TestCase):\n    test_second = Contract.test_first\n', 1),
    ('inherited method registered under a subclass target',
     HEAD.format(second='Derived.test_first') + '\nclass Derived(Contract):\n    pass\n', 1),
    ('positive: two distinct methods',
     HEAD.format(second='Contract.test_second') + '    def test_second(self):\n        self.assertRaises(ValueError, int, "x")\n', 0),
    ('positive: same method name, distinct implementations in two classes', DISTINCT, 0),
]

failed = False
for name, source, want in cases:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'tools/task_tests/T-AA-01/coverage.py'
        path.parent.mkdir(parents=True)
        path.write_text(source, encoding='utf-8')
        out = io.StringIO()
        try:
            code = coverage.run_task(Path(tmp), TASK, out)
        except (ValueError, OSError) as exc:
            code = 1
            print(f"    rejected: {exc}", file=out)
    ok = code == want
    failed |= not ok
    print(f"{'OK ' if ok else 'BAD'} {name}: exit {code} (want {want})")
    if not ok:
        print(out.getvalue())
print('PASS: one implementation per required ID, aliases rejected' if not failed
      else 'FAIL: an alias registration was not rejected')
sys.exit(1 if failed else 0)
