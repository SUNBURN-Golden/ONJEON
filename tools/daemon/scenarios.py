"""Scenarios M28, M33-M44 of T-OP-00. Each scenario builds a fresh bench, drives the shared core through
the events of the scenario and compares expected values (written here as literals) with what the journal
and the stores show afterwards."""
import copy
import threading

from . import static_checks
from .core.ports import (CommitFailed, DiskFullError, IndexLockError, PreconditionFailed, PushFailed, SimulatedCrash)
from .mock_env import MockEnv

PASS, FAIL, GAP = "PASS", "FAIL", "GAP"
BASIC, HANDOFF, OTHER = "T-MOCK-BASIC", "T-MOCK-HANDOFF", "T-MOCK-OTHER"
TTL = 3600
ALWAYS_REVOKE = ["builder_write_credential", "builder_token", "preserve_credential"]


class Report:
    def __init__(self):
        self.checks = []

    def eq(self, name, expected, actual):
        ok = expected == actual
        self.checks.append({"name": name, "expected": expected, "actual": actual, "status": PASS if ok else FAIL})

    def gap(self, name, note, expected=None, actual=None):
        self.checks.append({"name": name, "expected": expected, "actual": actual, "status": GAP, "note": note})


# ---- journal views
def jr(env, mark=0):
    return env.journal()[mark:]


def mark(env):
    return len(env.journal())


def tr(js):
    return [(r["from"], r["to"], r["event"]) for r in js if r["kind"] == "transition_record"]


def se(js, *ids):
    return [r["id"] for r in js if r["kind"] == "side_effect_record" and (not ids or r["id"] in ids)]


def noops(js):
    return [(r["noop_event"], r["return_code"]) for r in js if r["kind"] == "noop_record"]


def rets(js):
    return [r["return_code"] for r in js if r["kind"] == "return_record"]


def first_seq(js, kind, **match):
    for r in js:
        if r["kind"] == kind and all(r.get(k) == v or r.get("args", {}).get(k) == v for k, v in match.items()):
            return r["seq"]
    return None


def sent_ids(env):
    return [s["envelope_id"] for s in env.ports.sender.sent]


def crash_after_issue(env, t):
    """The daemon dies right after issue_lease committed and before the instruction is sent."""
    env.ports.faults.arm("issue_lease:committed")
    return env.crash(lambda: env.grant(t))


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
    rep.eq("재시작: 부수 효과는 void 하나", ["void_outbox"], se(js))
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


# =============================================================== M42
def m42(rep, R, T):
    env = MockEnv(R, T)
    env.start_task(BASIC)
    crash_after_issue(env, BASIC)
    env.new_core()
    env.event("owner_cancelled", BASIC)
    t = env.task(BASIC)
    rep.eq("A 취소: 상태·취소 표시·outbox", ("cancelled", True, "pending"),
           (t["task_state"]["state"], t["task_state"]["cancelled"], t["outbox"][0]["status"]))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    t = env.task(BASIC)
    rep.eq("A 재시작: 전이 없음", [], tr(js))
    rep.eq("A 재시작: void 하나, issue_lease 없음", ["void_outbox"], se(js))
    rep.eq("A void 사유 cancelled", ("void", "cancelled"), (t["outbox"][0]["status"], t["outbox"][0]["void_reason"]))
    rep.eq("A 재발송 0건, 상태·세대 불변", ([], "cancelled", 1), (sent_ids(env), t["task_state"]["state"], t["lease_generation"]))

    env = MockEnv(R, T)
    env.start_task(BASIC)
    crash_after_issue(env, BASIC)
    env.new_core()
    env.event("unmapped_condition", BASIC)  # the lease ends (token revoked) and the task is returned
    t = env.task(BASIC)
    rep.eq("B 폐기: 임대 상태·outbox", ("revoked", "pending"), (t["lease_record"]["status"], t["outbox"][0]["status"]))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    t = env.task(BASIC)
    rep.eq("B 재시작: 전이 없음", [], tr(js))
    rep.eq("B void 하나", ["void_outbox"], se(js))
    rep.eq("B void 사유 revoked", ("void", "revoked"), (t["outbox"][0]["status"], t["outbox"][0]["void_reason"]))
    rep.eq("B 재발송 0건, 상태 returned 불변", ([], "returned"), (sent_ids(env), t["task_state"]["state"]))


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
    rep.eq("만료 봉투 결과는 late_envelope_rejected(noop), 상태 불변",
           ([("late_envelope_rejected", None)], [], "leased"), (noops(jr(env, m)), tr(jr(env, m)), env.state(BASIC)))
    rep.gap("만료 봉투의 late_envelope_rejected에 R-11 기록",
            "accept_envelope.on_fail.expired 문구에 R-11이 없다(다른 불일치 항목에는 있음). 만료 때 R-11을 기록할지 명세가 없어 기록하지 않음",
            expected="R-11 또는 없음(명세 미정)", actual=None)

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
        rep.eq(f"[{variant}] 손상 분류: returned", [("leased", "returned", "state_integrity.corruption")], tr(js))
        pending_void = ["void_outbox"] if variant.startswith("outbox 세대") else []
        rep.eq(f"[{variant}] 부수 효과: 토큰 폐기·자격 회수{'·pending void' if pending_void else ''}·R 코드",
               ["revoke_token", "revoke_credential", "revoke_credential", "revoke_credential"] + pending_void + ["record_r_code"],
               se(js))
        rep.eq(f"[{variant}] 반송 코드 R-08", ["R-08"], rets(js))
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
        env.reserve(BASIC)
        m = mark(env)
        env.grant(BASIC, "after_owner_resolved")
        rep.eq(f"[{variant}] queued→leased에서만 새 세대", ([("queued", "leased", "lease_granted")], 1, 2),
               (tr(jr(env, m)), len(se(jr(env, m), "issue_lease")), env.task(BASIC)["lease_generation"]))


# =============================================================== M40
def issue_count(env):
    return len(se(env.journal(), "issue_lease"))


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
        env.run_builders("heartbeat")

    step("시험 실패 뒤 재임대(building→building)", failed_tests)

    def handoff():
        env.submit(t, "switch_signal", b.signal_envelope(env.instr(t)))
        env.run_builders()

    step("인계(handoff→leased)", handoff)

    def returned_resume():
        b2 = env.builder_for(t)
        b2.send_result(env.instr(t), "verdict_requested")
        env.event("owner_resolved", t, resolution_ref="RES-1")
        env.reserve(t)
        env.grant(t, "after_owner_resolved")
        env.run_builders()

    step("반송 뒤 재개(returned→queued→leased)", returned_resume)
    rep.eq("각 경로: (세대 증가, issue_lease 기록) = (1, 1)", [(s[0], 1, 1) for s in steps], [(s[0], s[1], s[2]) for s in steps])
    rep.eq("최종 세대 = issue_lease 기록 수", issue_count(env), env.task(t)["lease_generation"])

    # many paths call issue_lease at once
    env = MockEnv(R, T)
    env.start_task(BASIC)
    results, lock = [], threading.Lock()

    def via_issue():
        try:
            env.core.issue_lease(BASIC, "initial")
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
    rep.gap("같은 lease_granted의 중복 도착",
            "먼저 처리된 경로가 queued→leased를 끝내면 나머지 lease_granted는 leased 상태에서 받을 전이가 없어 전이표 규칙대로 unmapped_condition(returned)으로 간다. noop_events에는 lease_granted 중복이 없다. 세대는 한 번만 바뀌지만 중복 알림이 과제를 반송시키는 것이 의도인지 명세가 없다",
            expected="중복 lease_granted는 noop 또는 명시된 처리", actual=f"최종 상태 {t_['task_state']['state']}")

    # the three records are stored as one transaction
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
    rep.eq("커밋 뒤 중단: 셋 모두 있음(pending)", (1, 1, "pending", 1), (t_["lease_generation"], t_["lease_record"]["lease_generation"], t_["outbox"][0]["status"], len(t_["outbox"])))
    eid = t_["outbox"][0]["envelope_id"]
    env.restart()
    rep.eq("재시작 뒤 outbox pending부터 같은 envelope_id로 발송", [eid], sent_ids(env))
    rep.gap("트랜잭션 기록 사이(세대·임대·outbox 사이)에서의 중단",
            "core_contract.atomicity가 '중간 재시작 주입 지점은 트랜잭션 전/후만'이라 정했으므로 기록 사이 중단은 시험하지 않는다. 시험한 것은 커밋 전/후 둘뿐",
            expected="세 기록 사이 중단 주입", actual="미실행(명세가 전/후만 허용)")
    rep.gap("task_state.state 갱신이 issue_lease 트랜잭션에 포함되는지",
            "atomic_record는 [lease_generation, lease_record, outbox] 셋이다. 전이 기록·state 갱신을 같은 커밋에 넣었다(포함하지 않으면 재시작 뒤 state=queued인 active 임대가 생겨 resend 검사의 task_state.state in [leased, building]이 거짓이 된다)",
            expected="명세 확정 필요", actual="같은 커밋에 포함")
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
    rep.eq("noop 기록 순서", [("heartbeat", None), ("heartbeat", None), ("envelope_duplicate_delivery", None), (None, "R-13")], noops(js))
    rep.eq("전이 0건, inbox_seen에는 first_heartbeat·h2·h3 세 키", (0, 3),
           (len(tr(js)), len(env.task(BASIC)["inbox_seen"])))
    rep.gap("signal 봉투(전환·상태 신호) 둘의 개별 처리",
            "envelope_identity 설명은 signal 봉투도 한 세대에 여러 번 정당하다고 하지만, 한 번 수락된 switch_signal은 building→handoff로 상태를 바꾸므로 같은 세대의 두 번째 signal이 어느 전이로 처리되는지 전이표에 없다(handoff에서 switch_signal 행 없음). 하트비트 봉투 둘로만 시험함",
            expected="signal 둘 각각 처리", actual="하트비트로 대체")
    rep.gap("heartbeat 봉투의 필수 목록",
            "core_contract.events_in.payloads.heartbeat에 envelope_id가 없다(first_heartbeat에는 있음). 멱등 키(concurrency.idempotency_key)에 envelope_id가 있으므로 키 필드를 필수 목록에 합쳐 사용함",
            expected="heartbeat payload에 envelope_id", actual="키 필드를 합침")


# =============================================================== M34
def m34(rep, R, T):
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
    rep.eq("두 번째는 envelope_duplicate_delivery(noop)", ("envelope_duplicate_delivery", [("envelope_duplicate_delivery", None)]),
           (o2["noop"], noops(js)))
    rep.eq("상태·처리 결과 불변", (snap1["task_state"], snap1["lease_record"], snap1["inbox_seen"]),
           (snap2["task_state"], snap2["lease_record"], snap2["inbox_seen"]))
    rep.eq("처음 처리의 수락 결과는 그대로", (True, True), (o1["accepted"], o2["accepted"] is False))


# =============================================================== M35
def new_key_check(env, t, first, old_instr, old_builder, g0):
    results = env.run_builders(first)
    kind, out = results[-1]
    new_gen = env.lease(t)["lease_generation"]
    st0 = env.state(t)
    late = env.submit(t, "heartbeat", old_builder.heartbeat_envelope(old_instr))
    st1 = env.state(t)
    nxt = env.submit(t, "heartbeat", env.builder_for(t).heartbeat_envelope(env.instr(t)))
    return (g0, new_gen, kind, out["accepted"], late["noop"], late["return_code"], st0 == st1, nxt["accepted"])


EXPECT_NEW_KEY = (1, 2, "started", True, "late_envelope_rejected", "R-11", True, True)


def m35(rep, R, T):
    # 1. returned -> queued -> leased
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    old, ob = copy.deepcopy(env.instr(BASIC)), env.builder_for(BASIC)
    ob.send_result(old, "verdict_requested")
    env.event("owner_resolved", BASIC, resolution_ref="RES-1")
    env.reserve(BASIC)
    env.grant(BASIC, "after_owner_resolved")
    rep.eq("반송 뒤 재개(returned→queued→leased)", EXPECT_NEW_KEY, new_key_check(env, BASIC, "first_heartbeat", old, ob, 1))
    replay = env.submit(BASIC, "first_heartbeat", copy.deepcopy(ob.seen_instructions[old["envelope_id"]]))
    rep.gap("이전 세대에서 이미 수락된 봉투의 재전송 분류",
            "accept_envelope.checks_in_order는 inbox_seen 검사를 임대·세대 검사보다 앞에 두므로, 이전 세대에서 이미 본 봉투가 다시 오면 envelope_duplicate_delivery로 분류된다. concurrency.fencing.late_envelope와 noop_events 설명은 이전 세대 멱등 키로 온 봉투를 late_envelope_rejected(R-11)와 같은 처리라고 한다. 둘 다 noop·상태 불변이지만 기록되는 noop 종류와 R-11 기록 여부가 다르다",
            expected="late_envelope_rejected(R-11)", actual=f"{replay['noop']}({replay['return_code']})")

    # 2. test failure -> re-lease (building -> building)
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    old, ob = copy.deepcopy(env.instr(BASIC)), env.builder_for(BASIC)
    ob.send_result(old, "failed_tests")
    rep.eq("시험 실패 뒤 재임대(building→building)", EXPECT_NEW_KEY, new_key_check(env, BASIC, "heartbeat", old, ob, 1))

    # 3. CI failure -> re-lease (ci_failed -> building)
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    old, ob = copy.deepcopy(env.instr(BASIC)), env.builder_for(BASIC)
    ob.send_result(old, "pr_opened", pr_number=3)
    env.event("ci_failed", BASIC)
    env.grant(BASIC, "retry_ci")
    rep.eq("CI 실패 뒤 재임대(ci_failed→building)", EXPECT_NEW_KEY, new_key_check(env, BASIC, "heartbeat", old, ob, 1))

    # 4. handoff (next builder)
    env = MockEnv(R, T)
    env.bring_to_building(HANDOFF)
    old, ob = copy.deepcopy(env.instr(HANDOFF)), env.builder_for(HANDOFF)
    switch(env)
    rep.eq("인계(handoff→leased)", EXPECT_NEW_KEY, new_key_check(env, HANDOFF, "first_heartbeat", old, ob, 1))

    # 5. paused_no_builder -> back
    env = MockEnv(R, T)
    env.bring_to_building(HANDOFF)
    old, ob = copy.deepcopy(env.instr(HANDOFF)), env.builder_for(HANDOFF)
    env.ports.builders.unavailable.add("mock-builder-2")
    switch(env)
    paused = env.state(HANDOFF)
    env.ports.builders.unavailable.discard("mock-builder-2")
    env.event("builder_available", HANDOFF, builder="mock-builder-2")
    rep.eq("일시중단(paused_no_builder) 뒤 복귀", ("paused_no_builder",) + EXPECT_NEW_KEY,
           (paused,) + new_key_check(env, HANDOFF, "first_heartbeat", old, ob, 1))
    rep.gap("각 경로가 새 세대를 부르는 reason",
            "transitions[]의 side_effects는 'issue_lease(task_id)'만 적고 reason 인자가 없다. reason은 전이가 떠나는 상태(queued/handoff/paused_no_builder/ci_failed/changes_requested/building)로 정했다. concurrency.lease_issue.signature에는 after_owner_resolved가 없고 core_contract.operations.issue_lease.inputs에는 있다",
            expected="전이마다 reason 명시", actual="떠나는 상태에서 유도")
    rep.gap("building→building 재임대 뒤 새 임대의 첫 하트비트",
            "result_failed_tests 재임대는 상태가 building에 남는데 first_heartbeat 전이는 leased→building뿐이다. 새 임대의 첫 봉투를 어떤 사건으로 받는지 명세가 없어 일반 heartbeat(noop)로 받았다",
            expected="새 임대의 첫 하트비트 사건", actual="heartbeat(noop)")
    rep.gap("임대 종료 시점",
            "issue_lease 전제는 '현재 세대의 임대가 종료(폐기)됨'인데 어느 전이가 임대를 끝내는지 구조화돼 있지 않다. concurrency.fencing.on_lease_end(읽기 목록 밖)를 가져와, lease 보유 상태(leased·building)를 handoff 밖으로 떠날 때와 새 임대를 발급하기 직전에 끝냈다",
            expected="임대 종료 전이 명시", actual="코어가 위 두 시점에 종료")


# =============================================================== M28
def m28(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    a = env.builder_for(BASIC)
    instr_a = copy.deepcopy(env.instr(BASIC))
    a.send_result(instr_a, "failed_tests")
    env.run_builders("heartbeat")
    cur = env.lease(BASIC)
    rep.eq("임대 B로 교체(token 1→2), 상태 building", (2, "building", "active"), (cur["fencing_token"], env.state(BASIC), cur["status"]))
    before = env.task(BASIC)
    m = mark(env)
    late_result = a.result_envelope(instr_a, "pr_opened")
    late_signal = a.signal_envelope(instr_a)
    late_hb = a.heartbeat_envelope(instr_a)
    outs = [env.submit(BASIC, "result", late_result), env.submit(BASIC, "switch_signal", late_signal),
            env.submit(BASIC, "heartbeat", late_hb)]
    js = jr(env, m)
    rep.eq("이전 임대 A의 결과·전환 신호·하트비트: late_envelope_rejected(R-11)", [("late_envelope_rejected", "R-11")] * 3, noops(js))
    rep.eq("현재 과제 전이 0건, fence_violation 없음", ([], False), (tr(js), any(r.get("event") == "fence_violation" for r in js)))
    after = env.task(BASIC)
    rep.eq("현재 임대 B·상태·inbox_seen 불변", (before["lease_record"], before["task_state"], before["inbox_seen"]),
           (after["lease_record"], after["task_state"], after["inbox_seen"]))
    rep.eq("수락 아님", [False] * 3, [o["accepted"] for o in outs])
    b_instr = env.instr(BASIC)
    ok = env.submit(BASIC, "heartbeat", env.builder_for(BASIC).heartbeat_envelope(b_instr))
    rep.eq("현재 임대 B의 봉투는 수락", True, ok["accepted"])
    m = mark(env)
    out = env.event("fence_violation", BASIC, envelope_id="V-OLD", lease_id=instr_a["lease_id"],
                    fencing_token=instr_a["fencing_token"], kind="push_without_daemon")
    rep.eq("옛 임대 이름의 위반 신고는 late로만 처리(전이 없음)", ([], [("late_envelope_rejected", "R-11")]), (tr(jr(env, m)), noops(jr(env, m))))
    out = env.event("fence_violation", BASIC, envelope_id="V-CUR", lease_id=b_instr["lease_id"],
                    fencing_token=b_instr["fencing_token"], kind="push_without_daemon")
    js = jr(env, m)
    rep.eq("현재 임대의 펜싱 위반만 fence_violation → returned", [("building", "returned", "fence_violation")], tr(js))
    rep.gap("푸시·PR 갱신의 펜싱 검사",
            "fencing.checked_at에 push·pr_update가 있으나 core_contract.operations에 푸시/PR 갱신 검사 연산이 없다. 결과 봉투·전환 신호·하트비트만 시험함",
            expected="푸시·PR 갱신도 토큰 검사", actual="미구현(연산 정의 없음)")
    rep.gap("fence_violation payload에 lease_generation 없음",
            "events_in.payloads.fence_violation에 lease_generation이 없어 accept_envelope의 세대 검사를 못 한다. fencing_token == lease_generation(store.lease_record) 관계로 세대를 채웠다",
            expected="payload에 세대", actual="토큰으로 대체")


# =============================================================== handoff helpers
def handoff_bench(R, T, task=HANDOFF, proc=None):
    env = MockEnv(R, T)
    if proc is not None:
        env.builders["mock-builder-1"].proc_options[task] = proc
    env.bring_to_building(task)
    path = env.instr(task)["worktree"]
    env.ports.worktree.write(path, "src/work.py", "print('work')\n")
    env.ports.worktree.write(path, "notes.txt", "n\n")
    return env, path


def switch(env, task=HANDOFF):
    b = env.builder_for(task)
    return env.submit(task, "switch_signal", b.signal_envelope(env.instr(task)))


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
    s_rev = first_seq(js, "side_effect_record", id="revoke_credential")
    s_conf = first_seq(js, "result_record", action="confirm_quiescent")
    s_pc = first_seq(js, "intent_record", action="preserve_commit")
    s_pp = first_seq(js, "intent_record", action="preserve_push")
    s_tok = first_seq(js, "side_effect_record", id="revoke_token")
    s_next = first_seq(js, "side_effect_record", id="issue_lease")
    order = [s_stop, s_iso, s_conf, s_pc, s_pp, s_tok, s_next]
    rep.eq("기록 순서: stop < isolate < confirm_quiescent < preserve(commit < push) < revoke_token < issue_lease",
           True, all(x is not None for x in order) and order == sorted(order))
    rep.eq("빌더 쓰기 자격 회수도 정지 확인보다 먼저", True, s_rev < s_conf)
    rep.eq("응답 없는 빌더: stop 기한이 지나 isolate가 프로세스 그룹을 종료", ["terminate_process_group"], se(js, "terminate_process_group"))
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
    rep.gap("제외 목록의 비밀값 패턴 항목(R-10)",
            "preserve_manifest.excludes의 마지막 항목은 '비밀값 패턴(R-10 검출 규칙)에 걸리는 파일 — 걸리면 보존하지 않고 R-10'이라는 문장이고, R-10 검출 규칙(패턴)이 구조화돼 있지 않다. 글롭 형태 항목만 제외 목록으로 쓰고 이 항목은 적용하지 않음",
            expected="비밀값 패턴 파일 → 보존 중단 R-10", actual="미구현")


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
    s_rev = first_seq(js, "side_effect_record", id="revoke_credential", credential="builder_write_credential")
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
    # (label, proc options, injection, expected transitions after switch, expected attempts, expected preservation)
    sw = ("building", "handoff", "switch_signal")
    cases.append(("정지 확인 실패 반복", dict(survives_kill=True, term_ignored=True), None,
                  [sw, ("handoff", "handoff", "quiescence_failed"), ("handoff", "handoff", "quiescence_failed"),
                   ("handoff", "handoff_blocked", "quiescence_failed")], {"quiescence_failed": 3}, "none"))
    runs = {  # how often each step ran: the retry starts where retry_from says
        "정지 확인 실패 반복": {"stop": 1, "isolate": 3, "confirm_quiescent": 3, "preserve_commit": 0, "preserve_push": 0},
        "index.lock": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 3, "preserve_push": 0},
        "디스크 부족": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 1, "preserve_push": 0},
        "커밋 실패": {"stop": 1, "isolate": 1, "confirm_quiescent": 2, "preserve_commit": 2, "preserve_push": 0},
        "푸시 실패(네트워크)": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 1, "preserve_push": 3},
        "푸시 실패(권한 거부)": {"stop": 1, "isolate": 1, "confirm_quiescent": 1, "preserve_commit": 1, "preserve_push": 1},
    }
    cases.append(("index.lock", None, ("commit", [IndexLockError(True)] * 5),
                  [sw, ("handoff", "handoff", "index_lock"), ("handoff", "handoff", "index_lock"), ("handoff", "handoff_blocked", "index_lock")],
                  {"index_lock": 3}, "none"))
    cases.append(("디스크 부족", None, ("commit", [DiskFullError()]),
                  [sw, ("handoff", "handoff_blocked", "disk_full")], {}, "none"))
    cases.append(("커밋 실패", None, ("commit", [CommitFailed("io")] * 5),
                  [sw, ("handoff", "handoff", "preserve_commit_failed"), ("handoff", "handoff_blocked", "preserve_commit_failed")],
                  {"preserve_commit_failed": 2}, "none"))
    cases.append(("푸시 실패(네트워크)", None, ("push", [PushFailed("network")] * 5),
                  [sw, ("handoff", "handoff", "preserve_commit_ok"), ("handoff", "handoff", "preserve_push_failed"),
                   ("handoff", "handoff", "preserve_push_failed"), ("handoff", "handoff_blocked", "preserve_push_failed")],
                  {"preserve_push_failed": 3}, "local_committed"))
    cases.append(("푸시 실패(권한 거부)", None, ("push", [PushFailed("permission_denied")] * 5),
                  [sw, ("handoff", "handoff", "preserve_commit_ok"), ("handoff", "handoff_blocked", "preserve_push_failed")],
                  {"preserve_push_failed": 1}, "local_committed"))
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
        # restart does not resume a blocked handoff
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
    env.event("recovery_decision", HANDOFF, recovery_ref="REC-1", action="retry")
    js = jr(env, m)
    rep.eq("[복구] recovery_decision 뒤 handoff로 돌아가 푸시만 하고 끝낸다",
           [("handoff_blocked", "handoff", "recovery_decision"), ("handoff", "handoff", "preserve_push_ok"), ("handoff", "leased", "preserved")],
           tr(js))
    rep.eq("[복구] 새 커밋 없음, 시도 횟수 초기화, 새 세대 2", (commits_before, 2),
           (env.ports.git.commit_count, env.task(HANDOFF)["lease_generation"]))
    rep.eq("[복구] issue_lease는 보존 성공 뒤 한 번", 1, len(se(js, "issue_lease")))

    env = envs["정지 확인 실패 반복"]
    env.ports.process.procs[HANDOFF].survives_kill = False
    m = mark(env)
    env.event("recovery_decision", HANDOFF, recovery_ref="REC-2", action="retry")
    rep.eq("[복구] 정지 확인 실패 뒤 복구: isolate부터 다시 해 보존까지 끝낸다", ("leased", 2),
           (env.state(HANDOFF), env.task(HANDOFF)["lease_generation"]))
    rep.eq("[복구] 복구 사건 열", [("handoff_blocked", "handoff", "recovery_decision"), ("handoff", "handoff", "preserve_commit_ok"),
                              ("handoff", "handoff", "preserve_push_ok"), ("handoff", "leased", "preserved")], tr(jr(env, m)))

    env = envs["디스크 부족"]
    m = mark(env)
    env.event("handoff_abandoned", HANDOFF, recovery_ref="REC-3", action="abandon")
    js = jr(env, m)
    rep.eq("[포기] handoff_abandoned → returned", [("handoff_blocked", "returned", "handoff_abandoned")], tr(js))
    rep.eq("[포기] 다음 임대 없음", (0, 1), (len(se(js, "issue_lease")), env.task(HANDOFF)["lease_generation"]))
    rep.gap("[포기] returned(R-14) 기록",
            "handoff_abandoned 전이(transitions[30])에는 return_code 필드가 없고, R-14와의 연결은 return_codes[].when(읽기 금지 키)뿐이다. 코어가 읽을 수 있는 구조화 필드가 없어 R-14를 기록하지 않았다",
            expected=["R-14"], actual=rets(js))
    env2 = envs["커밋 실패"]
    m = mark(env2)
    env2.event("recovery_decision", HANDOFF, recovery_ref="REC-4", action="abandon")
    rep.gap("recovery_decision(action=abandon) 처리",
            "transitions[29] cond가 action != abandon이라 abandon이면 전이가 없고, 포기는 handoff_abandoned 사건(transitions[30])이 받는다. handoff_abandoned의 events_in payload에는 action이 없는데 cond는 event.action == abandon을 요구한다. 두 사건의 payload 계약이 어긋난다",
            expected="포기 경로 하나", actual=f"recovery_decision(abandon) → 전이 {tr(jr(env2, m))}")
    rep.gap("attempts 증가 시점",
            "operations.handoff_failure는 cond 비교 뒤 attempts += 1 순으로 적혀 있으나, daemon_restart_during_handoff의 cond(restart_count < value + 1)는 증가 뒤 비교를 전제한다. 증가 뒤 비교로 해석해 3회째 실패에서 handoff_blocked가 된다(비교 뒤 증가면 4회째)",
            expected="명세 확정 필요", actual="증가 뒤 비교")
    rep.gap("index_lock의 재시도 시작 단계",
            "max_attempts.index_lock에 retry_from 구조화 필드가 없다(설명은 note에만 있음). 실패한 단계를 그대로 다시 하는 것으로 처리함",
            expected="retry_from", actual="실패 단계 재실행")


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

    # phase unreadable
    env, path = handoff_bench(R, T)
    env.ports.faults.arm("handoff:confirm_quiescent:start")
    env.crash(lambda: switch(env))
    env.store.tamper(lambda d: d["tasks"][HANDOFF]["handoff_record"].update(phase=None))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    rep.eq("[phase 확인 불가] handoff_blocked, issue_lease 0, 세대 불변", ([("handoff", "handoff_blocked", "daemon_restart_during_handoff")], 0, 1),
           (tr(js), len(se(js, "issue_lease")), env.task(HANDOFF)["lease_generation"]))
    rep.gap("phase 확인 불가의 분류",
            "state_integrity.corruption.detect의 '핸드오프 phase를 확인할 수 없다'는 returned(R-08)로 가고, transitions[27]은 같은 조건(phase == null)을 handoff_blocked로 보낸다. 같은 조건에 두 목적지가 있어 전이표(handoff_blocked)를 따르고 손상 탐지에서는 이 항목을 적용하지 않았다",
            expected="한 가지 분류", actual="전이표 우선")

    # restart while phase = revoke_token
    env, path = handoff_bench(R, T)
    env.ports.faults.arm("handoff:revoke_token:start")
    env.crash(lambda: switch(env))
    m = mark(env)
    env.restart()
    js = jr(env, m)
    hr = env.task(HANDOFF)["handoff_record"]
    rep.gap("phase=revoke_token·issue_next_lease에서의 재시작",
            "transitions[26]의 cond는 phase in [stop, isolate, confirm_quiescent, preserve]만 허용하고 transitions[27]은 phase == null 또는 횟수 초과만 받는다. revoke_token·issue_next_lease 단계의 재시작을 받는 전이가 없어 전이 없이 handoff에 멈춘다",
            expected="재개 또는 handoff_blocked",
            actual=f"state={env.state(HANDOFF)}, phase={hr['phase']}, 전이={tr(js)}")


# =============================================================== static group and perturbation
def perturb(node, mode):
    """Replace (mode 'garble') or remove (mode 'drop') every explanation key: when, note, _*."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in ("when", "note") or k.startswith("_"):
                if mode == "garble":
                    out[k] = "ZZ 이 문장을 코어가 읽으면 시험이 달라진다 ZZ"
                continue
            out[k] = perturb(v, mode)
        return out
    if isinstance(node, list):
        return [perturb(x, mode) for x in node]
    return node


def static(rep, R, T):
    for name, bad in static_checks.all_static(R):
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


SCENARIOS = [
    ("M28", "late-result-no-state-change", "이전 임대의 늦은 결과·전환 신호는 noop, 현재 상태 불변", m28),
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
