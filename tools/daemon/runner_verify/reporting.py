"""Runs the scenarios and turns their results into the files under docs/vm_check/<date>/: the JSON report, the
readable log, the filled §1b table, the §2 summary and the result overview."""
import hashlib
import json
import platform
import socket
import subprocess
import time
import traceback
from datetime import datetime, timezone

from . import cli_probe, static_checks
from .common import ROOT
from .registry import REQUIRED_TEST_IDS, SCENARIOS
from .report import FAIL, GAP, PARTIAL, PASS, UNCONFIRMED, Rep

VM_NOTE = ("이 실행은 사람이 준비한 VM의 CLI·원격·자격 설정이 아니라, 이 호스트에서 로컬 구성요소(bare 원격, hook, 스크립트 빌더, 시험 프록시)로 한 것이다. "
           "실제 호스트의 보호 브랜치·단기 자격과 벤더 CLI(claude CLI 하나를 빼고)는 확인하지 못했다.")
APPROVAL = "이 과제의 완료는 가동 승인이 아니다. 가동 여부는 05 §7의 점검표와 사용자 결정으로만 정해진다."


def run_scenario(entry, cx):
    rid, test_id, title, fn, real, limits = entry
    rep = Rep()
    error = None
    began = time.time()
    try:
        fn(rep, cx)
    except Exception:  # a scenario that cannot run counts as a failure
        error = traceback.format_exc()
        rep.checks.append({"name": "시나리오 실행", "status": FAIL, "expected": "예외 없음", "actual": error.strip().splitlines()[-1]})
    return {"r": rid, "test_id": test_id, "title": title, "status": rep.status(), "seconds": round(time.time() - began, 1),
            "real_components": real, "limits": limits, "checks": rep.checks, "evidence": rep.evidence,
            "not_proven": rep.not_proven, "findings": rep.findings, "error": error}


def select(spec):
    if not spec or spec == "all":
        return SCENARIOS
    wanted = {s.strip() for s in spec.split(",")}
    out = [e for e in SCENARIOS if e[0] in wanted or e[1] in wanted]
    if not out:
        raise SystemExit("unknown scenario. Known: " + ", ".join(f"{e[0]}={e[1]}" for e in SCENARIOS))
    return out


def git_out(*args):
    return subprocess.run(["git", "-C", str(ROOT)] + list(args), capture_output=True, text=True).stdout.strip()


def environment(cx):
    host = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:16]
    return {"host_hash": host, "os": platform.system() + " " + platform.release(), "python": platform.python_version(),
            "git": subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.strip(),
            "time_scale": cx.time_scale, "clock_advanced_by_harness_s": round(cx.advance_s),
            "clock_scaled_sleep_s": round(cx.scaled_sleep_s), "worlds": cx.worlds,
            "remote_kind": "provisioned_local_bare_repository" if cx.remote in ("auto", "local", None) else "existing_marked_bare_repository",
            "vm_verified": False, "vm_note": VM_NOTE,
            "lsof": bool(subprocess.run(["which", "lsof"], capture_output=True).returncode == 0),
            "unshare_mount_namespace": None}


def runner_profiles(results):
    """Per runner path, the exit codes that were confirmed. Empty unless the table confirmed them."""
    r7 = next((r for r in results if r["r"] == "R7"), None)
    out = {}
    table = (r7 or {}).get("evidence", {}).get("exit_code_table", {})
    for t in cli_probe.TARGETS:
        row = table.get(t["id"], {})
        ec = row.get("exit_codes") or {}
        out[t["label"]] = {"limit_exit_codes": ec.get("limit_exit_codes", []), "unavailable_exit_codes": ec.get("unavailable_exit_codes", []),
                           "provider_documented_quota_types": [], "confirmed": bool(ec.get("confirmed")),
                           "source": ("시험 프록시 재현" if ec else "미확인")}
    return out


def build_report(results, cx, before, after, target):
    covered = {}
    for r in results:
        if r["test_id"]:
            covered.setdefault(r["test_id"], []).append({"r": r["r"], "status": r["status"]})
    profile = runner_profiles(results)
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (PASS, FAIL, PARTIAL, UNCONFIRMED)}
    checks = [c for r in results for c in r["checks"]]
    product = {"head_before": before["head"], "head_after": after["head"],
               "refs_unchanged": before["refs"] == after["refs"], "remotes_unchanged": before["remotes"] == after["remotes"],
               "test_remote_pushes": cx.pushes, "merge_calls": 0,
               "refs_applied_outside_task_branches": cx.pushes["applied_refs_outside_task"]}
    return {
        "tool": "tools/daemon/runner_verify", "task": "T-OP-09", "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target": target, "environment": environment(cx), "vm_approval": APPROVAL,
        "summary": {"scenarios": len(results), "status_counts": counts,
                    "checks": len(checks), "checks_failed": sum(1 for c in checks if c["status"] == FAIL),
                    "checks_unconfirmed": sum(1 for c in checks if c["status"] == UNCONFIRMED),
                    "gaps": sum(1 for c in checks if c["status"] == GAP)},
        "required_test_ids": {t: covered.get(t, "not run") for t in REQUIRED_TEST_IDS},
        "runner_profile": profile, "product_branch_check": product, "results": results,
    }


# ---------------------------------------------------------------- text renderings
def compact(v):
    return json.dumps(v, ensure_ascii=False, default=str)


def render_log(report):
    lines = [f"# runner_verify log (T-OP-09)  generated_at={report['generated_at']}",
             f"# target: {report['target']}", f"# {VM_NOTE}", f"# {APPROVAL}", ""]
    for r in report["results"]:
        lines.append(f"== {r['r']} {r['test_id'] or '-'}: {r['title']}  [{r['status']}]  ({r['seconds']} s)")
        lines.append(f"   실제로 쓴 구성: {'; '.join(r['real_components'])}")
        lines.append(f"   한계: {'; '.join(r['limits'])}")
        for c in r["checks"]:
            lines.append(f"  [{c['status']}] {c['name']}")
            lines.append(f"      기대: {compact(c['expected'])}")
            lines.append(f"      실제: {compact(c['actual'])}")
            for k in ("reason", "note", "detail"):
                if c.get(k):
                    lines.append(f"      {k}: {compact(c[k])}")
        for item in r["not_proven"]:
            lines.append(f"  [증명하지 않은 것] {item}")
        if r["error"]:
            lines.append(r["error"])
        lines.append("")
    s = report["summary"]
    lines.append("== 요약")
    for r in report["results"]:
        n = len(r["checks"])
        passed = sum(1 for c in r["checks"] if c["status"] == PASS)
        lines.append(f"  {r['r']:4} {r['test_id'] or '-':38} {r['status']:12} 검사 {n}건 중 통과 {passed}")
    lines.append(f"  시나리오 {s['scenarios']}개: {s['status_counts']}  검사 {s['checks']}건, 실패 {s['checks_failed']}건, 미확인 {s['checks_unconfirmed']}건, 명세 불일치(GAP) {s['gaps']}건")
    lines.append(f"  필수 시험 ID: {report['required_test_ids']}")
    return "\n".join(lines) + "\n"


def render_exit_table(report):
    """05 §1b filled from the R6/R7 evidence. Unconfirmed stays unconfirmed."""
    r7 = next((r for r in report["results"] if r["r"] == "R7"), None)
    table = (r7 or {}).get("evidence", {}).get("exit_code_table", {})
    date = report["generated_at"][:10]
    head = ("| 실행 경로 | 설치·버전 | 모델 제공자 HTTP 응답을 데몬이 볼 수 있는 채널 | 한도 종료 코드 | 불가 종료 코드 | 구조화 오류 출력 | 확인 방법 | 상태(" + date + ") |\n"
            "|---|---|---|---|---|---|---|---|\n")
    rows = []
    for t in cli_probe.TARGETS:
        row = table.get(t["id"], {})
        ver = row.get("version") or ("설치됨, 버전 미확인" if row.get("installed") else "설치 확인 안 됨")
        ec = row.get("exit_codes")
        if ec:
            by = ec["codes_by_situation"]
            same = "모든 실패 상황이 같은 종료 코드 " + "/".join(str(c) for c in sorted({c for k, v in by.items() if k != "ok" for c in v})) \
                if len({c for k, v in by.items() if k != "ok" for c in v}) == 1 else "상황별로 갈림: " + compact(by)
            lim = ", ".join(map(str, ec["limit_exit_codes"])) or f"비어 있음({same}: 한도 구분 불가)"
            una = ", ".join(map(str, ec["unavailable_exit_codes"])) or f"비어 있음({same}: 불가 구분 불가)"
            channel = row["status_channel"] + " — 시험 프록시가 돌려준 429/500/503/529/401/403/400이 모두 result.api_error_status에 같은 값으로 실림"
            struct = "stream-json(api_retry·result 이벤트). 원문은 보존하지 않음(모델 식별자·세션 ID 포함)"
            how = "시험 프록시 재현 " + str(sum(len(v) for v in row["situations"].values())) + "회(상황 " + str(len(row["situations"])) + "가지)"
            status = "**채널 재현됨(이 버전·이 출력 모드), 종료 코드는 전환 근거 아님(runner_profile 비움)**" if not ec["confirmed"] else "**종료 코드 확인됨**"
        else:
            lim = una = struct = "미확인"
            channel = "미확인"
            how = row.get("unconfirmed_reason", "시험하지 않았다")
            status = "**미확인**"
        rows.append(f"| {t['label']} | {ver} | {channel} | {lim} | {una} | {struct} | {how} | {status} |")
    return ("# §1b 전환 신호의 근거: CLI별 종료 코드·구조화 오류 확인표 (T-OP-09 R6·R7 결과)\n\n"
            f"작성 {date}, 도구 `tools/daemon/runner_verify`. 미확인은 미확인으로 둔다. 확인되지 않은 종료 코드는 `runner_profile`에 넣지 않는다. "
            "자식 프로세스 stderr의 문자열은 전환 근거가 아니다.\n\n" + head + "\n".join(rows) + "\n\n"
            "읽는 법: 채널이 재현된 CLI는 `provider_http_response` 전환 신호를 그 구조화 출력에서 만들 수 있다. 종료 코드가 상황별로 갈리지 않으면 "
            "`runner_exit_code` 전환은 쓸 수 없고, 그 CLI는 `runner_profile.limit_exit_codes`·`unavailable_exit_codes`가 비어 있는 채로 "
            "(1)(3)(4)로만 전환한다. §1a(설치·인증·모델 증거)와 §2의 `model_matches_role`은 이 과제의 범위가 아니라 확인하지 않았다.\n")


def render_summary_json(report):
    """05 §2 record per runner path. Fields this task did not check are written as unconfirmed, not left out."""
    r7 = next((r for r in report["results"] if r["r"] == "R7"), None)
    table = (r7 or {}).get("evidence", {}).get("exit_code_table", {})
    out = []
    for t in cli_probe.TARGETS:
        row = table.get(t["id"], {})
        ec = row.get("exit_codes")
        out.append({"runner": t["label"], "role_name": "미확인", "installed": bool(row.get("installed")), "version": row.get("version"),
                    "auth": "미확인(확인하지 않음)", "model_evidence": [], "model_matches_role": None,
                    "min_call": {"ok": None, "latency_ms": None, "cost_units": None,
                                 "note": "실제 제공자 호출은 하지 않았다. 시험 프록시 호출만 했다"},
                    "exit_code_profile": {"confirmed": bool(ec and ec["confirmed"]),
                                          "source": "시험 프록시 재현" if ec else "미확인",
                                          "limit_exit_codes": (ec or {}).get("limit_exit_codes", []),
                                          "unavailable_exit_codes": (ec or {}).get("unavailable_exit_codes", [])},
                    "checked_at": report["generated_at"], "host_hash": report["environment"]["host_hash"]})
    return out


def render_overview(report):
    s = report["summary"]
    lines = ["# T-OP-09 실제 실행기 검증 결과 (R1~R22)", "",
             f"생성 {report['generated_at']} · 대상 {report['target']}", "",
             f"> {VM_NOTE}", f"> {APPROVAL}", "",
             f"시나리오 {s['scenarios']}개: " + ", ".join(f"{k} {v}" for k, v in s["status_counts"].items()) +
             f". 검사 {s['checks']}건 중 실패 {s['checks_failed']}건, 미확인 {s['checks_unconfirmed']}건, 명세 불일치(GAP) {s['gaps']}건.", "",
             "| R | 필수 시험 ID | 항목 | 결과 | 검사 | 실제로 쓴 구성 | 한계·대체물 |", "|---|---|---|---|---|---|---|"]
    for r in report["results"]:
        passed = sum(1 for c in r["checks"] if c["status"] == PASS)
        lines.append(f"| {r['r']} | {r['test_id'] or '-'} | {r['title']} | **{r['status']}** | {passed}/{len(r['checks'])} | "
                     f"{'; '.join(r['real_components'])} | {'; '.join(r['limits'])} |")
    lines += ["", "## 실패와 미확인", ""]
    any_bad = False
    for r in report["results"]:
        for c in r["checks"]:
            if c["status"] in (FAIL, UNCONFIRMED, GAP):
                any_bad = True
                why = c.get("reason") or c.get("note") or ""
                lines.append(f"- **{c['status']}** {r['r']} {c['name']}" + (f" — {why}" if why else ""))
    if not any_bad:
        lines.append("- 없음")
    lines += ["", "## 증명하지 않은 것 (시나리오별)", ""]
    for r in report["results"]:
        for item in r["not_proven"]:
            lines.append(f"- {r['r']}: {item}")
    lines += ["", "## 제품 브랜치", "", "```json", json.dumps(report["product_branch_check"], ensure_ascii=False, indent=1), "```", ""]
    return "\n".join(lines)
