"""Dry run of the daemon core (T-OP-00): runs scenarios M1-M44 (05 §5) on the shared core with mock adapters.

    python3 -I tools/daemon/dry_run.py --rules <daemon_rules.json> --tasks tools/daemon/mock_tasks.json --scenario all

Prints expected and actual values side by side for every check (the transition columns among them). Exit code 1 if
any check differs or a scenario raises. Checks marked GAP are specification gaps and do not change the exit code.
Scenarios without a required test id show "-". No network, no CLI, no model, no repository: mock adapters only.
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon import scenarios as sc  # noqa: E402
from daemon.core import Rules  # noqa: E402
from daemon.core.rules import OUTSIDE_READS  # noqa: E402
from daemon.spec_gaps import SPEC_GAPS, open_gaps, resolved_gaps  # noqa: E402


def run_scenario(entry, rules, tasks):
    mid, test_id, title, fn = entry
    rep = sc.Report()
    error = None
    try:
        fn(rep, rules, tasks)
    except Exception:  # a scenario that cannot run counts as a failure
        error = traceback.format_exc()
        rep.checks.append({"name": "시나리오 실행", "expected": "예외 없음", "actual": error.strip().splitlines()[-1], "status": sc.FAIL})
    return {"id": mid, "test_id": test_id, "title": title, "checks": rep.checks, "error": error}


def compact(v, limit=None):
    text = json.dumps(v, ensure_ascii=False, default=str)
    if limit and len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def scenario_status(res):
    statuses = {c["status"] for c in res["checks"]}
    if sc.FAIL in statuses:
        return "FAIL"
    if sc.GAP in statuses:
        return "PASS+GAP"
    return "PASS"


def select(arg):
    if arg == "all":
        return sc.SCENARIOS
    out = [e for e in sc.SCENARIOS if arg in (e[0], e[1])]
    if not out:
        raise SystemExit(f"unknown scenario {arg}. Known: " + ", ".join(f"{e[0]}={e[1]}" for e in sc.SCENARIOS))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--scenario", default="all", help="all, an M number (M41) or a test id")
    ap.add_argument("--report", help="also write the results as JSON to this path")
    ap.add_argument("--quiet", action="store_true", help="print only failures, gaps and the summary")
    ap.add_argument("--require-all", action="store_true", help="exit 1 if required test ids are not run")
    args = ap.parse_args(argv)

    results = [run_scenario(e, args.rules, args.tasks) for e in select(args.scenario)]
    failed = 0
    for res in results:
        status = scenario_status(res)
        print(f"== {res['id']} {res['test_id']}: {res['title']}  [{status}]")
        for c in res["checks"]:
            if c["status"] == sc.FAIL:
                failed += 1
            if args.quiet and c["status"] == sc.PASS:
                continue
            print(f"  [{c['status']}] {c['name']}")
            lim = None if c["status"] != sc.PASS else 160
            print(f"      기대: {compact(c['expected'], lim)}")
            print(f"      실제: {compact(c['actual'], lim)}")
            if c.get("note"):
                print(f"      명세 공백: {c['note']}")
        if res["error"]:
            print(res["error"])
    with open(args.tasks, encoding="utf-8") as f:
        tasks_cfg = json.load(f)
    required = tasks_cfg["t_op_00_required_test_ids"]
    ran = {r["test_id"] for r in results}
    not_run = [t for t in required if t not in ran]
    total = sum(len(r["checks"]) for r in results)
    gaps = sum(1 for r in results for c in r["checks"] if c["status"] == sc.GAP)
    print("\n== 요약")
    for res in results:
        passed = sum(1 for c in res["checks"] if c["status"] == sc.PASS)
        print(f"  {res['id']:7} {res['test_id']:40} {scenario_status(res):9} 검사 {len(res['checks'])}건 중 통과 {passed}")
    print(f"  검사 {total}건, 실패 {failed}건, 명세 공백 표시 {gaps}건")
    print(f"  필수 시험 ID {len(required)}개 중 이번에 실행한 것 {len(ran & set(required))}개, 실행하지 않은 것 {len(not_run)}개(이번 범위 밖)")
    if args.scenario == "all":
        print("  실행하지 않은 시험 ID: " + ", ".join(not_run))
    print(f"  코어가 읽은 필드의 문자열 안에서 꺼낸 토큰·해석 {len(Rules.token_log)}종(명세 공백 후보, --report에 목록)")
    print("  읽기 목록(core_contract.reads) 밖에서 읽는 값: " + ", ".join(f"{k}({v})" for k, v in OUTSIDE_READS.items()))
    print(f"  명세 공백: 해소(필드) {len(resolved_gaps())}건, 남았거나 새로 생긴 것 {len(open_gaps())}건")
    for g in open_gaps():
        print(f"   - {g['id']} [{g['status']}] {g['field']} @ {g['where']}: {g['need']}")
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps({"results": results, "not_run": not_run, "spec_gaps": SPEC_GAPS,
                                                 "string_tokens": sorted(map(list, Rules.token_log)),
                                                 "outside_reads": OUTSIDE_READS},
                                                ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    code = 1 if failed else 0
    if args.require_all and not_run:
        code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
