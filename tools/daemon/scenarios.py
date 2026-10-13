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
    env.core.tick()
    rep.eq("600초(heartbeat_s*2)에 만료 전이", [("leased", "queued", "lease_expired")], tr(jr(env, m)))


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
    rep.gap("void_reason=cancelled를 만드는 규칙",
            "store.outbox.void_reason에 cancelled가 있으나 resend_outbox.on_fail.revoked_or_cancelled는 항상 reason=revoked다. 취소와 폐기를 구분해 기록하는 규칙이 없어 revoked로 기록됨",
            expected="cancelled 또는 revoked(명세 미정)", actual="revoked")

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

SCENARIOS = [
    ("M41", "restart-ttl-expired-no-resend", "x", m41),
    ("M42", "restart-revoked-pending-void", "x", m42),
    ("M43", "restart-valid-pending-resend", "x", m43),
    ("M44", "restart-corrupt-record-returned", "x", m44),
]
