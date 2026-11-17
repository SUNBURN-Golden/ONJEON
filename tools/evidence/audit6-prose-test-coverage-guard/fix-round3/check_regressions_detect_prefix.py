"""audit6 fix round 3: the new alias regression must fail on the pre-fix runner.

    python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round3/check_regressions_detect_prefix.py <repository root> [revision]

Builds a temporary tree with the runner from the given revision (default
3b109a4, the reviewed head) and the current regression test file, then runs
the two new tests there. The alias rejection test must fail (the old runner
accepts aliases to one implementation) and the distinct-implementation positive
control must pass. Nothing is written to the given tree; docs are read through
a symlink.
"""
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

root = Path(sys.argv[1]).resolve()
revision = sys.argv[2] if len(sys.argv) > 2 else '3b109a4'
old = subprocess.run(['git', '-C', str(root), 'show', f'{revision}:tools/task_test_coverage.py'],
                     capture_output=True, text=True, check=True).stdout
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / 'tools/tests').mkdir(parents=True)
    (tmp / 'tools/task_test_coverage.py').write_text(old, encoding='utf-8')
    shutil.copy(root / 'tools/tests/test_task_test_coverage.py', tmp / 'tools/tests/')
    (tmp / 'docs').symlink_to(root / 'docs')
    sys.path.insert(0, str(tmp / 'tools/tests'))
    import test_task_test_coverage as t
    assert t.coverage.__file__ == str(tmp / 'tools/task_test_coverage.py'), t.coverage.__file__
    names = ('test_method_aliases_cannot_share_one_implementation',
             'test_distinct_implementations_with_same_method_name_pass')
    suite = unittest.TestSuite(t.TaskCoverageExecution(name) for name in names)
    buf = io.StringIO()
    result = unittest.TextTestRunner(stream=buf, verbosity=2).run(suite)
print(buf.getvalue())
# subTest failures surface as _SubTest cases named runTest; keep the parent names.
failed = {getattr(case, 'test_case', case)._testMethodName for case, _ in result.failures + result.errors}
ok = (result.testsRun == 2
      and failed == {names[0]})
print(f'pre-fix runner {revision}: ran={result.testsRun}, failing={sorted(failed)}')
print('PASS: new regression detects the pre-fix method-alias bypass' if ok
      else 'FAIL: regression does not isolate the pre-fix behavior')
sys.exit(0 if ok else 1)
