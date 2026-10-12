#!/usr/bin/env python3
"""설계 검토 묶음의 의미 검사(작업 그래프·데몬 규칙·문서 대조).

작성: 구현자(이 묶음의 작성자인 설계 담당과 분리). 설계 담당은 이 파일을 고치지 않는다.
사용자 검토(ffbcaf6, 2026-10-12)의 지적 F01~F12 중 기계로 판정할 수 있는 것을 검사한다.
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


def check(fid, name, ok, detail, kind="기계"):
    RESULTS.append({"finding": fid, "check": name, "ok": bool(ok), "kind": kind, "detail": detail})


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
    check("F03", "G2 시험이 선행 과제의 산출물만 쓴다", not bad, bad[:10])

    # G3 허용·금지 경로 충돌(F04). 넓은 허용 안의 좁은 금지(예: infra/** 중 infra/r2/jobs/**)는 예외 지정이라 충돌이 아니다.
    #    허용 경로 전체가 금지 경로 안에 들어가면(허용이 무의미) 충돌이다.
    bad = []
    for tid, t in tasks.items():
        for a in t.get("allowed_paths", []):
            for f in t.get("forbidden_paths", []):
                if a == f or fnmatch.fnmatch(sample(a), f):
                    bad.append(f"{tid}: 허용 {a} ↔ 금지 {f}")
    check("F04", "G3 같은 과제의 허용·금지 경로가 겹치지 않음", not bad, bad[:10])

    # G4 최종 관문이 모든 과제와 모든 기능 행을 덮는다(F05)
    finals = [tid for tid, t in tasks.items() if t.get("final_gate")]
    if not finals:
        sinks = [tid for tid in tasks if not any(tid in t.get("prereq_tasks", []) for t in tasks.values())]
        check("F05", "G4a 최종 관문 과제가 하나로 지정됨(final_gate)", False, f"final_gate 없음. 아무도 의존하지 않는 과제 {len(sinks)}개: {sinks[:12]}")
        final = "T-OP-08" if "T-OP-08" in tasks else (sinks[0] if sinks else None)
    else:
        check("F05", "G4a 최종 관문 과제가 하나로 지정됨(final_gate)", len(finals) == 1, finals)
        final = finals[0]
    if final:
        anc = ancestors(tasks, final, {})
        uncovered = sorted(set(tasks) - anc - {final})
        check("F05", "G4b 최종 관문이 다른 모든 과제를 선행으로 가짐", not uncovered, f"{final} 의 선행 밖 {len(uncovered)}개: {uncovered[:15]}")
    rows = integration_rows(repo)
    reg = T.get("feature_registry", [])
    covered = {r for f in reg for r in f.get("covers", [])}
    miss = [r for r in rows if r not in covered]
    check("F05", "G4c 통합안 §2 기능 행이 전부 feature_registry에 매핑됨", reg and not miss, f"행 {len(rows)}개 중 미매핑 {len(miss)}: {miss[:12]}")
    if reg and final:
        anc = ancestors(tasks, final, {}) | {final}
        bad = [f["id"] for f in reg if not f.get("tasks") or not set(f["tasks"]) <= anc or not set(f["tasks"]) <= set(tasks)]
        check("F05", "G4d 각 기능의 과제가 최종 관문의 선행에 있음", not bad, bad[:12])

    # G5 결정 차단: 문서(병합만)와 JSON의 일치(F10)
    tr = D.get("transitions", [])
    start_tr = [x for x in tr if x.get("from") == "blocked" and x.get("to") == "queued"]
    uses_all = [x["when"] for x in start_tr if "prereq_decisions" in x.get("when", "")]
    has_gates = all("decision_gates" in t for t in tasks.values())
    merge_checks = [x for x in tr if "decision_gates.merge" in x.get("when", "")]
    check("F10", "G5a 과제가 시작 차단과 병합 차단을 따로 적음(decision_gates)", has_gates, "decision_gates 없는 과제 " + str([tid for tid, t in tasks.items() if "decision_gates" not in t][:8]))
    check("F10", "G5b 시작 전이는 decision_gates.start만 본다", start_tr and not uses_all and all("decision_gates.start" in x.get("when", "") for x in start_tr), uses_all or [x.get("when") for x in start_tr])
    check("F10", "G5c 병합 대기 전이가 decision_gates.merge를 본다", bool(merge_checks), f"decision_gates.merge를 보는 전이 {len(merge_checks)}개")

    # G6 병합 뒤 상태(F12)
    post = set(D.get("post_merge_states", []))
    reach, frontier = {"merged"}, ["merged"]
    while frontier:
        s = frontier.pop()
        for x in tr:
            if x.get("from") == s and x.get("to") not in reach and x.get("to") not in ("returned", "cancelled"):
                reach.add(x["to"]); frontier.append(x["to"])
    eq_merged = [x["when"] for x in start_tr if re.search(r"==\s*merged", x.get("when", ""))]
    check("F12", "G6a post_merge_states가 merged에서 닿는 상태를 전부 포함", post and reach <= post, f"닿는 상태 {sorted(reach)} · 선언 {sorted(post)}")
    check("F12", "G6b 선행 충족을 '==merged'가 아니라 post_merge_states로 판정", start_tr and not eq_merged and all("post_merge_states" in x.get("when", "") for x in start_tr), eq_merged or [x.get("when") for x in start_tr])

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
    check("F06", "G7a 대기·복구 전이(event 필드 기준)", not miss, miss)
    dead = sorted({s for s in D.get("states", {}) if s not in ("done", "cancelled") and not any(x.get("from") in (s, "*") and x.get("to") != "returned" for x in tr if x.get("from") != "*")})
    check("F06", "G7b 종료가 아닌 상태마다 반송 외의 나가는 전이가 있음", not dead, dead)

    # G8 늦은 쓰기 차단(F07)
    conc = D.get("concurrency", {})
    fen = conc.get("fencing") or {}
    need_at = {"push", "pr_update", "result_accept"}
    need_end = {"terminate_process", "revoke_write_credential"}
    ok = bool(fen.get("token")) and need_at <= set(fen.get("checked_at", [])) and need_end <= set(fen.get("on_lease_end", [])) and bool(conc.get("isolation"))
    check("F07", "G8 임대 펜싱 토큰·격리·만료 시 프로세스 종료와 쓰기 권한 회수", ok, {"fencing": fen or "없음", "isolation": conc.get("isolation", "없음")})

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
    check("F11", "G9 전환 신호가 모델 제공자 응답·실행기 종료 코드로만 판정", not bad, bad[:10])

    # G10 CI가 이 검사와 온톨로지 검사를 실행(보고 정확성)
    wf = "".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(repo, ".github/workflows/*.yml")))
    check("C", "G10 CI가 spec_check.py와 ontology_check.py를 실행", "spec_check.py" in wf and "ontology_check.py" in wf, "워크플로에서 찾음" if "spec_check.py" in wf else "워크플로에 없음")

    # G11 문서 대조(텍스트 존재 검사: 의미 검토가 아님)
    c02 = read("02_구현계약.md")
    regress = re.search(r"원본 해시\s*\+\s*문서 역할", c02)
    check("F02", "G11a 02가 약관 판을 '원본 해시 + 문서 역할'로 정의하지 않음", not regress, regress.group(0) if regress else "없음", kind="존재 검사")
    check("F02", "G11b 02가 원본·구획·본문 판·계열을 나눔", all(w in c02 for w in ("DocumentSegment", "TermsEdition", "TermsLineage")), "", kind="존재 검사")
    check("F01", "G11c 02가 릴리스를 구성원 목록+내용 해시로 고정", "구성원 목록" in c02 and "내용 해시" in c02, "", kind="존재 검사")
    req = {"need-criteria-versioned": "F08", "need-result-reasons": "F08", "uncertainty-partial-hold": "F09",
           "release-frozen-members": "F01", "decision-gate-merge-only": "F10", "stale-approval-invalidated": "F06",
           "late-write-fenced": "F07", "provider-scoped-switch": "F11", "post-merge-prereq": "F12"}
    have = {x for t in tasks.values() for x in t.get("required_test_ids", [])}
    for rid, fid in req.items():
        check(fid, f"G12 필수 시험 ID '{rid}'를 가진 과제가 있음", rid in have, "", kind="존재 검사")
    need_feats = {"need-criteria": "판단 기준 관리(기준·기준의 판·출처)", "need-result-reasons": "유지·추가 없음·보류 결과와 이유"}
    ids = {f["id"] for f in reg}
    for fid, label in need_feats.items():
        check("F08", f"G13 기능 '{label}'이 feature_registry에 있음", fid in ids, "", kind="존재 검사")


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
        print(f"{'PASS' if r['ok'] else 'FAIL'} [{r['finding']}] ({r['kind']}) {r['check']}" + ("" if r["ok"] else f"\n      {r['detail']}"))
    mech = [r for r in RESULTS if r["kind"] == "기계"]
    print(f"\n요약: 기계 검사 {sum(r['ok'] for r in mech)}/{len(mech)} · 존재 검사 {sum(r['ok'] for r in RESULTS if r['kind'] != '기계')}/{len(RESULTS) - len(mech)} · {'전체 통과' if not fails else '실패 ' + str(len(fails))}")
    print("주의: 존재 검사는 이름·문구가 있는지만 본다. 제품 의미(F08·F09 등)의 적절성은 사람 검토 대상이다.")
    if out_json:
        json.dump(RESULTS, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
