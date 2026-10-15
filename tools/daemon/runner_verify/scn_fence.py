"""R1, R2, R3, R9: late writes and results of a replaced or ended lease, concurrent writes around a replacement, and
the hard stop of a job that keeps sending heartbeats. Real processes, a real git remote with a protected branch and
revocable credentials, real files; the clock offset is the only shifted thing (see common.py)."""
import json
import os
import time

from .harness import BASIC, HANDOFF, OTHER, first_seq, noops, rets, se, tr
from .common import read_jsonl, read_text

LATE_PUSH_OWN = "own_branch"


def late_actor(go_path, branch, with_result=True):
    """What a builder that escaped the group kill tries after its lease ended (runs in its own session)."""
    script = [{"op": "wait_file", "path": go_path, "timeout": 300},
              {"op": "git_commit", "allow_empty": True, "message": "late commit"},
              {"op": "push", "ref": f"refs/heads/{branch}"},
              {"op": "push", "ref": f"refs/heads/{branch}", "force": True},
              {"op": "push", "ref": "refs/heads/main"}]
    if with_result:
        script += [{"op": "result", "status": "pr_opened"}, {"op": "push_request"}, {"op": "heartbeat"}]
    return {"op": "spawn_survivor", "name": "late", "script": script}


def snapshot_task(w, task_id):
    t = w.task(task_id)
    return {k: t[k] for k in ("task_state", "lease_record", "outbox", "inbox_seen", "lease_generation")}


def accepted_pushes(w):
    return [e for e in w.push_log() if e["event"] == "pre_receive" and e["decision"] == "accepted"]


def rejected_pushes(w):
    return [e for e in w.push_log() if e["event"] == "pre_receive" and e["decision"] == "rejected"]


def drain_ok(w):
    r = w.drain()
    assert r.ok, r.payload
    return r.result


def finished(items):
    return [i["outcome"] for i in items if i.get("ok")]


# =============================================================== R1
def r1(rep, cx):
    with cx.world() as w:
        late_go = str(w.layout.root / "late_go")
        a_sha = str(w.layout.root / "a.sha")
        script = [{"op": "write", "path": "src/a.txt", "content": "A work\n"},
                  {"op": "git_commit", "message": "A work", "sha_file": a_sha},
                  late_actor(late_go, "task/T-MOCK-BASIC-a1"), {"op": "sleep", "s": 3600}]
        instr_a, a, _ = w.lease_to_building(BASIC, script)
        w.wait_log(a, "git_commit")
        w.wait_log(a, "spawn_survivor")
        refs0 = w.remote_refs()
        rep.eq("시작: 임대 A(세대 1, token 1)로 building", ("building", 1, 1),
               (w.state(BASIC), w.lease(BASIC)["lease_generation"], w.lease(BASIC)["fencing_token"]))

        # A stops sending heartbeats; the lease runs out (the clock is moved, the processes are real)
        m = w.mark()
        w.advance(2 * w.heartbeat_s() + 1)
        res = w.tick()
        js = w.journal()[m:]
        rep.eq("하트비트 두 번 누락: building→returned(R-08)", ([("building", "returned", "heartbeat_missed_twice")], ["R-08"]),
               (tr(js), rets(js)))
        rep.eq("임대 A 종료: 프로세스 그룹 종료·쓰기 자격 회수·토큰 회수가 기록된다", True,
               all(x in se(js) for x in ("terminate_process", "revoke_write_credential", "revoke_token")))
        a_gone = w.wait_gone(a, 10)
        rep.eq("A의 프로세스 그룹은 실제로 사라졌다(종료 신호 -9)", (True, -9, 0),
               (a_gone, a.popen.returncode, w.ports().process.alive_count(BASIC)))

        # replacement lease B
        w.event("owner_resolved", BASIC, {"resolution_ref": "RES-R1"}).result
        assert w.grant(BASIC).ok
        instr_b = w.latest_instruction(BASIC)
        b_sha = str(w.layout.root / "b.sha")
        b = w.start_builder(instr_b, [{"op": "first_heartbeat"}, {"op": "write", "path": "src/b.txt", "content": "B work\n"},
                                      {"op": "git_commit", "message": "B work", "sha_file": b_sha},
                                      {"op": "push_request"}, {"op": "sleep", "s": 3600}])
        w.wait_log(b, "first_heartbeat")
        w.wait_log(b, "push_request")
        first = drain_ok(w)  # B's first heartbeat, then B's own push request
        rep.eq("교체 임대 B(세대 2, token 2)가 building이고 B의 데몬 경유 푸시는 실행된다",
               ("building", 2, 2, [True]), (w.state(BASIC), w.lease(BASIC)["lease_generation"],
                                            w.lease(BASIC)["fencing_token"],
                                            [o.get("written") for o in finished(first) if "written" in o]))
        refs_b = w.remote_refs()
        b_commit = read_text(b_sha).strip()
        rep.eq("원격에는 B의 브랜치(task/…-a2)가 B의 커밋으로 생겼고 A의 브랜치·main은 그대로",
               (b_commit, refs0.get("refs/heads/main"), None),
               (refs_b.get("refs/heads/task/T-MOCK-BASIC-a2"), refs_b.get("refs/heads/main"),
                refs_b.get("refs/heads/task/T-MOCK-BASIC-a1")))

        # A's late actor (alive in another session, still holding A's revoked credential) acts now
        before = snapshot_task(w, BASIC)
        refs_before_late = w.remote_refs()
        pushes_before = len(w.push_log())
        m = w.mark()
        open(late_go, "w").close()
        w.wait_log(a, "heartbeat", suffix="late", timeout=60)
        pushes = [r for r in a.log(w, "late") if r["op"] == "push"]
        rep.eq("A의 실제 푸시 셋: 회수된 자격으로 자기 브랜치(거부), 같은 브랜치 강제 푸시(거부), 보호 브랜치 main(거부)",
               [("refs/heads/task/T-MOCK-BASIC-a1", False, "credential_revoked"), ("refs/heads/task/T-MOCK-BASIC-a1", True, "credential_revoked"),
                ("refs/heads/main", False, "protected_branch")],
               [(r["ref"], r["force"], r["reject"]) for r in pushes])
        rep.ok("두 푸시 모두 git 종료 코드가 0이 아니다", all(r["rc"] != 0 for r in pushes))
        rep.eq("원격 ref는 A의 늦은 푸시 전후로 같다(브랜치 SHA 불변)", refs_before_late, w.remote_refs())
        new_push_log = w.push_log()[pushes_before:]
        rep.eq("원격 푸시 로그: 늦은 푸시 셋은 모두 rejected이고 수락 0건",
               [("rejected", "credential_revoked"), ("rejected", "credential_revoked"), ("rejected", "protected_branch")],
               [(e["decision"], e["reason"]) for e in new_push_log if e["event"] == "pre_receive"])
        rep.eq("거부된 자격은 A의 builder_write_credential이고 A의 임대 id를 달고 있다", (["builder_write_credential"], [instr_a["lease_id"]]),
               (sorted({e["credential_name"] for e in new_push_log if e["event"] == "pre_receive" and e["credential_name"]}),
                sorted({e["lease_id"] for e in new_push_log if e["event"] == "pre_receive" and e["lease_id"]})))
        out = drain_ok(w)  # the late result, push request and heartbeat of A reach the daemon
        js = w.journal()[m:]
        rep.eq("A의 늦은 결과 봉투·푸시 요청·하트비트: late_envelope_rejected(R-11) 세 건", [("late_envelope_rejected", "R-11")] * 3, noops(js))
        rep.eq("현재 임대 B의 상태·임대·inbox_seen·세대는 불변, 전이 0건", (before, []), (snapshot_task(w, BASIC), tr(js)))
        wr = read_jsonl(w.layout.root / "remote_writes.jsonl")
        rep.eq("데몬이 낸 원격 쓰기는 B의 것 하나뿐(A의 푸시 요청은 원격 쓰기에 닿지 않았다)", [(True, 2)],
               [(x["executed"], x["lease_generation"]) for x in wr])
        rep.evid("timeline", {"a_lease": instr_a["lease_id"], "b_lease": instr_b["lease_id"],
                              "late_push_log": new_push_log, "refs_before": refs0, "refs_after": w.remote_refs(),
                              "late_outcomes": [i["outcome"] for i in out if i.get("ok")]})
        rep.not_proved("원격 거부(직접 푸시)가 데몬의 R-11 기록으로 이어지는 경로는 명세에 없다: 데몬이 R-11을 남기는 것은 데몬 경유 푸시 요청·결과 봉투·하트비트뿐이다",
                       "실제 Git 호스트의 보호 브랜치와 단기 자격 발급·회수는 사람이 적용하는 설정이다(04 §8). 여기서는 로컬 bare 저장소의 hook이 그 역할을 했다",
                       "A는 벤더 CLI가 아니라 스크립트 프로세스(standin)다")


# =============================================================== handoff pair shared by R2 and R3
def handoff_pair(w, with_late_actor=False, b_conflict=True):
    """Task HANDOFF: A (ignores the stop request, keeps writing the shared file, has a second writer in another
    session) asks for a switch; the daemon hands the task to B; B edits the same file in its own worktree."""
    go_switch = str(w.layout.root / "go_switch")
    late_go = str(w.layout.root / "late_go")
    shared = "src/shared.txt"
    script = [{"op": "ignore_term"}, {"op": "write", "path": shared, "content": "A first\n"},
              {"op": "spawn_survivor", "name": "writer", "script": [{"op": "loop_write", "path": shared, "interval": 0.005}]}]
    if with_late_actor:
        script.append(late_actor(late_go, "task/T-MOCK-HANDOFF-a1"))
    script += [{"op": "wait_file", "path": go_switch}, {"op": "switch_signal"},
               {"op": "loop_write", "path": shared, "interval": 0.005}]
    instr_a, a, _ = w.lease_to_building(HANDOFF, script)
    w.wait_log(a, "spawn_survivor", count=2 if with_late_actor else 1)
    open(go_switch, "w").close()
    w.wait_log(a, "switch_signal")
    t_switch = time.time_ns()
    m = w.mark()
    res = w.drain()  # the switch signal: stop, isolate, confirm_quiescent, preserve, revoke, issue the next lease
    assert res.ok, res.payload
    info = {"instr_a": instr_a, "a": a, "mark": m, "t_switch_ns": t_switch, "late_go": late_go, "shared": shared,
            "handoff_journal": w.journal()[m:]}
    instr_b = w.latest_instruction(HANDOFF)
    info["instr_b"] = instr_b
    if instr_b and instr_b["lease_id"] != instr_a["lease_id"]:
        b_sha = str(w.layout.root / "b.sha")
        script_b = [{"op": "first_heartbeat"}, {"op": "write", "path": shared, "content": "B edit\n"},
                    {"op": "git_commit", "message": "B edit", "sha_file": b_sha}, {"op": "push_request"},
                    {"op": "sleep", "s": 3600}]
        b = w.start_builder(instr_b, script_b)
        w.wait_log(b, "push_request")
        info.update(b=b, b_sha=b_sha)
        info["b_drain"] = drain_ok(w)
    return info


def credential_intervals(w, task_id, name="builder_write_credential"):
    """[(lease_id, issued_ns, first_revoked_ns or None)] from the credential log, in issue order."""
    out = []
    for e in w.cred_log():
        if e["task_id"] != task_id or e["name"] != name:
            continue
        if e["op"] == "issue":
            out.append([e["lease_id"], e["ns"], None])
        elif e["op"] == "revoke" and e.get("was_active"):
            for row in reversed(out):
                if row[2] is None:
                    row[2] = e["ns"]
                    break
    return [tuple(r) for r in out]


# =============================================================== R2
def r2(rep, cx):
    with cx.world() as w:
        info = handoff_pair(w, with_late_actor=True)
        instr_a, instr_b, js = info["instr_a"], info["instr_b"], info["handoff_journal"]
        rep.eq("인계 결과: building→handoff→leased, 세대 2, 빌더 교체", ("building", 2, "standin-builder-2"),
               (w.state(HANDOFF), w.lease(HANDOFF)["lease_generation"], w.lease(HANDOFF)["builder"]))
        # the order of the handoff sequence in the logs of the real processes and the remote (nanosecond times)
        proc, creds, pushes = w.proc_log(), w.cred_log(), w.push_log()
        sent = [s for s in w.sent() if s["task_id"] == HANDOFF and s["lease_generation"] == 2]
        stop = next(e["ns"] for e in proc if e["event"] == "stop_requested")
        kill = next(e["ns"] for e in proc if e["event"] == "terminate_group")
        revoke_write = next(e["ns"] for e in creds if e["op"] == "revoke" and e["name"] == "builder_write_credential" and e.get("was_active"))
        wip_push = next(e["ts_ns"] for e in pushes if e["event"] == "pre_receive" and e["decision"] == "accepted"
                        and e["credential_name"] == "preserve_credential")
        revoke_token = next(e["ns"] for e in creds if e["op"] == "revoke" and e["name"] == "builder_token" and e.get("was_active"))
        issue_next = sent[0]["ns"]
        timeline = [("stop(SIGTERM 요청)", stop), ("isolate(프로세스 그룹 종료)", kill), ("빌더 쓰기 자격 회수", revoke_write),
                    ("preserve(보존 자격의 푸시를 원격이 수락)", wip_push), ("revoke_token", revoke_token),
                    ("issue_next_lease(다음 지시 봉투 발송)", issue_next)]
        rep.eq("실제 로그의 시각 순서: stop < isolate < 자격 회수 < preserve < revoke_token < issue_next_lease",
               [t[0] for t in timeline], [t[0] for t in sorted(timeline, key=lambda x: x[1])])
        rep.ok("시각이 서로 다르고 엄격히 증가한다", len({t[1] for t in timeline}) == len(timeline))
        order = [first_seq(js, "intent_record", action="stop"), first_seq(js, "side_effect_record", id="worktree_readonly"),
                 first_seq(js, "result_record", action="confirm_quiescent"), first_seq(js, "intent_record", action="preserve_commit"),
                 first_seq(js, "intent_record", action="preserve_push"), first_seq(js, "side_effect_record", id="revoke_token"),
                 first_seq(js, "side_effect_record", id="issue_lease")]
        rep.eq("데몬 저널의 순서도 같다(stop → isolate → confirm_quiescent → preserve(커밋 → 푸시) → revoke_token → issue_lease)",
               True, all(x is not None for x in order) and order == sorted(order))
        # the late result of A
        before = snapshot_task(w, HANDOFF)
        m = w.mark()
        open(info["late_go"], "w").close()
        w.wait_log(info["a"], "heartbeat", suffix="late", timeout=60)
        out = drain_ok(w)
        js2 = w.journal()[m:]
        rep.eq("A의 늦은 결과 봉투·푸시 요청·하트비트: late_envelope_rejected(R-11) 세 건", [("late_envelope_rejected", "R-11")] * 3, noops(js2))
        late = [r for r in js2 if r["kind"] == "noop_record"]
        rep.eq("거부 이유는 lease_id·세대·토큰 불일치(lease_matches)", ["lease_matches"] * 3, [r.get("failed_check") for r in late])
        rep.eq("현재 임대 B의 상태 전이 0건, 상태·임대·inbox_seen 불변", ([], before), (tr(js2), snapshot_task(w, HANDOFF)))
        rep.eq("A의 결과 봉투는 사용량 기록에 들어가지 않았다(거부된 봉투는 기록하지 않음)", 0,
               len([r for r in w.snap().get("usage_record", []) if r["task_id"] == HANDOFF and r["calls"] is not None]))
        late_pushes = [r for r in info["a"].log(w, "late") if r["op"] == "push"]
        rep.eq("원격은 A의 늦은 푸시를 거부(일반 푸시는 B가 쌓은 브랜치와 갈라져 git이 먼저 막고, 강제 푸시는 회수된 자격으로 원격이 막는다)",
               [("refs/heads/task/T-MOCK-HANDOFF-a1", False, "non_fast_forward"), ("refs/heads/task/T-MOCK-HANDOFF-a1", True, "credential_revoked"),
                ("refs/heads/main", False, "protected_branch")],
               [(r["ref"], r["force"], r["reject"]) for r in late_pushes])
        rep.evid("handoff_timeline_ns", {name: ns for name, ns in timeline})
        rep.evid("late_outcomes", [i["outcome"] for i in out if i.get("ok")])
        rep.not_proved("순서 증거는 데몬이 남긴 로그, 프로세스 레지스터, 원격 hook 로그의 시각을 맞춰 본 것이다. 서로 다른 호스트의 시계는 맞추지 않았다(한 호스트)",
                       "A는 벤더 CLI가 아니라 스크립트 프로세스(standin)다")


# =============================================================== R3
def r3(rep, cx):
    with cx.world() as w:
        info = handoff_pair(w)
        a, instr_a, instr_b = info["a"], info["instr_a"], info["instr_b"]
        iv = credential_intervals(w, HANDOFF)
        rep.eq("쓰기 자격 구간이 임대마다 하나씩(A, B)", [instr_a["lease_id"], instr_b["lease_id"]], [r[0] for r in iv])
        a_iv, b_iv = iv[0], iv[1]
        rep.ok("A의 쓰기 자격은 B의 자격이 발급되기 전에 회수되었다(두 자격이 동시에 있던 구간 없음)",
               a_iv[2] is not None and a_iv[2] <= b_iv[1], {"A": a_iv[1:], "B": b_iv[1:]})
        rep.evid("credential_intervals_ns", {"A": [a_iv[1], a_iv[2]], "B": [b_iv[1], b_iv[2]]})
        killed = [e for e in w.proc_log() if e["event"] == "terminate_group"]
        w.wait_gone(a, 10)
        rep.eq("A 프로세스 그룹 종료 로그 한 건, 남은 구성원 0, 프로세스 종료 신호 -9", (1, 0, -9),
               (len(killed), killed[0]["left"], a.popen.returncode))
        wt = instr_a["worktree"]
        shared = os.path.join(wt, info["shared"])
        writable = []
        for path in (wt, os.path.join(wt, "src"), shared):
            writable.append(os.access(path, os.W_OK))
        rep.eq("A의 작업 트리는 읽기 전용(디렉터리와 파일에 쓰기 권한 없음)", [False, False, False], writable)
        try:
            with open(shared, "a") as f:
                f.write("late write\n")
            denied = False
        except PermissionError:
            denied = True
        rep.ok("A 트리에 대한 실제 쓰기 시도는 PermissionError로 막힌다", denied)
        writer_log = a.log(w, "writer")
        rep.ok("다른 세션에 남은 A의 두 번째 쓰기 프로세스는 격리 뒤 쓰기 실패를 겪었다(EACCES 기록)",
               any(r["op"] == "loop_write" and r.get("ok") is False for r in writer_log))
        m1 = w.ports().worktree.max_mtime(wt)
        time.sleep(0.6)
        m2 = w.ports().worktree.max_mtime(wt)
        rep.eq("격리 뒤 A 트리의 최대 mtime은 더 변하지 않는다", m1, m2)
        hr = w.task(HANDOFF)["handoff_record"]
        wip = hr["wip_commit_sha"]
        tree_now = w.git(["rev-parse", f"{wip}^{{tree}}"]).stdout.strip()
        rep.eq("보존 커밋의 tree OID == 정지 확인의 quiescent_tree_oid", hr["quiescent_tree_oid"], tree_now)
        acc = [(e["credential_name"], e["lease_id"]) for e in accepted_pushes(w)]
        rep.eq("원격이 수락한 푸시: A 임대에 대한 데몬 보존 자격 하나, 그다음 B의 빌더 자격 하나(A의 빌더 자격 푸시 0건)",
               [("preserve_credential", instr_a["lease_id"]), ("builder_write_credential", instr_b["lease_id"])], acc)
        b_commit = read_text(info["b_sha"]).strip()
        refs = w.remote_refs()
        rep.eq("원격 브랜치 끝 == B의 커밋(A의 WIP 위에 B가 쌓음)", (b_commit, wip),
               (refs["refs/heads/task/T-MOCK-HANDOFF-a1"], w.git(["rev-parse", f"{b_commit}^"]).stdout.strip()))
        rep.eq("같은 파일을 A는 tick 줄로, B는 'B edit'로 고쳤고 원격에는 B의 내용이 있다", ("B edit", True),
               (w.git(["show", f"{b_commit}:{info['shared']}"]).stdout.strip(),
                w.git(["show", f"{wip}:{info['shared']}"]).stdout.startswith(("tick", "A first"))))
        # A's old credential cannot push any more, from A's own tree
        w.git(["commit", "--allow-empty", "-q", "-m", "late commit of A"], cwd=wt, env={"GIT_COMMITTER_DATE": "2000-01-01T00:00:00"})
        late_sha = w.git(["rev-parse", "HEAD"], cwd=wt).stdout.strip()
        res = w.git(["push", "--force", str(w.remote), f"{late_sha}:refs/heads/task/T-MOCK-HANDOFF-a1"], cwd=wt, check=False,
                    env={"RV_PUSH_CREDENTIAL": a.token, "RV_PUSH_CLIENT": "builder-a"})
        rep.ok("A의 회수된 자격으로 지금 푸시해도 원격이 거부한다", res.returncode != 0 and "credential_revoked" in res.stderr)
        rep.not_proved("자격 구간은 데몬이 쓴 발급·회수 로그의 시각이다. 원격 hook은 푸시 시점에 같은 자격 기록을 읽는다. 실제 호스트의 토큰 만료·회수 전파 지연은 확인하지 못했다",
                       "읽기 전용 격리는 파일 권한이다. 같은 사용자의 살아 있는 프로세스가 권한을 되돌릴 수 있고, 그 경우를 막는 것은 프로세스 그룹 종료와 열린 쓰기 핸들 검사다(R11)",
                       "A·B는 벤더 CLI가 아니라 스크립트 프로세스(standin)다")


# =============================================================== R9
def r9(rep, cx):
    with cx.world() as w:
        late_go = str(w.layout.root / "late_go")
        script = [{"op": "ignore_term"}, {"op": "write", "path": "src/job.txt", "content": "job\n"},
                  late_actor(late_go, "task/T-MOCK-OTHER-a1"),
                  {"op": "spawn_child", "name": "loop", "script": [{"op": "ignore_term"},
                                                                    {"op": "loop_write", "path": "progress.txt", "interval": 0.01}]},
                  {"op": "heartbeat_forever", "every": 0.15}]
        instr, h, _ = w.lease_to_building(OTHER, script)
        w.wait_log(h, "spawn_child")
        grace = int(w.rules.number("hard_stop.grace_s"))
        w.event("owner_stop", OTHER, {"stop_ref": "STOP-R9"}).result
        stop_at = w.task(OTHER)["task_state"]["stop_requested_at"]
        w.ports().sender.request_stop(OTHER, instr["builder"])  # the stop request reaches the process (SIGTERM)
        time.sleep(0.5)
        rep.eq("중단 지시 직후: 상태는 building(전이는 stop 요청), SIGTERM을 무시한 프로세스는 살아 있다", ("building", True),
               (w.state(OTHER), w.ports().process.alive_count(OTHER) > 0))
        beats_before = 0
        while stop_at + grace - w.clock.now() > 12:
            w.advance(min(20, stop_at + grace - w.clock.now() - 12))
            time.sleep(0.4)
            out = drain_ok(w)
            beats_before += sum(1 for o in finished(out) if o.get("accepted"))
            w.tick()
            if w.state(OTHER) != "building":
                break
        rep.ok("기한(grace_s) 전에는 하트비트가 계속 수락되고 building이 유지된다", beats_before > 0 and w.state(OTHER) == "building",
               {"수락된 하트비트": beats_before, "남은 초": stop_at + grace - w.clock.now()})
        w.advance(max(0, stop_at + grace - w.clock.now()) + 1)
        time.sleep(0.4)
        drain_ok(w)
        m = w.mark()
        w.tick()
        js = w.journal()[m:]
        rep.eq("grace_s 경과: hard_stop_deadline → returned(R-07), 임대 종료(expired)", ([("building", "returned", "hard_stop_deadline")], ["R-07"], "expired"),
               (tr(js), rets(js), w.lease(OTHER)["status"]))
        rep.ok("프로세스 그룹 종료·쓰기 자격 회수·토큰 회수가 기록된다",
               all(x in se(js) for x in ("terminate_process", "revoke_write_credential", "revoke_token")))
        rep.eq("계속 하트비트를 보내던 실제 프로세스가 사라졌다(종료 신호 -9, 그룹 남은 구성원 0)", (True, -9, 0),
               (w.wait_gone(h, 10), h.popen.returncode, w.ports().process.alive_count(OTHER)))
        rep.eq("쓰기 자격은 원격 기록에서도 회수(원격이 revoked로 거절)", True,
               "credential_revoked" in w.git(["push", str(w.remote), "HEAD:refs/heads/task/T-MOCK-OTHER-a1"], cwd=instr["worktree"],
                                               check=False, env={"RV_PUSH_CREDENTIAL": h.token}).stderr)
        leftover = finished(drain_ok(w))  # heartbeats written just before the kill and not yet read
        rep.ok("죽기 직전에 쓴 하트비트가 남아 있었다면 모두 late로 거부된다(수락 0건)",
               all(not o.get("accepted") and o.get("noop") == "late_envelope_rejected" for o in leftover), leftover)
        time.sleep(1.0)
        rep.eq("그룹이 죽은 뒤에는 새 하트비트 파일이 오지 않는다", 0, len(list(w.layout.daemon_inbox.glob("*.json"))))
        rep.eq("데몬 보존 없음(daemon_preserve=false): 커밋·푸시 기록 0, 원격에 task 브랜치 없음", (0, 0, []),
               (len([r for r in w.journal() if r["kind"] == "intent_record" and r["action"] in ("preserve_commit", "preserve_push")]),
                len(accepted_pushes(w)), [r for r in w.remote_refs() if r.startswith("refs/heads/task/")]))
        before = snapshot_task(w, OTHER)
        m = w.mark()
        pushes_before = len(w.push_log())
        open(late_go, "w").close()
        w.wait_log(h, "heartbeat", suffix="late", timeout=60)
        out = drain_ok(w)
        js2 = w.journal()[m:]
        rep.eq("그 뒤의 봉투(결과·푸시 요청·하트비트)는 late_envelope_rejected(R-11)", [("late_envelope_rejected", "R-11")] * 3, noops(js2))
        rep.eq("상태 returned·임대 불변", (before, []), (snapshot_task(w, OTHER), tr(js2)))
        pl = [e for e in w.push_log()[pushes_before:] if e["event"] == "pre_receive"]
        rep.eq("그 뒤의 푸시 셋은 원격이 거부한다", [("rejected", "credential_revoked"), ("rejected", "credential_revoked"), ("rejected", "protected_branch")],
               [(e["decision"], e["reason"]) for e in pl])
        ro = not os.access(instr["worktree"], os.W_OK)
        if ro:
            rep.ok("끝난 임대의 작업 트리는 읽기 전용으로 남는다(04 §8)", True)
        else:
            rep.gap("끝난 임대의 작업 트리는 읽기 전용으로 남는다(04 §8)",
                    "hard_stop_deadline 전이의 부수 효과에 worktree_readonly가 없어 코어는 작업 트리를 읽기 전용으로 만들지 않는다. "
                    "R9의 통과 기준(프로세스 그룹 종료·자격 회수·뒤의 푸시·봉투 거부)에는 들어 있지 않다",
                    expected="읽기 전용", actual="쓰기 가능")
        rep.not_proved("SIGTERM을 무시하고 하트비트를 보내는 동작은 스크립트 프로세스(standin)로 시험했다. 벤더 CLI의 같은 동작은 R9 실제 CLI 변형(있으면 별도 기록)에서 본다",
                       "중단 지시를 빌더에게 전달하는 SIGTERM은 어댑터(sender.request_stop)가 보냈다. 코어의 request_stop 효과는 시각만 기록하고 전달 호출을 하지 않는다")
