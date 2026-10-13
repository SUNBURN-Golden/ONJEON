#!/usr/bin/env python3
"""설계 검토 묶음의 의미 검사(작업 그래프·데몬 규칙·문서 대조).

작성: 구현자(이 묶음의 작성자인 설계 담당과 분리). 설계 담당은 이 파일을 고치지 않는다.
사용자 검토(ffbcaf6, 2026-10-12)의 지적 중 기계로 판정할 수 있는 것을 검사한다. 지적 표지는 LABELS(원본 번호는 확인된 것만).
판정할 수 없는 것(제품 의미의 적절성)은 '존재 검사'로만 표시하고 통과를 의미 검토로 세지 않는다.

사용: python3 -I spec_check.py [--repo <저장소 루트>] [--json <결과 파일>]
종료 코드: 0 전부 통과, 1 실패 있음.

검사가 기대하는 형식(수정본이 지켜야 할 계약):
  tasks.json
    feature_registry: [{id, name, covers: ["2.x 행 이름", ...], tasks: [과제 ID]}]
    tasks[]: id, prereq_tasks, decision_gates{start:[], merge:[]}, allowed_paths, forbidden_paths,
             produces: ["crate:<이름>" | "path:<glob>" | "<종류>:<이름>"], consumes: [같은 형식],
             tests, features: [feature id], final_gate(정확히 하나 true), required_test_ids: [..]
  daemon_rules.json
    post_merge_states: [...]          # 병합 뒤 상태 전부. 선행 조건 충족은 이 집합으로 판정
    events: [...]                     # 전이를 일으키는 사건 이름
    transitions[]: from, to, event, when, by
    switch_policy.allowed_switch_signals[].detect[]: {source, match, scope}
    concurrency.fencing: {token, checked_at: [...], on_lease_end: [...]}, concurrency.isolation
    safety_verification_status: {장치: specified | dry_run_target | real_executor_required}
    concurrency.lease_issue: {function: issue_lease, atomic_record: [lease_generation, lease_record, outbox], restart_recovery}
    concurrency.envelope_identity: envelope_id | one_per_kind_per_generation
    preserve_manifest: {function, includes/excludes, deleted·untracked·mode·symlink 규칙, compare}; concurrency.quiescence가 같은 function 참조
    handoff_failure_policy: {max_attempts, always_revoke:[..., preserve_credential], ...}
    전이 event: quiescence_failed, index_lock, disk_full, preserve_commit_failed, preserve_push_failed, daemon_restart_during_handoff
    handoff→leased 전이의 when: preserve_succeeded 또는 recovery_decision
  tasks[].verification_kind: dry_run | real_executor (해당 과제만)
  07_수정대응표.md: 지적마다 변경 위치·시험 종류·증명 범위·미검증
"""
import fnmatch
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = os.path.dirname(HERE)


def load(name):
    return json.load(open(os.path.join(BUNDLE, name), encoding="utf-8"))


def read(name):
    return open(os.path.join(BUNDLE, name), encoding="utf-8").read()


RESULTS = []

# 지적 표지. 원본 번호는 사용자 상세 검토서(검증/사용자검토_ffbcaf6/REVIEW.md)의 F01~F12다.
LABELS = {
    "release": ("새 주장이 기존 릴리스에 유입", "F01"), "edition": ("약관 의미상 판과 파일 식별의 혼합", "F02"),
    "partial": ("영향받는 결론만 보류", "F03"), "order": ("먼저 통과해야 할 시험의 구현이 후속 작업에", "F04"),
    "perm": ("허용·금지 경로 충돌과 공용 파일 잠금", "F05"), "final": ("최종 감리가 전체 완성품을 요구하지 않음", "F06"),
    "wait": ("데몬 대기·병합 후 재개 경로", "F07"), "postmerge": ("데몬 대기·병합 후 재개 경로(병합 뒤 상태)", "F07"),
    "latewrite": ("점유 만료·중단 뒤 이전 작성자 차단", "F08"), "switch": ("일반 오류를 모델 사용량 제한으로 오인", "F09"),
    "gates": ("좁게 차단한다는 설명과 기계 규칙", "F10"), "needcrit": ("필요성 판단·판단 기준 관리", "F11"),
    "consistency": ("제약·근거·승격 상태 정의의 정합성", "F12"),
    "ci": ("검증 수준 정정(검토서 본문, 번호 없음)", "본문"), "trace": ("요구사항→계약→작업→시험→출시 증거 대응표(검토서 다음 작업 3)", "본문"),
    "link": ("입력 연결: 다른 회사 담보가 판매 구성에 붙음(재검토 R02, 추가 결함)", "R02"),
    "—": ("그래프 기본", "—"),
}


def check(fid, name, ok, detail, kind="기계"):
    label, orig = LABELS[fid]
    RESULTS.append({"finding": fid, "label": label, "original_id": orig, "check": name, "ok": bool(ok), "kind": kind, "detail": detail})


# ---------- 공통 도구 ----------
def sample(pattern):
    return pattern.replace("**", "s/t").replace("*", "x").replace("?", "q")


def overlap(a, b):
    """두 glob이 같은 파일을 가리킬 수 있는가(근사: 서로의 표본이 상대에 맞는가, 또는 접두 포함)."""
    if fnmatch.fnmatch(sample(a), b) or fnmatch.fnmatch(sample(b), a):
        return True
    pa, pb = a.split("*")[0], b.split("*")[0]
    return (a.endswith("**") and pb.startswith(pa)) or (b.endswith("**") and pa.startswith(pb))


def ancestors(tasks, tid, memo=None):
    memo = {} if memo is None else memo
    if tid in memo:
        return memo[tid]
    memo[tid] = set()
    out = set()
    for p in tasks[tid].get("prereq_tasks", []):
        if p in tasks:
            out |= {p} | ancestors(tasks, p, memo)
    memo[tid] = out
    return out


def repo_crates(repo):
    out = {}
    for cargo in glob.glob(os.path.join(repo, "**", "Cargo.toml"), recursive=True):
        if "/target/" in cargo:
            continue
        m = re.search(r'^\s*name\s*=\s*"([^"]+)"', open(cargo, encoding="utf-8").read(), re.M)
        if m:
            out[m.group(1)] = os.path.relpath(os.path.dirname(cargo), repo)
    return out


def produced_by(tasks, ref):
    """ref(crate:x / path:p)를 만드는 과제들."""
    kind, _, val = ref.partition(":")
    hits = set()
    for tid, t in tasks.items():
        for p in t.get("produces", []):
            pk, _, pv = p.partition(":")
            if pk != kind:
                continue
            if kind == "path" and (overlap(pv, val)):
                hits.add(tid)
            elif pv == val:
                hits.add(tid)
    return hits


def guess_crate_owner(tasks, crate):
    """구 형식(produces 없음)용 근사: onjeon-<x> 크레이트는 services/<x> 또는 packages/<x>를 허용 경로 루트로 가진 과제가 만든다."""
    short = crate.replace("onjeon-", "")
    roots = {f"services/{short}/**", f"packages/{short}/**", f"services/{short.replace('-', '_')}/**", f"packages/{short.replace('-', '_')}/**"}
    return {tid for tid, t in tasks.items() if roots & set(t.get("allowed_paths", []))}


def noop_events_of(D):
    return [e if isinstance(e, str) else e.get("event", "") for e in D.get("noop_events", [])]


def integration_rows(repo):
    """설계통합안 §2.1~§2.9 표의 기능 행 이름."""
    text = open(os.path.join(repo, "docs/blueprint/proposals/설계통합안_검토본.md"), encoding="utf-8").read()
    rows, sec, header_next = [], None, False
    for line in text.splitlines():
        m = re.match(r"^### (2\.\d+)\b", line)
        if m:
            sec = m.group(1) if m.group(1) != "2.10" else None
            header_next = True
            continue
        if line.startswith("## ") and not line.startswith("## 2."):
            sec = None
        if not sec or not line.startswith("|"):
            if not line.startswith("|"):
                header_next = True
            continue
        if re.match(r"^\|\s*-{3}", line):
            continue
        if header_next:
            header_next = False
            continue
        rows.append(f"{sec} {line.split('|')[1].strip()}")
    return rows


# ---------- 검사 ----------
def run(repo):
    T = load("tasks.json")
    D = load("daemon_rules.json")
    tasks = {t["id"]: t for t in T["tasks"]}
    new_schema = all("produces" in t for t in tasks.values())

    # G1 그래프
    missing = [(tid, p) for tid, t in tasks.items() for p in t.get("prereq_tasks", []) if p not in tasks]
    cyc = [tid for tid in tasks if tid in ancestors(tasks, tid, {})]
    check("—", "G1 선행 과제 존재·순환 없음", not missing and not cyc, f"없는 선행 {missing[:5]} · 순환 {cyc[:5]}")

    # G2 시험·입력이 아직 만들어지지 않은 산출물에 의존하지 않는다(F03)
    crates = repo_crates(repo)
    bad = []
    for tid, t in tasks.items():
        anc = ancestors(tasks, tid, {})
        refs = set(t.get("consumes", []))
        for cmd in t.get("tests", []):
            for c in re.findall(r"cargo test[^&;|]*?-p\s+([A-Za-z0-9_-]+)", cmd):
                refs.add("crate:" + c)
        for ref in refs:
            kind, _, val = ref.partition(":")
            if kind == "crate" and val in crates:
                continue  # 이미 저장소에 있음
            if kind == "path" and glob.glob(os.path.join(repo, val), recursive=True):
                continue
            owners = produced_by(tasks, ref) if new_schema else (guess_crate_owner(tasks, val) if kind == "crate" else set())
            if not owners:
                bad.append(f"{tid}: {ref} 를 만드는 과제가 없음")
            elif tid not in owners and not (owners & anc):
                bad.append(f"{tid}: {ref} 는 {sorted(owners)} 가 만드는데 선행이 아님")
    check("order", "G2 시험이 선행 과제의 산출물만 쓴다", not bad, bad[:10])

    # G3 허용·금지 경로 충돌(F04). 넓은 허용 안의 좁은 금지(예: infra/** 중 infra/r2/jobs/**)는 예외 지정이라 충돌이 아니다.
    #    허용 경로 전체가 금지 경로 안에 들어가면(허용이 무의미) 충돌이다.
    bad = []
    for tid, t in tasks.items():
        for a in t.get("allowed_paths", []):
            for f in t.get("forbidden_paths", []):
                if a == f or fnmatch.fnmatch(sample(a), f):
                    bad.append(f"{tid}: 허용 {a} ↔ 금지 {f}")
    check("perm", "G3 같은 과제의 허용·금지 경로가 겹치지 않음", not bad, bad[:10])

    # G4 최종 관문이 모든 과제와 모든 기능 행을 덮는다(F05)
    finals = [tid for tid, t in tasks.items() if t.get("final_gate")]
    if not finals:
        sinks = [tid for tid in tasks if not any(tid in t.get("prereq_tasks", []) for t in tasks.values())]
        check("final", "G4a 최종 관문 과제가 하나로 지정됨(final_gate)", False, f"final_gate 없음. 아무도 의존하지 않는 과제 {len(sinks)}개: {sinks[:12]}")
        final = "T-OP-08" if "T-OP-08" in tasks else (sinks[0] if sinks else None)
    else:
        check("final", "G4a 최종 관문 과제가 하나로 지정됨(final_gate)", len(finals) == 1, finals)
        final = finals[0]
    if final:
        anc = ancestors(tasks, final, {})
        uncovered = sorted(set(tasks) - anc - {final})
        check("final", "G4b 최종 관문이 다른 모든 과제를 선행으로 가짐", not uncovered, f"{final} 의 선행 밖 {len(uncovered)}개: {uncovered[:15]}")
    rows = integration_rows(repo)
    reg = T.get("feature_registry", [])
    covered = {r for f in reg for r in f.get("covers", [])}
    miss = [r for r in rows if r not in covered]
    check("final", "G4c 통합안 §2 기능 행이 전부 feature_registry에 매핑됨", reg and not miss, f"행 {len(rows)}개 중 미매핑 {len(miss)}: {miss[:12]}")
    if reg and final:
        anc = ancestors(tasks, final, {}) | {final}
        bad = [f["id"] for f in reg if not f.get("tasks") or not set(f["tasks"]) <= anc or not set(f["tasks"]) <= set(tasks)]
        check("final", "G4d 각 기능의 과제가 최종 관문의 선행에 있음", not bad, bad[:12])

    # G5 결정 차단: 문서(병합만)와 JSON의 일치(F10)
    tr = D.get("transitions", [])
    start_tr = [x for x in tr if x.get("from") == "blocked" and x.get("to") == "queued"]
    uses_all = [x["when"] for x in start_tr if "prereq_decisions" in x.get("when", "")]
    has_gates = all("decision_gates" in t for t in tasks.values())
    merge_checks = [x for x in tr if "decision_gates.merge" in x.get("when", "")]
    check("gates", "G5a 과제가 시작 차단과 병합 차단을 따로 적음(decision_gates)", has_gates, "decision_gates 없는 과제 " + str([tid for tid, t in tasks.items() if "decision_gates" not in t][:8]))
    check("gates", "G5b 시작 전이는 decision_gates.start만 본다", start_tr and not uses_all and all("decision_gates.start" in x.get("when", "") for x in start_tr), uses_all or [x.get("when") for x in start_tr])
    check("gates", "G5c 병합 대기 전이가 decision_gates.merge를 본다", bool(merge_checks), f"decision_gates.merge를 보는 전이 {len(merge_checks)}개")

    # G6 병합 뒤 상태(F12)
    post = set(D.get("post_merge_states", []))
    reach, frontier = {"merged"}, ["merged"]
    while frontier:
        s = frontier.pop()
        for x in tr:
            if x.get("from") == s and x.get("to") not in reach and x.get("to") not in ("returned", "cancelled"):
                reach.add(x["to"]); frontier.append(x["to"])
    eq_merged = [x["when"] for x in start_tr if re.search(r"==\s*merged", x.get("when", ""))]
    check("postmerge", "G6a post_merge_states가 merged에서 닿는 상태를 전부 포함", post and reach <= post, f"닿는 상태 {sorted(reach)} · 선언 {sorted(post)}")
    check("postmerge", "G6b 선행 충족을 '==merged'가 아니라 post_merge_states로 판정", start_tr and not eq_merged and all("post_merge_states" in x.get("when", "") for x in start_tr), eq_merged or [x.get("when") for x in start_tr])

    # G7 대기·복구 경로(F06)
    def has(frm, event=None, to=None, word=None):
        for x in tr:
            if x.get("from") not in (frm, "*"):
                continue
            if event and x.get("event") != event:
                continue
            if to and x.get("to") not in to:
                continue
            if word and word not in x.get("when", ""):
                continue
            return True
        return False
    need = [
        ("merge_wait", "reviewer_available", {"review_pending", "review_in_progress"}, "리뷰어 복귀 → 리뷰 재개"),
        ("merge_wait", "auditor_available", {"audit_pending"}, "감리 담당 복귀 → 감리 재개"),
        ("merge_wait", "decision_recorded", None, "결정 기록 → 병합 대기 사유 갱신"),
        ("merge_wait", "head_sha_changed", {"pr_open", "review_pending"}, "병합 대기 중 코드 변경 → 승인 무효·재리뷰"),
        ("audit_pending", "head_sha_changed", {"pr_open", "review_pending"}, "감리 대기 중 코드 변경 → 재리뷰"),
        ("review_in_progress", "head_sha_changed", {"pr_open", "review_pending"}, "리뷰 중 코드 변경 → 재리뷰"),
        ("review_approved", "head_sha_changed", {"pr_open", "review_pending"}, "승인 뒤 코드 변경 → 재리뷰"),
        ("blocked", "prereqs_satisfied", {"queued"}, "선행 충족(이미 완료된 선행 포함) → 시작 가능"),
    ]
    miss = [label for frm, ev, to, label in need if not has(frm, ev, to)]
    check("wait", "G7a 대기·복구 전이(event 필드 기준)", not miss, miss)
    dead = sorted({s for s in D.get("states", {}) if s not in ("done", "cancelled") and not any(x.get("from") in (s, "*") and x.get("to") != "returned" for x in tr if x.get("from") != "*")})
    check("wait", "G7b 종료가 아닌 상태마다 반송 외의 나가는 전이가 있음", not dead, dead)

    # G8 늦은 쓰기 차단(F07)
    conc = D.get("concurrency", {})
    fen = conc.get("fencing") or {}
    need_at = {"push", "pr_update", "result_accept"}
    need_end = {"terminate_process", "revoke_write_credential"}
    ok = bool(fen.get("token")) and need_at <= set(fen.get("checked_at", [])) and need_end <= set(fen.get("on_lease_end", [])) and bool(conc.get("isolation"))
    check("latewrite", "G8 임대 펜싱 토큰·격리·만료 시 프로세스 종료와 쓰기 권한 회수", ok, {"fencing": fen or "없음", "isolation": conc.get("isolation", "없음")})

    # G9 전환 신호는 모델 제공자 출처만(F11)
    bad = []
    allowed_src = {"provider_http_response", "runner_exit_code", "runner_auth_probe", "runner_version_probe"}
    for sig in D.get("switch_policy", {}).get("allowed_switch_signals", []):
        for det in sig.get("detect", []):
            if not isinstance(det, dict):
                bad.append(f"{sig['id']}: 구조 없는 문자열 규칙 '{det}'")
                continue
            if det.get("source") not in allowed_src:
                bad.append(f"{sig['id']}: 출처 {det.get('source')}")
            if det.get("source") == "provider_http_response" and det.get("scope") != "model_provider":
                bad.append(f"{sig['id']}: HTTP 규칙의 범위가 모델 제공자로 한정되지 않음")
    check("switch", "G9 전환 신호가 모델 제공자 응답·실행기 종료 코드로만 판정", not bad, bad[:10])

    # G10 CI가 이 검사와 온톨로지 검사를 실행(보고 정확성)
    wf = "".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(repo, ".github/workflows/*.yml")))
    check("ci", "G10 CI가 spec_check.py와 ontology_check.py를 실행", "spec_check.py" in wf and "ontology_check.py" in wf, "워크플로에서 찾음" if "spec_check.py" in wf else "워크플로에 없음")

    # G11 문서 대조(텍스트 존재 검사: 의미 검토가 아님)
    c02 = read("02_구현계약.md")
    regress = re.search(r"원본 해시\s*\+\s*문서 역할", c02)
    check("edition", "G11a 02가 약관 판을 '원본 해시 + 문서 역할'로 정의하지 않음", not regress, regress.group(0) if regress else "없음", kind="존재 검사")
    check("edition", "G11b 02가 원본·구획·본문 판·계열을 나눔", all(w in c02 for w in ("DocumentSegment", "TermsEdition", "TermsLineage")), "", kind="존재 검사")
    check("release", "G11c 02가 릴리스를 구성원 목록+내용 해시로 고정", "구성원 목록" in c02 and "내용 해시" in c02, "", kind="존재 검사")
    req = {"need-criteria-versioned": "needcrit", "need-result-reasons": "needcrit", "uncertainty-partial-hold": "partial",
           "release-frozen-members": "release", "decision-gate-merge-only": "gates", "stale-approval-invalidated": "wait",
           "late-write-fenced": "latewrite", "provider-scoped-switch": "switch", "post-merge-prereq": "postmerge",
           "release-referenced-nodes-frozen": "release", "release-usage-restriction-separate": "release",
           "edition-not-auto-by-fingerprint": "edition", "edition-composition-annex": "edition",
           "need-criteria-service-gate": "needcrit",
           "release-future-supersedes-frozen": "release", "edition-integrated-vs-separate-file": "edition",
           "edition-repack-same": "edition", "edition-one-rider-revised-in-integrated": "edition",
           "partial-hold-independent-contract-kept": "partial", "no-completeness-from-equal-candidates": "partial",
           "bootstrap-clean-main": "order", "release-readiness-rejects-incomplete": "final",
           "event-duplicate-noop": "wait", "event-out-of-order": "wait", "docs-pr-complete": "wait",
           "eleventh-pr-audit": "wait", "mis-merge-not-done": "wait",
           "usage-recorded-not-capped": "latewrite", "hard-stop-heartbeating-job": "latewrite",
           "switch-negative-test-output": "switch", "switch-negative-third-party-http": "switch",
           "d02-mock-start-allowed": "gates", "r2-local-work-allowed": "gates",
           "need-flow-keep-addnone-hold-unknown": "needcrit",
           "profile-historical-vs-service": "consistency",
           "edition-bundle-split-files": "edition", "edition-annex-missing-unconfirmed": "edition",
           "edition-ocr-normalization": "edition", "edition-annex-content-changed": "edition",
           "input-link-other-company": "link", "input-link-other-edition": "link",
           "input-link-multiple-candidates": "link", "input-link-order-independent": "link",
           "late-result-no-state-change": "latewrite", "lease-guards-all-paths": "latewrite",
           "envelope-permission-rejects-missing": "gates", "price-raw-kept-comparison-gated": "consistency",
           "reason-evidence-by-kind": "consistency",
           "handoff-quiescent-before-preserve": "latewrite", "retry-new-idempotency-key": "latewrite",
           "duplicate-delivery-noop": "latewrite", "input-link-multi-edition-config": "link",
           "input-link-unknown-scope-hold": "link", "input-link-unrelated-rider-allowed": "link", "input-link-competing-editions-hold": "link",
           "preserve-manifest-same-function": "latewrite", "preserve-failure-recoverable-stop": "latewrite",
           "daemon-restart-during-handoff": "latewrite", "envelope-id-distinct-events": "latewrite", "lease-issue-atomic-single-owner": "latewrite"}
    have = {x for t in tasks.values() for x in t.get("required_test_ids", [])}
    for rid, fid in req.items():
        check(fid, f"G12 필수 시험 ID '{rid}'를 가진 과제가 있음", rid in have, "", kind="존재 검사")
    # G14 실제 실행기 검증 과제가 모의 검증(dry-run)과 분리되어 있다(추가 기준 5)
    real = [t for t in tasks.values() if t.get("verification_kind") == "real_executor"]
    mock = [t for t in tasks.values() if t.get("verification_kind") == "dry_run"]
    need_real = {"late-write-fenced", "late-result-rejected", "resume-after-interrupt", "duplicate-run-prevented"}
    ok = bool(real) and bool(mock) and not ({t["id"] for t in real} & {t["id"] for t in mock}) and need_real <= {x for t in real for x in t.get("required_test_ids", [])}
    check("latewrite", "G14 실제 실행기 검증 과제(verification_kind=real_executor)가 dry-run 과제와 분리되고 중단·재개·늦은 결과·중복 실행 시험을 가짐", ok,
          f"real {[t['id'] for t in real]} · dry_run {[t['id'] for t in mock]} · 빠진 시험 {sorted(need_real - {x for t in real for x in t.get('required_test_ids', [])})}", kind="존재 검사")
    # G15 안전장치의 검증 상태를 '검증됨'으로 주장하지 않는다(실제 실행기 검증 전)
    claims = [k for k, v in (D.get("safety_verification_status") or {}).items() if v not in ("specified", "dry_run_target", "real_executor_required")]
    check("latewrite", "G15 daemon_rules.safety_verification_status가 있고 어느 장치도 '검증됨'이 아님", bool(D.get("safety_verification_status")) and not claims, claims or "상태 표 없음" if not D.get("safety_verification_status") else claims)
    # G16 대응표: 지적마다 변경 위치·시험 종류·증명 범위·미검증
    try:
        t07 = read("07_수정대응표.md")
    except FileNotFoundError:
        t07 = ""
    heads = ("변경 위치", "시험 종류", "증명 범위", "미검증")
    missing_labels = [lab for key, (lab, _) in LABELS.items() if key != "—" and lab not in t07]
    check("ci", "G16 07_수정대응표.md가 지적마다 변경 위치·시험 종류·증명 범위·미검증 칸을 가짐", t07 and all(h in t07 for h in heads) and not missing_labels,
          f"없는 칸 {[h for h in heads if h not in t07]} · 없는 지적 {missing_labels}", kind="존재 검사")
    # ---- 상세 검토서 대조로 추가한 검사(2026-10-12) ----
    # F05 공용 manifest·lockfile 잠금, 산출물 경로가 허용 경로 안
    shared = ("Cargo.toml", "Cargo.lock")
    bad = []
    for tid, t in tasks.items():
        for f in shared:
            if any(a == f or fnmatch.fnmatch(f, a) for a in t.get("allowed_paths", [])) and f not in t.get("conflict_paths", []):
                bad.append(f"{tid}: {f} 수정 권한이 있는데 conflict_paths에 없음")
    check("perm", "G17 공용 manifest·lockfile을 고치는 과제가 그 파일을 잠근다", not bad, bad[:10])
    bad = []
    for tid, t in tasks.items():
        for ref in t.get("produces", []):
            k, _, v = ref.partition(":")
            if k == "path" and not any(overlap(v, a) and (fnmatch.fnmatch(sample(v), a) or v == a) for a in t.get("allowed_paths", [])):
                bad.append(f"{tid}: 산출물 {v} 가 허용 경로 밖")
    check("perm", "G18 각 과제의 산출물 경로가 그 과제의 허용 경로 안", not bad, bad[:10])
    # F04 공통 완료 기준 중 다른 과제가 만드는 도구에 기대는 것은 적용 시점(applies_after)을 가진다
    staged_words = ("누출", "비노출", "스켈레톤")
    bad = [c for c in T.get("common_done_criteria", []) if isinstance(c, str) and any(w in c for w in staged_words)]
    bad += [c.get("text") for c in T.get("common_done_criteria", []) if isinstance(c, dict) and c.get("applies_after") not in tasks]
    check("order", "G19 도구에 기대는 공통 완료 기준이 그 도구를 만드는 과제 이후에만 적용됨(applies_after)", not bad, bad[:5])
    # F06 출시 요구마다 필수 과제·실제 데이터 증거·수락 시험, 제외는 승인된 범위 결정으로만
    bad = []
    for f in reg:
        if f.get("excluded"):
            if not f.get("scope_decision"):
                bad.append(f"{f['id']}: 제외인데 범위 결정 근거 없음")
        elif not (f.get("tasks") and f.get("evidence") and f.get("acceptance_tests")):
            bad.append(f"{f['id']}: tasks·evidence·acceptance_tests 중 빠짐")
    check("final", "G20 feature_registry 항목마다 필수 과제·실제 데이터 증거·수락 시험(제외는 범위 결정 근거)", reg and not bad, bad[:10], kind="존재 검사")
    # F07 명시적 no-op, 문서 PR 완료, 잘못된 병합은 완료가 아님
    noop = D.get("noop_events", [])
    check("wait", "G21 명시적 no-op 사건 목록(중복·대기 알림)", bool(noop), noop or "없음")
    docs_done = [x for x in tr if x.get("from") == "merged" and x.get("to") == "done" and "docs_only" in x.get("when", "")]
    check("wait", "G22 문서 PR의 병합 뒤 완료 전이", bool(docs_done), [x.get("event") for x in docs_done] or "없음")
    bad_merge = [x for x in tr if x.get("event") == "merged_without_valid_approval"]
    check("wait", "G23 유효한 승인 없이 병합된 사실은 기록하되 done으로 가지 않음", bad_merge and all(x.get("to") != "done" for x in bad_merge), [(x.get("from"), x.get("to")) for x in bad_merge] or "없음")
    # F09 전환 신호의 출처·attempt·호출 ID 검증
    val = set(D.get("switch_policy", {}).get("signal_validation", []))
    check("switch", "G24 전환 신호가 source·attempt·call_id를 검증", {"source", "attempt", "call_id"} <= val, sorted(val) or "없음")
    # F10 착수·실데이터 접근·병합·출시 조건을 따로
    keys = {"start", "real_data", "merge", "release"}
    bad = [tid for tid, t in tasks.items() if not keys <= set((t.get("decision_gates") or {}).keys())]
    check("gates", "G25 decision_gates가 start·real_data·merge·release를 따로 가짐", not bad, bad[:8])
    # F12 제약 목록 단일화, 시험 프로필 분리
    tb = json.load(open(os.path.join(repo, "docs/blueprint/proposals/온톨로지/tbox.json"), encoding="utf-8"))
    kmax = max(int(k["id"][1:]) for k in tb["constraints"])
    texts = {n: read(n) for n in ("01_코드설계.md", "02_구현계약.md", "03_작업명세.md", "06_검토사항_점검.md")}
    texts["tasks.json"] = json.dumps(T, ensure_ascii=False)
    stale = sorted({f"{n}: K1~K{m}" for n, tx in texts.items() for m in re.findall(r"K1\s*~\s*K(\d+)", tx) if int(m) != kmax})
    check("consistency", f"G26 제약 범위 표기가 T-box(K1~K{kmax})와 같음", not stale, stale[:8])
    prof = T.get("test_profiles", {})
    check("consistency", "G27 시험 프로필이 역사적 사례(historical_fixture)와 서비스 적합성(service_conformance)으로 나뉨", {"historical_fixture", "service_conformance"} <= set(prof), sorted(prof) or "없음")
    c02 = read("02_구현계약.md")
    check("consistency", "G28 02가 주장 종류별 근거 정책과 가격 관측의 보존·비교 자격 분리를 둠", "근거 정책" in c02 and "비교 자격" in c02, "", kind="존재 검사")
    # U-05(2026-10-13) 비용 정책: 비용 상한 없음, 사용량 기록은 유지, 비용 누적으로 멈추지 않음
    blob_d = json.dumps({k: v for k, v in D.items() if not k.startswith("_")}, ensure_ascii=False)
    be = D.get("budget_enforcement") or D.get("usage_recording") or {}
    cap_words = re.findall(r"max_cost_units|월 총비용 상한|월 총 비용 상한|예산 소진|budget_exhausted|cost_cap", blob_d)
    ok = not cap_words and bool(D.get("usage_recording")) and not any("예산" in (r.get("when") or "") or "비용" in (r.get("when") or "") for r in D.get("return_codes", []))
    check("latewrite", "G46 [U-05] 비용 상한·예산 소진 정지가 규칙에 없고 사용량 기록(usage_recording)은 있음", ok, {"남은 비용 상한 표현": sorted(set(cap_words)), "usage_recording": bool(D.get("usage_recording"))})
    # 진행 지시(2026-10-13) 제품 목적 대응표: 목적 → 소비자 기능 → 데이터·레이블 → 트윈 → 화면 → 작업 → 완료 증거
    try:
        t09 = read("09_제품목적_대응표.md")
    except FileNotFoundError:
        t09 = ""
    cols = ("제품 목적", "소비자 기능", "데이터", "트윈", "화면", "구현 작업", "완료 증거")
    ids09 = set(re.findall(r"T-[A-Z]{2}-\d{2}", t09))
    unknown = sorted(i for i in ids09 if i not in tasks)
    fin = next((tid for tid, t in tasks.items() if t.get("final_gate")), None)
    outside = sorted(i for i in ids09 if i in tasks and fin and i != fin and i not in ancestors(tasks, fin, {}))
    musts = ("미확보 사유", "종합점수", "결과를 바꾸는 조건")
    ok = t09 and all(c in t09 for c in cols) and ids09 and not unknown and not outside and all(m in t09 for m in musts)
    check("trace", "G47 09_제품목적_대응표: 칸 7개, 과제 ID가 실재하고 최종 관문 선행 안, 원칙(미확보 사유≠확보, 종합점수 없음, 결과를 바꾸는 조건 공개)", ok,
          {"없는 칸": [c for c in cols if c not in t09], "과제 ID 수": len(ids09), "없는 과제": unknown, "최종 관문 밖": outside, "없는 원칙 문구": [m for m in musts if m not in t09]}, kind="존재 검사")
    # 다음 작업 2: 모의 검증과 실제 데몬이 같은 전이·검증 코어를 쓴다
    core = D.get("execution_core", {})
    check("wait", "G30 dry-run과 실제 실행기가 같은 전이·검증 코어를 쓴다(execution_core.shared_by)", {"dry_run", "real_executor"} <= set(core.get("shared_by", [])), core or "없음")
    # ---- 재검토(9554c96) R01~R06 충돌 검사 ----
    # R03(F04) done_criteria·tests가 언급하는 과제 ID·크레이트는 자신 또는 선행이 만든 것이어야 한다
    bad = []
    for tid, t in tasks.items():
        anc = ancestors(tasks, tid, {}) | {tid}
        text = " ".join(t.get("tests", []) + [c if isinstance(c, str) else c.get("text", "") for c in t.get("done_criteria", [])])
        for ref in sorted(set(re.findall(r"T-[A-Z]{2}-\d{2}", text))):
            if ref in tasks and ref not in anc:
                bad.append(f"{tid}: 완료 기준·시험이 선행이 아닌 {ref}를 언급")
        for c in sorted(set(re.findall(r"onjeon-[a-z0-9-]+", text))):
            if c in crates:
                continue
            owners = produced_by(tasks, "crate:" + c)
            if owners and not (owners & anc):
                bad.append(f"{tid}: 완료 기준·시험이 {c}(만드는 과제 {sorted(owners)})에 기대는데 선행이 아님")
    check("order", "G31 [R03] done_criteria·tests가 자신과 선행 과제의 산출물만 요구", not bad, bad[:10])
    # R04① head 변경 뒤 상태가 하나이고, 그 상태를 시험 문구도 쓴다
    targets = {x.get("to") for x in tr if x.get("event") == "head_sha_changed"}
    stale_txt = " ".join(" ".join(t.get("tests", []) + [c if isinstance(c, str) else c.get("text", "") for c in t.get("done_criteria", [])])
                         for t in tasks.values() if "stale-approval-invalidated" in t.get("required_test_ids", []))
    ok = len(targets) == 1 and stale_txt and next(iter(targets)) in stale_txt and not ({"pr_open", "review_pending"} - targets) & set(re.findall(r"pr_open|review_pending", stale_txt))
    check("wait", "G32 [R04①] head_sha_changed의 목적지가 하나이고 stale-approval 시험의 기대 상태와 같음", ok, {"전이 목적지": sorted(t for t in targets if t), "시험 문구의 상태": sorted(set(re.findall(r"pr_open|review_pending", stale_txt)))})
    # R04② 늦은 결과·펜스 위반은 현재 임대에만 상태 전이를 일으킨다
    bad = [f"{x.get('from')}→{x.get('to')} ({x.get('event')})" for x in tr
           if re.search(r"fence|late|stale_lease", x.get("event") or "") and x.get("from") != x.get("to") and "current" not in (x.get("when") or "")]
    stale_noop = [e for e in noop_events_of(D) if re.search(r"late|stale", e)]
    check("latewrite", "G33 [R04②] 이전 임대의 늦은 결과는 상태를 바꾸지 않음(전이는 현재 임대 조건, 이전 임대 사건은 no-op)", not bad and bool(stale_noop), {"현재 임대 조건 없는 전이": bad, "늦은 결과 no-op": stale_noop})
    # R04③ 인계 순서: 보존 → 중단 → 토큰 폐기 → 다음 임대 발급
    seq = [st if isinstance(st, str) else st.get("id") for st in D.get("handoff_sequence", [])]
    # 재검토 e02755a S02로 순서 변경: 쓰기를 멈추고(필요하면 강제 격리) 정지를 확인한 뒤 보존한다
    want = ["stop", "isolate", "confirm_quiescent", "preserve", "revoke_token", "issue_next_lease"]
    pos = [seq.index(w) if w in seq else -1 for w in want]
    check("latewrite", "G34 [R04③·S02] handoff_sequence가 stop → isolate → confirm_quiescent → preserve → revoke_token → issue_next_lease 순서", -1 not in pos and pos == sorted(pos), seq or "없음")
    # R04④ 임대를 발급하는 모든 전이에 공통 가드
    guards = D.get("lease_guards", [])
    bad = [f"{x.get('from')}→leased ({x.get('event')})" for x in tr if x.get("to") == "leased" and "lease_guards" not in (x.get("when") or "") and x.get("guard") != "lease_guards"]
    check("latewrite", "G35 [R04④] 임대 발급 전이 전부가 lease_guards(충돌 검사·잠금·예산 예약)를 거침", bool(guards) and not bad, {"lease_guards": guards, "가드 없는 전이": bad})
    # R04⑤ 승인 head와 병합 커밋을 구분
    blob = json.dumps(D, ensure_ascii=False) + read("04_자동개발명세.md")
    need = ("approved_head_sha", "base_sha", "merge_commit_sha", "integration_check")
    ok = not re.search(r"merged_sha\s*==\s*approved_sha", blob) and all(k in blob for k in need)
    check("wait", "G36 [R04⑤] merged_sha == approved_sha 비교 없음, 승인 head·base·병합 커밋·통합 검증 구분", ok, [k for k in need if k not in blob] or "비교식 남음" if not ok else "")
    # S03·T04 중복 전달과 재시도 구분, 봉투 식별, 임대 발급의 단일 책임
    conc = D.get("concurrency", {})
    key = json.dumps(conc.get("idempotency_key", ""), ensure_ascii=False)
    issue = conc.get("lease_issue") or {}
    no_issue = [f"{x.get('from')}→leased ({x.get('event')})" for x in tr if x.get("to") == "leased"
                and "issue_lease" not in (x.get("when") or "") + json.dumps(x.get("side_effects", ""), ensure_ascii=False)]
    inc_pat = re.compile(r"lease_generation\s*(\+=|\+\s*1|를?\s*(올|증가))")
    dup_inc = [f"{x.get('from')}→{x.get('to')}" for x in tr if inc_pat.search(json.dumps(x.get("side_effects", ""), ensure_ascii=False) + (x.get("when") or ""))]
    dup_inc += [f"handoff_steps: {st if isinstance(st, str) else st.get('id')}" for st in D.get("switch_policy", {}).get("handoff_steps", []) + D.get("handoff_steps", [])
                if inc_pat.search(json.dumps(st, ensure_ascii=False))]
    ok = ("lease_generation" in key and bool(conc.get("duplicate_delivery")) and bool(conc.get("retry")) and not no_issue and not dup_inc
          and "lease_generation" in json.dumps(issue, ensure_ascii=False))
    check("latewrite", "G42 [S03·T04] 키에 lease_generation, 중복 전달·재시도 분리, 임대 발급은 issue_lease 한 곳(전이·인계 단계에서 따로 증가 안 함)", ok,
          {"키": key[:80], "lease_issue": bool(issue), "issue_lease 참조 없는 전이": no_issue, "따로 증가": dup_inc})
    ident = conc.get("envelope_identity")
    atomic = set((issue.get("atomic_record") or []))
    ok = ident in ("envelope_id", "one_per_kind_per_generation") and (ident != "envelope_id" or "envelope_id" in key) and {"lease_generation", "lease_record", "outbox"} <= atomic and bool(issue.get("restart_recovery"))
    check("latewrite", "G45 [T04] 봉투 식별 방식(envelope_id 또는 세대당 종류별 하나), 세대·임대 기록·outbox 원자 저장, 재시작 복구 규칙", ok,
          {"envelope_identity": ident, "atomic_record": sorted(atomic), "restart_recovery": bool(issue.get("restart_recovery"))})
    # T02 보존 해시: 정지 확인과 보존 확인이 같은 함수
    pm = D.get("preserve_manifest") or {}
    q_ref = json.dumps(conc.get("quiescence", {}), ensure_ascii=False)
    need = ("deleted", "untracked", "mode", "symlink", "excludes")
    blobpm = json.dumps(pm, ensure_ascii=False)
    ok = bool(pm.get("function")) and pm.get("function") in q_ref and pm.get("function") in json.dumps(pm.get("compare", ""), ensure_ascii=False) + json.dumps(D.get("handoff_failure_policy", {}), ensure_ascii=False) + blobpm and all(k in blobpm for k in need)
    check("latewrite", "G43 [T02] preserve_manifest(function·삭제·미추적·권한·심볼릭 링크·제외 경로)를 정지 확인과 보존 확인이 같이 씀", ok,
          {"function": pm.get("function"), "정지 확인이 참조": pm.get("function") in q_ref if pm.get("function") else False, "빠진 정의": [k for k in need if k not in blobpm]})
    # T03 인계 실패 경로
    fails = ("quiescence_failed", "index_lock", "disk_full", "preserve_commit_failed", "preserve_push_failed", "daemon_restart_during_handoff")
    miss = [e for e in fails if not any(x.get("event") == e for x in tr)]
    bad_to = [f"{x.get('event')}→leased" for x in tr if x.get("event") in fails and x.get("to") == "leased"]
    gate = [x for x in tr if x.get("to") == "leased" and x.get("from") == "handoff"]
    gate_ok = bool(gate) and all(("preserve_succeeded" in (x.get("when") or "") or "recovery_decision" in (x.get("when") or "")) for x in gate)
    pol = D.get("handoff_failure_policy") or {}
    ok = not miss and not bad_to and gate_ok and bool(pol.get("max_attempts")) and "preserve_credential" in json.dumps(pol.get("always_revoke", ""), ensure_ascii=False)
    check("latewrite", "G44 [T03] 인계 실패 사건마다 전이(임대 발급 아님), 다음 임대는 보존 성공 또는 복구 결정 뒤, 재시도 한도, 보존 자격 항상 회수", ok,
          {"전이 없는 실패 사건": miss, "임대로 가는 실패": bad_to, "handoff→leased 조건": [x.get("when", "")[:60] for x in gate], "max_attempts": pol.get("max_attempts"), "always_revoke": pol.get("always_revoke")})
    # R05 봉투에 권한 필드, 일반 금지와 정본 변경 예외의 일치
    req_fields = set(D.get("envelopes", {}).get("instruction", {}).get("required", []))
    check("gates", "G37 [R05] 지시 봉투 필수 필드에 real_data_allowed·canon_change_approval", {"real_data_allowed", "canon_change_approval"} <= req_fields, sorted({"real_data_allowed", "canon_change_approval"} - req_fields))
    rules = D.get("envelopes", {}).get("instruction", {}).get("rules_for_builder", [])
    bad = [r for r in rules if "정본" in r and "canon_change_approval" not in r]
    check("gates", "G38 [R05] 정본 변경 금지 문구가 승인 예외(canon_change_approval)와 일치", not bad, bad)
    # R06 같은 계약 안의 모순
    c02 = read("02_구현계약.md")
    bad = [ln.strip()[:80] for ln in c02.splitlines() if "PremiumObservation" in ln and "저장 거부" in ln]
    check("consistency", "G39 [R06①] 02가 PremiumObservation을 조건 부족으로 저장 거부하지 않음(원시 보존·비교 자격 분리)", not bad, bad)
    forms = sorted(set(re.findall(r"`clause:[^`]+`", c02)))
    check("consistency", "G40 [R06②] 02의 ClauseOccurrence ID 형식이 하나이고 추출 판을 포함", len(forms) == 1 and re.search(r"extract|추출", forms[0] if forms else ""), forms or "형식 없음")
    t09 = " ".join(" ".join(t.get("tests", []) + [c if isinstance(c, str) else c.get("text", "") for c in t.get("done_criteria", [])]) for tid, t in tasks.items() if tid == "T-AP-09")
    check("consistency", "G41 [R06③] T-AP-09가 이유 종류별 근거(사실→주장, 가정→사용자 가정, 기준 평가→기준 판)를 검사", all(w in t09 for w in ("사실 이유", "가정 이유", "기준 평가 이유")), "", kind="존재 검사")
    # 다음 작업 3: 요구사항 추적표
    try:
        t08 = read("08_요구추적표.md")
    except FileNotFoundError:
        t08 = ""
    cols = ("요구", "계약", "작업", "시험", "출시 증거")
    check("trace", "G29 08_요구추적표.md(요구→계약→작업→실제 데이터/화면 시험→출시 증거)", t08 and all(c in t08 for c in cols), [c for c in cols if c not in t08], kind="존재 검사")
    need_feats = {"need-criteria": "판단 기준 관리(기준·기준의 판·출처)", "need-result-reasons": "유지·추가 없음·보류 결과와 이유"}
    ids = {f["id"] for f in reg}
    for fid, label in need_feats.items():
        check("needcrit", f"G13 기능 '{label}'이 feature_registry에 있음", fid in ids, "", kind="존재 검사")


def main():
    args = sys.argv[1:]
    repo = os.path.abspath(os.path.join(BUNDLE, "../../../.."))
    out_json = None
    if "--repo" in args:
        repo = os.path.abspath(args[args.index("--repo") + 1])
    if "--json" in args:
        out_json = args[args.index("--json") + 1]
    run(repo)
    fails = [r for r in RESULTS if not r["ok"]]
    for r in RESULTS:
        print(f"{'PASS' if r['ok'] else 'FAIL'} [{r['original_id']} {r['label']}] ({r['kind']}) {r['check']}" + ("" if r["ok"] else f"\n      {r['detail']}"))
    mech = [r for r in RESULTS if r["kind"] == "기계"]
    print(f"\n요약: 기계 검사 {sum(r['ok'] for r in mech)}/{len(mech)} · 존재 검사 {sum(r['ok'] for r in RESULTS if r['kind'] != '기계')}/{len(RESULTS) - len(mech)} · {'전체 통과' if not fails else '실패 ' + str(len(fails))}")
    print("주의: '기계' 검사는 JSON 구조·그래프를 계산해서 판정하지만, 명세의 정합성만 본다. 실제 데몬·서비스의 동작 검증이 아니다.")
    print("      '존재 검사'는 필드·문구가 있는지만 본다. 판단 기준 관리·부분 보류 등 제품 의미의 적절성은 사람 검토 대상이다.")
    if out_json:
        json.dump(RESULTS, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
