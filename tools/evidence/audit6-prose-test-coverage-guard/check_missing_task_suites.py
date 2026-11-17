"""Show the honest current completion state; missing product suites must fail.

No native product implementation or release evidence is manufactured here.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
DATA = json.loads((ROOT / 'docs/blueprint/proposals/설계검토_결과/tasks.json').read_text())
products = [t for t in DATA['tasks'] if t['id'] not in ('T-OP-00', 'T-OP-09')]
prose = sum(s.startswith('시험 ') for t in products for s in t['tests'])
print(f'product_tasks={len(products)}, prose_descriptions={prose}')
for task in products:
    tid = task['id']
    result = subprocess.run([sys.executable, '-I', str(ROOT / 'tools/task_test_coverage.py'), '--task', tid],
                            cwd=ROOT, capture_output=True, text=True)
    required = task['required_test_ids']
    # This audit only installs the guard. Required-ID suites are not yet shipped by product tasks.
    if required:
        assert result.returncode == 1, (tid, result.stdout, result.stderr)
        assert 'No such file' in result.stderr and '/coverage.py' in result.stderr, result.stderr
    else:
        assert result.returncode == 0 and 'required_test_ids=[]' in result.stdout, result
    print(f'{tid}: required={len(required)}, exit={result.returncode}, '
          + ('missing suite rejected' if required else 'explicit empty required list'))
print('PASS: no unimplemented required ID was reported as passing')
