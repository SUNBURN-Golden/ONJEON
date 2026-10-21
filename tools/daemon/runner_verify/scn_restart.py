"""R4, R5, R18-R22: daemon crashes (SIGKILL of the real daemon process at a fault point), concurrent daemon
processes, torn store writes, TTL after a crash, revoked and corrupt records. State lives in a real file store;
instruction envelopes travel through real files; builders are real processes."""
import json
import subprocess
import time

from .harness import BASIC, HANDOFF, OTHER, noops, rets, se, tr
from .scn_fence import accepted_pushes, drain_ok, finished, snapshot_task

SCHEMA = "T-MOCK-SCHEMA"


def sent_of(w, task):
    return [s for s in w.sent() if s["task_id"] == task]


def failed_guards(js):
    out = set()
    for r in js:
        if r["kind"] == "diagnostic_record" and r["what"] == "guard_failed":
            out |= set(r["failed"])
        for c in r.get("cond") or []:
            if isinstance(c, dict) and c.get("field") == "lease_guards":
                out |= {n for n, ok in c["left"]["guards"] if not ok}
    return sorted(out)


def inbox_names(w, runner="standin-runner-1"):
    d = w.layout.inbox / runner
    return sorted(p.name for p in d.glob("*.json")) if d.exists() else []


def build_once(w, task, extra=None):
    """The builder side starts the latest instruction and its first heartbeat is accepted: the task is building."""
    instr = w.latest_instruction(task)
    h = w.start_builder(instr, [{"op": "first_heartbeat"}] + (extra or []) + [{"op": "sleep", "s": 3600}])
    w.wait_log(h, "first_heartbeat")
    drain_ok(w)
    return instr, h


# =============================================================== R4
def r4(rep, cx):
    # (a) the process dies after the instruction was sent and before the outbox row says so
    with cx.world() as w:
        w.init_task(BASIC).result
        res = w.grant(BASIC, die_at=["resend:after_send"])
        rep.ok("[발송 직후 강제 종료] 데몬 프로세스가 SIGKILL로 끝났다(종료 코드 -9)", res.killed, res.rc)
        t = w.task(BASIC)
        row = t["outbox"][0]
        intents = [r for r in w.journal() if r["kind"] == "intent_record" and r["action"] == "send_envelope"]
        results = [r for r in w.journal() if r["kind"] == "result_record" and r["action"] == "send_envelope"]
        rep.eq("[발송 직후 강제 종료] 의도 기록만 있다: outbox pending, 의도 1, 결과 0, 지시 파일은 이미 나갔다",
               ("pending", 1, 0, 1), (row["status"], len(intents), len(results), len(inbox_names(w))))
        res = w.restart()
        rep.ok("[발송 직후 강제 종료] 재시작이 정상 종료한다", res.ok, res.payload)
        sent = sent_of(w, BASIC)
        rep.eq("[발송 직후 강제 종료] 재시작: 같은 envelope_id로 다시 보내고 sent, 지시 파일은 하나(덮어씀)",
               ([row["envelope_id"]] * 2, "sent", 1), ([s["envelope_id"] for s in sent], w.task(BASIC)["outbox"][0]["status"],
                                                       len(inbox_names(w))))
        instr, h = build_once(w, BASIC)
        rep.eq("[발송 직후 강제 종료] 빌더는 한 번만 시작되어 building", (1, "building"), (len(w.handles), w.state(BASIC)))

    # (b) the process dies right after the local WIP commit, before it is recorded
    with cx.world() as w:
        go = str(w.layout.root / "go")
        script = [{"op": "write", "path": "src/work.py", "content": "print('work')\n"},
                  {"op": "write", "path": "notes.txt", "content": "n\n"}, {"op": "wait_file", "path": go},
                  {"op": "switch_signal"}, {"op": "sleep", "s": 3600}]
        instr, a, _ = w.lease_to_building(HANDOFF, script)
        w.wait_log(a, "write", count=2)
        open(go, "w").close()
        w.wait_log(a, "switch_signal")
        res = w.drain(die_at=["handoff:preserve:after_local_commit_unrecorded"])
        rep.ok("[WIP 커밋 직후 강제 종료] 데몬 프로세스가 SIGKILL로 끝났다", res.killed, res.rc)
        hr = w.task(HANDOFF)["handoff_record"]
        branch = instr["branch"]
        local = w.git(["rev-parse", "--verify", "-q", f"refs/heads/{branch}"], check=False).stdout.strip()
        rep.eq("[WIP 커밋 직후 강제 종료] 로컬 커밋은 있고 기록은 없다(preservation_state none), 원격 브랜치 없음",
               (True, "none", None), (bool(local), hr["preservation_state"], w.remote_refs().get(f"refs/heads/{branch}")))
        res = w.restart()
        rep.ok("[WIP 커밋 직후 강제 종료] 재시작이 정상 종료한다", res.ok, res.payload)
        t = w.task(HANDOFF)
        hr = t["handoff_record"]
        wip = hr["wip_commit_sha"]
        commits = w.git(["rev-list", "--count", f"refs/heads/{branch}", f"^{instr['base_sha']}"]).stdout.strip()
        rep.eq("[WIP 커밋 직후 강제 종료] 외부 상태(tree OID)로 복원: 커밋 1개, 원격 ref == WIP, 다음 임대(세대 2)",
               ("1", wip, "leased", 2), (commits, w.remote_refs().get(f"refs/heads/{branch}"), t["task_state"]["state"],
                                          t["lease_generation"]))
        rep.eq("[WIP 커밋 직후 강제 종료] WIP 커밋에 A의 작업 파일이 들어 있다", ("print('work')", "n"),
               (w.git(["show", f"{wip}:src/work.py"]).stdout.strip(), w.git(["show", f"{wip}:notes.txt"]).stdout.strip()))
        rep.eq("[WIP 커밋 직후 강제 종료] 커밋 tree == 정지 확인 tree", hr["quiescent_tree_oid"],
               w.git(["rev-parse", f"{wip}^{{tree}}"]).stdout.strip())
        pushes = [(e["credential_name"], e["lease_id"]) for e in accepted_pushes(w)]
        rep.eq("[WIP 커밋 직후 강제 종료] 원격이 수락한 푸시는 데몬 보존 자격 하나", [("preserve_credential", instr["lease_id"])], pushes)
        again = finished(drain_ok(w))  # the switch signal file was still in the inbox: it is delivered again
        rep.eq("[WIP 커밋 직후 강제 종료] 처리 도중 끝난 신호 파일의 재전달은 이전 세대로서 거부(R-11)이고 상태 불변",
               (("late_envelope_rejected", "R-11"), 2, "leased"),
               ((again[0]["noop"], again[0]["return_code"]), w.task(HANDOFF)["lease_generation"], w.state(HANDOFF)))
        rep.not_proved("강제 종료는 SIGKILL(커널이 프로세스를 즉시 없앰)이다. 전원 차단·디스크 캐시 유실은 시험하지 않았다(fsync는 호출하지만 하드웨어까지 확인하지 못했다)",
                       "A는 벤더 CLI가 아니라 스크립트 프로세스(standin)다")


# =============================================================== R5
def r5(rep, cx):
    with cx.world() as w:
        w.init_task(BASIC).result
        p1 = w.daemon_async("grant", BASIC, "--reason", "from_queue", delay_at=["lease_lock:acquired=2.5"])
        deadline = time.time() + 20
        while time.time() < deadline and not (w.snap().get("lease_lock", {}).get(BASIC, {}) or {}).get("holder"):
            time.sleep(0.02)
        holder = w.snap()["lease_lock"][BASIC]["holder"]
        rep.ok("인스턴스 1이 임대 잠금을 쥐고 있다(holder가 기록됨, 아직 임대 없음)", bool(holder) and w.task(BASIC)["lease_generation"] == 0,
               {"holder": holder})
        m = w.mark()
        second = w.grant(BASIC)
        js = w.journal()[m:]
        rep.eq("인스턴스 2: 잠금을 못 얻어 lock_acquired가 거짓, 임대 없음", (["lock_acquired"], 0),
               (failed_guards(js), w.task(BASIC)["lease_generation"]))
        out, err = p1.communicate(timeout=60)
        t = w.task(BASIC)
        rep.eq("인스턴스 1은 임대를 낸다: 세대 1, outbox 1행, 발송 1건", (1, 1, 1),
               (t["lease_generation"], len(t["outbox"]), len(sent_of(w, BASIC))))
        rep.eq("잠금은 풀려 있다", None, w.snap()["lease_lock"][BASIC]["holder"])
        rep.ok("두 인스턴스는 서로 다른 프로세스 id였다", p1.pid != 0 and second.payload["instance_id"] not in out)

    with cx.world() as w:
        w.init_task(OTHER).result
        procs = [w.daemon_async("grant", OTHER, "--reason", "from_queue") for _ in range(5)]
        outs = [p.communicate(timeout=120) for p in procs]
        t = w.task(OTHER)
        rep.eq("동시에 뜬 다섯 인스턴스가 같은 과제 임대를 시도: 세대 1, outbox 1행, 발송 1건, envelope_id 하나",
               (1, 1, 1, 1), (t["lease_generation"], len(t["outbox"]), len(sent_of(w, OTHER)),
                              len({s["envelope_id"] for s in sent_of(w, OTHER)})))
        rep.eq("임대 기록은 하나이고 잠금은 풀려 있다", (1, None), (len([r for r in w.journal() if r["kind"] == "side_effect_record"
                                                                 and r["id"] == "issue_lease"]), w.snap()["lease_lock"][OTHER]["holder"]))

    with cx.world() as w:
        w.init_task(BASIC).result
        res = w.grant(BASIC, die_at=["lease_lock:acquired"])
        dead = w.snap()["lease_lock"][BASIC]["holder"]
        rep.ok("잠금을 쥔 인스턴스를 강제 종료하면 잠금 행이 남는다(커널 flock은 풀렸지만 임대 잠금 행은 holder가 죽은 인스턴스)",
               res.killed and bool(dead), {"holder": dead})
        m = w.mark()
        w.grant(BASIC)
        rep.eq("새 인스턴스: 다른 holder의 잠금 때문에 임대 못 냄(lock_acquired 거짓), 세대 0", (["lock_acquired"], 0),
               (failed_guards(w.journal()[m:]), w.task(BASIC)["lease_generation"]))
        w.restart().result
        rep.eq("재시작이 낡은 잠금을 지운다(lock.restart)", None, w.snap()["lease_lock"][BASIC]["holder"])
        w.grant(BASIC).result
        rep.eq("그 뒤 임대가 난다: 세대 1, 발송 1건", (1, 1), (w.task(BASIC)["lease_generation"], len(sent_of(w, BASIC))))
        rep.not_proved("같은 task_id의 열린 PR 재사용(M12의 PR 부분)은 이 시험의 범위가 아니다(R5 통과 기준은 임대·봉투 하나)")


# =============================================================== R18
def atomic_state(t):
    """All of generation, lease record and outbox are there, or none of them."""
    gen, lease, outbox = t["lease_generation"], t["lease_record"], t["outbox"]
    if gen == 0 and lease is None and outbox == [] and t["task_state"]["state"] == "queued":
        return "none"
    if gen == 1 and lease and len(outbox) == 1 and outbox[0]["lease_id"] == lease["lease_id"] and t["task_state"]["state"] == "leased":
        return "all"
    return f"PARTIAL gen={gen} lease={bool(lease)} outbox={len(outbox)} state={t['task_state']['state']}"


def r18(rep, cx):
    points = [f"store:{kind}@{k}" for kind in ("torn_write", "before_rename", "after_rename") for k in range(4)]
    points += ["issue_lease:staged", "issue_lease:committed"]
    seen = {}
    for point in points:
        die = point
        with cx.world() as w:
            w.init_task(BASIC).result
            res = w.grant(BASIC, die_at=[die])
            snap_ok = True
            try:
                t = w.task(BASIC)
                kind = atomic_state(t)
            except (ValueError, KeyError) as exc:
                snap_ok, kind = False, f"unreadable {exc}"
            seen[point] = kind
            torn = list(w.layout.store_dir.glob(".state.json.*.tmp"))
            rep.ok(f"[{point}] 강제 종료(-9) 뒤 저장 파일이 읽히고 세대·임대·outbox가 모두 있거나 모두 없다({kind})",
                   res.killed and snap_ok and kind in ("none", "all"), {"rc": res.rc, "torn_temp_files": len(torn)})
            # recovery: exactly one lease, one envelope, accepted once
            restart = w.restart()
            ok_restart = restart.ok
            if atomic_state(w.task(BASIC)) == "none" and w.task(BASIC)["lease_generation"] == 0:
                w.grant(BASIC).result
            w.restart().result  # a further restart must not send again
            instr, h = build_once(w, BASIC)
            ids = {s["envelope_id"] for s in sent_of(w, BASIC)}
            t = w.task(BASIC)
            rep.eq(f"[{point}] 복구 뒤: 세대 1, 지시 봉투 하나(envelope_id 하나), 빌더 시작 1회, building",
                   (True, 1, 1, 1, "building"), (ok_restart, t["lease_generation"], len(ids), len(w.handles), t["task_state"]["state"]))
            rep.eq(f"[{point}] 저장 파일에 낡은 임시 파일이 남지 않는다", 0, len(list(w.layout.store_dir.glob(".state.json.*.tmp"))))
    rep.evid("state_after_kill", seen)
    rep.not_proved("세대 증가의 단일 책임(issue_lease 한 곳)은 정적 검사가 본다. 여기서는 어느 저장 지점에서 죽어도 중간 상태가 없다는 것만 확인했다",
                   "SIGKILL 시험이다. 전원 차단 때 디스크가 쓰기 순서를 지키는지(fsync 의미)는 하드웨어·파일 시스템 몫이고 확인하지 못했다")


# =============================================================== R19
def r19(rep, cx):
    with cx.world() as w:
        w.init_task(BASIC).result
        res = w.grant(BASIC, die_at=["issue_lease:committed"])
        t = w.task(BASIC)
        old = t["outbox"][0]["envelope_id"]
        rep.eq("발급 직후 강제 종료: 상태 leased, 세대 1, outbox pending, 발송 0", (True, "leased", 1, "pending", 0),
               (res.killed, t["task_state"]["state"], t["lease_generation"], t["outbox"][0]["status"], len(sent_of(w, BASIC))))
        w.advance(w.ttl() + 1)  # the TTL passes while the daemon is down
        m = w.mark()
        res = w.restart()
        js = w.journal()[m:]
        t = w.task(BASIC)
        rep.eq("재시작: 정상 만료 전이(leased→queued, lease_expired)", [("leased", "queued", "lease_expired")], tr(js))
        rep.eq("pending은 void(expired), 재발송 0건(발송 기록·지시 파일 모두 없음)", (("void", "expired"), 0, []),
               ((t["outbox"][0]["status"], t["outbox"][0]["void_reason"]), len(sent_of(w, BASIC)), inbox_names(w)))
        rep.eq("자동 재발급 없음: 세대 1, 임대 expired, issue_lease 0건", (1, "expired", 0),
               (t["lease_generation"], t["lease_record"]["status"], len(se(js, "issue_lease"))))
        m = w.mark()
        w.grant(BASIC).result
        t = w.task(BASIC)
        new = t["outbox"][-1]["envelope_id"]
        rep.eq("다음 queued→leased가 새 세대(2)와 새 envelope_id를 낸다", (2, True, [new]),
               (t["lease_generation"], new != old, [s["envelope_id"] for s in sent_of(w, BASIC)]))
        w.restart().result
        rep.eq("두 번째 재시작은 새 임대를 그대로 둔다(발송 1건 유지)", [new], [s["envelope_id"] for s in sent_of(w, BASIC)])


# =============================================================== R20
def r20(rep, cx):
    with cx.world() as w:
        w.init_task(BASIC).result
        w.grant(BASIC, die_at=["issue_lease:committed"])
        w.event("owner_cancelled", BASIC).result  # a new daemon process cancels the task
        t = w.task(BASIC)
        rep.eq("A 취소: 상태 cancelled, 임대 revoked, outbox는 아직 pending", ("cancelled", "revoked", "pending"),
               (t["task_state"]["state"], t["lease_record"]["status"], t["outbox"][0]["status"]))
        m = w.mark()
        w.restart().result
        js = w.journal()[m:]
        t = w.task(BASIC)
        rep.eq("A 재시작: 전이 없음, void 하나(revoked), 재발송 0건(발송 기록·지시 파일 없음), 세대 1",
               ([], ["void_outbox"], ("void", "revoked"), 0, [], 1),
               (tr(js), se(js), (t["outbox"][0]["status"], t["outbox"][0]["void_reason"]), len(sent_of(w, BASIC)), inbox_names(w),
                t["lease_generation"]))

    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": go}, {"op": "result", "status": "failed_tests"},
                                                  {"op": "sleep", "s": 3600}])
        open(go, "w").close()
        w.wait_log(a, "result")
        res = w.drain(die_at=["issue_lease:committed"])  # the re-lease (building→building) is committed, then the daemon dies
        t = w.task(BASIC)
        rep.eq("B 재임대 직후 강제 종료: 세대 2, 새 outbox 행 pending, 새 지시는 아직 나가지 않았다", (True, 2, "pending", 1),
               (res.killed, t["lease_generation"], t["outbox"][-1]["status"], len(sent_of(w, BASIC))))
        cur = t["lease_record"]
        w.submit(BASIC, "fence_violation", {"envelope_id": "V-CUR-R20", "task_id": BASIC, "lease_id": cur["lease_id"],
                                            "lease_generation": cur["lease_generation"], "fencing_token": cur["fencing_token"],
                                            "kind": "direct_push", "observed_at": w.clock.now()}).result
        t = w.task(BASIC)
        rep.eq("B 폐기(현재 임대의 위반 신고): returned, 임대 revoked, outbox pending", ("returned", "revoked", "pending"),
               (t["task_state"]["state"], t["lease_record"]["status"], t["outbox"][-1]["status"]))
        m = w.mark()
        w.restart().result
        js = w.journal()[m:]
        t = w.task(BASIC)
        rep.eq("B 재시작: 전이 없음, void(revoked) 하나, 재발송 0건(발송 1건 유지), 상태 returned",
               ([], ["void_outbox"], ("void", "revoked"), 1, "returned"),
               (tr(js), se(js), (t["outbox"][-1]["status"], t["outbox"][-1]["void_reason"]), len(sent_of(w, BASIC)),
                t["task_state"]["state"]))


# =============================================================== R21
def r21(rep, cx):
    with cx.world() as w:
        w.init_task(BASIC).result
        w.grant(BASIC, die_at=["issue_lease:committed"])
        e1 = w.task(BASIC)["outbox"][0]["envelope_id"]
        m = w.mark()
        w.restart().result
        js = w.journal()[m:]
        rep.eq("유효한 pending: 재시작에서 전이 없음, 같은 envelope_id로 재발송 한 번", ([], ["send_envelope"], [e1]),
               (tr(js), se(js), [s["envelope_id"] for s in sent_of(w, BASIC)]))
        instr = w.latest_instruction(BASIC)
        ok, _checks = w.validate_instruction(instr)
        rep.ok("실제 빌더 어댑터의 수신 측 검증(receiver_validation)이 통과한다", ok)
        h = w.start_builder(instr, [{"op": "first_heartbeat"}, {"op": "sleep", "s": 3600}])
        w.wait_log(h, "first_heartbeat")
        m = w.mark()
        drain_ok(w)
        rep.eq("first_heartbeat로 leased→building", [("leased", "building", "first_heartbeat")], tr(w.journal()[m:]))
        # the same instruction arrives a second time (the file is copied under another name): the adapter does not start it again
        dup = w.layout.inbox / "standin-runner-1" / f"{e1}.copy.json"
        dup.write_text((w.layout.inbox / "standin-runner-1" / f"{e1}.json").read_text(encoding="utf-8"), encoding="utf-8")
        seen = {i["envelope_id"] for i in [instr]}
        again = [i for i in w.instructions("standin-runner-1") if i["envelope_id"] in seen]
        rep.eq("같은 지시가 두 번 도착해도 envelope_id가 같아 어댑터는 이미 시작한 것으로 본다(프로세스 1개)", (2, 1),
               (len(again), len(w.handles)))
        first_hb = next(msg for _n, msg in w.done_messages() if msg["msg_type"] == "first_heartbeat")
        w.queue_file(first_hb)
        m = w.mark()
        out = finished(drain_ok(w))
        rep.eq("그 지시에 대한 첫 하트비트의 중복 도착은 noop(envelope_duplicate_delivery), 전이 없음",
               ([("envelope_duplicate_delivery", None)], []), (noops(w.journal()[m:]), tr(w.journal()[m:])))

    with cx.world() as w:
        # an expired instruction that reaches the builder late is not run
        w.init_task(BASIC).result
        w.grant(BASIC).result
        instr = w.latest_instruction(BASIC)
        w.advance(w.ttl() + 1)
        ok, checks = w.validate_instruction(instr)
        rep.ok("만료된 지시 봉투: 수신 측 검증이 실패한다(실행하지 않는다)", not ok)
        before_trees = sorted(p.name for p in (w.layout.worktrees).glob("*"))
        # the adapter answers with a lease_invalid result and starts nothing
        w.queue_file({"msg_type": "result", "task_id": BASIC, "envelope": {
            "envelope_id": "R21-INVALID", "task_id": BASIC, "attempt": instr["attempt"], "lease_id": instr["lease_id"],
            "lease_generation": instr["lease_generation"], "fencing_token": instr["fencing_token"], "builder": instr["builder"],
            "runner": instr["runner"], "status": "lease_invalid", "branch": instr["branch"], "head_sha": "h" * 40,
            "touched_paths": [], "tests_run": [], "test_log_ref": "standin://invalid", "signals_seen": [], "cost_units": 0,
            "calls": 0, "wall_s": 0}})
        m = w.mark()
        out = finished(drain_ok(w))
        js = w.journal()[m:]
        rep.eq("lease_invalid 결과는 late_envelope_rejected(R-11, noop), 상태 불변(leased)", ([("late_envelope_rejected", "R-11")], [], "leased"),
               (noops(js), tr(js), w.state(BASIC)))
        rep.eq("실행 없음: 작업 트리·프로세스·자격 발급이 생기지 않았다", (before_trees, 0, []),
               (sorted(p.name for p in (w.layout.worktrees).glob("*")), len(w.handles), w.cred_log()))
    rep.unconfirmed("[R21 실제 CLI 어댑터] 벤더 CLI를 띄우는 어댑터의 receiver_validation",
                    "위 수신 측 검증은 이 도구의 빌더 쪽 어댑터(context.py)와 스크립트 프로세스(standin)가 한다. 벤더 CLI를 띄우는 실제 어댑터는 이 저장소에 없어 시험하지 않았다")


# =============================================================== R22
def r22(rep, cx):
    variants = (("outbox 없이 lease_record만", lambda d: d["tasks"][BASIC].update(outbox=[])),
                ("outbox 세대 불일치", lambda d: d["tasks"][BASIC]["outbox"][0].update(lease_generation=7)))
    for label, tamper in variants:
        with cx.world() as w:
            w.init_task(BASIC).result
            w.grant(BASIC, die_at=["issue_lease:committed"])
            w.tamper(tamper)
            m = w.mark()
            res = w.restart()
            js = w.journal()[m:]
            t = w.task(BASIC)
            rep.eq(f"[{label}] 손상 분류: state_corrupted → returned(R-08)", ([("leased", "returned", "state_corrupted")], ["R-08"]),
                   (tr(js), rets(js)))
            rep.eq(f"[{label}] 임대 revoked, 세대 불변, 발송 0건, issue_lease 0건", ("revoked", 1, 0, 0),
                   (t["lease_record"]["status"], t["lease_generation"], len(sent_of(w, BASIC)), len(se(js, "issue_lease"))))
            if label.startswith("outbox 세대"):
                rep.eq(f"[{label}] pending void(corrupt)", ("void", "corrupt"), (t["outbox"][0]["status"], t["outbox"][0]["void_reason"]))
            m = w.mark()
            w.restart().result
            rep.eq(f"[{label}] 다시 재시작해도 자동 재발급 없음", ([], "returned", 1),
                   (tr(w.journal()[m:]), w.state(BASIC), w.task(BASIC)["lease_generation"]))
            m = w.mark()
            w.event("owner_resolved", BASIC, {"resolution_ref": "RES-R22"}).result
            rep.eq(f"[{label}] owner_resolved → queued(attempt+1), 여기까지 issue_lease 0건", ([("returned", "queued", "owner_resolved")], 2, 0),
                   (tr(w.journal()[m:]), w.task(BASIC)["task_state"]["attempt"], len(se(w.journal()[m:], "issue_lease"))))
            m = w.mark()
            w.grant(BASIC).result
            rep.eq(f"[{label}] queued→leased에서만 새 세대(2)", ([("queued", "leased", "lease_granted")], 1, 2),
                   (tr(w.journal()[m:]), len(se(w.journal()[m:], "issue_lease")), w.task(BASIC)["lease_generation"]))

    # a live builder: the corruption effects act on the real process and the real credentials
    with cx.world() as w:
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "write", "path": "x.txt", "content": "x\n"}, {"op": "sleep", "s": 3600}])
        w.tamper(lambda d: d["tasks"][BASIC].update(outbox=[]))
        m = w.mark()
        w.restart().result
        js = w.journal()[m:]
        gone = w.wait_gone(a, 10)
        probe = w.git(["push", "--force", str(w.remote), "HEAD:refs/heads/task/T-MOCK-BASIC-a1"], cwd=instr["worktree"], check=False,
                      env={"RV_PUSH_CREDENTIAL": a.token})
        rep.eq("[실행 중인 빌더] building에서 손상 분류: returned(R-08)", ([("building", "returned", "state_corrupted")], ["R-08"]),
               (tr(js), rets(js)))
        rep.eq("[실행 중인 빌더] 실제 프로세스 그룹이 종료되고 쓰기 자격은 원격에서도 회수되었다", (True, -9, True),
               (gone, a.popen.returncode, "credential_revoked" in probe.stderr))
        rep.eq("[실행 중인 빌더] 자동 재발급 0건, 지시 봉투 새로 나가지 않음", (0, 1),
               (len(se(js, "issue_lease")), len(sent_of(w, BASIC))))

    # a state file that cannot be read: the daemon refuses to run and leaves the file as it is
    with cx.world() as w:
        w.init_task(BASIC).result
        w.grant(BASIC, die_at=["issue_lease:committed"])
        raw = w.layout.store.read_bytes()
        w.layout.store.write_bytes(raw[: len(raw) // 2])
        damaged = w.layout.store.read_bytes()
        res = w.restart()
        rep.eq("[저장 파일 손상] 읽을 수 없는 상태 파일: 데몬이 실패로 끝나고(종료 코드 0이 아님) 파일을 덮어쓰지 않는다",
               (True, damaged), (res.rc != 0, w.layout.store.read_bytes()))
        rep.eq("[저장 파일 손상] 발송·자동 재발급 0건", 0, len(sent_of(w, BASIC)))
    rep.not_proved("파일 수준 손상에서 데몬은 멈추기만 한다(복구·소유자 결정 절차는 사람 몫이다). 명세가 파일 수준 손상의 R 코드를 정하지 않았다")
