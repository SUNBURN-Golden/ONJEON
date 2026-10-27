"""audit2-daemon-coverage-reverse: which coverage holes each tree catches.

    python3 -I tools/evidence/audit2-daemon-coverage-reverse/repro_coverage_reverse.py <repository root>

Part 1 runs the three assertions of Coverage.test_test_ids_are_the_ones_in_tasks_json as they stood at 991334c on the
full scenario list and on the list with one required scenario dropped. Part 2 runs `dry_run.py --require-all` on small
scenario lists (M41, M44 with a two-id required list) with one id missing, unlisted, run twice or listed twice, and
prints the exit code. Mock adapters only; the given tree is imported, nothing is written there.
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "tools"))
from daemon import dry_run, scenarios as sc  # noqa: E402

RULES = root / "docs/blueprint/proposals/설계검토_결과/daemon_rules.json"
TASKS = root / "tools/daemon/mock_tasks.json"
required = json.loads(TASKS.read_text(encoding="utf-8"))["t_op_00_required_test_ids"]


def old_assertions(entries):
    implemented = [e[1] for e in entries if e[0] != "STATIC"]
    return {"unlisted": [t for t in implemented if t not in required and t != "-"],
            "missing": sorted(set(required) - set(implemented)),
            "no_repeat": len([t for t in implemented if t != "-"]) == len(set(t for t in implemented if t != "-"))}


print(f"tree: {'fixed' if hasattr(dry_run, 'coverage') else 'base'}; required ids {len(required)}, "
      f"scenarios {len(sc.SCENARIOS)} (with a required id {len([e for e in sc.SCENARIOS if e[1] in required])})")
print("part 1, 991334c test assertions, full list:", old_assertions(sc.SCENARIOS))
drop = [e for e in sc.SCENARIOS if e[0] != "M41"]
print("part 1, 991334c test assertions, M41 dropped:", old_assertions(drop))

m41, m44 = sc.SCENARIOS[[e[0] for e in sc.SCENARIOS].index("M41")], sc.SCENARIOS[[e[0] for e in sc.SCENARIOS].index("M44")]
req2 = [m41[1], m44[1]]
cases = {
    "exact": ([m41, m44], req2),
    "missing": ([m41], req2),
    "unlisted": ([m41, m44, ("M44x", "not-in-list", m44[2], m44[3])], req2),
    "run twice": ([m41, m44, ("M44x", m44[1], m44[2], m44[3])], req2),
    "listed twice": ([m41, m44], req2 + [m41[1]]),
}
for name, (scen, req) in cases.items():
    cfg = json.loads(TASKS.read_text(encoding="utf-8"))
    cfg["t_op_00_required_test_ids"] = req
    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(sc, "SCENARIOS", scen), contextlib.redirect_stdout(buf):
        p = Path(tmp) / "tasks.json"
        p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        code = dry_run.main(["--rules", str(RULES), "--tasks", str(p), "--scenario", "all", "--quiet", "--require-all"])
    lines = [ln.strip() for ln in buf.getvalue().splitlines() if "시험 ID" in ln or "실패 " in ln]
    print(f"part 2, --require-all {name}: exit {code}")
    for ln in lines:
        print("    " + ln)
