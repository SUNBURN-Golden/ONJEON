"""Scenarios M26, M28-M30, M33-M44 of T-OP-00 (the lease, envelope, restart and handoff core). M1-M25, M27, M31 and
M32 are in scenarios_flow.py. Each scenario builds a fresh bench, drives the shared core through the events of the
scenario and compares expected values (written here as literals) with what the journal and the stores show
afterwards."""
import copy
import re
import threading

from . import static_checks
from .bench import (ALWAYS_REVOKE, BASIC, FAIL, GAP, HANDOFF, OTHER, PASS, TTL, Report, crash_after_issue, failed_guard_ids,  # noqa: F401
                    fake_secret, first_seq, handoff_bench, jr, mark, noops, rets, se, sent_ids, switch, tr)
from .core.ports import (CommitFailed, DiskFullError, IndexLockError, PreconditionFailed, PushFailed, SimulatedCrash)  # noqa: F401
from .mock_env import MockEnv
from .scenarios_flow import FLOW_SCENARIOS

# =============================================================== M41
def m41(rep, R, T):
    env = MockEnv(R, T)
    env.start_task(BASIC)
    rep.eq("발급 직후 중단 지점", "issue_lease:committed", crash_after_issue(env, BASIC))
    t = env.task(BASIC)
    old = t["outbox"][0]["envelope_id"]
    rep.eq("중단 시점: 상태·세대·outbox·발송", ("leased", 1, "pending", 0),
           (t["task_state"]["state"], t["lease_generation"], t["outbox"][0]["status"], len(sent_ids(env))))
    env.clock.advance(TTL + 1)
    m = mark(env)
    env.restart()
    js = jr(env, m)
    rep.eq("재시작: 정상 만료 전이", [("leased", "queued", "lease_expired")], tr(js))
    rep.eq("재시작: 부수 효과 = end_lease(만료)와 임대 종료 부수 효과(on_lease_end), void",
           ["end_lease", "terminate_process", "revoke_write_credential", "revoke_token", "record_handoff", "void_outbox"], se(js))
    t = env.task(BASIC)
    rep.eq("pending outbox는 void(expired)", ("void", "expired"), (t["outbox"][0]["status"], t["outbox"][0]["void_reason"]))
    rep.eq("재발송 0건", [], sent_ids(env))
    rep.eq("자동 재발급 없음(세대 1, 상태 queued, 임대 expired)", (1, "queued", "expired"),
           (t["lease_generation"], t["task_state"]["state"], t["lease_record"]["status"]))
    rep.eq("재시작에서 issue_lease 0건", 0, len(se(js, "issue_lease")))
    m = mark(env)
    env.grant(BASIC)
    js = jr(env, m)
    t = env.task(BASIC)
    new = t["outbox"][-1]["envelope_id"]
    rep.eq("그 뒤 queued→leased", [("queued", "leased", "lease_granted")], tr(js))
    rep.eq("issue_lease 한 번과 새 봉투 발송", ["issue_lease", "send_envelope"], se(js, "issue_lease", "send_envelope"))
    rep.eq("새 세대", 2, t["lease_generation"])
    rep.eq("새 envelope_id는 옛 것과 다르다", True, new != old)
    rep.eq("발송된 봉투는 새 것뿐(옛 envelope_id 재사용 없음)", [new], sent_ids(env))
    env.restart()
    rep.eq("두 번째 재시작은 새 임대를 그대로 둔다(발송 1건 유지)", [new], sent_ids(env))

    # G22: a leased lease that never got a heartbeat expires at issued_at + heartbeat_s*2, in the restart
    # classification and in the transition alike
    env = MockEnv(R, T)
    env.start_task(BASIC)
    crash_after_issue(env, BASIC)
    env.clock.advance(599)
    m = mark(env)
    env.restart()
    rep.eq("하트비트 없는 leased: 599초에는 정상(재발송)", ([], 1), (tr(jr(env, m)), len(sent_ids(env))))
    env.clock.advance(1)
    env.store.tamper(lambda d: d.update(secret_hits=[{"task_id": BASIC, "match_count": 1}]))
    env.core.tick()
    rep.eq("600초(heartbeat_s*2)에 만료 전이", [("leased", "queued", "lease_expired")], tr(jr(env, m)))
    rep.eq("정상 만료로 끝난 tick도 대기 중인 비밀값 검출을 처리한다(남기지 않음)",
           (False, ["secret_redacted_outside_scan_states"]),
           ("secret_hits" in env.snap(), [r["what"] for r in jr(env, m) if r["kind"] == "diagnostic_record" and r["what"].startswith("secret_")]))

    # the lease expires between the send and the marking transaction: mark_sent is a compare-and-set on
    # checks[pending], so the void(expired) row is not overwritten with sent
    env = MockEnv(R, T)
    env.start_task(BASIC)

    def expire_now(task_id):
        env.clock.advance(TTL + 1)
        env.core.tick()
    env.ports.sender.during_send = expire_now
    m = mark(env)
    env.grant(BASIC)
    js = jr(env, m)
    row = env.task(BASIC)["outbox"][0]
    rep.eq("발송과 표시 사이 만료: 행은 void(expired)로 남고 sent_at 없음, 발송 기록 0, 결과 not_marked",
           (("void", "expired", None), [], ["not_marked"], ["outbox_not_pending_at_mark"]),
           ((row["status"], row["void_reason"], row["sent_at"]), se(js, "send_envelope"),
            [r["outcome"] for r in js if r["kind"] == "result_record" and r["action"] == "send_envelope"],
            [r["what"] for r in js if r["kind"] == "diagnostic_record" and r["what"] == "outbox_not_pending_at_mark"]))
    m = mark(env)
    rep.eq("이미 나간 그 봉투: 빌더는 lease_invalid만, R-11 noop, 상태 queued 그대로", (["lease_invalid"], [("late_envelope_rejected", "R-11")], [], "queued"),
           ([o[0] for o in env.run_builders()], noops(jr(env, m)), tr(jr(env, m)), env.state(BASIC)))


# =============================================================== M42
def m42(rep, R, T):
    env = MockEnv(R, T)
    env.start_task(BASIC)
    crash_after_issue(env, BASIC)
    env.new_core()
    env.event("owner_cancelled", BASIC)
    t = env.task(BASIC)
    rep.eq("A 취소: 상태·취소 표시·임대·outbox", ("cancelled", True, "revoked", "pending"),
           (t["task_state"]["state"], t["task_state"]["cancelled"], t["lease_record"]["status"], t["outbox"][0]["status"]))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    t = env.task(BASIC)
    rep.eq("A 재시작: 전이 없음", [], tr(js))
    rep.eq("A 재시작: void 하나, issue_lease 없음", ["void_outbox"], se(js))
    rep.eq("A void(revoked_or_cancelled → reason revoked)", ("void", "revoked"), (t["outbox"][0]["status"], t["outbox"][0]["void_reason"]))
    rep.eq("A 재발송 0건, 상태·세대 불변", ([], "cancelled", 1), (sent_ids(env), t["task_state"]["state"], t["lease_generation"]))
    rep.eq("취소도 revoked로 기록하고 void_reason 열거에 cancelled가 없다(G41)", ("revoked", False),
           (t["outbox"][0]["void_reason"], "cancelled" in env.rules.get("core_contract.store.enums.outbox_void_reason")))

    # B: a re-lease (building -> building) is committed, the daemon dies, then the current lease is revoked
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    b = env.builder_for(BASIC)
    old = copy.deepcopy(env.instr(BASIC))
    env.ports.faults.arm("issue_lease:committed")
    env.crash(lambda: b.send_result(old, "failed_tests"))
    env.new_core()
    cur = env.lease(BASIC)
    env.submit(BASIC, "fence_violation", {"envelope_id": "V-CUR", "task_id": BASIC, "lease_id": cur["lease_id"],
               "lease_generation": cur["lease_generation"], "fencing_token": cur["fencing_token"],
               "kind": "direct_push", "observed_at": env.clock.now()})
    t = env.task(BASIC)
    rep.eq("B 폐기: 상태·임대 상태·outbox", ("returned", "revoked", "pending"),
           (t["task_state"]["state"], t["lease_record"]["status"], t["outbox"][-1]["status"]))
    m = mark(env)
    sent_before = len(sent_ids(env))
    env.restart()
    js = jr(env, m)
    t = env.task(BASIC)
    rep.eq("B 재시작: 전이 없음", [], tr(js))
    rep.eq("B void 하나", ["void_outbox"], se(js))
    rep.eq("B void 사유 revoked", ("void", "revoked"), (t["outbox"][-1]["status"], t["outbox"][-1]["void_reason"]))
    rep.eq("B 재발송 0건, 상태 returned 불변", (sent_before, "returned"), (len(sent_ids(env)), t["task_state"]["state"]))


# =============================================================== M43
def m43(rep, R, T):
    env = MockEnv(R, T)
    env.start_task(BASIC)
    crash_after_issue(env, BASIC)
    e1 = env.task(BASIC)["outbox"][0]["envelope_id"]
    m = mark(env)
    env.restart()
    js = jr(env, m)
    rep.eq("유효한 pending: 재시작에서 전이 없음", [], tr(js))
    rep.eq("같은 envelope_id로 재발송 한 번", ["send_envelope"], se(js))
    rep.eq("발송된 봉투", [e1], sent_ids(env))
    t = env.task(BASIC)
    rep.eq("outbox status=sent, 세대 불변", ("sent", 1), (t["outbox"][0]["status"], t["lease_generation"]))
    m = mark(env)
    results = env.run_builders()
    b = env.builders["mock-builder-1"]
    rep.eq("빌더는 수신 측 검증을 통과해 실행", ([e1], [], ["started"]), (b.executed, b.invalid, [r[0] for r in results]))
    rep.eq("first_heartbeat로 building", [("leased", "building", "first_heartbeat")], tr(jr(env, m)))
    m = mark(env)
    hb = b.seen_instructions[e1]
    out1 = env.submit(BASIC, "first_heartbeat", copy.deepcopy(hb))
    out2 = b.on_instruction(copy.deepcopy(env.instr(BASIC)))
    rep.eq("같은 봉투 중복 도착은 noop", [("envelope_duplicate_delivery", None)] * 2, noops(jr(env, m)))
    rep.eq("중복 도착 뒤 상태·전이 불변", ("building", []), (env.state(BASIC), tr(jr(env, m))))
    rep.eq("중복 도착 결과 표시", ("envelope_duplicate_delivery", "duplicate"), (out1["noop"], out2[0]))

    # an envelope that reaches the builder after its lease expired
    env = MockEnv(R, T)
    env.start_task(BASIC)
    env.ports.sender.hold = True
    env.grant(BASIC)
    e1 = sent_ids(env)[0]
    env.clock.advance(TTL + 1)
    env.ports.sender.release()
    m = mark(env)
    results = env.run_builders()
    b = env.builders["mock-builder-1"]
    rep.eq("만료 봉투: 빌더는 실행하지 않는다", ([], [e1], {}), (b.executed, b.invalid, env.ports.process.procs))
    rep.eq("만료 봉투: lease_invalid 결과만 보냄", ["lease_invalid"], [r[0] for r in results])
    rep.eq("만료 봉투 결과는 late_envelope_rejected(noop, R-11 기록: G06 확정), 상태 불변",
           ([("late_envelope_rejected", "R-11")], [], "leased"), (noops(jr(env, m)), tr(jr(env, m)), env.state(BASIC)))

    # an old envelope (old generation) that reaches the builder after a new lease was issued
    env = MockEnv(R, T)
    env.start_task(BASIC)
    env.ports.sender.hold = True
    env.grant(BASIC)
    env.clock.advance(TTL + 1)
    env.core.tick()
    env.grant(BASIC)
    old, new = sent_ids(env)
    env.ports.sender.release()
    m = mark(env)
    results = env.run_builders()
    b = env.builders["mock-builder-1"]
    rep.eq("세대가 바뀐 옛 봉투: 빌더는 새 봉투만 실행", ([new], [old]), (b.executed, b.invalid))
    rep.eq("옛 봉투의 lease_invalid는 R-11 late_envelope_rejected, 새 봉투는 building",
           ([("late_envelope_rejected", "R-11")], [("leased", "building", "first_heartbeat")]),
           (noops(jr(env, m)), tr(jr(env, m))))


# =============================================================== M44
def m44(rep, R, T):
    for variant, tamper in (
        ("outbox 없이 lease_record만", lambda d: d["tasks"][BASIC].update(outbox=[])),
        ("outbox 세대 불일치", lambda d: d["tasks"][BASIC]["outbox"][0].update(lease_generation=7)),
    ):
        env = MockEnv(R, T)
        env.start_task(BASIC)
        crash_after_issue(env, BASIC)
        env.store.tamper(tamper)
        m = mark(env)
        env.restart()
        js = jr(env, m)
        t = env.task(BASIC)
        rep.eq(f"[{variant}] 손상 분류: 사건 state_corrupted → returned", [("leased", "returned", "state_corrupted")], tr(js))
        pending_void = ["void_outbox"] if variant.startswith("outbox 세대") else []
        rep.eq(f"[{variant}] 부수 효과: 임대 종료·토큰 폐기·자격 회수{'·pending void' if pending_void else ''}·R 코드",
               ["end_lease", "terminate_process", "record_handoff", "revoke_token", "revoke_write_credential",
                "revoke_preserve_credential"] + pending_void + ["record_r_code"], se(js))
        rep.eq(f"[{variant}] 반송 코드 R-08", ["R-08"], rets(js))
        rep.eq(f"[{variant}] 효과 id가 회수하는 자격(credential_of_effect)",
               [("revoke_token", "builder_token"), ("revoke_write_credential", "builder_write_credential"),
                ("revoke_preserve_credential", "preserve_credential")],
               [(r["id"], r["args"]["credential"]) for r in js if r["kind"] == "side_effect_record"
                and r["id"] in ("revoke_token", "revoke_write_credential", "revoke_preserve_credential")])
        if pending_void:
            rep.eq(f"[{variant}] pending void(corrupt)", ("void", "corrupt"), (t["outbox"][0]["status"], t["outbox"][0]["void_reason"]))
        rep.eq(f"[{variant}] 임대 revoked, 세대 불변, 발송 0, issue_lease 0", ("revoked", 1, [], 0),
               (t["lease_record"]["status"], t["lease_generation"], sent_ids(env), len(se(js, "issue_lease"))))
        m = mark(env)
        env.restart()
        rep.eq(f"[{variant}] 다시 재시작해도 자동 재발급 없음", ([], "returned", 1),
               (tr(jr(env, m)), env.state(BASIC), env.task(BASIC)["lease_generation"]))
        m = mark(env)
        env.event("owner_resolved", BASIC, resolution_ref="RES-1")
        rep.eq(f"[{variant}] owner_resolved → queued(attempt+1)", ([("returned", "queued", "owner_resolved")], 2),
               (tr(jr(env, m)), env.task(BASIC)["task_state"]["attempt"]))
        rep.eq(f"[{variant}] 이 시점까지 issue_lease 0건", 0, len(se(jr(env, m), "issue_lease")))
        m = mark(env)
        env.grant(BASIC, "from_queue")
        rep.eq(f"[{variant}] queued→leased에서만 새 세대", ([("queued", "leased", "lease_granted")], 1, 2),
               (tr(jr(env, m)), len(se(jr(env, m), "issue_lease")), env.task(BASIC)["lease_generation"]))


# =============================================================== M40
def issue_count(env):
    return len(se(env.journal(), "issue_lease"))


def issue_reasons(env):
    return [r["args"]["reason"] for r in env.journal() if r["kind"] == "side_effect_record" and r["id"] == "issue_lease"]


def m40(rep, R, T):
    env = MockEnv(R, T)
    steps = []
    t = HANDOFF

    def step(label, fn):
        g0, i0 = env.task(t)["lease_generation"] if t in env.snap()["tasks"] else 0, issue_count(env)
        fn()
        steps.append((label, env.task(t)["lease_generation"] - g0, issue_count(env) - i0))

    step("초기 발급(queued→leased)", lambda: env.bring_to_building(t))
    b = env.builder_for(t)

    def failed_tests():
        b.send_result(env.instr(t), "failed_tests")
        env.run_builders("first_heartbeat")

    step("시험 실패 뒤 재임대(building→building)", failed_tests)

    def handoff():
        env.submit(t, "switch_signal", b.signal_envelope(env.instr(t)))
        env.run_builders()

    step("인계(handoff→leased)", handoff)

    def returned_resume():
        b2 = env.builder_for(t)
        b2.send_result(env.instr(t), "verdict_requested")
        env.event("owner_resolved", t, resolution_ref="RES-1")
        env.grant(t, "from_queue")
        env.run_builders()

    step("반송 뒤 재개(returned→queued→leased)", returned_resume)
    rep.eq("각 경로: (세대 증가, issue_lease 기록) = (1, 1)", [(s[0], 1, 1) for s in steps], [(s[0], s[1], s[2]) for s in steps])
    rep.eq("최종 세대 = issue_lease 기록 수", issue_count(env), env.task(t)["lease_generation"])
    rep.eq("각 경로가 부른 issue_lease의 reason(전이 side_effects의 args)", ["from_queue", "retry_failed_tests", "handoff", "from_queue"],
           issue_reasons(env))

    # many paths call issue_lease at once
    env = MockEnv(R, T)
    env.start_task(BASIC)
    results, lock = [], threading.Lock()

    def via_issue():
        try:
            env.core.issue_lease(BASIC, "from_queue")
            r = "issued"
        except PreconditionFailed:
            r = "precondition_failed"
        with lock:
            results.append(r)

    threads = [threading.Thread(target=via_issue) for _ in range(8)]
    [x.start() for x in threads]
    [x.join() for x in threads]
    t_ = env.task(BASIC)
    rep.eq("동시 8개 호출: 성공 1, 전제 실패 7", (1, 7), (results.count("issued"), results.count("precondition_failed")))
    rep.eq("세대 1, 임대 기록 1개, outbox 1행, issue_lease 기록 1건", (1, 1, 1, 1),
           (t_["lease_generation"], t_["lease_record"]["lease_generation"], len(t_["outbox"]), issue_count(env)))

    # the same lease_granted event handled by many paths at once
    env = MockEnv(R, T)
    env.start_task(BASIC)
    threads = [threading.Thread(target=lambda: env.grant(BASIC)) for _ in range(8)]
    [x.start() for x in threads]
    [x.join() for x in threads]
    t_ = env.task(BASIC)
    rep.eq("같은 lease_granted를 8개 경로가 처리: 세대 1, issue_lease 기록 1건, 임대 기록 1개", (1, 1, 1),
           (t_["lease_generation"], issue_count(env), t_["lease_record"]["lease_generation"]))
    rep.eq("나머지 7개는 noop(lease_granted_duplicate), 상태 leased 그대로(G24 확정)",
           ([("lease_granted_duplicate", None)] * 7, "leased"), (noops(env.journal()), t_["task_state"]["state"]))

    # the records are stored as one transaction
    env = MockEnv(R, T)
    env.start_task(BASIC)
    env.ports.faults.arm("issue_lease:staged")
    point = env.crash(lambda: env.grant(BASIC))
    env.restart()
    t_ = env.task(BASIC)
    rep.eq("커밋 전 중단: 세대·임대·outbox 모두 없음", ("issue_lease:staged", 0, None, [], "queued", 0),
           (point, t_["lease_generation"], t_["lease_record"], t_["outbox"], t_["task_state"]["state"], issue_count(env)))
    env.ports.faults.arm("issue_lease:committed")
    env.crash(lambda: env.grant(BASIC))
    t_ = env.task(BASIC)
    rep.eq("커밋 뒤 중단: 셋 모두 있음(pending), task_state·전이 기록도 같은 커밋(G23)",
           (1, 1, "pending", 1, "leased", [("queued", "leased", "lease_granted")]),
           (t_["lease_generation"], t_["lease_record"]["lease_generation"], t_["outbox"][0]["status"], len(t_["outbox"]),
            t_["task_state"]["state"], tr(env.journal())[-1:]))
    eid = t_["outbox"][0]["envelope_id"]
    env.restart()
    rep.eq("재시작 뒤 outbox pending부터 같은 envelope_id로 발송", [eid], sent_ids(env))
    for name, bad in (
            ("lease_generation 대입은 issue_lease 안에서만", static_checks.single_lease_generation_writer()),
            ("전이 side_effects·인계 단계에 별도 증가 없음(데이터)", static_checks.rules_issue_only_in_side_effects(env.raw)),
            ("임대를 발급하는 전이는 모두 issue_lease를 부름(데이터)", static_checks.issuing_transitions_call_issue_lease(env.raw))):
        rep.eq("정적: " + name, [], bad)


# =============================================================== M39
def m39(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    b = env.builder_for(BASIC)
    instr = env.instr(BASIC)
    m = mark(env)
    h2 = b.heartbeat_envelope(instr)
    h3 = b.heartbeat_envelope(instr)
    o2 = env.submit(BASIC, "heartbeat", h2)
    env.clock.advance(60)
    o3 = env.submit(BASIC, "heartbeat", h3)
    rep.eq("같은 세대, 다른 envelope_id 둘은 각각 처리", (True, True, "heartbeat", "heartbeat"),
           (o2["accepted"], o3["accepted"], o2["noop"], o3["noop"]))
    hb_at = env.lease(BASIC)["last_heartbeat_at"]
    rep.eq("둘 다 임대 갱신(마지막 하트비트 시각이 두 번째 시각)", env.clock.now(), hb_at)
    env.clock.advance(60)
    o2b = env.submit(BASIC, "heartbeat", copy.deepcopy(h2))
    rep.eq("같은 envelope_id 재전송은 noop, 갱신 없음", ("envelope_duplicate_delivery", hb_at),
           (o2b["noop"], env.lease(BASIC)["last_heartbeat_at"]))
    bad = {k: v for k, v in b.heartbeat_envelope(instr).items() if k != "envelope_id"}
    o4 = env.submit(BASIC, "heartbeat", bad)
    js = jr(env, m)
    rep.eq("envelope_id 없는 봉투는 거부(R-13), 수락 아님", (False, "R-13"), (o4["accepted"], o4["return_code"]))
    rep.eq("noop 기록 순서", [("heartbeat", None), ("heartbeat", None), ("envelope_duplicate_delivery", None),
                          ("envelope_rejected_invalid", "R-13")], noops(js))
    rep.eq("전이 0건, inbox_seen에는 first_heartbeat·h2·h3 세 키", (0, 3),
           (len(tr(js)), len(env.task(BASIC)["inbox_seen"])))

    # signal envelopes (G28, G13): a second switch_signal of the same generation while the handoff is running
    env = MockEnv(R, T)
    env.bring_to_building(HANDOFF)
    b = env.builder_for(HANDOFF)
    instr = env.instr(HANDOFF)
    env.ports.faults.arm("handoff:isolate:start")
    s1 = b.signal_envelope(instr)
    env.crash(lambda: env.submit(HANDOFF, "switch_signal", s1))
    env.new_core()
    m = mark(env)
    s2 = b.signal_envelope(instr)
    o2 = env.submit(HANDOFF, "switch_signal", s2)
    o2b = env.submit(HANDOFF, "switch_signal", copy.deepcopy(s2))
    s3 = {k: v for k, v in b.signal_envelope(instr).items() if k != "envelope_id"}
    o3 = env.submit(HANDOFF, "switch_signal", s3)
    js = jr(env, m)
    rep.eq("인계 중 같은 세대의 둘째 signal(다른 envelope_id)은 수락되어 switch_signal_during_handoff(noop), 전이 없음",
           (True, "switch_signal_during_handoff", [], "handoff"), (o2["accepted"], o2["noop"], tr(js), env.state(HANDOFF)))
    rep.eq("같은 envelope_id 재전송은 noop, envelope_id 없는 signal은 거부(R-13)",
           ([("switch_signal_during_handoff", None), ("envelope_duplicate_delivery", None), ("envelope_rejected_invalid", "R-13")]),
           noops(js))
    rep.eq("첫 signal은 building→handoff 한 번, 세대 불변", (1, 1),
           (tr(env.journal()).count(("building", "handoff", "switch_signal")), env.task(HANDOFF)["lease_generation"]))


# =============================================================== M34
def m34(rep, R, T):
    # inside a live lease: the same idempotency key twice is a duplicate delivery (noop), nothing changes
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    b = env.builder_for(BASIC)
    hb = b.heartbeat_envelope(env.instr(BASIC))
    m = mark(env)
    o1 = env.submit(BASIC, "heartbeat", copy.deepcopy(hb))
    snap1 = env.task(BASIC)
    o2 = env.submit(BASIC, "heartbeat", copy.deepcopy(hb))
    snap2 = env.task(BASIC)
    rep.eq("살아 있는 임대 안: 두 번째는 envelope_duplicate_delivery(noop)",
           (True, "envelope_duplicate_delivery", [("heartbeat", None), ("envelope_duplicate_delivery", None)]),
           (o1["accepted"], o2["noop"], noops(jr(env, m))))
    rep.eq("상태·처리 결과 불변", (snap1["task_state"], snap1["lease_record"], snap1["inbox_seen"]),
           (snap2["task_state"], snap2["lease_record"], snap2["inbox_seen"]))

    # a result envelope ends the lease (end_lease); its re-delivery meets the lease check before the duplicate check
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    b = env.builder_for(BASIC)
    res = b.result_envelope(env.instr(BASIC), "pr_opened", pr_number=12)
    m = mark(env)
    o1 = env.submit(BASIC, "result", copy.deepcopy(res))
    snap1 = env.task(BASIC)
    o2 = env.submit(BASIC, "result", copy.deepcopy(res))
    js = jr(env, m)
    snap2 = env.task(BASIC)
    rep.eq("처음 처리: building→pr_open", [("building", "pr_open", "result_pr_opened")], tr(js))
    rep.eq("결과 봉투 재전달: 처리 결과·상태 불변(noop 하나)", (False, 1, snap1["task_state"], snap1["inbox_seen"]),
           (o2["accepted"], len(noops(js)), snap2["task_state"], snap2["inbox_seen"]))
    rep.eq("처음 처리의 수락 결과는 그대로", True, o1["accepted"])
    rep.eq("임대를 끝낸 결과 봉투의 재전달은 envelope_duplicate_delivery(noop)이고 late가 아니다(G40: not_seen이 lease_active_unexpired 앞)",
           ("envelope_duplicate_delivery", None), (o2["noop"], o2["return_code"]))
    rep.eq("끝난 임대의 사용량 기록은 처음 수락한 한 번뿐(중복 전달은 기록하지 않음, G46)", 1,
           len([r for r in js if r["kind"] == "side_effect_record" and r["id"] == "record_usage" and r["args"].get("phase") == "after_result"]))
    fresh = b.result_envelope(env.instr(BASIC), "failed_tests")
    o3 = env.submit(BASIC, "result", fresh)
    rep.eq("처음 보는 봉투가 끝난 임대로 오면 late_envelope_rejected(R-11)", ("late_envelope_rejected", "R-11", "pr_open"),
           (o3["noop"], o3["return_code"], env.state(BASIC)))


# =============================================================== M35
def new_key_check(env, t, first, old_instr, old_builder, g0):
    m = mark(env)
    results = env.run_builders(first)
    first_tr = tr(jr(env, m))
    kind, out = results[-1]
    new_gen = env.lease(t)["lease_generation"]
    st0 = env.state(t)
    late = env.submit(t, "heartbeat", old_builder.heartbeat_envelope(old_instr))
    st1 = env.state(t)
    nxt = env.submit(t, "heartbeat", env.builder_for(t).heartbeat_envelope(env.instr(t)))
    return (g0, new_gen, kind, out["accepted"], late["noop"], late["return_code"], st0 == st1, nxt["accepted"],
            issue_reasons(env)[-1], first_tr)


def expect_new_key(reason, first_tr):
    return (1, 2, "started", True, "late_envelope_rejected", "R-11", True, True, reason, [first_tr])


def m35(rep, R, T):
    lt = ("leased", "building", "first_heartbeat")
    bb = ("building", "building", "first_heartbeat")
    # 1. returned -> queued -> leased
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    old, ob = copy.deepcopy(env.instr(BASIC)), env.builder_for(BASIC)
    ob.send_result(old, "verdict_requested")
    env.event("owner_resolved", BASIC, resolution_ref="RES-1")
    env.grant(BASIC, "from_queue")
    rep.eq("반송 뒤 재개(returned→queued→leased)", expect_new_key("from_queue", lt), new_key_check(env, BASIC, "first_heartbeat", old, ob, 1))
    replay = env.submit(BASIC, "first_heartbeat", copy.deepcopy(ob.seen_instructions[old["envelope_id"]]))
    rep.eq("이전 세대에서 이미 수락된 봉투의 재전송은 late_envelope_rejected(R-11)(G25 확정: 세대 검사가 중복 검사보다 앞)",
           ("late_envelope_rejected", "R-11"), (replay["noop"], replay["return_code"]))

    # 2. test failure -> re-lease (building -> building): the new lease's first envelope is first_heartbeat (G15)
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    old, ob = copy.deepcopy(env.instr(BASIC)), env.builder_for(BASIC)
    ob.send_result(old, "failed_tests")
    rep.eq("시험 실패 뒤 재임대(building→building)", expect_new_key("retry_failed_tests", bb), new_key_check(env, BASIC, "first_heartbeat", old, ob, 1))

    # 3. CI failure -> re-lease (ci_failed -> building)
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    old, ob = copy.deepcopy(env.instr(BASIC)), env.builder_for(BASIC)
    ob.send_result(old, "pr_opened", pr_number=3)
    env.event("ci_failed", BASIC)
    env.grant(BASIC, "retry_ci")
    rep.eq("CI 실패 뒤 재임대(ci_failed→building)", expect_new_key("retry_ci", bb), new_key_check(env, BASIC, "first_heartbeat", old, ob, 1))

    # 4. handoff (next builder)
    env = MockEnv(R, T)
    env.bring_to_building(HANDOFF)
    old, ob = copy.deepcopy(env.instr(HANDOFF)), env.builder_for(HANDOFF)
    switch(env)
    rep.eq("인계(handoff→leased)", expect_new_key("handoff", lt), new_key_check(env, HANDOFF, "first_heartbeat", old, ob, 1))

    # 5. paused_no_builder -> back
    env = MockEnv(R, T)
    env.bring_to_building(HANDOFF)
    old, ob = copy.deepcopy(env.instr(HANDOFF)), env.builder_for(HANDOFF)
    env.ports.builders.unavailable.add("mock-builder-2")
    switch(env)
    paused = env.state(HANDOFF)
    env.ports.builders.unavailable.discard("mock-builder-2")
    env.event("builder_available", HANDOFF, builder="mock-builder-2")
    rep.eq("일시중단(paused_no_builder) 뒤 복귀", ("paused_no_builder",) + expect_new_key("resume_paused", lt),
           (paused,) + new_key_check(env, HANDOFF, "first_heartbeat", old, ob, 1))


# =============================================================== M28
def m28(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    a = env.builder_for(BASIC)
    instr_a = copy.deepcopy(env.instr(BASIC))
    a.send_result(instr_a, "failed_tests")
    env.run_builders("first_heartbeat")
    cur = env.lease(BASIC)
    rep.eq("임대 B로 교체(token 1→2), 상태 building", (2, "building", "active"), (cur["fencing_token"], env.state(BASIC), cur["status"]))
    before = env.task(BASIC)
    m = mark(env)
    late_result = a.result_envelope(instr_a, "pr_opened")
    late_signal = a.signal_envelope(instr_a)
    late_hb = a.heartbeat_envelope(instr_a)
    outs = [env.submit(BASIC, "result", late_result), env.submit(BASIC, "switch_signal", late_signal),
            env.submit(BASIC, "heartbeat", late_hb)]
    push_a = dict(lease_id=instr_a["lease_id"], lease_generation=instr_a["lease_generation"],
                  fencing_token=instr_a["fencing_token"], envelope_id="P-OLD", via="daemon", branch=instr_a["branch"], sha="a" * 40)
    pout = env.event("push_requested", BASIC, **push_a)
    pr_a = env.event("pr_update_requested", BASIC, lease_id=instr_a["lease_id"], lease_generation=1, fencing_token=1,
                     envelope_id="U-OLD", via="daemon", pr_number=3)
    js = jr(env, m)
    rep.eq("이전 임대 A의 결과·전환 신호·하트비트·푸시·PR 갱신: late_envelope_rejected(R-11)", [("late_envelope_rejected", "R-11")] * 5, noops(js))
    rep.eq("현재 과제 전이 0건, fence_violation 없음, 원격 쓰기 0건", ([], False, []),
           (tr(js), any(r.get("event") == "fence_violation" for r in js), env.ports.remote.writes))
    after = env.task(BASIC)
    rep.eq("현재 임대 B·상태·inbox_seen 불변", (before["lease_record"], before["task_state"], before["inbox_seen"]),
           (after["lease_record"], after["task_state"], after["inbox_seen"]))
    rep.eq("수락 아님", [False] * 5, [o["accepted"] for o in outs] + [pout["accepted"], pr_a["accepted"]])
    b_instr = env.instr(BASIC)
    ok = env.submit(BASIC, "heartbeat", env.builder_for(BASIC).heartbeat_envelope(b_instr))
    rep.eq("현재 임대 B의 봉투는 수락", True, ok["accepted"])
    m = mark(env)
    old_report = {"envelope_id": "V-OLD", "task_id": BASIC, "lease_id": instr_a["lease_id"],
                  "lease_generation": 1, "fencing_token": 1, "kind": "direct_push", "observed_at": env.clock.now()}
    env.submit(BASIC, "fence_violation", old_report)
    rep.eq("옛 임대 이름의 위반 신고는 late로만 처리(전이 없음)", ([], [("late_envelope_rejected", "R-11")]), (tr(jr(env, m)), noops(jr(env, m))))
    m = mark(env)
    good = env.event("push_requested", BASIC, lease_id=b_instr["lease_id"], lease_generation=2, fencing_token=2,
                     envelope_id="P-CUR", via="daemon", branch=b_instr["branch"], sha="b" * 40)
    rep.eq("현재 임대 B의 데몬 경유 푸시는 실행된다(execute_write 1건)", (True, [("push", BASIC, 2, "P-CUR")], ["execute_write"]),
           (good["written"], env.ports.remote.writes, se(jr(env, m), "execute_write")))
    m = mark(env)
    direct = env.event("push_requested", BASIC, lease_id=b_instr["lease_id"], lease_generation=2, fencing_token=2,
                       envelope_id="P-DIRECT", via="builder", branch=b_instr["branch"], sha="c" * 40)
    rep.eq("현재 임대의 데몬 우회 푸시만 fence_violation → returned(R-11), 쓰기 거부",
           ([("building", "returned", "fence_violation")], False, 1, ["R-11"]),
           (tr(jr(env, m)), direct["written"], len(env.ports.remote.writes), rets(jr(env, m))))

    # a violation report that names the current lease
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    b_instr = env.instr(BASIC)
    m = mark(env)
    env.submit(BASIC, "fence_violation", {"envelope_id": "V-CUR", "task_id": BASIC, "lease_id": b_instr["lease_id"],
               "lease_generation": 1, "fencing_token": 1, "kind": "write_after_revoke", "observed_at": env.clock.now()})
    rep.eq("현재 임대 이름의 위반 신고는 fence_violation → returned(R-11), 임대 revoked",
           ([("building", "returned", "fence_violation")], ["R-11"], "revoked"),
           (tr(jr(env, m)), rets(jr(env, m)), env.lease(BASIC)["status"]))


# =============================================================== M33
def m33(rep, R, T):
    env, path = handoff_bench(R, T, proc=dict(writes_forever=True, term_ignored=True, ghost=True))
    env.clock.advance(3)
    m = mark(env)
    out = switch(env)
    js = jr(env, m)
    t = env.task(HANDOFF)
    hr = t["handoff_record"]
    s_stop = first_seq(js, "intent_record", action="stop")
    s_iso = first_seq(js, "side_effect_record", id="worktree_readonly")
    s_rev = first_seq(js, "side_effect_record", id="revoke_write_credential")
    s_conf = first_seq(js, "result_record", action="confirm_quiescent")
    s_pc = first_seq(js, "intent_record", action="preserve_commit")
    s_pp = first_seq(js, "intent_record", action="preserve_push")
    s_tok = first_seq(js, "side_effect_record", id="revoke_token")
    s_next = first_seq(js, "side_effect_record", id="issue_lease")
    order = [s_stop, s_iso, s_conf, s_pc, s_pp, s_tok, s_next]
    rep.eq("기록 순서: stop < isolate < confirm_quiescent < preserve(commit < push) < revoke_token < issue_lease",
           True, all(x is not None for x in order) and order == sorted(order))
    rep.eq("빌더 쓰기 자격 회수도 정지 확인보다 먼저", True, s_rev < s_conf)
    kills = [r["args"]["terminated"] for r in js if r["kind"] == "side_effect_record" and r["id"] == "terminate_process"]
    rep.eq("응답 없는 빌더: stop 기한이 지나 isolate가 프로세스 그룹을 종료(첫 기록 terminated=True), 임대 종료 때는 이미 없음",
           [True, False], kills)
    results = [r for r in js if r["kind"] == "result_record" and r["action"] == "stop"]
    rep.eq("stop 결과: 기한 경과", "grace_expired", results[0]["outcome"])
    trace = env.ports.git.trace
    rep.eq("물리적 커밋·푸시는 정지 확인 뒤에만(저널 위치 비교)", True, all(pos > s_conf for _, pos in trace) and len(trace) == 2)
    rep.eq("정지 확인 전 커밋·푸시 0건", [("commit", True), ("push", True)], [(k, pos > s_conf) for k, pos in trace])
    commit_sha = hr["wip_commit_sha"]
    oid_calls = env.ports.git.oid_calls
    c = env.ports.git.commits[commit_sha]
    rep.eq("보존 커밋 tree OID == quiescent_tree_oid", hr["quiescent_tree_oid"], c["tree"])
    again = env.ports.git.git_write_tree_oid(path)
    rep.eq("격리 뒤 작업 트리는 변하지 않았다(지금 계산한 OID도 같다)", hr["quiescent_tree_oid"], again)
    rep.eq("격리 뒤의 쓰기 시도는 거부되었고 보존본에 없다", (True, False), (len(env.ports.worktree.denied_writes) > 0, "ghost.txt" in c["paths"]))
    rep.eq("정지 확인 시점: 프로세스 0·쓰기 핸들 0", (0, 0), (env.ports.process.alive_count(HANDOFF), env.ports.worktree.open_write_handles(path)))
    rep.eq("정지 확인의 OID 계산 2회 + 보존 커밋 1회가 같은 함수 git_write_tree_oid", 3, oid_calls)
    rep.eq("끝난 상태: 새 임대(2), 보존 상태 remote_pushed", ("leased", 2, "remote_pushed"),
           (env.state(HANDOFF), t["lease_generation"], hr["preservation_state"]))
    rep.eq("원격 ref == wip_commit_sha", commit_sha, env.ports.git.remote["task/T-MOCK-HANDOFF-a1"])


# =============================================================== M29
def m29(rep, R, T):
    env, path = handoff_bench(R, T)
    old = copy.deepcopy(env.instr(HANDOFF))
    old_builder = env.builder_for(HANDOFF)
    env.clock.advance(1)
    # the daemon dies right after the push was recorded: token revoked, next lease not issued yet
    env.ports.faults.arm("handoff:issue_next_lease:start")
    m = mark(env)
    env.crash(lambda: switch(env))
    js = jr(env, m)
    seq = R_sequence(env)
    marks = {
        "stop": first_seq(js, "intent_record", action="stop"),
        "isolate": first_seq(js, "side_effect_record", id="worktree_readonly"),
        "confirm_quiescent": first_seq(js, "result_record", action="confirm_quiescent"),
        "preserve": first_seq(js, "intent_record", action="preserve_commit"),
        "revoke_token": first_seq(js, "side_effect_record", id="revoke_token"),
    }
    push = first_seq(js, "intent_record", action="preserve_push")
    rep.eq("handoff_sequence(데이터)의 앞 다섯 단계가 모두 기록되고 순서대로다", (True, True),
           (all(marks.get(s) is not None for s in seq[:-1]), [marks[s] for s in seq[:-1]] == sorted(marks[s] for s in seq[:-1])))
    rep.eq("preserve(커밋·푸시)는 데몬 보존 자격으로, 푸시 기록이 revoke_token보다 앞", True, marks["preserve"] < push < marks["revoke_token"])
    t = env.task(HANDOFF)
    rep.eq("revoke 뒤·다음 발급 전: 세대 1, issue_lease 0건, 임대 handed_off, 토큰 폐기 표시",
           (1, 0, "handed_off", True), (t["lease_generation"], len(se(js, "issue_lease")), t["lease_record"]["status"],
                                        t["handoff_record"]["token_revoked"]))
    m2 = mark(env)
    env.new_core()
    late = env.submit(HANDOFF, "heartbeat", old_builder.heartbeat_envelope(old))
    rep.eq("폐기 뒤 옛 세대 봉투는 late_envelope_rejected(R-11), 상태·세대 불변", (("late_envelope_rejected", "R-11"), "handoff", 1),
           ((late["noop"], late["return_code"]), env.state(HANDOFF), env.task(HANDOFF)["lease_generation"]))
    env.restart()
    js2 = jr(env, m2)
    t = env.task(HANDOFF)
    rep.eq("새 토큰·세대는 폐기 뒤에만: 재시작 뒤 issue_lease 1건으로 세대 2, 상태 leased", (1, 2, "leased"),
           (len(se(js2, "issue_lease")), t["lease_generation"], t["task_state"]["state"]))
    rep.eq("새 세대 지시 봉투는 발급 뒤에 하나 나간다", [2], [s["lease_generation"] for s in env.ports.sender.sent[1:]])
    rep.eq("issue_lease는 revoke_token 기록보다 뒤", True, first_seq(js2, "side_effect_record", id="issue_lease") > marks["revoke_token"])


def R_sequence(env):
    return list(env.rules.sequence)


# =============================================================== M36
def build_manifest_tree(wt, path):
    w = lambda rel, content="x\n", mode=0o644: wt.write(path, rel, content, mode)
    w("src/keep.py", "keep\n")
    w("src/deleted.py", "gone\n")
    w("new_untracked.txt", "u\n")
    w("run.sh", "#!/bin/sh\n", 0o755)
    wt.symlink(path, "link", "src/keep.py")
    w("target/out.bin", "o\n")
    w("node_modules/pkg/index.js", "n\n")
    w("build/x.o", "b\n")
    w(".env", "A=1\n")
    w("id.pem", "k\n")
    w("my_secret.txt", "s\n")
    w("config_credentials.json", "c\n")
    w("src/__pycache__/m.pyc", "p\n")
    w("debug.log", "ignored by .gitignore\n")
    w(".gitignore", "*.log\n")
    wt.mkdir(path, "empty_dir")
    wt.delete(path, "src/deleted.py")


def m36(rep, R, T):
    env = MockEnv(R, T)
    wt, git = env.ports.worktree, env.ports.git
    base = "/mock/base"
    wt.ensure(base)
    wt.write(base, "src/keep.py", "keep\n")
    o0 = git.git_write_tree_oid(base)
    cases = [
        ("삭제된 추적 파일: 트리에서 항목 없음(OID 변화)", lambda p: wt.delete(p, "src/keep.py"), "changes"),
        ("미추적 파일 추가: 포함(OID 변화)", lambda p: wt.write(p, "new.txt", "u\n"), "changes"),
        ("실행 권한 변경: 모드 100755(OID 변화)", lambda p: wt.chmod(p, "src/keep.py", 0o755), "changes"),
        ("심볼릭 링크: 120000, 대상 경로 문자열(OID 변화)", lambda p: wt.symlink(p, "ln", "src/keep.py"), "changes"),
        ("제외 경로(target/, node_modules/, .env, *.pem, *secret*, .git/): OID 불변", lambda p: [
            wt.write(p, "target/a", "1"), wt.write(p, "node_modules/b/c", "1"), wt.write(p, ".env", "1"), wt.write(p, "k.pem", "1"),
            wt.write(p, "my_secret.txt", "1"), wt.write(p, ".git/config", "1")], "same"),
        ("빈 디렉터리: OID 불변", lambda p: wt.mkdir(p, "emptydir"), "same"),
        (".gitignore 대상: OID 불변", lambda p: [wt.write(p, ".gitignore", "*.log\n"), wt.write(p, "x.log", "1")], "gitignore"),
    ]
    for i, (name, mutate, kind) in enumerate(cases):
        p = f"/mock/case{i}"
        wt.ensure(p)
        wt.write(p, "src/keep.py", "keep\n")
        if kind == "gitignore":
            wt.write(p, ".gitignore", "*.log\n")
            o_ref = git.git_write_tree_oid(p)
            wt.write(p, "x.log", "1")
            rep.eq(name, "same", "same" if git.git_write_tree_oid(p) == o_ref else "changes")
            continue
        mutate(p)
        got = git.git_write_tree_oid(p)
        rep.eq(name, kind, "same" if got == o0 else "changes")
    # a symlink is hashed by its target string and the target file is not followed
    pl = "/mock/ln"
    wt.ensure(pl)
    wt.write(pl, "target/out.bin", "A")
    wt.symlink(pl, "ln", "target/out.bin")
    oa = git.git_write_tree_oid(pl)
    wt.write(pl, "target/out.bin", "B")
    rep.eq("심볼릭 링크는 대상 파일 내용을 따라가지 않는다(대상 내용을 바꿔도 OID 불변)", oa, git.git_write_tree_oid(pl))
    wt.symlink(pl, "ln", "other/path")
    rep.eq("대상 경로 문자열이 바뀌면 OID가 바뀐다", True, git.git_write_tree_oid(pl) != oa)

    # the same mix through the core: confirm_quiescent OID == preservation commit tree
    env, path = handoff_bench(R, T)
    build_manifest_tree(env.ports.worktree, path)
    env.clock.advance(1)
    switch(env)
    hr = env.task(HANDOFF)["handoff_record"]
    git = env.ports.git
    c = git.commits[hr["wip_commit_sha"]]
    rep.eq("코어 경로: 정지 확인 OID == 보존 커밋 tree OID", hr["quiescent_tree_oid"], c["tree"])
    keep = [".gitignore", "link", "new_untracked.txt", "notes.txt", "run.sh", "src/keep.py", "src/work.py"]
    rep.eq("보존 커밋의 경로: 삭제·제외·.gitignore·빈 디렉터리 없음", keep, c["paths"])
    from .mock_adapters import MockWorktree
    clone = MockWorktree(env.clock, env.ports.credentials)
    clone.ensure("/c")
    for rel in c["paths"]:
        e = env.ports.worktree.trees[path]["files"][rel]
        clone.trees["/c"]["files"][rel] = dict(e)
    rep.eq("커밋에 든 파일만으로 다시 계산한 OID도 같다", c["tree"], _recompute(git, clone))
    rep.eq("OID 계산은 하나의 함수(정지 확인 2회 + 커밋 1회 + 위 재계산)", True, git.oid_calls >= 3)
    for name, bad in (("다른 해시 정의 없음, 트리 해시는 git_write_tree_oid에서만", static_checks.single_tree_identity_function()),):
        rep.eq("정적: " + name, [], bad)

    # G38: a file that matches a secret pattern before preservation stops the handoff: no commit, no push
    env, path = handoff_bench(R, T)
    env.ports.worktree.write(path, "creds_note.txt", fake_secret("api_key"))
    env.clock.advance(1)
    m = mark(env)
    switch(env)
    js = jr(env, m)
    t = env.task(HANDOFF)
    rep.eq("[비밀값 파일] scan[preserve_files] 검출 → handoff→returned(secret_detected), R-10",
           ([("building", "handoff", "switch_signal"), ("handoff", "returned", "secret_detected")], ["R-10"]), (tr(js), rets(js)))
    rep.eq("[비밀값 파일] 보존 커밋·푸시 0건, 임대 revoked, 작업 트리 읽기 전용, 자격 전부 회수",
           (0, 0, "revoked", True, sorted(ALWAYS_REVOKE)),
           (env.ports.git.commit_count, env.ports.git.push_count, t["lease_record"]["status"],
            env.ports.worktree.trees[path]["readonly"], sorted(t["handoff_record"]["credentials_revoked"])))
    rep.eq("[비밀값 파일] 기록에는 파일 이름과 개수만 있고 일치한 문자열은 없다", (["creds_note.txt"], False),
           ([r for r in js if r["kind"] == "result_record" and r["outcome"] == "secret_detected"][0]["args"]["files"],
            any("x" * 20 in str(r) for r in env.journal())))
    rep.eq("[비밀값 파일] 다음 임대 없음(세대 1, issue_lease 0)", (1, 0), (t["lease_generation"], len(se(js, "issue_lease"))))


def _recompute(git, clone):
    old = git.wt
    git.wt = clone
    try:
        return git.git_write_tree_oid("/c")
    finally:
        git.wt = old


# =============================================================== M37
def blocked_invariants(rep, label, env, js, path):
    t = env.task(HANDOFF)
    hr = t["handoff_record"]
    s_iso = first_seq(js, "side_effect_record", id="worktree_readonly")
    s_rev = first_seq(js, "side_effect_record", id="revoke_write_credential")
    s_pc = first_seq(js, "intent_record", action="preserve_commit")
    if s_pc is not None:
        rep.eq(f"[{label}] 빌더 쓰기 차단·자격 회수가 보존보다 먼저", True, s_iso < s_pc and s_rev < s_pc)
    rep.eq(f"[{label}] 상태 handoff_blocked", "handoff_blocked", t["task_state"]["state"])
    rep.eq(f"[{label}] always_revoke 전부 회수(preserve_credential 포함)", sorted(ALWAYS_REVOKE), sorted(hr["credentials_revoked"]))
    rep.eq(f"[{label}] 작업 트리 쓰기 금지 유지", (True, True), (hr["worktree_readonly"], env.ports.worktree.trees[path]["readonly"]))
    creds = env.ports.credentials
    rep.eq(f"[{label}] 모의 자격 저장소에 활성 자격 없음", [], sorted(n for n, tid in creds.active if tid == HANDOFF))
    rep.eq(f"[{label}] issue_lease 호출 0건(인계 이후), 세대 불변", (0, 1), (len(se(js, "issue_lease")), t["lease_generation"]))
    rep.eq(f"[{label}] 막힌 뒤 봉투 발송 0건", [], se(js, "send_envelope"))


def m37(rep, R, T):
    cases = []
    sw = ("building", "handoff", "switch_signal")
    qf, ic, pcf, ppf = ("handoff", "handoff", "quiescence_failed"), ("handoff", "handoff", "index_lock"), \
        ("handoff", "handoff", "preserve_commit_failed"), ("handoff", "handoff", "preserve_push_failed")
    blocked = lambda ev: ("handoff", "handoff_blocked", ev)
    # attempt_counting = increment_then_compare: attempts <= max_attempts retries, so max_attempts=3 stops at the 4th failure
    cases.append(("정지 확인 실패 반복", dict(survives_kill=True, term_ignored=True), None,
                  [sw, qf, qf, qf, blocked("quiescence_failed")], {"quiescence_failed": 4}, "none"))
    runs = {  # how often each step ran: the retry starts where retry_detail.retry_from says
        "정지 확인 실패 반복": {"stop": 1, "isolate": 4, "confirm_quiescent": 4, "preserve_commit": 0, "preserve_push": 0},
        "index.lock": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 4, "preserve_push": 0},
        "디스크 부족": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 1, "preserve_push": 0},
        "커밋 실패": {"stop": 1, "isolate": 1, "confirm_quiescent": 3, "preserve_commit": 3, "preserve_push": 0},
        "푸시 실패(네트워크)": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 1, "preserve_push": 4},
        "푸시 실패(권한 거부)": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 1, "preserve_push": 1},
    }
    cases.append(("index.lock", None, ("commit", [IndexLockError(False)] * 6),
                  [sw, ic, ic, ic, blocked("index_lock")], {"index_lock": 4}, "none"))
    cases.append(("디스크 부족", None, ("commit", [DiskFullError()]),
                  [sw, blocked("disk_full")], {}, "none"))
    cases.append(("커밋 실패", None, ("commit", [CommitFailed("io")] * 6),
                  [sw, pcf, pcf, blocked("preserve_commit_failed")], {"preserve_commit_failed": 3}, "none"))
    ok = ("handoff", "handoff", "preserve_commit_ok")
    cases.append(("푸시 실패(네트워크)", None, ("push", [PushFailed("network")] * 6),
                  [sw, ok, ppf, ppf, ppf, blocked("preserve_push_failed")], {"preserve_push_failed": 4}, "local_committed"))
    cases.append(("푸시 실패(권한 거부)", None, ("push", [PushFailed("permission_denied")] * 6),
                  [sw, ok, blocked("preserve_push_failed")], {"preserve_push_failed": 1}, "local_committed"))
    envs, paths = {}, {}
    for label, proc, inj, exp_tr, exp_att, exp_pres in cases:
        env, path = handoff_bench(R, T, proc=proc)
        paths[label] = path
        if inj:
            getattr(env.ports.git, "inject")(*inj)
        env.clock.advance(1)
        m = mark(env)
        switch(env)
        js = jr(env, m)
        hr = env.task(HANDOFF)["handoff_record"]
        rep.eq(f"[{label}] 전이 열(max_attempts 안에서만 재시도, 넘으면 handoff_blocked)", exp_tr, tr(js))
        attempts = {k: v for k, v in hr["attempts"].items() if v}
        rep.eq(f"[{label}] 시도 횟수", exp_att, attempts)
        rep.eq(f"[{label}] preservation_state", exp_pres, hr["preservation_state"])
        done = {k: sum(1 for r in js if r["kind"] == "intent_record" and r["action"] == k) for k in runs[label]}
        rep.eq(f"[{label}] 단계별 실행 횟수(재시도는 retry_from 단계부터)", runs[label], done)
        blocked_invariants(rep, label, env, js, paths[label])
        m2 = mark(env)
        env.restart()
        env.core.tick()
        rep.eq(f"[{label}] 재시작·시간 경과로는 재개되지 않는다(recovery_decision 전)", ([], "handoff_blocked", 1),
               (tr(jr(env, m2)), env.state(HANDOFF), env.task(HANDOFF)["lease_generation"]))
        envs[label] = env

    # recovery_decision(retry) resumes; a local commit means push only
    env = envs["푸시 실패(네트워크)"]
    env.ports.git.injected["push"] = []
    commits_before = env.ports.git.commit_count
    m = mark(env)
    env.event("recovery_decision", HANDOFF, recovery_ref=None, action="retry")
    rep.eq("[복구] recovery_ref 없는 recovery_decision은 받지 않는다(handoff_blocked 유지)", ([], "handoff_blocked"),
           (tr(jr(env, m)), env.state(HANDOFF)))
    m = mark(env)
    env.event("recovery_decision", HANDOFF, recovery_ref="REC-1", action="retry")
    js = jr(env, m)
    rep.eq("[복구] recovery_decision 뒤 handoff로 돌아가 푸시만 하고 끝낸다",
           [("handoff_blocked", "handoff", "recovery_decision"), ("handoff", "handoff", "preserve_push_ok"), ("handoff", "leased", "preserved")],
           tr(js))
    rep.eq("[복구] 새 커밋 없음, 새 세대 2", (commits_before, 2), (env.ports.git.commit_count, env.task(HANDOFF)["lease_generation"]))
    rep.eq("[복구] issue_lease는 보존 성공 뒤 한 번", 1, len(se(js, "issue_lease")))
    rep.eq("[복구] reset_attempts 기록", 1, len(se(js, "reset_attempts")))

    env = envs["정지 확인 실패 반복"]
    env.ports.process.procs[HANDOFF].survives_kill = False
    m = mark(env)
    env.event("recovery_decision", HANDOFF, recovery_ref="REC-2", action="retry")
    rep.eq("[복구] 정지 확인 실패 뒤 복구: isolate부터 다시 해 보존까지 끝낸다", ("leased", 2),
           (env.state(HANDOFF), env.task(HANDOFF)["lease_generation"]))
    rep.eq("[복구] 복구 사건 열", [("handoff_blocked", "handoff", "recovery_decision"), ("handoff", "handoff", "preserve_commit_ok"),
                              ("handoff", "handoff", "preserve_push_ok"), ("handoff", "leased", "preserved")], tr(jr(env, m)))
    phases = [r["args"]["value"] for r in jr(env, m) if r["kind"] == "side_effect_record" and r["id"] == "set_handoff_field"
              and r["args"]["field"] == "phase"][:1]
    rep.eq("[복구] 로컬 커밋 없음 → recovery_decision 행(preservation_state != local_committed)이 phase=isolate (G30)", ["isolate"], phases)
    env = envs["푸시 실패(네트워크)"]
    first = [r for r in env.journal() if r["kind"] == "side_effect_record" and r["id"] == "set_handoff_field"
             and r["args"]["field"] == "phase" and r["seq"] > first_seq(env.journal(), "transition_record", event="recovery_decision")][:1]
    rep.eq("[복구] 로컬 커밋 있음 → 다른 행(preservation_state == local_committed)이 phase=preserve_remote (G30)",
           ["preserve_remote"], [r["args"]["value"] for r in first])

    env = envs["디스크 부족"]
    m = mark(env)
    env.event("recovery_decision", HANDOFF, recovery_ref="REC-3", action="abandon")
    js = jr(env, m)
    rep.eq("[포기] recovery_decision(action=abandon) → returned(R-14)", ([("handoff_blocked", "returned", "recovery_decision")], ["R-14"]),
           (tr(js), rets(js)))
    rep.eq("[포기] 다음 임대 없음", (0, 1), (len(se(js, "issue_lease")), env.task(HANDOFF)["lease_generation"]))
    rep.eq("[포기] 활성 임대를 끝내고 반송(G37): 임대 revoked", "revoked", env.lease(HANDOFF)["status"])
    m = mark(env)
    env.event("owner_resolved", HANDOFF, resolution_ref="RES-ABANDON")
    env.grant(HANDOFF)
    rep.eq("[포기] owner_resolved 뒤 queued→leased가 막히지 않는다(새 세대 2)",
           ([("returned", "queued", "owner_resolved"), ("queued", "leased", "lease_granted")], 2),
           (tr(jr(env, m)), env.task(HANDOFF)["lease_generation"]))

    env = envs["커밋 실패"]
    m = mark(env)
    env.event("owner_cancelled", HANDOFF)
    js = jr(env, m)
    rep.eq("[취소] handoff_blocked→cancelled: set_cancelled, 임대 revoked(G37)",
           ([("handoff_blocked", "cancelled", "owner_cancelled")], True, "revoked"),
           (tr(js), env.task(HANDOFF)["task_state"]["cancelled"], env.lease(HANDOFF)["status"]))

    # G39: index.lock whose owner process is alive -> retry from isolate (owner_alive_then); otherwise from preserve
    for alive, start, isolates in ((True, "isolate", 2), (False, "preserve", 1)):
        env, path = handoff_bench(R, T)
        env.ports.git.inject("commit", [IndexLockError(alive)])
        env.clock.advance(1)
        m = mark(env)
        switch(env)
        js = jr(env, m)
        resumed = [r["args"]["stage"] for r in js if r["kind"] == "side_effect_record" and r["id"] == "resume_from_phase"]
        ran = sum(1 for r in js if r["kind"] == "intent_record" and r["action"] == "isolate")
        rep.eq(f"[index.lock 소유 프로세스 생존={alive}] {start}부터 재시도하고 보존을 마친다",
               ([start], isolates, "leased", 2), (resumed, ran, env.state(HANDOFF), env.task(HANDOFF)["lease_generation"]))


# =============================================================== M38
def m38(rep, R, T):
    points = [
        ("stop 단계", "handoff:stop:start"),
        ("isolate 단계", "handoff:isolate:start"),
        ("confirm_quiescent 단계", "handoff:confirm_quiescent:start"),
        ("preserve 단계(로컬 커밋 전)", "handoff:preserve:start"),
        ("preserve 로컬 커밋 직후·기록 전", "handoff:preserve:after_local_commit_unrecorded"),
        ("로컬 커밋 기록 뒤·푸시 전", "handoff:preserve:after_local_commit_recorded"),
        ("푸시 직후·기록 전", "handoff:preserve:after_push_unrecorded"),
        ("issue_next_lease 단계(토큰 폐기 뒤·다음 발급 전)", "handoff:issue_next_lease:start"),
    ]
    for label, point in points:
        env, path = handoff_bench(R, T, proc=dict(writes_forever=True))
        env.clock.advance(1)
        env.ports.faults.arm(point)
        m = mark(env)
        got = env.crash(lambda: switch(env))
        env.restart()
        js = jr(env, m)
        t = env.task(HANDOFF)
        hr = t["handoff_record"]
        rep.eq(f"[{label}] 중단 지점", point, got)
        rep.eq(f"[{label}] 재시작 사건이 한 번 기록되고 phase부터 재개되어 완료",
               ("leased", 2, 1, "remote_pushed"), (t["task_state"]["state"], t["lease_generation"], hr["restart_count"], hr["preservation_state"]))
        rep.eq(f"[{label}] 재시작 사건 전이", 1, tr(js).count(("handoff", "handoff", "daemon_restart_during_handoff")))
        rep.eq(f"[{label}] 세대는 마지막 issue_lease 한 번만 바뀌고, 발송된 봉투는 새 세대 지시 하나뿐",
               (1, 1, [2]), (len(se(js, "issue_lease")), len(se(js, "send_envelope")), [s["lease_generation"] for s in env.ports.sender.sent[1:]]))
        git = env.ports.git
        rep.eq(f"[{label}] 커밋 1개·푸시 1회(이미 있는 것은 tree OID·ref로 확인해 다시 하지 않음)", (1, 1), (git.commit_count, git.push_count))
        rep.eq(f"[{label}] 원격 ref == 보존 커밋, 커밋 tree == quiescent_tree_oid", (hr["wip_commit_sha"], hr["quiescent_tree_oid"]),
               (git.remote["task/T-MOCK-HANDOFF-a1"], git.commits[hr["wip_commit_sha"]]["tree"]))
        rep.eq(f"[{label}] 쓰기 금지 유지, 보존 자격 회수", (True, False), (hr["worktree_readonly"], env.ports.credentials.is_active("preserve_credential", HANDOFF)))

    # restart_resume.confirm_quiescent -> isolate: the stage after a restart is read from the data
    env, path = handoff_bench(R, T)
    env.ports.faults.arm("handoff:confirm_quiescent:start")
    env.crash(lambda: switch(env))
    m = mark(env)
    env.restart()
    isolates = sum(1 for r in jr(env, m) if r["kind"] == "intent_record" and r["action"] == "isolate")
    rep.eq("restart_resume[confirm_quiescent]=isolate: 재시작 뒤 isolate를 다시 한다", 1, isolates)

    # phase = revoke_token (a stage the normal flow does not stop at): continue with revoke_token, then issue_next_lease
    env, path = handoff_bench(R, T)
    env.ports.faults.arm("handoff:preserve:after_push_unrecorded")
    env.crash(lambda: switch(env))
    env.store.tamper(lambda d: d["tasks"][HANDOFF]["handoff_record"].update(phase="revoke_token", preservation_state="remote_pushed"))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    t = env.task(HANDOFF)
    rep.eq("[phase=revoke_token] 재시작: 토큰 폐기를 마치고 다음 임대 발급", ("leased", 2, 1),
           (t["task_state"]["state"], t["lease_generation"], len(se(js, "issue_lease"))))
    rep.eq("[phase=revoke_token] 임대 종료(handed_off) 기록이 발급보다 먼저", True,
           first_seq(js, "side_effect_record", id="end_lease") < first_seq(js, "side_effect_record", id="issue_lease"))

    # a second restart in the same handoff exceeds daemon_restart_during_handoff = 1
    env, path = handoff_bench(R, T)
    env.ports.faults.arm("handoff:confirm_quiescent:start")
    env.crash(lambda: switch(env))
    env.new_core()
    env.ports.faults.arm("handoff:preserve:start")
    env.crash(lambda: env.core.handle_event({"event": "daemon_restart"}))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    rep.eq("[두 번째 재시작] 한도 초과: handoff_blocked", [("handoff", "handoff_blocked", "daemon_restart_during_handoff")], tr(js))
    rep.eq("[두 번째 재시작] 자격 전부 회수·쓰기 금지·issue_lease 0·발송 0", (sorted(ALWAYS_REVOKE), True, 0, 0),
           (sorted(env.task(HANDOFF)["handoff_record"]["credentials_revoked"]), env.task(HANDOFF)["handoff_record"]["worktree_readonly"],
            len(se(js, "issue_lease")), len(se(js, "send_envelope"))))

    # phase unreadable: transitions decide (handoff_blocked); the corruption list does not claim it (_phase_note)
    env, path = handoff_bench(R, T)
    env.ports.faults.arm("handoff:confirm_quiescent:start")
    env.crash(lambda: switch(env))
    env.store.tamper(lambda d: d["tasks"][HANDOFF]["handoff_record"].update(phase=None))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    rep.eq("[phase 확인 불가] handoff_blocked, issue_lease 0, 세대 불변", ([("handoff", "handoff_blocked", "daemon_restart_during_handoff")], 0, 1),
           (tr(js), len(se(js, "issue_lease")), env.task(HANDOFF)["lease_generation"]))

    # G31: restart_resume.<stage> = {check, then, else}
    cases = [
        ("preserve, 로컬 커밋 없음", "handoff:preserve:start", "local_commit_exists", "else", "confirm_quiescent", 1),
        ("preserve, 로컬 커밋 있음(기록 전)", "handoff:preserve:after_local_commit_unrecorded", "local_commit_exists", "then", None, 0),
        ("preserve_remote, 원격 ref 없음", "handoff:preserve:after_local_commit_recorded", "remote_ref_equals_wip_commit", "else", "preserve_remote", 0),
        ("preserve_remote, 원격 ref 있음(기록 전)", "handoff:preserve:after_push_unrecorded", "remote_ref_equals_wip_commit", "then", None, 0),
    ]
    for label, point, check, branch, stage, confirms in cases:
        env, path = handoff_bench(R, T)
        env.clock.advance(1)
        env.ports.faults.arm(point)
        env.crash(lambda: switch(env))
        m = mark(env)
        env.restart()
        js = jr(env, m)
        rr = [r["args"] for r in js if r["kind"] == "side_effect_record" and r["id"] == "resume_from_phase"][0]
        ran = sum(1 for r in js if r["kind"] == "intent_record" and r["action"] == "confirm_quiescent")
        rep.eq(f"[{label}] restart_resume 검사 {check} → {branch}" + (f"(단계 {stage})" if stage else "(사건으로 기존 보존 채택)"),
               (check, branch, stage, confirms, "leased", 1),
               (rr["check"], rr["branch"], rr["stage"], ran, env.state(HANDOFF), env.ports.git.commit_count))

    env, path = handoff_bench(R, T)
    env.clock.advance(1)
    env.ports.faults.arm("handoff:preserve:start")
    env.crash(lambda: switch(env))
    from .core.ports import QueryUnavailable
    env.ports.git.inject("find_commit", [QueryUnavailable()])
    m = mark(env)
    env.restart()
    js = jr(env, m)
    rep.eq("[preserve, 로컬 커밋 확인 불가] phase를 읽을 수 없음 → handoff_blocked, issue_lease 0, 커밋 0",
           ([("handoff", "handoff", "daemon_restart_during_handoff"), ("handoff", "handoff_blocked", "daemon_restart_during_handoff")], 0, 0),
           (tr(js), len(se(js, "issue_lease")), env.ports.git.commit_count))
    rep.eq("그 재시작은 restart_count를 한 번만 올린다(되먹임 사건이 다시 세지 않음)", 1,
           env.task(HANDOFF)["handoff_record"]["restart_count"])


# =============================================================== M30
GUARD_FOR = {"conflict": "no_conflict_lease", "writer": "single_writer", "lock": "lock_acquired",
             "parallel": "max_parallel_leases", "slot": "usage_slot_ready", "envelope": "instruction_envelope_valid",
             "builder": "builder_available"}
# no runner available also makes the candidate instruction unbuildable, so two guards fail together
FAILS_WITH = {"builder": ["builder_available", "instruction_envelope_valid"]}
ALL_TASKS = (BASIC, HANDOFF, OTHER)


def _fake_active(env, task, branch=None):
    env.core.register_task(task, "building")
    now = env.clock.now()
    env.store.tamper(lambda d: d["tasks"][task].update(lease_generation=1, lease_record={
        "lease_id": "FAKE-" + task, "task_id": task, "lease_generation": 1, "fencing_token": 1, "builder": "x",
        "runner": "x", "branch": branch or f"task/{task}-a1", "base_sha": "b" * 40, "issued_at": now,
        "expires_at": now + TTL, "last_heartbeat_at": None, "status": "active"}))


def _end_fake(env, task):
    env.store.tamper(lambda d: d["tasks"][task]["lease_record"].update(status="revoked"))


def inject(env, kind, task):
    others = [t for t in ALL_TASKS if t != task]
    if kind == "conflict":
        env.ports.catalog.tasks[others[0]]["conflict_paths"] = list(env.ports.catalog.tasks[task]["conflict_paths"])
        _fake_active(env, others[0])
    elif kind == "writer":
        attempt = env.task(task)["task_state"]["attempt"]
        _fake_active(env, others[0], branch=f"task/{task}-a{attempt}")
    elif kind == "parallel":
        for o in others:
            _fake_active(env, o)
    elif kind == "lock":
        env.store.tamper(lambda d: d.setdefault("lease_lock", {}).update({task: {"task_id": task, "holder": "other-daemon", "acquired_at": 1}}))
    elif kind == "slot":
        # a slot already prepared for the next generation (an earlier guard run) would hide the failure
        env.store.tamper(lambda d: d.update(usage_record=[u for u in d.get("usage_record", []) if not (
            u["task_id"] == task and u["envelope_id"] is None)]))
        env.ports.faults.arm_fail("usage:slot_create", None)
    elif kind == "envelope":
        env._saved_inputs = env.ports.catalog.tasks[task]["inputs"]
        env.ports.catalog.tasks[task]["inputs"] = None
    elif kind == "builder":
        env.ports.builders.unavailable.update({"mock-builder-1", "mock-builder-2"})


def release(env, kind, task):
    others = [t for t in ALL_TASKS if t != task]
    if kind in ("conflict", "writer", "parallel"):
        for o in (others if kind == "parallel" else others[:1]):
            _end_fake(env, o)
    elif kind == "lock":
        env.store.tamper(lambda d: d["lease_lock"].update({task: {"task_id": task, "holder": None, "acquired_at": None}}))
    elif kind == "slot":
        env.ports.faults.clear_fail("usage:slot_create")
    elif kind == "envelope":
        env.ports.catalog.tasks[task]["inputs"] = env._saved_inputs
    elif kind == "builder":
        env.ports.builders.unavailable.clear()


def _to_pr_open(env, t):
    env.bring_to_building(t)
    env.builder_for(t).send_result(env.instr(t), "pr_opened", pr_number=3)


def path_queued(env):
    env.start_task(BASIC)
    return BASIC, "queued", lambda: env.grant(BASIC, "from_queue"), lambda: env.grant(BASIC, "from_queue")


def path_failed_tests(env):
    """Failed-test reports have an explicit on_cond_fail return when reissue cannot proceed."""
    env.bring_to_building(BASIC)
    res = env.builder_for(BASIC).result_envelope(env.instr(BASIC), "failed_tests")

    def fail():
        return env.submit(BASIC, "result", copy.deepcopy(res))
    return BASIC, "building", fail, fail


def event_writes(snap):
    """The store without the journal and the lease lock: the lock has its own committed writes around the
    event's transaction (G45), the journal keeps the diagnostics of a rejection."""
    return {k: v for k, v in snap.items() if k not in ("journal", "lease_lock")}


def path_ci_failed(env):
    _to_pr_open(env, BASIC)
    env.event("ci_failed", BASIC)
    return BASIC, "ci_failed", lambda: env.grant(BASIC, "retry_ci"), lambda: env.grant(BASIC, "retry_ci")


def path_changes_requested(env):
    _to_pr_open(env, BASIC)
    for ev in ("ci_passed", "reviewer_assigned", "review_changes_requested"):
        env.event(ev, BASIC)
    return BASIC, "changes_requested", lambda: env.grant(BASIC, "retry_review"), lambda: env.grant(BASIC, "retry_review")


def path_handoff(env):
    env.bring_to_building(HANDOFF)
    return HANDOFF, "handoff", lambda: switch(env), lambda: env.event("preserved", HANDOFF)


def path_paused(env):
    env.bring_to_building(HANDOFF)
    env.ports.builders.unavailable.add("mock-builder-2")
    switch(env)
    assert env.state(HANDOFF) == "paused_no_builder", env.state(HANDOFF)
    env.ports.builders.unavailable.clear()
    return HANDOFF, "paused_no_builder", lambda: env.event("builder_available", HANDOFF, builder="mock-builder-2"), \
        lambda: env.event("builder_available", HANDOFF, builder="mock-builder-2")


PATHS = [("queued→leased", path_queued, True), ("시험 실패 뒤 재임대", path_failed_tests, True),
         ("ci_failed→building", path_ci_failed, True), ("changes_requested→building", path_changes_requested, True),
         ("handoff→leased", path_handoff, False), ("paused_no_builder→leased", path_paused, False)]


def m30(rep, R, T):
    probe = MockEnv(R, T)
    rep.eq("lease_guards(데이터)의 id 전부가 이 시험의 주입 대상이다", sorted(GUARD_FOR.values()),
           sorted(g["id"] for g in probe.rules.view["lease_guards"]))
    rep.eq("가드 종류: adapter 1(builder_available), core 1(instruction_envelope_valid), 나머지 store",
           {"builder_available": "adapter", "instruction_envelope_valid": "core"},
           {g["id"]: g["kind"] for g in probe.rules.view["lease_guards"] if g["kind"] != "store"})
    for label, build, with_builder in PATHS:
        for kind, gid in GUARD_FOR.items():
            if kind == "builder" and not with_builder:
                continue
            env = MockEnv(R, T)
            task, state0, attempt, retry = build(env)
            if label == "handoff→leased":
                inject(env, kind, task)
                g0, i0, s0 = env.task(task)["lease_generation"], issue_count(env), len(sent_ids(env))
                m = mark(env)
                attempt()
                js = jr(env, m)
                cur_state = env.state(task)
                st_ok = cur_state == "handoff"
            else:
                inject(env, kind, task)
                g0, i0, s0 = env.task(task)["lease_generation"], issue_count(env), len(sent_ids(env))
                before = event_writes(env.snap())
                m = mark(env)
                attempt()
                js = jr(env, m)
                st_ok = env.state(task) == state0
                if kind != "envelope" and label != "시험 실패 뒤 재임대":
                    rep.eq(f"[{label} / 주입 {kind}] 가드 대기는 트랜잭션 전체를 버린다(카운터·inbox_seen·사용량 슬롯 포함 "
                           "저널·임대 잠금 밖 store 불변), 저널에는 진단만", (True, ["diagnostic_record"]),
                           (event_writes(env.snap()) == before, sorted({r["kind"] for r in js})))
            t = env.task(task)
            if kind == "envelope":
                # G48: a deterministic validation failure is envelope_invalid -> returned(R-13) on every path
                rep.eq(f"[{label} / 주입 {kind}] envelope_invalid → returned(R-13), 임대·발송 없음",
                       ((g0, 0, s0), [(state0, "returned", "envelope_invalid")], ["R-13"]),
                       ((t["lease_generation"], issue_count(env) - i0, len(sent_ids(env))),
                        [x for x in tr(js) if x[2] == "envelope_invalid"], rets(js)))
                if state0 == "building":
                    rep.eq(f"[{label} / 주입 {kind}] building의 지금 임대는 returned로 끝난다", "returned", t["lease_record"]["status"])
            elif label == "시험 실패 뒤 재임대":
                rep.eq(f"[{label} / 주입 {kind}] on_cond_fail → returned(R-03), 현재 임대 폐기, 카운터 1, 새 임대·발송 없음",
                       ([("building", "returned", "unmapped_condition")], ["R-03"], "revoked", 1, g0, 0, s0),
                       (tr(js), rets(js), t["lease_record"]["status"], t["task_state"]["consecutive_failed_tests"],
                        t["lease_generation"], issue_count(env) - i0, len(sent_ids(env))))
            else:
                rep.eq(f"[{label} / 주입 {kind}] 임대 미발급(세대·issue_lease·발송 불변, 상태 유지)", (g0, 0, s0, True),
                       (t["lease_generation"], issue_count(env) - i0, len(sent_ids(env)), st_ok))
            rep.eq(f"[{label} / 주입 {kind}] 막은 가드는 {FAILS_WITH.get(kind, [gid])}", sorted(FAILS_WITH.get(kind, [gid])), failed_guard_ids(js))
            rep.eq(f"[{label} / 주입 {kind}] 평가가 끝나면 이 데몬의 임대 잠금은 풀려 있다(G45)", True,
                   (env.snap().get("lease_lock", {}).get(task) or {}).get("holder") in (None, "other-daemon"))
            release(env, kind, task)
            if kind == "envelope" or label == "시험 실패 뒤 재임대":
                env.event("owner_resolved", task, resolution_ref="RES-ENV")
                env.grant(task, "from_queue")
            else:
                retry()
            t = env.task(task)
            rep.eq(f"[{label} / 주입 {kind}] 주입을 풀면 발급되고 토큰(세대)이 +1", (g0 + 1, i0 + 1), (t["lease_generation"], issue_count(env)))

    # G29: conflict_paths overlap as patterns (a nested glob), not as equal strings
    env = MockEnv(R, T)
    env.bring_to_building("T-MOCK-KN")
    env.start_task("T-MOCK-KN-REL")
    m = mark(env)
    env.grant("T-MOCK-KN-REL")
    paths = (env.ports.catalog.task("T-MOCK-KN")["conflict_paths"], env.ports.catalog.task("T-MOCK-KN-REL")["conflict_paths"])
    rep.eq("[G29] 중첩 글롭(<dir>/** ↔ <dir>/release/**)은 겹침: 임대 없음, 막은 가드 no_conflict_lease, 문자열 교집합은 비어 있다",
           ("queued", ["no_conflict_lease"], set()), (env.state("T-MOCK-KN-REL"), failed_guard_ids(jr(env, m)), set(paths[0]) & set(paths[1])))


# =============================================================== M26
def usage_rows(env, task):
    return [u for u in env.snap().get("usage_record", []) if u["task_id"] == task]


def m26(rep, R, T):
    BIG = 10 ** 9
    env = MockEnv(R, T)
    env.start_task(BASIC)
    m = mark(env)
    env.grant(BASIC)
    js = jr(env, m)
    sent = sent_ids(env)[0]
    u = usage_rows(env, BASIC)
    rep.eq("지시 봉투 전에 사용량 기록 슬롯이 만들어진다(슬롯 기록 < 발송 기록)", True,
           first_seq(js, "side_effect_record", id="record_usage") < first_seq(js, "side_effect_record", id="send_envelope"))
    rep.eq("슬롯: 과제·세대·봉투·생성 시각이 있고 calls·wall_s·cost_units는 아직 없다",
           [(BASIC, 1, sent, env.clock.now(), None, None, None, None)],
           [(r["task_id"], r["lease_generation"], r["envelope_id"], r["slot_created_at"], r["calls"], r["wall_s"], r["cost_units"], r["recorded_at"]) for r in u])
    env.run_builders()
    b = env.builder_for(BASIC)
    # results with an absurd cost: recorded, never a reason to stop
    m = mark(env)
    b.send_result(env.instr(BASIC), "failed_tests", cost_units=BIG, calls=7, wall_s=120)
    env.run_builders("first_heartbeat")
    js = jr(env, m)
    u = usage_rows(env, BASIC)
    rep.eq("결과 봉투의 calls·wall_s·cost_units가 usage_record에 기록된다(세대 1)", (7, 120, BIG, True),
           (u[0]["calls"], u[0]["wall_s"], u[0]["cost_units"], u[0]["recorded_at"] is not None))
    rep.eq("비용 1e9 누적 뒤에도 새 임대·발송이 막히지 않고 반송이 없다(세대 2 발송, 상태 building, 반송 0)",
           (2, 2, "building", []), (env.task(BASIC)["lease_generation"], len(sent_ids(env)), env.state(BASIC), rets(js)))
    rep.eq("그 전이는 시험 실패 재임대 하나뿐(비용으로 생긴 전이 없음)", [("building", "building", "result_failed_tests"),
                                                      ("building", "building", "first_heartbeat")], tr(js))
    # a failing recording after the result: a warning and a retry entry, the result is processed all the same
    env.ports.faults.arm_fail("usage:record_result", 1)
    m = mark(env)
    b2 = env.builder_for(BASIC)
    b2.send_result(env.instr(BASIC), "failed_tests", cost_units=BIG, calls=3, wall_s=60)
    js = jr(env, m)
    snap = env.snap()
    rep.eq("기록 실패: 결과 봉투 처리는 계속(재임대 세대 3), 경고만 남기고 재시도 대기 1건, 반송 0",
           (3, 1, 1, []), (env.task(BASIC)["lease_generation"], len(snap["usage_retry"]),
                           sum(1 for r in js if r["kind"] == "diagnostic_record" and r["what"] == "usage_record_failed_warning"), rets(js)))
    rep.eq("기록 실패 시점의 사용량 행은 비어 있다", (None, None), (usage_rows(env, BASIC)[1]["calls"], usage_rows(env, BASIC)[1]["cost_units"]))
    written = env.core.retry_usage()
    u = usage_rows(env, BASIC)
    rep.eq("비동기 재시도가 뒤늦게 기록한다", (1, 3, BIG, 0), (written, u[1]["calls"], u[1]["cost_units"], len(env.snap()["usage_retry"])))
    env.run_builders("first_heartbeat")
    # the retry limit of the same failure is unchanged (R-06 at the 3rd), whatever the cost
    m = mark(env)
    env.builder_for(BASIC).send_result(env.instr(BASIC), "failed_tests", cost_units=BIG, calls=1, wall_s=1)
    js = jr(env, m)
    rep.eq("같은 실패 재시도 한도: 3회째 returned(R-06), 임대 종료", ([("building", "returned", "result_failed_tests")], ["R-06"], 3),
           (tr(js), rets(js), env.task(BASIC)["lease_generation"]))
    total = sum(r["cost_units"] or 0 for r in usage_rows(env, BASIC))
    rep.eq("누적 비용 3e9가 기록되어 있다", 3 * BIG, total)
    # another task is not held back by that total
    env.start_task(OTHER)
    env.grant(OTHER)
    rep.eq("다른 과제의 새 임대도 막히지 않는다", ("leased", 1), (env.state(OTHER), env.task(OTHER)["lease_generation"]))

    # no response: heartbeat missed twice, and max_wall_s exceeded, behave as before
    env = MockEnv(R, T)
    env.bring_to_building(HANDOFF)
    env.clock.advance(601)
    m = mark(env)
    env.core.tick()
    rep.eq("응답 없음 정지: 하트비트 2회 누락 → returned(R-08)", ([("building", "returned", "heartbeat_missed_twice")], ["R-08"]),
           (tr(jr(env, m)), rets(jr(env, m))))
    env = MockEnv(R, T)
    env.bring_to_building(OTHER)
    b = env.builder_for(OTHER)
    instr = env.instr(OTHER)
    wall = instr["limits"]["max_wall_s"]
    t0 = env.clock.now()
    while env.clock.now() - t0 < wall - 300:
        env.clock.advance(300)
        env.submit(OTHER, "heartbeat", b.heartbeat_envelope(instr))
    env.clock.advance(wall - (env.clock.now() - t0) - 1)
    m = mark(env)
    env.event("hard_stop_deadline", OTHER)
    rep.eq("max_wall_s 직전의 hard_stop_deadline은 받지 않는다", ([], "building"), (tr(jr(env, m)), env.state(OTHER)))
    env.clock.advance(1)
    m = mark(env)
    env.event("hard_stop_deadline", OTHER)
    rep.eq("max_wall_s 초과 → returned(R-07)(비용이 아니라 응답 없음·무한 반복 통제)", ([("building", "returned", "hard_stop_deadline")], ["R-07"]),
           (tr(jr(env, m)), rets(jr(env, m))))

    # the slot can fail only as a storage failure (usage_slot_ready), and that is a wait, not a cost decision
    env = MockEnv(R, T)
    env.start_task(BASIC)
    env.ports.faults.arm_fail("usage:slot_create", None)
    m = mark(env)
    env.grant(BASIC)
    rep.eq("슬롯 쓰기 불가(저장소 장애): 임대 없이 대기(queued), 반송 0", (0, "queued", []),
           (env.task(BASIC)["lease_generation"], env.state(BASIC), rets(jr(env, m))))
    env.ports.faults.clear_fail("usage:slot_create")
    env.grant(BASIC)
    rep.eq("저장소가 돌아오면 발급된다", ("leased", 1), (env.state(BASIC), env.task(BASIC)["lease_generation"]))
    for name, bad in (("비용 상한·예산 예약·소진 정지 표현 없음", static_checks.no_cost_cap(env.raw, T)),):
        rep.eq("정적: " + name, [], bad)
    rep.eq("lease_guards 중 사용량 관련 가드는 usage_slot_ready 하나(예약이 아니라 기록 슬롯)", ["usage_slot_ready"],
           [g["id"] for g in env.rules.view["lease_guards"] if "usage" in g["id"]])


# =============================================================== static group and perturbation
def _structured_when(value):
    return isinstance(value, list) and bool(value) and all(isinstance(x, dict) and "field" in x and "op" in x for x in value)


def perturb(node, mode):
    """Replace (mode 'garble') or remove (mode 'drop') every explanation key: when, note, _*. A `when` that holds
    structured predicates (noop_rules) is data, not an explanation, and is left alone."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if (k in ("when", "note") and not (k == "when" and _structured_when(v))) or k.startswith("_"):
                if mode == "garble":
                    out[k] = "ZZ 이 문장을 코어가 읽으면 시험이 달라진다 ZZ"
                continue
            out[k] = perturb(v, mode)
        return out
    if isinstance(node, list):
        return [perturb(x, mode) for x in node]
    return node


def static(rep, R, T):
    for name, bad in static_checks.all_static(R, T):
        rep.eq("정적: " + name, [], bad)
    import json
    with open(R, encoding="utf-8") as f:
        raw = json.load(f)
    others = [e[3] for e in SCENARIOS if e[0] != "STATIC"]
    base = [[(c["name"], c["status"], c["actual"]) for c in run_one(fn, R, T)] for fn in others]
    for mode in ("garble", "drop"):
        alt = perturb(raw, mode)
        got = [[(c["name"], c["status"], c["actual"]) for c in run_one(fn, alt, T)] for fn in others]
        rep.eq(f"설명 키(when·note·_*)를 {'엉뚱한 문장으로 바꾸거나' if mode == 'garble' else '지워도'} 모든 시나리오의 검사 이름·상태·실제 값이 같다",
               base, got)


def run_one(fn, R, T):
    rep = Report()
    fn(rep, R, T)
    return rep.checks


CORE_SCENARIOS = [
    ("M26", "usage-recorded-not-capped", "사용량 기록(슬롯·결과), 상한으로 멈추지 않음, 재시도 한도·응답 없음 정지는 그대로", m26),
    ("M28", "late-result-no-state-change", "이전 임대의 늦은 결과·전환 신호·푸시는 noop, 현재 상태 불변", m28),
    ("M29", "handoff-order", "인계 기록 순서와 폐기 뒤 옛 세대 거부, 새 세대는 폐기 뒤에만", m29),
    ("M30", "lease-guards-all-paths", "모든 임대 발급 경로에서 가드가 하나라도 거짓이면 임대 없음", m30),
    ("M33", "handoff-quiescent-before-preserve", "응답 없는 빌더의 보존: isolate 먼저, 정지 확인 뒤에만 preserve", m33),
    ("M34", "duplicate-delivery-noop", "같은 멱등 키 봉투의 중복 전달은 noop", m34),
    ("M35", "retry-new-idempotency-key", "재개·재임대·인계·복귀마다 새 세대·새 키", m35),
    ("M36", "preserve-manifest-same-function", "정지 확인 OID와 보존 커밋 tree OID가 같은 함수", m36),
    ("M37", "preserve-failure-recoverable-stop", "보존 실패 주입: max_attempts 안 재시도, 넘으면 handoff_blocked", m37),
    ("M38", "daemon-restart-during-handoff", "인계 도중 재시작: phase부터 재개 또는 handoff_blocked", m38),
    ("M39", "envelope-id-distinct-events", "envelope_id가 다르면 별개 사건, 같으면 noop, 없으면 거부", m39),
    ("M40", "lease-issue-atomic-single-owner", "issue_lease 단일 책임, 한 트랜잭션, 세대 한 번만", m40),
    ("M41", "restart-ttl-expired-no-resend", "발급 직후 중단 뒤 TTL 경과: void(expired), 재발송 0", m41),
    ("M42", "restart-revoked-pending-void", "폐기·취소된 임대의 pending 봉투는 void, 재발송 0", m42),
    ("M43", "restart-valid-pending-resend", "유효한 pending은 같은 id로 재발송, 수신 측 검증", m43),
    ("M44", "restart-corrupt-record-returned", "손상 기록은 returned(R-08), 자동 재발급 0", m44),
    ("STATIC", "static-checks", "정적 검사와 설명 키 무시 검증", static),
]


def _order(entry):
    m = re.fullmatch(r"M(\d+)([a-z]?)", entry[0])
    return (0, int(m.group(1)), m.group(2)) if m else (1, 0, "")


SCENARIOS = sorted(CORE_SCENARIOS + FLOW_SCENARIOS, key=_order)
