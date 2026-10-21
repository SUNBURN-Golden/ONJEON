"""R6, R7, R10 and the real-CLI variant of R9: what a vendor CLI does against the test provider proxy.

Only a CLI with a confirmed way to reach the proxy is started (see fixtures/cli_targets.json); it gets a dummy key and
an isolated home directory. Everything the other CLIs would need (a login, a documented base-URL setting) is not
available on this host and is recorded as unconfirmed, never as a guess. Raw CLI output is not kept."""
import json
import os
import shutil
import threading
import time
from pathlib import Path

from . import cli_probe
from .harness import BASIC, HANDOFF, OTHER, noops, rets, se, tr
from .proxy import ProviderProxy
from .scn_fence import drain_ok, finished, snapshot_task


def cli_available(t):
    return bool(cli_probe.find(t)) and bool(t.get("proxy"))


def cli_builders(w, t):
    exe = cli_probe.find(t)
    b = json.loads(json.dumps(w.builders))
    return [{"name": "cli-builder-1", "runner": "cli-runner-1", "family": "cli-family-a", "probe": [exe, *t["version_args"]]}, b[1]]


def poll(fn, timeout=40, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def cli_output(path):
    try:
        return cli_probe.parse_stream(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {"retries": [], "result": None}


def start_lease_with_cli(w, t, px, retries, task=HANDOFF, prompt="hi", argv_wrap=None):
    """Lease a task to the CLI builder, start the real CLI as its process and let the adapter send the first heartbeat."""
    w.init_task(task).result
    assert w.grant(task).ok
    instr = w.latest_instruction(task)
    home = w.layout.root / "cli_home"
    env = cli_probe.cli_env(t, px.url, home, retries)
    argv = cli_probe.cli_args(t, prompt)
    if argv_wrap:
        argv = argv_wrap + argv
    out = w.layout.root / f"cli_{instr['lease_id']}.out"
    h = w.start_command(instr, argv, env, out)
    w.queue_file(w.envelope_msg(instr, "first_heartbeat"))
    drain_ok(w)
    return instr, h, out


def channel_signal(w, instr, kinds):
    """What a status-channel adapter does: the structured status the CLI printed becomes a switch signal
    (source provider_http_response) for the daemon. Nothing else is turned into a signal."""
    if not kinds:
        return False
    w.queue_file(w.envelope_msg(instr, "switch_signal", status=kinds[0]))
    return True


def switch_case(rep, cx, t, label, mode, retries, expect_signal, expect_status):
    with cx.world() as w:
        w.use_builders(cli_builders(w, t))
        px = ProviderProxy(mode).start()
        try:
            instr, h, out = start_lease_with_cli(w, t, px, retries)
            rep.eq(f"[{label}] 실제 CLI가 빌더 프로세스로 building이 되었다", ("building", "cli-builder-1"), (w.state(HANDOFF), w.lease(HANDOFF)["builder"]))
            got = poll(lambda: (lambda o: o if o["result"] else None)(cli_output(out)))
            calls = px.message_calls()
            rep.ok(f"[{label}] 시험 프록시에 CLI의 모델 호출이 도달했다(상태 {sorted({c['status'] for c in calls})})", bool(calls))
            statuses = [r["error_status"] for r in (got or {"retries": []})["retries"]]
            res = (got or {}).get("result") or {}
            rep.eq(f"[{label}] CLI의 구조화 출력(stream-json)에 제공자 HTTP 상태가 실린다: result.api_error_status", expect_status,
                   res.get("api_error_status"))
            kinds = cli_probe.signals_from_stream(got["retries"] if got else [], res) if got else []
            rep.eq(f"[{label}] 상태 채널에서 낸 전환 신호", expect_signal, kinds)
            m = w.mark()
            sent = channel_signal(w, instr, kinds)
            drain_ok(w)
            js = w.journal()[m:]
            if expect_signal:
                rep.eq(f"[{label}] 데몬이 신호를 받아 전환한다(building→handoff→leased, 두 번째 빌더)", (("building", "handoff", "switch_signal"), "leased", "standin-builder-2"),
                       (tr(js)[0], w.state(HANDOFF), w.lease(HANDOFF)["builder"]))
                w.wait_gone(h, 10)
                rep.eq(f"[{label}] 인계 뒤 CLI 프로세스 그룹이 남아 있지 않다", 0, w.ports().process.alive_count(HANDOFF))
            else:
                rep.eq(f"[{label}] 전환 신호가 없으면 전환하지 않는다(building 유지, 세대 1)", ("building", 1),
                       (w.state(HANDOFF), w.lease(HANDOFF)["lease_generation"]))
            return {"label": label, "mode": mode, "statuses": statuses, "result": {k: res.get(k) for k in ("api_error_status", "terminal_reason", "is_error")},
                    "signals": kinds, "proxy_statuses": sorted({c["status"] for c in calls})}
        finally:
            px.stop()


def r6(rep, cx):
    t = cli_probe.target("cli-claude")
    rows = []
    if cx.with_cli and cli_available(t):
        rows.append(switch_case(rep, cx, t, "claude CLI, 프록시 429", "429", 1, ["usage_limit"], 429))
        rows.append(switch_case(rep, cx, t, "claude CLI, 프록시 503 연속", "503", 3, ["service_unavailable"], 503))
        rows.append(switch_case(rep, cx, t, "claude CLI, 프록시 401", "401", 1, ["auth_failure"], 401))
        # negative: the provider answers normally but the text talks about limits; a child output says 429
        with cx.world() as w:
            w.use_builders(cli_builders(w, t))
            px = ProviderProxy("ok", reply_text="HTTP 429 rate limit exceeded quota exceeded").start()
            try:
                instr, h, out = start_lease_with_cli(w, t, px, 1)
                got = poll(lambda: (lambda o: o if o["result"] else None)(cli_output(out)))
                kinds = cli_probe.signals_from_stream(got["retries"], got["result"]) if got else ["?"]
                rep.eq("[음성] 정상 응답이지만 본문에 '429 rate limit'이 있는 CLI: 상태 채널은 신호를 내지 않는다", ([], 0),
                       (kinds, (got["result"] or {}).get("api_error_status") and 1 or 0))
                m = w.mark()
                for src, status, extra in (("child_process_stderr", "usage_limit", {"text": "rate limit exceeded"}),
                                           ("test_output", "usage_limit", {"text": "HTTP 429"}),
                                           ("target_site_http", "auth_failure", {"http_status": 403}),
                                           ("repo_api", "auth_failure", {"http_status": 401})):
                    w.queue_file(w.envelope_msg(instr, "switch_signal", source=src, status=status, **extra))
                drain_ok(w)
                rep.eq("[음성] 자식 출력·시험 로그·수집 대상 403·저장소 API 401 출처의 신호는 전환시키지 않는다(실제 파일 큐 경로)",
                       ("building", 1, []), (w.state(HANDOFF), w.lease(HANDOFF)["lease_generation"], tr(w.journal()[m:])))
            finally:
                px.stop()
    else:
        rep.unconfirmed("[claude CLI] 시험 프록시로 보낼 수 있는 실제 CLI가 이 실행에 없다", "CLI 미설치이거나 --no-cli")
    # negatives that do not need a vendor CLI: the scripted builder prints rate-limit text and sends it as a child output
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(HANDOFF, [{"op": "wait_file", "path": go},
                                                    {"op": "switch_signal", "source": "child_process_stderr", "status": "usage_limit",
                                                     "fields": {"text": "rate limit exceeded"}},
                                                    {"op": "switch_signal", "source": "target_site_http", "status": "auth_failure",
                                                     "fields": {"http_status": 403}},
                                                    {"op": "sleep", "s": 3600}])
        open(go, "w").close()
        w.wait_log(a, "switch_signal", count=2)
        m = w.mark()
        drain_ok(w)
        rep.eq("[스크립트 프로세스] 자식 출력 429 문구·수집 대상 403은 전환이 아니다(building 유지, 세대 1, 전이 0)", ("building", 1, []),
               (w.state(HANDOFF), w.lease(HANDOFF)["lease_generation"], tr(w.journal()[m:])))
    # the other CLIs: nothing can be measured on this host
    for tid in ("cli-cursor", "cli-grokbuild", "cli-devin", "cli-claude-glm", "cli-gpt-route"):
        tt = cli_probe.target(tid)
        ver = cli_probe.version(tt) if tt.get("command") else None
        rep.unconfirmed(f"[{tt['label']}] 모델 제공자 상태가 CLI의 상태 채널로 데몬에 도달하는지",
                        f"{tt['unconfirmed_reason']}" + (f" (설치 확인: 버전 {ver})" if ver else ""))
    rep.evid("claude_rows", rows)
    rep.evid("runner_profile_for_unconfirmed", {"limit_exit_codes": [], "unavailable_exit_codes": [],
                                                 "note": "도달이 확인되지 않은 CLI는 provider_http_response·exit code 전환을 쓰지 않는다(그 CLI는 인증·버전 프로브로만 전환)"})
    rep.not_proved("프록시는 CLI의 기본 주소 설정으로 가리킨 로컬 서버다. 실제 제공자가 내는 429·5xx 본문·헤더·재시도 지시와의 차이는 확인하지 못했다",
                   "확인한 것은 이 CLI 버전과 이 출력 모드(stream-json)에서의 상태 채널이다. 다른 모드·버전은 다시 확인해야 한다",
                   "claude CLI 밖의 실행 경로(Cursor, grokbuild, Devin, GLM 프로필, GPT Astra 경로)는 이 호스트에서 시험하지 못했다(§1b 확인표는 미확인으로 남는다)")


# =============================================================== R7
SITUATIONS = [("429", "429", 1, 2), ("500", "500", 3, 1), ("503", "503", 3, 1), ("529", "529", 3, 1), ("401", "401", 1, 1),
              ("403", "403", 1, 1), ("400_quota", "400_quota", 1, 1), ("ok", "ok", 1, 1)]


def r7(rep, cx):
    table = {}
    for t in cli_probe.TARGETS:
        row = {"label": t["label"], "installed": bool(cli_probe.find(t)) if t.get("command") else False,
               "version": cli_probe.version(t) if t.get("command") else None}
        if cx.with_cli and cli_available(t):
            px = ProviderProxy("ok").start()
            home = Path(cx.workdir or "/tmp") / f"rv-cli-home-{t['id']}"
            runs = {}
            try:
                for name, mode, retries, times in SITUATIONS:
                    px.set_mode(mode)
                    runs[name] = [cli_probe.run_once(t, px.url, home, retries, cwd=str(home.parent)) for _ in range(times)]
                closed = cli_probe.run_once(t, "http://127.0.0.1:9", home, 1, cwd=str(home.parent))
                runs["connection_refused"] = [closed]
                usage = cli_probe.run_once(t, px.url, home, 1, extra_args=["--no-such-flag-for-test"], cwd=str(home.parent))
                runs["local_usage_error"] = [usage]
            finally:
                px.stop()
                shutil.rmtree(home, ignore_errors=True)
            row["exit_codes"] = cli_probe.exit_code_row(runs)
            row["situations"] = {k: [{"rc": r["rc"], "api_error_status": (r["result"] or {}).get("api_error_status"),
                                      "retry_statuses": [x["error_status"] for x in r["retries"]], "wall_s": r["wall_s"]} for r in v]
                                 for k, v in runs.items()}
            row["status_channel"] = t["proxy"]["status_channel"]
        else:
            row["exit_codes"] = None
            row["unconfirmed_reason"] = t.get("unconfirmed_reason", "이 실행에서 시험하지 않았다")
        table[t["id"]] = row
    rep.evid("exit_code_table", table)
    claude = table["cli-claude"]
    if claude.get("exit_codes"):
        sit = claude["situations"]
        for name, status in (("429", 429), ("500", 500), ("503", 503), ("529", 529), ("401", 401), ("403", 403), ("400_quota", 400)):
            rep.eq(f"[claude CLI] 프록시 {name}: result.api_error_status가 프록시가 돌려준 상태와 같다", [status] * len(sit[name]),
                   [r["api_error_status"] for r in sit[name]])
        rep.eq("[claude CLI] 같은 상황을 두 번 돌린 429의 종료 코드가 같다(재현됨)", True, len({r["rc"] for r in sit["429"]}) == 1)
        codes = claude["exit_codes"]
        # the rule: a code goes into runner_profile only if it is unique to the situation
        expected_limit = [c for c in codes["codes_by_situation"].get("429", []) if c != 0 and not any(
            c in v for k, v in codes["codes_by_situation"].items() if k != "429")]
        rep.eq("[claude CLI] runner_profile.limit_exit_codes는 한도 상황에만 나타난 종료 코드만 담는다(다른 실패와 겹치면 비어 있다)",
               expected_limit, codes["limit_exit_codes"])
        rep.eq("[claude CLI] 확인되지 않은 종료 코드는 runner_profile에 넣지 않는다: 종료 코드가 한도·불가·인증·일반 실패에서 겹치면 두 목록 모두 비어 있다",
               True, (not codes["confirmed"]) == (codes["limit_exit_codes"] == [] and codes["unavailable_exit_codes"] == []))
    else:
        rep.unconfirmed("[claude CLI] 종료 코드 재현", "CLI 미설치이거나 --no-cli")
    for tid, row in table.items():
        if tid != "cli-claude":
            rep.unconfirmed(f"[{row['label']}] 종료 코드·구조화 오류 확인", row.get("unconfirmed_reason", "시험하지 않았다"))
    rep.not_proved("종료 코드는 시험 프록시가 만든 상황에서 얻은 값이다. 공식 문서의 종료 코드 표와 대조하지 않았다",
                   "§1b 확인표의 '모델 제공자 HTTP 응답을 데몬이 볼 수 있는 채널'은 claude CLI의 stream-json 출력(이 버전)만 확인되었다")


# =============================================================== R10
def r10(rep, cx):
    t = cli_probe.target("cli-claude")
    HUGE = 10 ** 9
    if cx.with_cli and cli_available(t):
        with cx.world() as w:
            w.use_builders(cli_builders(w, t))
            px = ProviderProxy("ok").start()
            try:
                instr, h, out = start_lease_with_cli(w, t, px, 1, task=BASIC)
                got = poll(lambda: (lambda o: o if o["result"] else None)(cli_output(out)), timeout=60)
                w.wait_gone(h, 20)
                wall = max(1, int(round(time.time() - h.began)))
                calls = px.message_calls()
                ok_calls = [c for c in calls if c["status"] == 200]
                tokens = sum(c.get("tokens_in", 0) + c.get("tokens_out", 0) for c in ok_calls)
                rep.ok("실제 CLI 실행이 끝났고 프록시가 모델 호출을 계량했다", bool(got) and len(ok_calls) >= 1,
                       {"calls": len(ok_calls), "tokens_metered": tokens, "cli_reported_cost_usd": (got or {}).get("result", {}).get("cli_cost_usd")})
                w.queue_file(w.envelope_msg(instr, "result", status="failed_tests", calls=len(ok_calls), wall_s=wall, cost_units=tokens))
                drain_ok(w)
                row = [r for r in w.snap()["usage_record"] if r["task_id"] == BASIC and r["lease_generation"] == 1][0]
                rep.eq("usage_record(세대 1)에 calls·wall_s·cost_units가 기록된다", (len(ok_calls), wall, tokens),
                       (row["calls"], row["wall_s"], row["cost_units"]))
                rep.evid("metering", {"calls": "프록시 계량", "wall_s": "호스트 측정", "cost_units": "프록시가 센 토큰 수(단위는 명세에 없다)",
                                      "cost_amount": "기록 불가(프록시는 단가표를 모른다; 제공자 청구 대조는 월 1회 사람)",
                                      "cli_self_reported_cost_usd_reference": (got or {}).get("result", {}).get("cli_cost_usd")})
                rep.eq("기록 뒤 같은 과제의 새 임대(세대 2)가 막히지 않는다", ("building", 2), (w.state(BASIC), w.lease(BASIC)["lease_generation"]))
            finally:
                px.stop()
    else:
        rep.unconfirmed("[실제 CLI 실행의 calls·wall_s·cost_units 기록]", "시험 프록시로 보낼 수 있는 실제 CLI가 이 실행에 없다")
    # accumulated usage does not stop anything; the failure controls stay
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": go},
                                                  {"op": "result", "status": "failed_tests",
                                                   "fields": {"cost_units": HUGE, "calls": HUGE, "wall_s": HUGE}},
                                                  {"op": "sleep", "s": 3600}])
        open(go, "w").close()
        w.wait_log(a, "result")
        finished(drain_ok(w))
        row = [r for r in w.snap()["usage_record"] if r["task_id"] == BASIC and r["lease_generation"] == 1][0]
        rep.eq("누적 사용량이 10^9여도 기록되고 거부되지 않는다", (HUGE, HUGE, HUGE), (row["cost_units"], row["calls"], row["wall_s"]))
        rep.eq("새 임대(같은 과제 세대 2)가 막히지 않았다", ("building", 2), (w.state(BASIC), w.lease(BASIC)["lease_generation"]))
        instr2 = w.latest_instruction(BASIC)
        h2 = w.start_builder(instr2, [{"op": "first_heartbeat"}, {"op": "result", "status": "failed_tests", "fields": {"cost_units": HUGE}},
                                      {"op": "sleep", "s": 3600}])
        w.wait_log(h2, "result")
        finished(drain_ok(w))
        instr3 = w.latest_instruction(BASIC)
        h3 = w.start_builder(instr3, [{"op": "first_heartbeat"}, {"op": "result", "status": "failed_tests", "fields": {"cost_units": HUGE}},
                                      {"op": "sleep", "s": 3600}])
        w.wait_log(h3, "result")
        m = w.mark()
        finished(drain_ok(w))
        rep.eq("같은 실패 재시도 한도는 그대로: 세 번째 시험 실패에서 R-06 반송(전환이 아니다)", (["R-06"], "returned", 3),
               (rets(w.journal()[m:]), w.state(BASIC), w.lease(BASIC)["lease_generation"]))
        # another task: a new lease is issued although the total usage is huge
        w.init_task(OTHER).result
        res = w.grant(OTHER)
        rep.eq("다른 과제의 새 임대도 막히지 않는다(누적 사용량이 커도)", "leased", w.state(OTHER))
        instr_o = w.latest_instruction(OTHER)
        ho = w.start_builder(instr_o, [{"op": "first_heartbeat"}, {"op": "sleep", "s": 3600}])
        w.wait_log(ho, "first_heartbeat")
        drain_ok(w)
        w.advance(2 * w.heartbeat_s() + 1)
        m = w.mark()
        w.tick()
        rep.eq("응답 없음 정지는 그대로: 하트비트 두 번 누락이면 R-08", (["R-08"], "returned"), (rets(w.journal()[m:]), w.state(OTHER)))

    # the recording itself fails: a warning and a retry entry, nothing stops
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": go},
                                                  {"op": "result", "status": "failed_tests", "fields": {"cost_units": 7, "calls": 3, "wall_s": 9}},
                                                  {"op": "sleep", "s": 3600}])
        open(go, "w").close()
        w.wait_log(a, "result")
        m = w.mark()
        res = w.drain(fail=["usage:record_result"])
        js = w.journal()[m:]
        rep.eq("기록이 실패해도 결과 봉투는 수락되고 재임대가 이어진다(경고와 재시도 항목만)", (True, "building", 2, ["usage_record_failed_warning"]),
               (res.ok, w.state(BASIC), w.lease(BASIC)["lease_generation"],
                [r["what"] for r in js if r["kind"] == "diagnostic_record" and r["what"].startswith("usage_record")]))
        rep.eq("재시도 항목이 남아 있고, 비동기 재시도가 값을 채운다", (1, 1, (3, 9, 7)),
               (len(w.snap().get("usage_retry", [])), w.daemon("retry-usage").result["written"],
                (lambda r: (r["calls"], r["wall_s"], r["cost_units"]))(
                    [x for x in w.snap()["usage_record"] if x["task_id"] == BASIC and x["lease_generation"] == 1][0])))
    rep.not_proved("호출 수·토큰은 프록시를 거친 호출만 계량한다. 프록시를 거치지 않는 직접 호출·제공자 청구액과의 대조는 하지 않았다(사람이 월 1회, 05 §3)",
                   "cost_units의 단위는 명세에 정의가 없다. 이 시험은 프록시가 센 토큰 수를 넣었고 금액이 아니다",
                   "누적 10^9는 스크립트 프로세스가 결과 봉투에 적은 자기 보고 값이다")


# =============================================================== R9, real CLI variant
def r9_real_cli(rep, cx):
    t = cli_probe.target("cli-claude")
    if not (cx.with_cli and cli_available(t)):
        rep.unconfirmed("[R9 실제 CLI 변형] 하트비트를 계속 보내는 실제 CLI 프로세스의 강제 종료", "시험 프록시로 보낼 수 있는 실제 CLI가 이 실행에 없다")
        return
    with cx.world() as w:
        w.use_builders(cli_builders(w, t))
        px = ProviderProxy("hang").start()
        stop_beats = threading.Event()
        try:
            instr, h, out = start_lease_with_cli(w, t, px, 1, task=OTHER, argv_wrap=["sh", "-c", 'trap "" TERM; exec "$@"', "sh"])
            poll(lambda: px.message_calls(), timeout=60)
            rep.ok("[실제 CLI] CLI의 모델 호출이 프록시에 붙잡혀 있고 프로세스는 살아 있다(하트비트를 보내는 어댑터와 함께)",
                   h.popen.poll() is None and bool(px.message_calls()))

            def beats():
                while not stop_beats.is_set() and h.popen.poll() is None:
                    w.queue_file(w.envelope_msg(instr, "heartbeat"))
                    time.sleep(0.3)
            th = threading.Thread(target=beats, daemon=True)
            th.start()
            grace = int(w.rules.number("hard_stop.grace_s"))
            w.event("owner_stop", OTHER, {"stop_ref": "STOP-R9-CLI"}).result
            stop_at = w.task(OTHER)["task_state"]["stop_requested_at"]
            w.ports().sender.request_stop(OTHER, instr["builder"])
            time.sleep(1.0)
            survived = h.popen.poll() is None
            rep.evid("claude_survived_sigterm", survived)
            if survived:
                rep.ok("[실제 CLI] SIGTERM을 무시한 채(trap으로 무시 설정을 물려줌) 살아 있고 하트비트가 계속 간다", True)
            else:
                rep.unconfirmed("[실제 CLI] SIGTERM을 무시하며 하트비트를 보내는 실제 CLI의 강제 종료(grace_s 뒤 그룹 종료)",
                                "이 CLI는 SIGTERM에 스스로 종료했다(셸 trap으로 무시를 물려줘도 자체 핸들러가 이를 덮었다). "
                                "grace_s 뒤 그룹 종료가 이 CLI를 끝낸 것이 아니므로 그 부분은 스크립트 프로세스(standin) 결과만 있다")
            while stop_at + grace - w.clock.now() > 12 and w.state(OTHER) == "building":
                w.advance(min(20, stop_at + grace - w.clock.now() - 12))
                time.sleep(0.4)
                drain_ok(w)
                w.tick()
            w.advance(max(0, stop_at + grace - w.clock.now()) + 1)
            time.sleep(0.4)
            drain_ok(w)
            m = w.mark()
            w.tick()
            js = w.journal()[m:]
            rep.eq("[실제 CLI] grace_s 경과: hard_stop_deadline → returned(R-07)", ([("building", "returned", "hard_stop_deadline")], ["R-07"]),
                   (tr(js), rets(js)))
            rep.eq("[실제 CLI] 실제 CLI 프로세스 그룹이 사라졌다(남은 구성원 0)", (True, 0), (w.wait_gone(h, 10), w.ports().process.alive_count(OTHER)))
            stop_beats.set()
            th.join(timeout=3)
            rep.ok("[실제 CLI] 쓰기 자격 회수(자격 저장소에 살아 있는 자격 없음)", not w.ports().credentials.is_active("builder_write_credential", OTHER))
            w.queue_file(w.envelope_msg(instr, "heartbeat"))
            m = w.mark()
            drain_ok(w)
            rep.ok("[실제 CLI] 그 뒤 도착한 봉투는 모두 late로 거부된다(수락 0건)", all(n[0] == "late_envelope_rejected" for n in noops(w.journal()[m:])) and
                   w.state(OTHER) == "returned")
        finally:
            stop_beats.set()
            px.stop()
