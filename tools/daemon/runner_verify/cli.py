"""Entry point of the real executor verification (T-OP-09).

    bash tools/daemon/runner_verify/run.sh --remote auto --report docs/vm_check/<date>/runner_verify.json

Runs R1-R22 (05 §6) against real processes, a real git remote with a protected branch, a real file store and, where
a confirmed way exists, a real vendor CLI against a test provider proxy. Writes next to --report: the JSON report, the
readable log, the filled §1b table, the §2 summary, the result overview and the static check log. Exit code 1 if any
check failed or a scenario could not run; unconfirmed items are recorded and do not change the exit code.
This is a development tool. It is not the daemon, merges nothing and writes only to the test remote's T-MOCK-* branches.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from daemon.runner_verify import reporting, static_checks  # noqa: E402
from daemon.runner_verify.common import DEFAULT_RULES, DEFAULT_TASKS, ROOT  # noqa: E402
from daemon.runner_verify.context import Ctx  # noqa: E402
from daemon.runner_verify.remote import RemoteRefused, check_accepts  # noqa: E402
from daemon.runner_verify.report import FAIL  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--remote", default="auto", help="auto (provision a throwaway bare repository) or the path of a "
                    "repository created by this tool. URLs and the product repository are refused.")
    ap.add_argument("--report", required=True, help="path of the JSON report; the other files go to the same directory")
    ap.add_argument("--rules", default=str(DEFAULT_RULES))
    ap.add_argument("--tasks", default=str(DEFAULT_TASKS))
    ap.add_argument("--scenario", default="all", help="all, R numbers or test ids, comma separated")
    ap.add_argument("--time-scale", type=float, default=0.05, help="fraction of a requested sleep that is waited for real "
                    "(the rest moves the daemon's clock offset); 1 waits everything")
    ap.add_argument("--no-cli", action="store_true", help="do not start vendor CLIs (their parts are recorded as unconfirmed)")
    ap.add_argument("--workdir", help="parent directory of the throwaway state directories")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.remote not in ("auto", "local"):
        try:
            check_accepts(args.remote)
        except RemoteRefused as exc:
            print(f"remote refused: {exc}", file=sys.stderr)
            return 2
    out_dir = Path(args.report).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    before = static_checks.product_repo_state()
    cx = Ctx(rules=args.rules, tasks=args.tasks, remote=args.remote, time_scale=args.time_scale, workdir=args.workdir,
             with_cli=not args.no_cli)
    results = []
    for entry in reporting.select(args.scenario):
        res = reporting.run_scenario(entry, cx)
        results.append(res)
        if not args.quiet:
            print(f"{res['r']:4} {res['test_id'] or '-':38} {res['status']:12} ({res['seconds']} s)", flush=True)
    after = static_checks.product_repo_state()
    target = {"parent_commit": reporting.git_out("rev-parse", "HEAD"), "branch": reporting.git_out("rev-parse", "--abbrev-ref", "HEAD")}
    report = reporting.build_report(results, cx, before, after, target)
    from daemon.runner_verify.scn_handoff import userns_available
    report["environment"]["unshare_mount_namespace"] = userns_available()

    log = reporting.render_log(report)
    table = reporting.render_exit_table(report)
    summary = json.dumps(reporting.render_summary_json(report), ensure_ascii=False, indent=1)
    overview = reporting.render_overview(report)
    text = json.dumps(report, ensure_ascii=False, indent=1, default=str)
    leaks = static_checks.no_leak_in_outputs(text + log + table + summary + overview)
    model_ids = static_checks.no_model_identifiers(extra_texts=[("report", text), ("log", log), ("table", table), ("overview", overview)])
    secrets = static_checks.secrets_absent(args.rules, extra_texts=[("report", text), ("log", log), ("table", table), ("overview", overview)])
    static = static_checks.all_static(args.rules) + [
        ("산출물에 원문·세션 ID·사용자 경로 누출 없음", leaks), ("산출물에 모델 식별자 모양·비밀값 없음", model_ids + secrets),
        ("runner_profile에는 확인된 종료 코드만", static_checks.runner_profile_confirmed_only(report["runner_profile"])),
        ("제품 저장소의 ref·HEAD·원격이 실행 전후 같다", [] if report["product_branch_check"]["refs_unchanged"]
         and report["product_branch_check"]["remotes_unchanged"] and before["head"] == after["head"] else ["changed"]),
        ("시험 원격에 적용된 ref는 task/T-MOCK-* 브랜치뿐", report["product_branch_check"]["refs_applied_outside_task_branches"]),
        ("병합 호출 0건", [] if report["product_branch_check"]["merge_calls"] == 0 else ["merge"])]
    static_lines = ["# static and log checks of runner_verify"] + [f"[{'FAIL' if bad else 'PASS'}] {name}" + ("".join(f"\n      {b}" for b in bad)) for name, bad in static]
    (out_dir / "runner_verify.log").write_text(log, encoding="utf-8")
    (out_dir / "exit_code_table.md").write_text(table, encoding="utf-8")
    (out_dir / "summary.json").write_text(summary + "\n", encoding="utf-8")
    (out_dir / "RESULTS.md").write_text(overview, encoding="utf-8")
    (out_dir / "static_checks.log").write_text("\n".join(static_lines) + "\n", encoding="utf-8")
    report["static_checks"] = [{"name": n, "violations": b} for n, b in static]
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")

    s = report["summary"]
    print(f"시나리오 {s['scenarios']}개 {s['status_counts']}, 검사 {s['checks']}건 중 실패 {s['checks_failed']}, 미확인 {s['checks_unconfirmed']}, GAP {s['gaps']}")
    print("정적·로그 검사: " + ("모두 통과" if not any(b for _n, b in static) else "위반 있음(static_checks.log)"))
    print("이 과제의 완료는 가동 승인이 아니다.")
    failed = s["checks_failed"] or any(r["error"] for r in results) or any(b for _n, b in static)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
