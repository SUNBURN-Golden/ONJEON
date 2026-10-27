"""Scenarios M1-M25, M27, M31, M32 (with M10a·M10b, M18a·M18b) of T-OP-00: the life cycle from the queue to the
pull request, review, audit, landing and the periodic audit, and the stop and permission rules.

Each scenario builds a fresh bench, drives the shared core (builder envelopes through the mock builder, observations
through core.observe) and compares expected values written here as literals with the journal and the stores.
"""
import copy
import threading

from . import static_checks
from .core import DaemonCore
from .core.observation import authors_families
from .core.ports import PushFailed
from .mock_env import MockEnv
from .bench import (BASIC, HANDOFF, OTHER, crash_after_issue, failed_guard_ids, handoff_bench, jr, mark, noops, rets, se,
                    sent_ids, switch, tr)

H1, H2, H3 = "1" * 40, "2" * 40, "3" * 40
SUCC, GATED, SCHEMA, DOCS = "T-MOCK-SUCC", "T-MOCK-GATED", "T-MOCK-SCHEMA", "T-MOCK-DOCS"
CANON, CANON_FREE, NOGATES = "T-MOCK-CANON", "T-MOCK-CANON-FREE", "T-MOCK-NOGATES"
TO_MERGE_WAIT = [("blocked", "queued", "prereqs_satisfied"), ("queued", "leased", "lease_granted"),
                 ("leased", "building", "first_heartbeat"), ("building", "pr_open", "result_pr_opened"),
                 ("pr_open", "review_pending", "ci_passed"), ("review_pending", "review_in_progress", "reviewer_assigned"),
                 ("review_in_progress", "review_approved", "review_approved"), ("review_approved", "merge_wait", "audit_not_required")]


# ---------------------------------------------------------------- helpers
def sample_path(env, t, name="src/x.py"):
    return env.ports.catalog.task(t)["allowed_paths"][0].replace("**", name)


def pr_of(env, t):
    return env.snap().get("pr", {}).get(t)


def open_pr(env, t, touched=None, head=H1, pr_number=7):
    env.bring_to_building(t)
    return env.builder_for(t).send_result(env.instr(t), "pr_opened", pr_number=pr_number, head_sha=head,
                                          touched_paths=touched or [sample_path(env, t)])


def review(env, t, verdict="approved", sha=None):
    pr = pr_of(env, t)
    name = pr["reviewer"]
    return env.observe(t, "review_result", verdict=verdict, sha=sha or pr["head_sha"], reviewer=name,
                       reviewer_family=env.ports.builders.family(name))


def approve_to_wait(env, t, touched=None, head=H1):
    open_pr(env, t, touched, head)
    env.observe(t, "ci", conclusion="success", sha=head)
    review(env, t)


def land(env, t, head=None, base=None, merge_commit=None, check="mock://ci/base"):
    pr = pr_of(env, t)
    return env.observe(t, "landing", head_sha_at_merge=head or pr["approved_head_sha"] or pr["head_sha"],
                       base_sha_at_merge=base or pr["approved_base_sha"] or pr["base_sha"],
                       merge_commit_sha=merge_commit or ("c" * 39 + t[-1]), integration_check=check)


def clone(env, src, new_id):
    task = copy.deepcopy(env.ports.catalog.task(src))
    task["task_id"] = new_id
    root = task["allowed_paths"][0].split("/")[0]
    task["allowed_paths"] = [f"{root}/mock/{new_id.lower()}/**"]
    task["conflict_paths"] = list(task["allowed_paths"])
    env.ports.catalog.add(task)
    return new_id


def land_full(env, t, merge_commit):
    approve_to_wait(env, t)
    return land(env, t, merge_commit=merge_commit)


def counter(env):
    return env.snap().get("audit", {"merged_impl_counter": 0, "batches": []})


# =============================================================== M1
def m1(rep, R, T):
    env = MockEnv(R, T)
    m = mark(env)
    approve_to_wait(env, BASIC)
    js = jr(env, m)
    pr = pr_of(env, BASIC)
    rep.eq("정상 흐름 전이 열: queued→…→merge_wait", TO_MERGE_WAIT, tr(js))
    rep.eq("merge_wait의 사유 ready, 승인 SHA = PR head", ("ready", H1), (pr["merge_wait_reason"], pr["approved_head_sha"]))
    rep.eq("리뷰어는 작성 계열 밖(작성 mock-family-a, 리뷰 mock-family-b)", (["mock-family-a"], "mock-family-b"),
           (authors_families(env.core, env.snap(), BASIC), env.ports.builders.family(pr["reviewer"])))
    rep.eq("병합 API 호출 0건: 원격 쓰기에 병합 없음, 병합·자동 병합 함수 없음(정적)", ([], []),
           ([w for w in env.ports.remote.writes if "merge" in w[0]], static_checks.no_merge_api()))
    rep.eq("데몬은 merge_wait에서 멈춘다(사람의 병합 관측 전에는 merged 없음)", "merge_wait", env.state(BASIC))


# =============================================================== M2
def m2(rep, R, T):
    env, path = handoff_bench(R, T)
    old = env.lease(HANDOFF)
    b = env.builder_for(HANDOFF)
    env.clock.advance(1)
    m = mark(env)
    out = env.submit(HANDOFF, "switch_signal", b.signal_envelope(env.instr(HANDOFF), status="usage_limit",
                                                                   source="provider_http_response", http_status=429))
    js = jr(env, m)
    rep.eq("전환 신호 봉투는 수락된다", True, out["accepted"])
    t = env.task(HANDOFF)
    hr = t["handoff_record"]
    rep.eq("모의 제공자 429(model_provider): building→handoff→leased(2순위)",
           [("building", "handoff", "switch_signal"), ("handoff", "handoff", "preserve_commit_ok"),
            ("handoff", "handoff", "preserve_push_ok"), ("handoff", "leased", "preserved")], tr(js))
    rep.eq("다음 빌더는 2순위, 새 토큰(세대 2), 옛 임대 handed_off", ("mock-builder-2", 2, 2),
           (t["lease_record"]["builder"], t["lease_record"]["fencing_token"], t["lease_generation"]))
    rep.eq("WIP SHA가 원격 ref에 있고 인계 기록(record_handoff)이 남는다", (env.ports.git.remote[old["branch"]], True),
           (hr["wip_commit_sha"], "record_handoff" in se(js)))
    env.run_builders()
    rep.eq("authors_families에 새 계열이 더해진다", ["mock-family-a", "mock-family-b"],
           authors_families(env.core, env.snap(), HANDOFF))
    rep.eq("새 빌더의 첫 하트비트로 building", "building", env.state(HANDOFF))


# =============================================================== M3
def m3(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    builders, gens, m = [], [], mark(env)
    for _ in range(2):
        env.builder_for(BASIC).send_result(env.instr(BASIC), "failed_tests")
        env.run_builders()
        builders.append(env.lease(BASIC)["builder"])
        gens.append(env.lease(BASIC)["fencing_token"])
    rep.eq("시험 실패는 전환이 아니다: 같은 빌더 재임대, 매번 새 토큰", (["mock-builder-1"] * 2, [2, 3], 0),
           (builders, gens, sum(1 for x in tr(jr(env, m)) if x[1] == "handoff")))
    m = mark(env)
    env.builder_for(BASIC).send_result(env.instr(BASIC), "failed_tests")
    rep.eq("3회째 returned(R-06), 임대 끝", ([("building", "returned", "result_failed_tests")], ["R-06"], "returned"),
           (tr(jr(env, m)), rets(jr(env, m)), env.lease(BASIC)["status"]))


# =============================================================== M4
def m4(rep, R, T):
    env = MockEnv(R, T)
    env.ports.reviewers.unavailable.add("mock-builder-2")
    open_pr(env, BASIC)
    m = mark(env)
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    rep.eq("작성 계열 밖 후보가 없으면 merge_wait(reviewer_unavailable). 작성 계열 후보는 가용이어도 제외",
           ([("pr_open", "review_pending", "ci_passed"), ("review_pending", "merge_wait", "reviewer_unavailable")], "reviewer_unavailable", True),
           (tr(jr(env, m)), pr_of(env, BASIC)["merge_wait_reason"],
            {"name": "mock-builder-1", "family": "mock-family-a", "available": True} in env.ports.reviewers.candidates()))
    m = mark(env)
    env.observe(BASIC, "reviewers_changed")
    rep.eq("가용 리뷰어가 아직 없으면 그대로", [], tr(jr(env, m)))
    env.ports.reviewers.unavailable.clear()
    m = mark(env)
    env.observe(BASIC, "reviewers_changed")
    rep.eq("다른 계열 리뷰어가 돌아오면 reviewer_available → review_pending → 배정",
           [("merge_wait", "review_pending", "reviewer_available"), ("review_pending", "review_in_progress", "reviewer_assigned")],
           tr(jr(env, m)))
    review(env, BASIC)
    rep.eq("리뷰 뒤 merge_wait(ready)", ("merge_wait", "ready"), (env.state(BASIC), pr_of(env, BASIC)["merge_wait_reason"]))

    # self review: the family comes from the reviewer registry, never from the payload; a result that cannot be
    # attributed is rejected (fail closed) and leaves no review record
    def rejected(js):
        return [(r["what"], r.get("reason")) for r in js if r["kind"] == "diagnostic_record"
                and r["what"] in ("self_review_rejected", "review_result_rejected")]

    env = MockEnv(R, T)
    open_pr(env, BASIC)
    cases = [
        ("작성자 본인(mock-builder-1, 작성 계열) → self_review_rejected",
         dict(reviewer="mock-builder-1", reviewer_family="mock-family-a"), [("self_review_rejected", None)]),
        ("작성자가 다른 계열을 주장해도 레지스트리의 계열로 판정 → 거부(reviewer_family_mismatch)",
         dict(reviewer="mock-builder-1", reviewer_family="mock-family-b"), [("review_result_rejected", "reviewer_family_mismatch")]),
        ("reviewer_family 없음 → 거부(reviewer_family_missing)",
         dict(reviewer="mock-builder-1"), [("review_result_rejected", "reviewer_family_missing")]),
        ("reviewer_family가 빈 값 → 거부(reviewer_family_missing)",
         dict(reviewer="mock-builder-2", reviewer_family=""), [("review_result_rejected", "reviewer_family_missing")]),
        ("등록되지 않은 리뷰어 → 거부(reviewer_not_registered)",
         dict(reviewer="mock-unknown", reviewer_family="mock-family-b"), [("review_result_rejected", "reviewer_not_registered")]),
    ]
    for label, extra, expect in cases:
        m = mark(env)
        env.observe(BASIC, "review_result", verdict="approved", sha=H1, **extra)
        rep.eq(f"[리뷰어 배정 전] {label}: 전이·보류·리뷰 기록 없음",
               (expect, [], "pr_open", 0, {}), (rejected(jr(env, m)), tr(jr(env, m)), env.state(BASIC),
                                               len(pr_of(env, BASIC)["review_results"]), env.snap().get("held", {})))
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    m = mark(env)
    env.observe(BASIC, "review_result", verdict="approved", sha=H1, reviewer="mock-builder-1", reviewer_family="mock-family-b")
    rep.eq("[리뷰어 배정 뒤] 배정된 리뷰어(mock-builder-2)가 아닌 보고는 거부(reviewer_not_assigned)",
           ([("review_result_rejected", "reviewer_not_assigned")], [], "review_in_progress"),
           (rejected(jr(env, m)), tr(jr(env, m)), env.state(BASIC)))
    m = mark(env)
    review(env, BASIC)
    rep.eq("배정된 리뷰어의 결과는 수락되어 merge_wait(ready)", ([], "merge_wait", "ready"),
           (rejected(jr(env, m)), env.state(BASIC), pr_of(env, BASIC)["merge_wait_reason"]))


# =============================================================== M5
def m5(rep, R, T):
    def head_change(env, t, new):
        m = mark(env)
        env.observe(t, "head_sha", sha=new)
        return jr(env, m)

    # merge_wait(ready)
    env = MockEnv(R, T)
    approve_to_wait(env, BASIC)
    js = head_change(env, BASIC, H2)
    pr = pr_of(env, BASIC)
    rep.eq("[merge_wait] head 변경 → pr_open, 리뷰 결과 무효(invalidated_at, 삭제 아님), R-04 기록, 승인 SHA 지움",
           ([("merge_wait", "pr_open", "head_sha_changed")], ["R-04"], 1, True, None),
           (tr(js), rets(js), len(pr["review_results"]), pr["review_results"][0]["invalidated_at"] is not None, pr["approved_head_sha"]))
    m = mark(env)
    env.observe(BASIC, "ci", conclusion="success", sha=H2)
    review(env, BASIC)
    rep.eq("[merge_wait] CI 재검사 뒤 변경분 재리뷰 → merge_wait(ready), 승인 SHA = 새 head",
           ([("pr_open", "review_pending", "ci_passed"), ("review_pending", "review_in_progress", "reviewer_assigned"),
             ("review_in_progress", "review_approved", "review_approved"), ("review_approved", "merge_wait", "audit_not_required")], H2),
           (tr(jr(env, m)), pr_of(env, BASIC)["approved_head_sha"]))
    m = mark(env)
    review(env, BASIC, sha=H1)
    rep.eq("[merge_wait] 옛 SHA의 리뷰 결과는 상태를 바꾸지 않는다", ([], "merge_wait"), (tr(jr(env, m)), env.state(BASIC)))

    # audit_pending (an immediate-audit task)
    env = MockEnv(R, T)
    approve_to_wait(env, SCHEMA, touched=["packages/schemas/x.json"])
    js = head_change(env, SCHEMA, H2)
    pr = pr_of(env, SCHEMA)
    rep.eq("[audit_pending] head 변경 → pr_open, 리뷰 결과 무효, R-04",
           ([("audit_pending", "pr_open", "head_sha_changed")], ["R-04"], True),
           (tr(js), rets(js), all(r["invalidated_at"] is not None for r in pr["review_results"])))
    m = mark(env)
    env.observe(SCHEMA, "audit_result", verdict="pass", sha=H1)
    rep.eq("[audit_pending] 무효가 된 SHA의 감리 결과는 적용되지 않는다(R-04 기록)", ([], ["R-04"], "pr_open"),
           (tr(jr(env, m)), rets(jr(env, m)), env.state(SCHEMA)))

    # review_in_progress and changes_requested
    env = MockEnv(R, T)
    open_pr(env, BASIC)
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    rep.eq("[review_in_progress] head 변경 → pr_open", [("review_in_progress", "pr_open", "head_sha_changed")], tr(head_change(env, BASIC, H2)))
    env.observe(BASIC, "ci", conclusion="success", sha=H2)
    review(env, BASIC, verdict="changes_requested")
    js = head_change(env, BASIC, H3)
    rep.eq("[changes_requested] head 변경 → pr_open, 지적 결과도 무효(R-04)",
           ([("changes_requested", "pr_open", "head_sha_changed")], ["R-04"]), (tr(js), rets(js)))

    # review_approved: in this core the audit decision follows in the same operation, so the row is driven directly
    env = MockEnv(R, T)
    open_pr(env, BASIC)
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    env.event("review_approved", BASIC)
    js = head_change(env, BASIC, H2)
    rep.eq("[review_approved] 전이표 행을 직접 적용한 상태에서 head 변경 → pr_open(목적지는 pr_open 하나). "
           "직접 적용이라 무효로 만들 리뷰 결과가 없으므로 R-04도 없다(R-04는 위 다섯 상태에서 검사)",
           ([("review_approved", "pr_open", "head_sha_changed")], [], None),
           (tr(js), rets(js), pr_of(env, BASIC)["approved_head_sha"]))
    dests = sorted({x["to"] for x in env.raw["transitions"] if x["event"] == "head_sha_changed"})
    rep.eq("head_sha_changed 행의 목적지는 pr_open 하나(데이터)", ["pr_open"], dests)


# =============================================================== M6
def m6(rep, R, T):
    env = MockEnv(R, T)
    open_pr(env, SCHEMA, touched=["packages/schemas/x.json"])
    env.observe(SCHEMA, "ci", conclusion="success", sha=H1)
    m = mark(env)
    review(env, SCHEMA)
    rep.eq("즉시 감리 경로(packages/schemas/**) → review_approved→audit_pending",
           [("review_in_progress", "review_approved", "review_approved"), ("review_approved", "audit_pending", "audit_required")],
           tr(jr(env, m)))
    m = mark(env)
    env.observe(SCHEMA, "audit_result", verdict="pass", sha=H1)
    rep.eq("감리 통과 → merge_wait(ready)", ([("audit_pending", "merge_wait", "audit_pass")], "ready"),
           (tr(jr(env, m)), pr_of(env, SCHEMA)["merge_wait_reason"]))
    env = MockEnv(R, T)
    open_pr(env, SCHEMA, touched=["packages/schemas/x.json"])
    env.observe(SCHEMA, "ci", conclusion="success", sha=H1)
    env.observe(SCHEMA, "auditor_status", available=False)
    m = mark(env)
    review(env, SCHEMA)
    rep.eq("감리 담당이 없으면 merge_wait(auditor_unavailable)", ("auditor_unavailable", ("audit_pending", "merge_wait", "auditor_unavailable")),
           (pr_of(env, SCHEMA)["merge_wait_reason"], tr(jr(env, m))[-1]))
    m = mark(env)
    env.observe(SCHEMA, "auditor_status", available=True)
    env.observe(SCHEMA, "audit_result", verdict="pass", sha=H1)
    rep.eq("감리 담당 복귀 → audit_pending → 통과 → merge_wait(ready)",
           ([("merge_wait", "audit_pending", "auditor_available"), ("audit_pending", "merge_wait", "audit_pass")], "ready"),
           (tr(jr(env, m)), pr_of(env, SCHEMA)["merge_wait_reason"]))
    env = MockEnv(R, T)
    approve_to_wait(env, BASIC)
    rep.eq("즉시 감리 경로가 아닌 PR은 audit_not_required", ("review_approved", "merge_wait", "audit_not_required"), tr(env.journal())[-1])


# =============================================================== M7 / M24 shared
def _land_series(env, n_impl, docs_at=()):
    """n_impl implementation PRs; a docs-only PR is landed before the k-th implementation PR for k in docs_at."""
    impl, docs, closed_at = [], [], None
    for k in range(1, n_impl + 1):
        if k in docs_at:
            d = clone(env, DOCS, f"T-MOCK-DOCS-{k:02d}")
            land_full(env, d, "d" * 38 + f"{k:02d}")
            docs.append(d)
        t = clone(env, BASIC, f"T-MOCK-IMPL-{k:02d}")
        land_full(env, t, "e" * 38 + f"{k:02d}")
        impl.append(t)
        batches = counter(env)["batches"]
        if closed_at is None and batches and batches[0]["closed"]:
            closed_at = k
    return impl, docs, closed_at


def m7(rep, R, T):
    env = MockEnv(R, T)
    impl, docs, closed_at = _land_series(env, 10, docs_at=(3, 7))
    a = counter(env)
    rep.eq("구현 PR 10개 + docs-only 2개: 카운터는 구현 PR만 센다", 10, a["merged_impl_counter"])
    rep.eq("10번째 구현 PR에서 묶음 하나가 닫힌다(audit_queued 묶음)", (10, [("B1", 10, True)]),
           (closed_at, [(b["batch_id"], len(b["tasks"]), b["closed"]) for b in a["batches"]]))
    rep.eq("구현 PR은 모두 audit_queued, docs-only는 done", (["audit_queued"] * 10, ["done", "done"]),
           ([env.state(t) for t in impl], [env.state(t) for t in docs]))


def m24(rep, R, T):
    env = MockEnv(R, T)
    impl, _docs, closed_at = _land_series(env, 11)
    a = counter(env)
    rep.eq("10번째에서 묶음 B1이 닫히고 11번째는 새 묶음 B2(묶음 안 카운터 1)",
           ([("B1", 10, True), ("B2", 1, False)], 11, 1),
           ([(b["batch_id"], len(b["tasks"]), b["closed"]) for b in a["batches"]], a["merged_impl_counter"], a["merged_impl_counter"] % 10))
    rep.eq("B1 감리 전에도 11번째 PR은 막히지 않고 audit_queued(B2)", ("audit_queued", True),
           (env.state(impl[10]), impl[10] in a["batches"][1]["tasks"]))
    m = mark(env)
    env.observe(None, "batch_audit_result", batch_id="B1", verdict="pass")
    rep.eq("B1 감리 통과: B1의 10개만 done, 11번째는 B2에서 audit_queued로 남는다",
           (["done"] * 10, "audit_queued", 10), ([env.state(t) for t in impl[:10]], env.state(impl[10]),
                                                 tr(jr(env, m)).count(("audit_queued", "done", "batch_audit_pass"))))
    m = mark(env)
    env.observe(None, "batch_audit_result", batch_id="B2", verdict="pass")
    rep.eq("닫히지 않은 묶음 B2에는 감리 결과를 적용하지 않는다", ([], "audit_queued"), (tr(jr(env, m)), env.state(impl[10])))
    rep.eq("묶음은 10번째 구현 PR에서 닫혔다", 10, closed_at)


# =============================================================== M8 / M9
def m8(rep, R, T):
    env = MockEnv(R, T)
    m = mark(env)
    open_pr(env, BASIC, touched=["tools/mock/basic/ok.py", "docs/BLUEPRINT.md"])
    js = jr(env, m)
    rep.eq("touched_paths에 허용 경로 밖(docs/BLUEPRINT.md) → result_out_of_scope → returned(R-01)",
           (("building", "returned", "result_out_of_scope"), ["R-01"], "returned"), (tr(js)[-1], rets(js), env.lease(BASIC)["status"]))
    rep.eq("PR 기록을 만들지 않는다", None, pr_of(env, BASIC))
    # paths are normalized before they are compared: '..' segments, absolute paths and globs never count as inside
    for label, bad in (("'..'로 허용 경로를 빠져나가는 경로", "tools/mock/basic/../../../docs/BLUEPRINT.md"),
                       ("'..'로 허용 경로 안으로 돌아오는 경로도 거부", "tools/mock/basic/../basic/ok.py"),
                       ("절대 경로", "/workspace/onjeon-run/tools/mock/basic/ok.py"),
                       ("역슬래시 경로", "tools\\mock\\basic\\ok.py"),
                       ("글롭 문자가 든 경로", "tools/mock/basic/*"),
                       ("빈 경로", "")):
        env = MockEnv(R, T)
        m = mark(env)
        open_pr(env, BASIC, touched=["tools/mock/basic/ok.py", bad])
        rep.eq(f"{label}({bad!r}) → result_out_of_scope → returned(R-01), PR 기록 없음",
               (("building", "returned", "result_out_of_scope"), ["R-01"], None), (tr(jr(env, m))[-1], rets(jr(env, m)), pr_of(env, BASIC)))
    env = MockEnv(R, T)
    m = mark(env)
    open_pr(env, BASIC, touched=["tools/mock/basic/./sub//ok.py"])
    rep.eq("'.' 조각과 겹친 슬래시는 정규화되어 허용 경로 안이면 통과, PR 기록은 정규형",
           ("pr_open", ["tools/mock/basic/sub/ok.py"]), (env.state(BASIC), pr_of(env, BASIC)["changed_paths"]))


def m9(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    m = mark(env)
    env.builder_for(BASIC).send_result(env.instr(BASIC), "verdict_requested", verdict_question="mock?")
    rep.eq("verdict_requested → returned(R-02), 임대 끝", ([("building", "returned", "result_verdict_requested")], ["R-02"], "returned"),
           (tr(jr(env, m)), rets(jr(env, m)), env.lease(BASIC)["status"]))


# =============================================================== M10 / M10a / M10b
def m10(rep, R, T):
    env = MockEnv(R, T)
    env.start_task(GATED)
    rep.eq("merge=[D-MOCK-X] 미기록, start=[] → 시작은 막히지 않는다(start만 본다)", ("queued", []),
           (env.state(GATED), env.task(GATED)["task_state"]["decisions_recorded"]))
    m = mark(env)
    env.grant(GATED)
    env.run_builders()
    env.builder_for(GATED).send_result(env.instr(GATED), "pr_opened", pr_number=9, head_sha=H1,
                                      touched_paths=[sample_path(env, GATED)])
    env.observe(GATED, "ci", conclusion="success", sha=H1)
    review(env, GATED)
    rep.eq("작성·리뷰까지 진행 → merge_wait(decision_pending)",
           (TO_MERGE_WAIT[1:-1] + [("review_approved", "merge_wait", "decision_pending")], "decision_pending"),
           (tr(jr(env, m)), pr_of(env, GATED)["merge_wait_reason"]))
    m = mark(env)
    env.observe(None, "decision_record", decision_id="D-MOCK-X", recorded_at=env.clock.now(), recorded_by="mock-owner",
                source_ref="mock://decision/x")
    rep.eq("결정 기록 뒤 decision_recorded → merge_wait(ready)", ([("merge_wait", "merge_wait", "decision_recorded")], "ready"),
           (tr(jr(env, m)), pr_of(env, GATED)["merge_wait_reason"]))
    land(env, GATED)
    rep.eq("그 뒤 병합 관측은 유효(merged 이후 상태)", True, env.state(GATED) in ("merged", "audit_queued", "done"))

    env = MockEnv(R, T)
    env.ports.catalog.tasks[GATED]["decision_gates"]["start"] = ["D-MOCK-S"]
    env.start_task(GATED)
    rep.eq("start=[D-MOCK-S] 미기록이면 blocked", "blocked", env.state(GATED))
    env.observe(None, "decision_record", decision_id="D-MOCK-S", recorded_at=env.clock.now(), recorded_by="mock-owner",
                source_ref="mock://decision/s")
    rep.eq("start 결정 기록 뒤 queued", "queued", env.state(GATED))


def _real_data_start(rep, R, T, task, label, local, real):
    env = MockEnv(R, T)
    m = mark(env)
    env.bring_to_building(task)
    instr = env.instr(task)
    rep.eq(f"[{label}] real_data 결정 미기록이어도 queued→leased→building", TO_MERGE_WAIT[:3], tr(jr(env, m)))
    rep.eq(f"[{label}] 지시 봉투 real_data_allowed=false", False, instr["real_data_allowed"])
    rep.eq(f"[{label}] 모의 빌더는 로컬·모의 단계만 실행하고 실데이터 단계는 건너뛴다", [(local, True), (real, False)],
           env.builder_for(task).steps[task])
    gate = env.ports.catalog.task(task)["decision_gates"]["real_data"][0]
    env.observe(None, "decision_record", decision_id=gate, recorded_at=env.clock.now(), recorded_by="mock-owner",
                source_ref="mock://decision/real")
    env.builder_for(task).send_result(env.instr(task), "failed_tests")
    env.run_builders()
    rep.eq(f"[{label}] 결정 기록 뒤의 새 임대에서는 real_data_allowed=true, 실데이터 단계도 실행", (True, [(local, True), (real, True)]),
           (env.instr(task)["real_data_allowed"], env.builder_for(task).steps[task]))


def m10a(rep, R, T):
    _real_data_start(rep, R, T, "T-MOCK-REVIEW", "D-02", "mock_provider_review", "real_provider_review")


def m10b(rep, R, T):
    _real_data_start(rep, R, T, "T-MOCK-ARCHIVE", "D-04", "local_object_store_write", "r2_write")


# =============================================================== M11
def m11(rep, R, T):
    # (a) the send intent is recorded, the process dies after sending and before marking it sent
    env = MockEnv(R, T)
    env.start_task(BASIC)
    env.ports.faults.arm("resend:after_send")
    env.crash(lambda: env.grant(BASIC))
    row = env.task(BASIC)["outbox"][0]
    intents = [r for r in env.journal() if r["kind"] == "intent_record" and r["action"] == "send_envelope"]
    rep.eq("[발송 의도만 기록] 중단 시점: outbox pending, 의도 기록 1, 결과 기록 0", ("pending", 1, 0),
           (row["status"], len(intents), len([r for r in env.journal() if r["kind"] == "result_record"])))
    env.restart()
    rep.eq("[발송 의도만 기록] 재시작: 같은 envelope_id로 다시 보내고 sent", ([row["envelope_id"]] * 2, "sent"),
           (sent_ids(env), env.task(BASIC)["outbox"][0]["status"]))
    out = env.run_builders()
    b = env.builders["mock-builder-1"]
    rep.eq("[발송 의도만 기록] 빌더는 한 번만 실행하고 두 번째 도착은 중복", (1, ["started", "duplicate"], "building"),
           (len(b.executed), [o[0] for o in out], env.state(BASIC)))

    # (b) the local commit was made but not recorded: the restart finds it by tree OID (WIP kept, no second commit)
    env, path = handoff_bench(R, T)
    env.clock.advance(1)
    env.ports.faults.arm("handoff:preserve:after_local_commit_unrecorded")
    env.crash(lambda: switch(env))
    env.restart()
    hr = env.task(HANDOFF)["handoff_record"]
    rep.eq("[로컬 커밋 기록 전 중단] 외부 상태(tree OID)로 복원: 커밋 1개, 원격 ref == WIP, 다음 임대",
           (1, hr["wip_commit_sha"], "leased"),
           (env.ports.git.commit_count, env.ports.git.remote["task/T-MOCK-HANDOFF-a1"], env.state(HANDOFF)))

    # (c) a lease record without its outbox cannot be restored: R-08
    env = MockEnv(R, T)
    env.start_task(BASIC)
    crash_after_issue(env, BASIC)
    env.store.tamper(lambda d: d["tasks"][BASIC].update(outbox=[]))
    m = mark(env)
    env.restart()
    rep.eq("[복원 불가] returned(R-08), 자동 재발급 없음", ([("leased", "returned", "state_corrupted")], ["R-08"], 1),
           (tr(jr(env, m)), rets(jr(env, m)), env.task(BASIC)["lease_generation"]))


# =============================================================== M12
def m12(rep, R, T):
    env = MockEnv(R, T)
    env.start_task(BASIC)
    a = env.core
    env.ports.faults.arm("lease_lock:acquired")
    env.crash(lambda: env.grant(BASIC))
    lock = env.snap()["lease_lock"][BASIC]
    rep.eq("데몬 A가 잠금을 잡고 중단: 잠금 holder = A의 instance id", a.instance_id, lock["holder"])
    b = DaemonCore(env.rules, env.ports)
    m = mark(env)
    b.handle_event({"event": "lease_granted", "task_id": BASIC, "payload": {"reason": "from_queue"}})
    rep.eq("데몬 B: 다른 인스턴스가 쥔 잠금 → lock_acquired 거짓, 임대 없음", (["lock_acquired"], 0, "queued"),
           (failed_guard_ids(jr(env, m)), env.task(BASIC)["lease_generation"], env.state(BASIC)))
    env.core = b
    env.core.handle_event({"event": "daemon_restart"})
    rep.eq("B 재시작: 다른 holder의 잠금을 지운다(lock.restart)", None, env.snap()["lease_lock"][BASIC]["holder"])
    env.grant(BASIC)
    rep.eq("그 뒤 B가 발급: 세대 1, 봉투 1", (1, 1), (env.task(BASIC)["lease_generation"], len(sent_ids(env))))

    env = MockEnv(R, T)
    env.start_task(BASIC)
    cores = [env.core, DaemonCore(env.rules, env.ports)]
    threads = [threading.Thread(target=lambda c=c: c.handle_event({"event": "lease_granted", "task_id": BASIC,
                                                                   "payload": {"reason": "from_queue"}})) for c in cores * 3]
    [x.start() for x in threads]
    [x.join() for x in threads]
    t = env.task(BASIC)
    rep.eq("두 인스턴스가 동시에 같은 과제 임대 시도: 세대 1, outbox 1행, 발송 1건, 같은 envelope_id",
           (1, 1, 1), (t["lease_generation"], len(t["outbox"]), len(sent_ids(env))))
    rep.eq("잠금은 모두 풀려 있다", None, env.snap()["lease_lock"][BASIC]["holder"])

    env = MockEnv(R, T)
    open_pr(env, BASIC, pr_number=7)
    env.observe(BASIC, "ci", conclusion="failure", sha=H1)
    env.grant(BASIC, "retry_ci")
    env.run_builders()
    env.builder_for(BASIC).send_result(env.instr(BASIC), "pr_opened", pr_number=8, head_sha=H2,
                                      touched_paths=[sample_path(env, BASIC)])
    rep.eq("같은 task_id의 열린 PR 재사용(pr_dedup): 번호 7 유지, head 갱신", (7, H2, "pr_open"),
           (pr_of(env, BASIC)["pr_number"], pr_of(env, BASIC)["head_sha"], env.state(BASIC)))


# =============================================================== M13
def m13(rep, R, T):
    env = MockEnv(R, T)
    a, b = "T-MOCK-KN", "T-MOCK-KN-REL"
    both = []

    def active():
        snap = env.snap()["tasks"]
        both.append(sum(1 for x in (a, b) if x in snap and (snap[x]["lease_record"] or {}).get("status") == "active"))

    env.bring_to_building(a)
    active()
    env.start_task(b)
    env.grant(b)
    active()
    rep.eq("conflict_paths가 패턴으로 겹치는 과제는 동시에 임대하지 않는다", ("queued", 0), (env.state(b), env.task(b)["lease_generation"]))
    env.builder_for(a).send_result(env.instr(a), "pr_opened", pr_number=1, head_sha=H1, touched_paths=[sample_path(env, a)])
    active()
    env.grant(b)
    active()
    rep.eq("앞 과제의 임대가 끝나면 뒤 과제가 임대된다", ("leased", 1), (env.state(b), env.task(b)["lease_generation"]))
    rep.eq("어느 시점에도 활성 임대는 둘 중 하나 이하", True, max(both) <= 1)


# =============================================================== M14
def m14(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    token = "cfut_" + "a" * 24  # the shape of a secret pattern, built at run time
    m = mark(env)
    out = env.builder_for(BASIC).send_result(env.instr(BASIC), "failed_tests", signals_seen=["log line " + token])
    js = jr(env, m)
    rep.eq("[결과 봉투·로그] 패턴 검출 → building→returned(secret_detected), R-10, 즉시 중단",
           ([("building", "returned", "secret_detected")], ["R-10"], "revoked"), (tr(js), rets(js), env.lease(BASIC)["status"]))
    rep.eq("[결과 봉투·로그] 프로세스 종료·토큰 폐기, 봉투는 처리하지 않음(수락 아님, 사용량 기록 없음, inbox 키 1개)",
           (True, True, False, None, 1), ("terminate_process" in se(js), "revoke_token" in se(js), out["accepted"],
                                          env.snap()["usage_record"][0]["calls"], len(env.task(BASIC)["inbox_seen"])))
    rep.eq("[결과 봉투·로그] 일치한 문자열은 어디에도 기록되지 않는다", False, token in str(env.snap()))

    env, path = handoff_bench(R, T)
    env.ports.worktree.write(path, "notes2.txt", "k = " + token + "\n")
    env.clock.advance(1)
    m = mark(env)
    switch(env)
    js = jr(env, m)
    rep.eq("[인계 중 보존 전] handoff→returned(secret_detected, R-10), 보존·푸시 0건",
           (("handoff", "returned", "secret_detected"), ["R-10"], 0, 0),
           (tr(js)[-1], rets(js), env.ports.git.commit_count, env.ports.git.push_count))

    env, path = handoff_bench(R, T)
    env.ports.git.inject("push", [PushFailed("remote said: ghp_" + "Q" * 36)])
    env.clock.advance(1)
    m = mark(env)
    switch(env)
    js = jr(env, m)
    t = env.task(HANDOFF)
    rep.eq("[기록 문자열(journal_text)] 푸시 오류 문구의 비밀값 → 가린 뒤 handoff→returned(R-10), 푸시 0건",
           (("handoff", "returned", "secret_detected"), ["R-10"], 0), (tr(js)[-1], rets(js), env.ports.git.push_count))
    rep.eq("[기록 문자열(journal_text)] 실패 기록과 저널에는 가린 값만 남는다", ("<redacted>", False),
           (t["handoff_record"]["failure_log"][0]["reason"], "Q" * 36 in str(env.snap())))


# =============================================================== M15
def m15(rep, R, T):
    five = [{"name": f"mock-builder-{i}", "runner": f"mock-runner-{i}", "family": f"mock-family-{c}"}
            for i, c in zip(range(1, 6), "abcde")]
    env = MockEnv(R, T, builders=five)
    env.bring_to_building(HANDOFF)
    path = env.instr(HANDOFF)["worktree"]
    env.ports.worktree.write(path, "src/w.py", "w\n")
    env.ports.builders.unavailable.update(b["name"] for b in five)
    env.clock.advance(1)
    m = mark(env)
    env.submit(HANDOFF, "switch_signal", env.builder_for(HANDOFF).signal_envelope(
        env.instr(HANDOFF), status="runner_missing", source="runner_version_probe"))
    js = jr(env, m)
    t = env.task(HANDOFF)
    rep.eq("빌더 5개 모두 runner_missing → 보존 뒤 paused_no_builder", ("handoff", "paused_no_builder", "no_builder"), tr(js)[-1])
    rep.eq("대체 없음: issue_lease 0, 세대 1, 작업은 원격에 보존", (0, 1, "remote_pushed"),
           (len(se(js, "issue_lease")), t["lease_generation"], t["handoff_record"]["preservation_state"]))


# =============================================================== M16
def m16(rep, R, T):
    env = MockEnv(R, T)
    rep.eq("정적: 병합 API·자동 병합 설정 호출 함수 0건", [], static_checks.no_merge_api())
    policy = env.raw["roles"]["merge"]
    rep.eq("규칙: auto_merge=false, 사람만 병합, 데몬의 병합 권한 두 항목 모두 false", (False, "human_only", [False, False]),
           (env.raw["auto_merge"], policy["by"], [v for k, v in sorted(policy.items()) if k.startswith("daemon_may_")]))
    rep.eq("모의 원격 포트에는 push·pr_update 외의 쓰기가 없다", [], [n for n in dir(env.ports.remote) if "merge" in n.lower()])


# =============================================================== M17
def m17(rep, R, T):
    env = MockEnv(R, T)
    env.builders["mock-builder-1"].proc_options[HANDOFF] = dict(ghost=True)
    env.core.register_task(HANDOFF, "blocked")
    env.store.tamper(lambda d: d["tasks"][HANDOFF].update(lease_generation=6))  # six earlier leases
    env.core.evaluate_prereqs(HANDOFF)
    env.grant(HANDOFF)
    env.run_builders()
    a_instr = copy.deepcopy(env.instr(HANDOFF))
    a = env.builder_for(HANDOFF)
    env.ports.worktree.write(a_instr["worktree"], "src/a.py", "a\n")
    env.clock.advance(1)
    m = mark(env)
    switch(env)
    env.run_builders()
    js = jr(env, m)
    rep.eq("임대 A(token 7) 전환 뒤 임대 B(token 8) building", (7, 8, "building"),
           (a_instr["fencing_token"], env.lease(HANDOFF)["fencing_token"], env.state(HANDOFF)))
    rep.eq("A 프로세스 그룹 종료·쓰기 자격·토큰 회수 기록", True,
           all(x in se(js) for x in ("terminate_process", "revoke_write_credential", "revoke_token")))
    before = env.task(HANDOFF)
    m = mark(env)
    late_push = env.event("push_requested", HANDOFF, lease_id=a_instr["lease_id"], lease_generation=7, fencing_token=7,
                          envelope_id="P-A", via="daemon", branch=a_instr["branch"], sha="a" * 40)
    late_res = env.submit(HANDOFF, "result", a.result_envelope(a_instr, "pr_opened"))
    rep.eq("A의 늦은 푸시·결과는 쓰지도 수락하지도 않는다", (False, False), (late_push["accepted"], late_res["accepted"]))
    rep.eq("A의 늦은 푸시·결과: late_envelope_rejected(R-11), 상태·임대 B 불변, 원격 쓰기 0",
           ([("late_envelope_rejected", "R-11")] * 2, [], before["lease_record"], before["task_state"], []),
           (noops(jr(env, m)), tr(jr(env, m)), env.lease(HANDOFF), env.task(HANDOFF)["task_state"], env.ports.remote.writes))
    b_instr = env.instr(HANDOFF)
    ok = env.event("push_requested", HANDOFF, lease_id=b_instr["lease_id"], lease_generation=8, fencing_token=8,
                   envelope_id="P-B", via="daemon", branch=b_instr["branch"], sha="b" * 40)
    rep.eq("B의 쓰기만 수락(원격 쓰기는 세대 8 하나)", (True, [8]), (ok["written"], [w[2] for w in env.ports.remote.writes]))
    rep.eq("교체 전후 동시 쓰기 0건: A의 격리 뒤 쓰기는 모두 거부되고 B의 작업 트리와 다르다",
           (True, True), (len(env.ports.worktree.denied_writes) > 0,
                          all(p == a_instr["worktree"] for _, p in env.ports.worktree.denied_writes)))


# =============================================================== M18 / M18a / M18b
def _signal(env, t, **kw):
    return env.submit(t, "switch_signal", env.builder_for(t).signal_envelope(env.instr(t), **kw))


def _no_switch(rep, R, T, label, kw):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    m = mark(env)
    _signal(env, BASIC, **kw)
    rep.eq(f"[{label}] 전환 없음(building 유지, 세대 1, handoff 기록 없음)", ("building", 1, None, []),
           (env.state(BASIC), env.task(BASIC)["lease_generation"], env.task(BASIC)["handoff_record"], tr(jr(env, m))))


def m18(rep, R, T):
    _no_switch(rep, R, T, "자식 시험 로그 'rate limit exceeded'", dict(source="child_process_output", status="usage_limit",
                                                                     text="rate limit exceeded"))
    _no_switch(rep, R, T, "수집 대상 403", dict(source="target_site_http", status="auth_failure", http_status=403))
    _no_switch(rep, R, T, "모의 제공자 429라도 허용 출처가 아닌 곳에서 관측", dict(source="child_process_stderr", status="usage_limit",
                                                                         http_status=429))
    for source, status in (("provider_http_response", "usage_limit"), ("runner_exit_code", "usage_limit"),
                           ("runner_auth_probe", "auth_failure")):
        env = MockEnv(R, T)
        env.bring_to_building(HANDOFF)
        env.clock.advance(1)
        m = mark(env)
        _signal(env, HANDOFF, source=source, status=status)
        rep.eq(f"[{source}] 전환한다(building→handoff→leased)", (("building", "handoff", "switch_signal"), "leased"),
               (tr(jr(env, m))[0], env.state(HANDOFF)))
    rep.eq("허용 출처는 데이터 네 가지뿐", ["provider_http_response", "runner_auth_probe", "runner_exit_code", "runner_version_probe"],
           sorted(MockEnv(R, T).rules.get("switch_policy.allowed_sources")))


def m18a(rep, R, T):
    _no_switch(rep, R, T, "시험 로그 HTTP 429", dict(source="child_process_stderr", status="usage_limit", text="HTTP 429"))
    _no_switch(rep, R, T, "시험 로그 quota exceeded", dict(source="test_output", status="usage_limit", text="quota exceeded"))
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    m = mark(env)
    env.builder_for(BASIC).send_result(env.instr(BASIC), "failed_tests", signals_seen=["HTTP 429 quota exceeded"])
    rep.eq("실패 결과 봉투의 429 문자열도 전환이 아니다(같은 빌더 재임대)", ([("building", "building", "result_failed_tests")], "mock-builder-1"),
           (tr(jr(env, m)), env.lease(BASIC)["builder"]))


def m18b(rep, R, T):
    for label, kw in (("수집 대상 403", dict(source="target_site_http", status="auth_failure", http_status=403)),
                      ("수집 대상 503", dict(source="target_site_http", status="service_unavailable", http_status=503)),
                      ("저장소 API 401", dict(source="repo_api", status="auth_failure", http_status=401))):
        _no_switch(rep, R, T, label, kw)


# =============================================================== M19 / M25
def m19(rep, R, T):
    env = MockEnv(R, T)
    _land_series(env, 9)
    env.start_task(SUCC)
    rep.eq("선행 과제가 시작 전이면 후속은 blocked", "blocked", env.state(SUCC))
    approve_to_wait(env, BASIC)
    rep.eq("선행이 merge_wait이면 후속은 아직 blocked", "blocked", env.state(SUCC))
    m = mark(env)
    land(env, BASIC, merge_commit="f" * 40)
    rep.eq("선행 merged → audit_queued 사이에 후속 blocked→queued(post_merge_states)",
           [("merge_wait", "merged", "pr_merged_observed"), ("merged", "audit_queued", "impl_counter_incremented"),
            ("blocked", "queued", "prereqs_satisfied")], tr(jr(env, m)))
    env.observe(None, "batch_audit_result", batch_id="B1", verdict="pass")
    rep.eq("선행 done 뒤에도 후속은 queued, 임대 가능", ("done", "queued"), (env.state(BASIC), env.state(SUCC)))
    # audit2-daemon-wildcard-from-terminal: the * -> returned unmapped_condition rows do not apply to done
    m = mark(env)
    env.event("pr_merged_observed", BASIC)
    rep.eq("선행 done 뒤 다시 전달된 병합 관측은 기록만(event_after_terminal_state), 반송 없음, 후속 queued 유지",
           ("done", "queued", [], [], [("event_after_terminal_state", None)]),
           (env.state(BASIC), env.state(SUCC), tr(jr(env, m)), rets(jr(env, m)), noops(jr(env, m))))
    env.grant(SUCC)
    rep.eq("후속 임대", "leased", env.state(SUCC))


def m25(rep, R, T):
    env = MockEnv(R, T)
    env.start_task(SUCC)
    env.ports.reviewers.unavailable.add("mock-builder-2")
    open_pr(env, BASIC)
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    m = mark(env)
    land(env, BASIC, head=H1, base="b" * 40)
    js = jr(env, m)
    facts = env.snap()["completion_facts"]
    rep.eq("merge_wait(reviewer_unavailable)에서 병합 관측 → merged_invalid_approval, R-12",
           ([("merge_wait", "merged_invalid_approval", "merged_without_valid_approval")], ["R-12"]), (tr(js), rets(js)))
    rep.eq("완료 사실에 무효 병합으로 기록, 카운터 0, done·post_merge 아님, 후속 blocked",
           (False, 0, "merged_invalid_approval", "blocked"),
           (facts[0]["valid"], counter(env)["merged_impl_counter"], env.state(BASIC), env.state(SUCC)))
    for state_label, prep in (("리뷰어 배정 전(pr_open)", lambda e: open_pr(e, OTHER)),
                              ("리뷰 중", lambda e: (open_pr(e, OTHER), e.observe(OTHER, "ci", conclusion="success", sha=H1)))):
        env = MockEnv(R, T)
        prep(env)
        before = env.state(OTHER)
        m = mark(env)
        land(env, OTHER, head=H1, base="b" * 40)
        rep.eq(f"[{state_label}] 병합 관측 → merged_invalid_approval(R-12), done 아님",
               ([(before, "merged_invalid_approval", "merged_without_valid_approval")], ["R-12"]), (tr(jr(env, m)), rets(jr(env, m))))
    # a state with no merged_without_valid_approval row: the engine falls through to unmapped_condition (R-03),
    # and R-12 is not recorded on top of it
    m = mark(env)
    env.observe(OTHER, "landing", head_sha_at_merge=H2, base_sha_at_merge="b" * 40, merge_commit_sha="d" * 40,
                integration_check="mock://ci/base")
    rep.eq("[merged_invalid_approval] 행이 없는 상태에서 다른 병합 관측 → unmapped_condition(R-03)만, R-12 중복 없음",
           ([("merged_invalid_approval", "returned", "unmapped_condition")], ["R-03"]), (tr(jr(env, m)), rets(jr(env, m))))
    # a missing SHA is never a match (None == None must not validate a landing), and landings without a merge
    # commit are told apart by their other fields
    for label, wipe, extra in (("병합 시점 head 없음", {}, dict(head_sha_at_merge=None)),
                               ("병합 시점 base 없음", {}, dict(base_sha_at_merge=None)),
                               ("승인 SHA도 병합 시점 head도 없음(None == None)", dict(approved_head_sha=None), dict(head_sha_at_merge=None))):
        env = MockEnv(R, T)
        approve_to_wait(env, BASIC)
        pr = pr_of(env, BASIC)
        payload = dict(head_sha_at_merge=pr["approved_head_sha"], base_sha_at_merge=pr["approved_base_sha"],
                       merge_commit_sha="e" * 40, integration_check="mock://ci/base")
        payload.update(extra)
        if wipe:
            env.store.tamper(lambda d, w=wipe: d["pr"][BASIC].update(w))
        m = mark(env)
        env.observe(BASIC, "landing", **payload)
        rep.eq(f"[merge_wait(ready)] {label} → merged_invalid_approval(R-12), 완료 사실 valid=False",
               ([("merge_wait", "merged_invalid_approval", "merged_without_valid_approval")], ["R-12"], [False]),
               (tr(jr(env, m)), rets(jr(env, m)), [f["valid"] for f in env.snap()["completion_facts"]]))
    env = MockEnv(R, T)
    approve_to_wait(env, BASIC)
    m = mark(env)
    env.observe(BASIC, "landing", head_sha_at_merge=H2, base_sha_at_merge="b" * 40, integration_check="mock://ci/base")
    env.observe(BASIC, "landing", head_sha_at_merge=H2, base_sha_at_merge="b" * 40, integration_check="mock://ci/base")
    env.observe(BASIC, "landing", head_sha_at_merge=H3, base_sha_at_merge="b" * 40, integration_check="mock://ci/base")
    js = jr(env, m)
    rep.eq("merge_commit_sha 없는 병합 관측: 같은 내용의 되풀이만 noop, 다른 관측은 따로 기록(합쳐지지 않음)",
           ([("merge_wait", "merged_invalid_approval", "merged_without_valid_approval"),
             ("merged_invalid_approval", "returned", "unmapped_condition")], [("pr_merged_observed_duplicate", None)], 2),
           (tr(js), noops(js), len(env.snap()["completion_facts"])))

    env = MockEnv(R, T)
    prep(env)
    land(env, OTHER, head=H1, base="b" * 40)
    m = mark(env)
    env.event("owner_cancelled", OTHER)
    rep.eq("merged_invalid_approval 취소에는 set_cancelled(G37)", (True, ["set_cancelled"]),
           (env.task(OTHER)["task_state"]["cancelled"], se(jr(env, m), "set_cancelled")))


# =============================================================== M20 / M21 / M22 / M23
def m20(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(BASIC)
    env.builder_for(BASIC).send_result(env.instr(BASIC), "verdict_requested")
    m = mark(env)
    env.event("owner_resolved", BASIC)
    rep.eq("resolution_ref 없는 해소 기록은 받지 않는다", ([], "returned"), (tr(jr(env, m)), env.state(BASIC)))
    env.event("owner_resolved", BASIC, resolution_ref="RES-20")
    rep.eq("owner_resolved → queued(attempt+1)", ("queued", 2), (env.state(BASIC), env.task(BASIC)["task_state"]["attempt"]))
    env.grant(BASIC)
    rep.eq("다음 임대는 새 토큰·새 브랜치(attempt 2)", (2, "task/T-MOCK-BASIC-a2"), (env.lease(BASIC)["fencing_token"], env.lease(BASIC)["branch"]))


def m21(rep, R, T):
    env = MockEnv(R, T)
    open_pr(env, BASIC)
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    snap = env.task(BASIC)
    m = mark(env)
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    rep.eq("ci_passed 두 번째: noop(ci_passed_duplicate), 상태 불변", ([("ci_passed_duplicate", None)], [], snap["task_state"]),
           (noops(jr(env, m)), tr(jr(env, m)), env.task(BASIC)["task_state"]))
    review(env, BASIC)
    land(env, BASIC, merge_commit="9" * 40)
    m = mark(env)
    land(env, BASIC, merge_commit="9" * 40)
    rep.eq("병합 관측 두 번째: noop(pr_merged_observed_duplicate), 상태·카운터·완료 사실 불변",
           ([("pr_merged_observed_duplicate", None)], [], "audit_queued", 1, 1),
           (noops(jr(env, m)), tr(jr(env, m)), env.state(BASIC), counter(env)["merged_impl_counter"], len(env.snap()["completion_facts"])))


def m22(rep, R, T):
    env = MockEnv(R, T)
    open_pr(env, BASIC)
    m = mark(env)
    env.observe(BASIC, "review_result", verdict="approved", sha=H1, reviewer="mock-builder-2", reviewer_family="mock-family-b")
    rep.eq("review_approved가 ci_passed보다 먼저: 보류(전이 0, 반송 0)", ([], [], "pr_open", 1),
           (tr(jr(env, m)), rets(jr(env, m)), env.state(BASIC), len(env.snap()["held"][BASIC])))
    m = mark(env)
    env.observe(BASIC, "ci", conclusion="success", sha=H1)
    rep.eq("ci_passed 뒤 순서가 맞을 때 보류분 적용 → merge_wait(ready)",
           [("pr_open", "review_pending", "ci_passed"), ("review_pending", "review_in_progress", "reviewer_assigned"),
            ("review_in_progress", "review_approved", "review_approved"), ("review_approved", "merge_wait", "audit_not_required")],
           tr(jr(env, m)))

    env = MockEnv(R, T)
    open_pr(env, BASIC)
    env.observe(BASIC, "review_result", verdict="approved", sha=H1, reviewer="mock-builder-2", reviewer_family="mock-family-b")
    env.observe(BASIC, "head_sha", sha=H2)
    m = mark(env)
    env.observe(BASIC, "ci", conclusion="success", sha=H2)
    rep.eq("보류된 결과의 SHA가 맞지 않으면 무효(R-04), 반송 아님, 리뷰는 진행 중으로 남는다",
           ([("pr_open", "review_pending", "ci_passed"), ("review_pending", "review_in_progress", "reviewer_assigned")], ["R-04"], "review_in_progress", []),
           (tr(jr(env, m)), rets(jr(env, m)), env.state(BASIC), env.snap()["held"][BASIC]))


def m23(rep, R, T):
    env = MockEnv(R, T)
    approve_to_wait(env, DOCS, touched=["docs/mock/guide.md"])
    m = mark(env)
    land(env, DOCS)
    rep.eq("docs/** 뿐인 PR: merged→done(docs_only), 카운터 불변",
           ([("merge_wait", "merged", "pr_merged_observed"), ("merged", "done", "impl_counter_incremented")], 0, []),
           (tr(jr(env, m)), counter(env)["merged_impl_counter"], counter(env)["batches"]))


# =============================================================== M27
def m27(rep, R, T):
    env = MockEnv(R, T)
    env.bring_to_building(OTHER)
    b = env.builder_for(OTHER)
    grace = int(env.rules.number("hard_stop.grace_s"))
    m = mark(env)
    env.event("owner_stop", OTHER, stop_ref="STOP-1")
    at = env.task(OTHER)["task_state"]["stop_requested_at"]
    env.clock.advance(30)
    env.event("owner_stop", OTHER, stop_ref="STOP-2")
    rep.eq("owner_stop: building→building(stop 요청), 두 번째는 owner_stop_already_requested, 기한 그대로",
           ([("building", "building", "owner_stop")], [("owner_stop_already_requested", None)], at),
           (tr(jr(env, m)), noops(jr(env, m)), env.task(OTHER)["task_state"]["stop_requested_at"]))
    while env.clock.now() < at + grace - 1:
        env.clock.advance(min(30, at + grace - 1 - env.clock.now()))
        env.submit(OTHER, "heartbeat", b.heartbeat_envelope(env.instr(OTHER)))
        env.core.tick()
    rep.eq("기한 전에는 하트비트가 와도 building", "building", env.state(OTHER))
    env.clock.advance(1)
    env.submit(OTHER, "heartbeat", b.heartbeat_envelope(env.instr(OTHER)))
    m = mark(env)
    env.core.tick()
    js = jr(env, m)
    rep.eq("grace_s 경과: hard_stop_deadline → returned(R-07), 임대 종료(expired)·토큰 폐기",
           ([("building", "returned", "hard_stop_deadline")], ["R-07"], "expired", True),
           (tr(js), rets(js), env.lease(OTHER)["status"], "revoke_token" in se(js)))
    rep.eq("데몬 보존 없음(daemon_preserve=false): 커밋·푸시 0", (0, 0), (env.ports.git.commit_count, env.ports.git.push_count))
    late = env.submit(OTHER, "heartbeat", b.heartbeat_envelope(env.instr(OTHER)))
    rep.eq("그 뒤 하트비트는 late_envelope_rejected(R-11), 상태 불변", ("late_envelope_rejected", "R-11", "returned"),
           (late["noop"], late["return_code"], env.state(OTHER)))

    env, path = handoff_bench(R, T)
    env.ports.faults.arm("handoff:isolate:start")
    env.crash(lambda: switch(env))
    env.new_core()
    m = mark(env)
    env.event("owner_stop", HANDOFF, stop_ref="STOP-H")
    rep.eq("인계 중 owner_stop은 noop(owner_stop_ignored_during_handoff)", ([("owner_stop_ignored_during_handoff", None)], []),
           (noops(jr(env, m)), tr(jr(env, m))))

    env = MockEnv(R, T)
    env.start_task(BASIC)
    env.grant(BASIC)
    m = mark(env)
    env.event("owner_stop", BASIC, stop_ref="STOP-L")
    rep.eq("일 시작 전(leased)의 owner_stop은 unmapped_condition(R-03), 활성 임대를 끝낸다(G37)",
           ([("leased", "returned", "unmapped_condition")], ["R-03"], "revoked"), (tr(jr(env, m)), rets(jr(env, m)), env.lease(BASIC)["status"]))

    env = MockEnv(R, T)
    env.bring_to_building(OTHER)
    b = env.builder_for(OTHER)
    wall = env.instr(OTHER)["limits"]["max_wall_s"]
    t0 = env.lease(OTHER)["issued_at"]
    while env.clock.now() < t0 + wall:
        env.clock.advance(min(240, t0 + wall - env.clock.now()))
        env.submit(OTHER, "heartbeat", b.heartbeat_envelope(env.instr(OTHER)))
        if env.clock.now() < t0 + wall:
            env.core.tick()
    rep.eq("max_wall_s 직전까지는 하트비트로 building", "building", env.state(OTHER))
    m = mark(env)
    env.core.tick()
    rep.eq("max_wall_s 초과: 시계가 hard_stop_deadline을 일으킨다(R-07)", ([("building", "returned", "hard_stop_deadline")], ["R-07"]),
           (tr(jr(env, m)), rets(jr(env, m))))


# =============================================================== M31
def m31(rep, R, T):
    env = MockEnv(R, T)
    approve_to_wait(env, BASIC)
    m = mark(env)
    land(env, BASIC, merge_commit="5" * 40, check="mock://ci/base/42")
    js = jr(env, m)
    fact = env.snap()["completion_facts"][0]
    rep.eq("squash 병합(merge_commit_sha ≠ approved_head_sha)이어도 head·base가 승인과 같으면 merged",
           ("merge_wait", "merged", "pr_merged_observed"), tr(js)[0])
    rep.eq("완료 사실: approved_head_sha·base_sha·head_sha_at_merge·merge_commit_sha·integration_check",
           {"approved_head_sha": H1, "base_sha": "b" * 40, "head_sha_at_merge": H1, "merge_commit_sha": "5" * 40,
            "integration_check": "mock://ci/base/42"},
           {k: fact[k] for k in ("approved_head_sha", "base_sha", "head_sha_at_merge", "merge_commit_sha", "integration_check")})
    rep.eq("record_merge_observation 부수 효과 1건, 유효", (1, True),
           (len(se(js, "record_merge_observation")), [r for r in js if r.get("id") == "record_merge_observation"][0]["args"]["valid"]))

    env = MockEnv(R, T)
    approve_to_wait(env, BASIC)
    m = mark(env)
    land(env, BASIC, head=H2, merge_commit="6" * 40)
    rep.eq("승인 뒤 head가 바뀐 채 병합 → merged_invalid_approval(R-12), 완료 사실에 무효로 기록",
           ([("merge_wait", "merged_invalid_approval", "merged_without_valid_approval")], ["R-12"], False),
           (tr(jr(env, m)), rets(jr(env, m)), env.snap()["completion_facts"][0]["valid"]))
    env = MockEnv(R, T)
    approve_to_wait(env, BASIC)
    m = mark(env)
    land(env, BASIC, base="0" * 40, merge_commit="7" * 40)
    rep.eq("base가 승인 시점과 다르면 무효(R-12)", ["R-12"], rets(jr(env, m)))


# =============================================================== M32
def m32(rep, R, T):
    from .core.envelope_validator import validate_instruction
    env = MockEnv(R, T)
    env.start_task(NOGATES)
    m = mark(env)
    env.grant(NOGATES)
    js = jr(env, m)
    rep.eq("(a) real_data_allowed를 계산할 수 없는 과제(real_data 목록 없음) → 봉투에 필드 없음 → envelope_invalid → returned(R-13), 발송 0",
           ([("queued", "returned", "envelope_invalid")], ["R-13"], [], 0), (tr(js), rets(js), sent_ids(env), env.task(NOGATES)["lease_generation"]))

    env = MockEnv(R, T)
    env.start_task(BASIC)
    env.grant(BASIC)
    good = copy.deepcopy(env.ports.sender.inboxes["mock-runner-1"][0])  # the instruction as the builder received it
    dec = env.task(BASIC)["task_state"]["decisions_recorded"]
    missing = {k: v for k, v in good.items() if k != "real_data_allowed"}
    wrong = dict(good, real_data_allowed=False)
    rep.eq("(a) 검증기: real_data_allowed 없는 봉투 invalid(real_data_allowed_is_bool), 결정 관문과 다른 값 invalid",
           (("valid", []), ("invalid", ["real_data_allowed"]), ("invalid", ["real_data_allowed"])),
           (validate_instruction(env.core, BASIC, good, dec), validate_instruction(env.core, BASIC, missing, dec),
            validate_instruction(env.core, BASIC, wrong, dec)))
    rep.eq("(a) 검증기는 받은 봉투를 바꾸지 않는다", False, "real_data_allowed" in missing)
    gated = dict(good, real_data_allowed=True)
    env.ports.catalog.tasks[BASIC]["decision_gates"]["real_data"] = ["D-MOCK-RD"]
    rep.eq("(a) real_data=[D-MOCK-RD] 미기록인데 true인 봉투 invalid, false면 valid",
           ("invalid", "valid"), (validate_instruction(env.core, BASIC, gated, dec)[0],
                                  validate_instruction(env.core, BASIC, dict(good, real_data_allowed=False), dec)[0]))

    def canon_case(label, approval, record, expect_missing):
        env = MockEnv(R, T)
        env.ports.catalog.tasks[CANON]["canon_change"]["approval"] = approval
        for dec_id in record:
            env.observe(None, "decision_record", decision_id=dec_id, recorded_at=env.clock.now(), recorded_by="mock-owner",
                        source_ref="mock://decision")
        env.start_task(CANON)
        m = mark(env)
        out = env.grant(CANON)
        payload = (out.get("emitted") or [{}])[0]
        rep.eq(f"({label}) → envelope_invalid → returned(R-13), 발송 0, 빠진 항목 {expect_missing}",
               ([("queued", "returned", "envelope_invalid")], ["R-13"], [], True),
               (tr(jr(env, m)), rets(jr(env, m)), sent_ids(env), payload.get("applied", False)))
        from .core.lease import candidate_validation
        got = candidate_validation(env.core, env.snap(), CANON, "from_queue")  # a copy of the store: nothing is written
        rep.eq(f"({label}) 검증기의 빠진 항목", ("invalid", expect_missing), got)

    scope = ["tools/mock/canon/vocab.json"]
    canon_case("b) 정본 변경 과제에 canon_change_approval 없음", None, [], ["canon_change_approval"])
    canon_case("c) decision_ref 미기록", {"decision_ref": "D-MOCK-CANON", "scope_paths": scope}, [], ["canon_change_approval.decision_ref"])
    canon_case("d) scope_paths에 allowed_paths 밖", {"decision_ref": "D-MOCK-CANON", "scope_paths": scope + ["docs/BLUEPRINT.md"]},
               ["D-MOCK-CANON"], ["canon_change_approval.scope_paths"])

    env = MockEnv(R, T)
    env.observe(None, "decision_record", decision_id="D-MOCK-CANON", recorded_at=env.clock.now(), recorded_by="mock-owner",
                source_ref="mock://decision")
    env.bring_to_building(CANON)
    m = mark(env)
    env.builder_for(CANON).send_result(env.instr(CANON), "pr_opened", pr_number=4, head_sha=H1, touched_paths=scope)
    rep.eq("(e) 올바른 승인: 발송되고 scope_paths 안의 정본 수정은 R-01이 아니다",
           (1, [("building", "pr_open", "result_pr_opened")], [], {"decision_ref": "D-MOCK-CANON", "scope_paths": scope}),
           (len(sent_ids(env)), tr(jr(env, m)), rets(jr(env, m)), env.instr(CANON)["canon_change_approval"]))

    env = MockEnv(R, T)
    env.bring_to_building(CANON_FREE)
    m = mark(env)
    env.builder_for(CANON_FREE).send_result(env.instr(CANON_FREE), "pr_opened", pr_number=5, head_sha=H1, touched_paths=scope)
    rep.eq("(f) canon_change 없는 과제가 허용 경로 안의 정본 파일을 고치면 R-01", ([("building", "returned", "result_out_of_scope")], ["R-01"]),
           (tr(jr(env, m)), rets(jr(env, m))))
    env = MockEnv(R, T)
    env.ports.catalog.tasks[CANON_FREE]["canon_change"] = None
    env.start_task(CANON_FREE)
    env.ports.catalog.tasks[CANON_FREE]["canon_change"] = {"required": False, "approval": {"decision_ref": "D-MOCK-CANON", "scope_paths": scope}}
    m = mark(env)
    env.grant(CANON_FREE)
    rep.eq("canon_change가 필요 없는 과제에 승인이 실리면 거부(R-13)", ["R-13"], rets(jr(env, m)))

    env = MockEnv(R, T)
    env.bring_to_building("T-MOCK-REVIEW")
    rep.eq("(g) real_data_allowed=false 봉투로 모의·로컬 작업은 진행된다", ("building", False, [("mock_provider_review", True), ("real_provider_review", False)]),
           (env.state("T-MOCK-REVIEW"), env.instr("T-MOCK-REVIEW")["real_data_allowed"], env.builder_for("T-MOCK-REVIEW").steps["T-MOCK-REVIEW"]))


FLOW_SCENARIOS = [
    ("M1", "-", "정상 흐름: queued→…→merge_wait(ready), 병합 API 0건", m1),
    ("M2", "-", "사용량 제한 전환: 429(model_provider) → handoff → 2순위 빌더", m2),
    ("M3", "-", "시험 실패는 전환이 아니다: 같은 빌더 재임대, 3회면 R-06", m3),
    ("M4", "-", "리뷰어 없음 → merge_wait(reviewer_unavailable) → 복귀, 작성 계열·귀속 불가 리뷰는 거부", m4),
    ("M5", "stale-approval-invalidated", "승인 뒤 코드 변경: pr_open, 옛 결과 무효(R-04)", m5),
    ("M6", "-", "즉시 감리: review_approved→audit_pending→merge_wait(ready)", m6),
    ("M7", "-", "정기 감리 카운터: 구현 PR만 세어 10번째에서 묶음", m7),
    ("M8", "-", "허용 경로 밖 수정 → R-01", m8),
    ("M9", "-", "판단 요청 → R-02", m9),
    ("M10", "decision-gate-merge-only", "결정 관문: merge 결정은 merge_wait만 막는다", m10),
    ("M10a", "d02-mock-start-allowed", "real_data=[D-02] 미기록: 시작 허용, real_data_allowed=false", m10a),
    ("M10b", "r2-local-work-allowed", "real_data=[D-04] 미기록: 로컬 작업 허용, R2 쓰기만 건너뜀", m10b),
    ("M11", "-", "재시작 복원: 외부 상태 조회로 복원 또는 R-08", m11),
    ("M12", "-", "중복 실행 방지: 잠금으로 하나만, 열린 PR 재사용", m12),
    ("M13", "-", "충돌 경로 직렬화", m13),
    ("M14", "-", "비밀값 검출: R-10 즉시 중단(결과 봉투·인계 중 파일·기록 문자열)", m14),
    ("M15", "-", "모든 빌더 불가: paused_no_builder, 대체 없음", m15),
    ("M16", "-", "병합 금지(정적)", m16),
    ("M17", "late-write-fenced", "늦은 쓰기 펜싱: A(token 7) 거부, B(token 8)만 수락", m17),
    ("M18", "provider-scoped-switch", "전환 출처 제한: 허용 출처만 전환", m18),
    ("M18a", "switch-negative-test-output", "시험 로그의 429·quota 문자열은 전환이 아니다", m18a),
    ("M18b", "switch-negative-third-party-http", "수집 대상 403/503·저장소 API 401은 전환이 아니다", m18b),
    ("M19", "post-merge-prereq", "선행 merged→audit_queued→done 뒤 후속 queued", m19),
    ("M20", "-", "반송 재개: owner_resolved → queued(attempt+1, 새 토큰)", m20),
    ("M21", "event-duplicate-noop", "중복 사건: ci_passed·병합 관측 두 번은 noop", m21),
    ("M22", "event-out-of-order", "순서 뒤바뀐 사건: 보류 뒤 적용, SHA 불일치는 R-04", m22),
    ("M23", "docs-pr-complete", "문서 PR: merged→done, 카운터 불변", m23),
    ("M24", "eleventh-pr-audit", "11번째 PR은 새 묶음, 앞 묶음 감리가 막지 않음", m24),
    ("M25", "mis-merge-not-done", "잘못된 병합: merged_invalid_approval(R-12), done 아님", m25),
    ("M27", "hard-stop-heartbeating-job", "강제 종료 기한: owner_stop 뒤 grace_s, max_wall_s", m27),
    ("M31", "merge-observation-fields", "병합 관측 필드: squash는 merged, head 변경 뒤 병합은 R-12", m31),
    ("M32", "envelope-permission-rejects-missing", "봉투 권한 필드: 누락·잘못된 승인은 R-13, 정본 무단 수정은 R-01", m32),
]
