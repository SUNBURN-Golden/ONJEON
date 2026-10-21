"""R8, R12, R13, R17: envelope delivery over real paths (file queue, HTTP with a lost response), new idempotency keys
after every kind of re-lease, distinct envelope ids, and the decision gate / return-resume flow on the real store."""
import http.client
import json
import socket
import time

from .harness import BASIC, HANDOFF, OTHER, noops, rets, se, tr
from .scn_fence import accepted_pushes, drain_ok, finished, snapshot_task
from .scn_restart import build_once, sent_of

GATED = "T-MOCK-GATED"


def copy_queue_file(w, name, times):
    """Deliver the same message again under other file names (a retransmission by the file queue)."""
    src = w.layout.daemon_done / name
    msg = json.loads(src.read_text(encoding="utf-8"))
    return [w.queue_file(msg, name=f"{time.time_ns()}-retx{i}.json") for i in range(times)]


def last_done(w, msg_type):
    return [(n, m) for n, m in w.done_messages() if m["msg_type"] == msg_type][-1]


# =============================================================== R12
def r12(rep, cx):
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": go}, {"op": "heartbeat"},
                                                  {"op": "result", "status": "pr_opened", "fields": {"pr_number": 12}},
                                                  {"op": "sleep", "s": 3600}])
        # stand-in sends a heartbeat; the file is delivered three times
        open(go, "w").close()
        w.wait_log(a, "result")
        first = sorted(w.layout.daemon_inbox.glob("*.json"))
        hb_file = next(p for p in first if json.loads(p.read_text())["msg_type"] == "heartbeat")
        res_file = next(p for p in first if json.loads(p.read_text())["msg_type"] == "result")
        hb_msg = json.loads(hb_file.read_text())
        res_msg = json.loads(res_file.read_text())
        res_file.rename(w.layout.root / "held_result.json")  # the result waits; the heartbeat goes first
        w.queue_file(hb_msg, name=f"{time.time_ns()}-retx1.json")
        w.queue_file(hb_msg, name=f"{time.time_ns()}-retx2.json")
        m = w.mark()
        out = finished(drain_ok(w))
        js = w.journal()[m:]
        rep.eq("파일 큐에서 같은 하트비트가 세 번 도착: 처음 하나만 수락, 나머지 둘은 noop(envelope_duplicate_delivery)",
               ([True, False, False], [("heartbeat", None), ("envelope_duplicate_delivery", None), ("envelope_duplicate_delivery", None)]),
               ([bool(o.get("accepted")) for o in out], noops(js)))
        after_first = snapshot_task(w, BASIC)
        # the same message again: nothing changes
        w.queue_file(hb_msg, name=f"{time.time_ns()}-retx3.json")
        finished(drain_ok(w))
        rep.eq("한 번 더 도착해도 상태 저장소(상태·임대·inbox_seen)는 그대로", after_first, snapshot_task(w, BASIC))
        # crash between processing and moving the file: the file is delivered again after restart
        hb2 = dict(hb_msg, envelope=dict(hb_msg["envelope"], envelope_id="R12-HB2", at=w.clock.now()))
        w.queue_file(hb2, name=f"{time.time_ns()}-crash.json")
        res = w.drain(die_at=["drain:processed_unmoved"])
        snap_after_crash = snapshot_task(w, BASIC)
        rep.ok("처리한 뒤 파일을 옮기기 전에 데몬이 죽었다: 파일은 큐에 남고 처리 결과는 저장되어 있다",
               res.killed and any(p.name.endswith("crash.json") for p in w.layout.daemon_inbox.glob("*.json")))
        m = w.mark()
        out = finished(drain_ok(w))
        rep.eq("재시작 뒤 같은 파일이 다시 전달되면 noop이고 상태는 첫 처리 뒤와 같다",
               ([("envelope_duplicate_delivery", None)], snap_after_crash), (noops(w.journal()[m:]), snapshot_task(w, BASIC)))
        # a result envelope ends the lease; its redelivery is a duplicate, not a late one (G40)
        (w.layout.root / "held_result.json").rename(w.layout.daemon_inbox / f"{time.time_ns()}-result.json")
        m = w.mark()
        finished(drain_ok(w))
        rep.eq("결과 봉투는 처음 처리되어 building→pr_open", [("building", "pr_open", "result_pr_opened")], tr(w.journal()[m:]))
        snap_res = snapshot_task(w, BASIC)
        w.queue_file(res_msg, name=f"{time.time_ns()}-retx-result.json")
        m = w.mark()
        out = finished(drain_ok(w))
        rep.eq("임대를 끝낸 결과 봉투의 재전달은 envelope_duplicate_delivery(noop)이고 late가 아니다, 상태 불변",
               ([("envelope_duplicate_delivery", None)], snap_res), (noops(w.journal()[m:]), snapshot_task(w, BASIC)))
        rep.eq("사용량 기록은 처음 수락한 한 번뿐", 1,
               len([r for r in w.journal() if r["kind"] == "side_effect_record" and r["id"] == "record_usage"
                    and r["args"].get("phase") == "after_result"]))

    # HTTP delivery with a response that is lost: the client times out and sends the same envelope again
    with cx.world() as w:
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "sleep", "s": 3600}])
        hb = {"msg_type": "heartbeat", "task_id": BASIC, "envelope": {
            "envelope_id": "R12-HTTP-HB", "task_id": BASIC, "lease_id": instr["lease_id"],
            "lease_generation": instr["lease_generation"], "fencing_token": instr["fencing_token"], "at": w.clock.now()}}
        server = w.daemon_async("serve", "--duration", "40", "--delay-first-response", "1.5")
        port_file = w.layout.root / "http_port"
        deadline = time.time() + 20
        while time.time() < deadline and not port_file.exists():
            time.sleep(0.05)
        port = int(port_file.read_text())
        statuses = []
        for attempt in (1, 2):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
            try:
                conn.request("POST", "/message", json.dumps(hb), {"content-type": "application/json"})
                statuses.append(("ok", json.loads(conn.getresponse().read())["outcome"].get("noop")))
            except (socket.timeout, OSError):
                statuses.append(("timeout", None))
            finally:
                conn.close()
        (w.layout.root / "http_stop").write_text("1")
        server.communicate(timeout=60)
        log = [json.loads(line) for line in (w.layout.root / "http_server.jsonl").read_text().splitlines()]
        rep.eq("HTTP: 첫 요청은 응답이 늦어 클라이언트가 시간 초과, 같은 봉투 재시도는 noop(envelope_duplicate_delivery)로 응답",
               [("timeout", None), ("ok", "envelope_duplicate_delivery")], statuses)
        rep.eq("서버 기록: 첫 처리는 수락(heartbeat), 둘째는 noop, 상태 저장소의 inbox_seen에는 키 하나만 늘었다",
               (["heartbeat", "envelope_duplicate_delivery"], 1),
               ([e["res"]["outcome"].get("noop") for e in log],
                len([k for k in w.task(BASIC)["inbox_seen"] if "R12-HTTP-HB" in k])))
    rep.not_proved("HTTP는 같은 호스트의 로컬 서버다. 네트워크 지연·재정렬·부분 전송은 확인하지 못했다")


# =============================================================== R13
def relase_checks(rep, label, w, task, old_instr, old_hb_msg, expect_reason, g0=1):
    t = w.task(task)
    new_instr = w.latest_instruction(task)
    gen_now = t["lease_generation"]
    rep.eq(f"[{label}] 상태 저장소의 lease_generation이 바뀐다({g0}→{g0 + 1})와 지시 봉투 envelope_id가 다르다",
           (g0 + 1, True), (gen_now, new_instr["envelope_id"] != old_instr["envelope_id"]))
    h = w.start_builder(new_instr, [{"op": "first_heartbeat"}, {"op": "sleep", "s": 3600}])
    w.wait_log(h, "first_heartbeat")
    m = w.mark()
    out = finished(drain_ok(w))
    rep.eq(f"[{label}] 새 세대의 첫 봉투(first_heartbeat)는 수락된다", True, bool(out and out[0].get("accepted")))
    rep.eq(f"[{label}] 발급 사유", expect_reason,
           [r["args"]["reason"] for r in w.journal() if r["kind"] == "side_effect_record" and r["id"] == "issue_lease"][-1])
    before = snapshot_task(w, task)
    w.queue_file(old_hb_msg, name=f"{time.time_ns()}-oldgen.json")
    m = w.mark()
    finished(drain_ok(w))
    rep.eq(f"[{label}] 이전 세대 키의 늦은 봉투는 late_envelope_rejected(R-11)이고 상태 불변", ([("late_envelope_rejected", "R-11")], before),
           (noops(w.journal()[m:]), snapshot_task(w, task)))
    keys = list(w.task(task)["inbox_seen"])
    gens = sorted({int(k.split("|")[1]) for k in keys})
    rep.eq(f"[{label}] 멱등 키(task|세대|종류|envelope_id)에 새 세대 키가 생기고 그 이전 세대의 키는 남지 않는다", [g0, g0 + 1], gens)
    return h


def first_hb_msg(w):
    return next(m for _n, m in w.done_messages() if m["msg_type"] == "first_heartbeat")


def r13(rep, cx):
    # 1. test failure -> re-lease on the same builder (building -> building)
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": go}, {"op": "result", "status": "failed_tests"},
                                                  {"op": "sleep", "s": 3600}])
        old_hb = first_hb_msg(w)
        open(go, "w").close()
        w.wait_log(a, "result")
        finished(drain_ok(w))
        relase_checks(rep, "시험 실패 뒤 재임대", w, BASIC, instr, old_hb, "retry_failed_tests")

    # 2. returned -> owner_resolved -> queued -> leased
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": go}, {"op": "result", "status": "verdict_requested"},
                                                  {"op": "sleep", "s": 3600}])
        old_hb = first_hb_msg(w)
        open(go, "w").close()
        w.wait_log(a, "result")
        finished(drain_ok(w))
        w.event("owner_resolved", BASIC, {"resolution_ref": "RES-R13"}).result
        w.grant(BASIC).result
        relase_checks(rep, "반송 뒤 재개", w, BASIC, instr, old_hb, "from_queue")

    # 3. handoff (the stand-in asks for a switch)
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(HANDOFF, [{"op": "write", "path": "w.txt", "content": "w\n"}, {"op": "wait_file", "path": go},
                                                    {"op": "switch_signal"}, {"op": "sleep", "s": 3600}])
        old_hb = first_hb_msg(w)
        open(go, "w").close()
        w.wait_log(a, "switch_signal")
        finished(drain_ok(w))
        relase_checks(rep, "인계", w, HANDOFF, instr, old_hb, "handoff")

    # 4. no builder available -> paused_no_builder -> a builder comes back
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(HANDOFF, [{"op": "write", "path": "w.txt", "content": "w\n"}, {"op": "wait_file", "path": go},
                                                    {"op": "switch_signal"}, {"op": "sleep", "s": 3600}])
        old_hb = first_hb_msg(w)
        (w.layout.root / "unavailable.json").write_text(json.dumps(["standin-builder-2"]))
        open(go, "w").close()
        w.wait_log(a, "switch_signal")
        finished(drain_ok(w))
        paused = w.state(HANDOFF)
        (w.layout.root / "unavailable.json").write_text("[]")
        w.event("builder_available", HANDOFF, {"builder": "standin-builder-2"}).result
        rep.eq("[일시중단 뒤 복귀] 다음 빌더가 없으면 paused_no_builder, 돌아오면 leased", ("paused_no_builder", "leased"),
               (paused, w.state(HANDOFF)))
        relase_checks(rep, "일시중단 뒤 복귀", w, HANDOFF, instr, old_hb, "resume_paused")
    rep.not_proved("재임대 경로는 모의 과제의 상태 기계 경로다. CI 실패 뒤 재임대(ci_failed→building)는 관측 계층 입력이 필요해 이 도구에서 시험하지 않았다(R8과 같은 관측 입력 경로)")


# =============================================================== R17
def r17(rep, cx):
    with cx.world() as w:
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": str(w.layout.root / "go")},
                                                  {"op": "heartbeat"}, {"op": "heartbeat"}, {"op": "sleep", "s": 3600}])
        open(w.layout.root / "go", "w").close()
        w.wait_log(a, "heartbeat", count=2)
        files = sorted(w.layout.daemon_inbox.glob("*.json"))
        hb1, hb2 = (json.loads(p.read_text()) for p in files[:2])
        rep.ok("실제 어댑터(스크립트 프로세스)가 보낸 하트비트 둘은 envelope_id가 다르다", hb1["envelope"]["envelope_id"] != hb2["envelope"]["envelope_id"])
        w.advance(60)
        hb3 = dict(hb2, envelope=dict(hb2["envelope"], envelope_id="R17-HB3", at=w.clock.now()))
        for p in files[2:]:
            pass
        w.queue_file(hb2, name=f"{time.time_ns()}-retx.json")  # same envelope_id as hb2, delivered again
        bad = json.loads(json.dumps(hb2))
        del bad["envelope"]["envelope_id"]
        w.queue_file(bad, name=f"{time.time_ns()}-noid.json")
        m = w.mark()
        out = finished(drain_ok(w))
        js = w.journal()[m:]
        rep.eq("같은 세대·다른 envelope_id 둘은 각각 처리, 같은 envelope_id 재전송은 noop, envelope_id 없음은 거부(R-13)",
               [("heartbeat", None), ("heartbeat", None), ("envelope_duplicate_delivery", None), ("envelope_rejected_invalid", "R-13")],
               noops(js))
        rep.eq("전이 0건, inbox_seen에는 first_heartbeat와 하트비트 둘, 세 키", (0, 3), (len(tr(js)), len(w.task(BASIC)["inbox_seen"])))

    # signal envelopes while a handoff is running
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(HANDOFF, [{"op": "write", "path": "w.txt", "content": "w\n"}, {"op": "wait_file", "path": go},
                                                    {"op": "switch_signal"}, {"op": "switch_signal"}, {"op": "sleep", "s": 3600}])
        open(go, "w").close()
        w.wait_log(a, "switch_signal", count=2)
        names = sorted(p.name for p in w.layout.daemon_inbox.glob("*.json"))
        second = w.layout.daemon_inbox / names[1]
        held = w.layout.root / "held_signal.json"
        second.rename(held)  # the first signal starts the handoff, the daemon dies when it begins to isolate
        res = w.drain(die_at=["handoff:isolate:start"])
        rep.ok("첫 signal이 인계를 시작하고 데몬이 isolate 시작 지점에서 죽었다", res.killed and w.state(HANDOFF) == "handoff", w.state(HANDOFF))
        s2 = json.loads(held.read_text())
        w.queue_file(s2, name=f"{time.time_ns()}-s2.json")
        w.queue_file(s2, name=f"{time.time_ns()}-s2dup.json")
        s3 = json.loads(held.read_text())
        del s3["envelope"]["envelope_id"]
        w.queue_file(s3, name=f"{time.time_ns()}-s3noid.json")
        m = w.mark()
        out = finished(drain_ok(w))
        js = w.journal()[m:]
        rep.eq("죽은 데몬이 처리 중이던 첫 signal 파일의 재전달은 noop, 인계 중 같은 세대의 둘째 signal(다른 envelope_id)은 switch_signal_during_handoff(noop), 같은 envelope_id 재전송은 noop, envelope_id 없음은 R-13",
               [("envelope_duplicate_delivery", None), ("switch_signal_during_handoff", None), ("envelope_duplicate_delivery", None), ("envelope_rejected_invalid", "R-13")], noops(js))
        rep.eq("전이 0건, 상태 handoff, 세대 1", ([], "handoff", 1), (tr(js), w.state(HANDOFF), w.task(HANDOFF)["lease_generation"]))
        w.restart().result
        rep.eq("재시작으로 인계가 끝나고 첫 signal은 building→handoff 한 번뿐", (1, "leased", 2),
               (tr(w.journal()).count(("building", "handoff", "switch_signal")), w.state(HANDOFF), w.task(HANDOFF)["lease_generation"]))


# =============================================================== R8
def r8(rep, cx):
    H1 = "1" * 40
    with cx.world() as w:
        go = str(w.layout.root / "go")
        w.init_task(GATED).result
        rep.eq("merge=[D-MOCK-X] 미기록, start=[] → 시작은 막히지 않는다", "queued", w.state(GATED))
        w.grant(GATED).result
        instr = w.latest_instruction(GATED)
        touched = "tools/mock/gated/x.py"
        h = w.start_builder(instr, [{"op": "first_heartbeat"}, {"op": "result", "status": "pr_opened",
                                                                   "fields": {"pr_number": 9, "head_sha": H1, "touched_paths": [touched]}},
                                    {"op": "sleep", "s": 3600}])
        w.wait_log(h, "result")
        m = w.mark()
        drain_ok(w)
        w.observe(GATED, "ci", {"conclusion": "success", "sha": H1}).result
        pr = w.snap()["pr"][GATED]
        w.observe(GATED, "review_result", {"verdict": "approved", "sha": pr["head_sha"], "reviewer": pr["reviewer"],
                                           "reviewer_family": w.ports().builders.family(pr["reviewer"])}).result
        pr = w.snap()["pr"][GATED]
        rep.eq("작성·리뷰까지 진행 → merge_wait(decision_pending)", ("merge_wait", "decision_pending"),
               (w.state(GATED), pr["merge_wait_reason"]))
        m = w.mark()
        w.observe(None, "decision_record", {"decision_id": "D-MOCK-X", "recorded_at": w.clock.now(), "recorded_by": "mock-owner",
                                            "source_ref": "mock://decision/x"}).result
        rep.eq("결정 기록 뒤 decision_recorded → merge_wait(ready)", ([("merge_wait", "merge_wait", "decision_recorded")], "ready"),
               (tr(w.journal()[m:]), w.snap()["pr"][GATED]["merge_wait_reason"]))
        rep.eq("모든 단계에서 병합 호출 0건(원격에 기록된 병합 쓰기·task 브랜치 밖 쓰기 없음)", ([], 0),
               ([e for e in w.push_log() if e["event"] == "applied" and not e["ref"].startswith("refs/heads/task/")], len(accepted_pushes(w))))
    with cx.world() as w:
        go = str(w.layout.root / "go")
        instr, a, _ = w.lease_to_building(BASIC, [{"op": "wait_file", "path": go}, {"op": "result", "status": "verdict_requested"},
                                                  {"op": "sleep", "s": 3600}])
        open(go, "w").close()
        w.wait_log(a, "result")
        finished(drain_ok(w))
        rep.eq("verdict_requested → returned(R-02)", ("returned", ["R-02"]), (w.state(BASIC), rets(w.journal())))
        m = w.mark()
        w.event("owner_resolved", BASIC).result
        rep.eq("resolution_ref 없는 해소 기록은 받지 않는다", ([], "returned"), (tr(w.journal()[m:]), w.state(BASIC)))
        w.event("owner_resolved", BASIC, {"resolution_ref": "RES-20"}).result
        rep.eq("owner_resolved → queued(attempt+1)", ("queued", 2), (w.state(BASIC), w.task(BASIC)["task_state"]["attempt"]))
        w.grant(BASIC).result
        rep.eq("다음 임대는 새 토큰·새 브랜치(attempt 2)", (2, "task/T-MOCK-BASIC-a2"),
               (w.lease(BASIC)["fencing_token"], w.lease(BASIC)["branch"]))
    rep.not_proved("CI·리뷰·결정 기록 입력은 시험 도구가 관측 계층에 직접 넣은 것이다(실제 CI·리뷰 서비스 없음). 이 시험이 보는 것은 같은 규칙이 실제 상태 저장소·프로세스에서도 같은 전이를 낸다는 것이다")
