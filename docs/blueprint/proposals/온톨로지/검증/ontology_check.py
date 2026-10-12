#!/usr/bin/env python3
"""온톨로지 사례 검증(토의 자료용, 시험 전용).

1. 일관성 제약 K1~K13을 A-box에 검사한다(릴리스별).
2. 질문 → 지식 조회 → 입력 단계 판정 → 규칙 엔진 실행(Rust 실행기) → 설명·근거 사슬을 만든다.
3. 제약마다 일부러 깨뜨린 A-box를 넣어 검사기가 의도한 이유로 실패하는지 확인한다(자체 시험).

계산은 규칙 엔진만 한다. 이 스크립트는 지식 조회, 코드 소속 판정(입력 단계), 결과 설명만 한다.
사용: python3 -I ontology_check.py <runner 실행 파일>
"""
import copy
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # 온톨로지/
TBOX = json.load(open(os.path.join(ROOT, "tbox.json"), encoding="utf-8"))
ABOX = json.load(open(os.path.join(ROOT, "abox_cases.json"), encoding="utf-8"))
ANCHORS = {"계약일", "보장개시일", "갱신일", "부활일", "결과보고일", "진단확정일", "청구일"}
UNITS = {"day", "calendar_month", "calendar_year"}
PRIVATE_PREFIX = ("contract:", "person:", "upload:")
TERMS_ROLES = {"보통약관", "특약 약관", "별표"}
STRUCTURAL = {"uses_edition", "realizes", "disclosure_of"}
# 릴리스가 고정하는 구역. 확보 작업(acquisition_tasks)은 운영 상태라 릴리스 밖이다
CURRENT = "rel:case-r26"  # 질문·릴리스 시험의 기준 릴리스. r24·r25는 정정 이력 재현용
SECTIONS = ("raw_assets", "segments", "terms_editions", "terms_lineages", "clauses", "nodes", "assertions", "conflicts", "gaps", "premium_observations")


# ---------- 릴리스와 현재 주장 ----------
def _rule_files(items):
    out = {}
    for a in items:
        if a.get("rule_path"):
            path = os.path.join(ROOT, a["rule_path"])
            out[a["rule_path"]] = hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None
    return out


def content_hash(members_content, rule_files):
    blob = json.dumps({"members": members_content, "rule_files": rule_files}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _select(abox, members):
    return {k: sorted([x for x in abox.get(k, []) if x["id"] in set(members.get(k, []))], key=lambda x: x["id"]) for k in SECTIONS}


def freeze(abox, members):
    """릴리스 고정: 구성원 ID 목록 + 규칙 파일 해시 + 내용 해시."""
    sel = _select(abox, members)
    rules = _rule_files(sel["assertions"])
    return {"members": {k: sorted(members.get(k, [])) for k in SECTIONS}, "rule_files": rules, "content_sha256": content_hash(sel, rules)}


def candidate_view(abox):
    """릴리스 후보: 지금 저장된 전부. 아직 고정되지 않았으므로 K15를 검사하지 않는다."""
    v = {k: sorted(copy.deepcopy(abox.get(k, [])), key=lambda x: x["id"]) for k in SECTIONS}  # 고정 릴리스와 같은 순서
    v["acquisition_tasks"] = abox["acquisition_tasks"]
    v["_integrity"] = []
    for k in ("_rule_override", "_capability_override"):
        if k in abox:
            v[k] = abox[k]
    return v


def view(abox, release_id):
    """고정 릴리스가 읽는 내용만 돌려준다. 목록 밖 주장은 나중에 추가돼도 보이지 않는다(K15)."""
    rel = next(r for r in abox["releases"] if r["id"] == release_id)
    members = rel["members"]
    sel = _select(abox, members)
    integrity = []
    for k in SECTIONS:
        have = {x["id"] for x in sel[k]}
        for mid in members.get(k, []):
            if mid not in have:
                integrity.append(("K15", mid, f"{release_id} 구성원이 저장소에 없음"))
    rules = _rule_files(sel["assertions"])
    if rules != rel["rule_files"]:
        integrity.append(("K15", release_id, "규칙 파일 해시가 고정값과 다름"))
    elif content_hash(sel, rules) != rel["content_sha256"]:
        integrity.append(("K15", release_id, "구성원 내용이 제자리에서 바뀜(내용 해시 불일치)"))
    v = copy.deepcopy(sel)
    v["acquisition_tasks"] = abox["acquisition_tasks"]
    v["_integrity"] = integrity
    for k in ("_rule_override", "_capability_override"):
        if k in abox:
            v[k] = abox[k]
    return v


def current_assertions(v):
    pool = v["assertions"]
    superseded = {a["supersedes"] for a in pool if a.get("supersedes")}
    return [a for a in pool if a["id"] not in superseded], pool


def edition_status(v, cur):
    """판마다: 구성 부분별 덮임 여부, 검수 없는 지문 불일치, 상태(confirmed / identity_unconfirmed)."""
    segs = {s["id"]: s for s in v["segments"]}
    out = {}
    for e in v["terms_editions"]:
        parts = [(p["fingerprint"]["rule"], p["fingerprint"]["sha256"]) for p in e.get("parts", [])]
        covered, mismatch, acc = set(), [], []
        for a in cur:
            if a["predicate"] != "realizes" or a["object"] != e["id"] or a["review_status"] != "accepted" or a["subject"] not in segs:
                continue
            acc.append(a["id"])
            fp = segs[a["subject"]].get("fingerprint") or {}
            key = (fp.get("rule"), fp.get("sha256"))
            reviewed = (a.get("decision") or {}).get("by") == "review_decision"
            if key in parts:
                covered.add(key)
            elif any(r == key[0] for r, _ in parts):
                if reviewed and (a.get("decision") or {}).get("covers"):
                    covered.add(tuple(a["decision"]["covers"]))
                else:
                    mismatch.append((a["id"], "같은 정규화 규칙에서 지문이 다름(내용 차이 후보)"))
            else:
                if reviewed and (a.get("decision") or {}).get("covers"):
                    covered.add(tuple(a["decision"]["covers"]))
                else:
                    mismatch.append((a["id"], f"정규화 규칙이 달라 지문 비교 불가({key[0]})"))
        missing = [p for p in parts if p not in covered]
        state = "confirmed" if acc and not missing and not mismatch else "identity_unconfirmed"
        out[e["id"]] = {"accepted_realizes": acc, "missing": missing, "unreviewed_mismatch": mismatch, "state": state}
    return out


def terms_clauses(v, cur):
    """약관 구획에 있고, 그 구획이 accepted realizes로 본문 판에 이어진 조항 → 판 ID."""
    segs = {s["id"]: s for s in v["segments"]}
    realized = {a["subject"]: a["object"] for a in cur if a["predicate"] == "realizes" and a["review_status"] == "accepted"}
    out = {}
    for c in v["clauses"]:
        s = segs.get(c["segment"])
        if s and s["doc_role"] in TERMS_ROLES and c["segment"] in realized:
            out[c["id"]] = realized[c["segment"]]
    return out


# ---------- KCD 코드 소속(입력 단계) ----------
def parse_code(c):
    m = re.fullmatch(r"([A-Z])(\d\d)(?:\.(\d+))?", c)
    if not m:
        raise ValueError("코드 형식: " + c)
    return m.group(1), int(m.group(2)), m.group(3)


def in_range(code, rng):
    L, major, minor = parse_code(code)
    if "-" in rng:
        a, b = rng.split("-")
        La, ma, _ = parse_code(a)
        Lb, mb, _ = parse_code(b)
        return L == La == Lb and ma <= major <= mb
    Lr, mr, nr = parse_code(rng)
    if L != Lr or major != mr:
        return False
    return nr is None or (minor is not None and minor.startswith(nr))


def node(abox, nid):
    return next((n for n in abox["nodes"] if n["id"] == nid), None)


def membership(abox, cur, cat_id, code, trail):
    """True/False/None(판정 불가)와 근거 주장 목록을 trail에 쌓는다."""
    inc = [a for a in cur if a["subject"] == cat_id and a["predicate"] == "includes_codes"]
    exc = [a for a in cur if a["subject"] == cat_id and a["predicate"] == "excludes_codes"]
    if not inc:
        return None
    unknown = False

    def contains(obj_id, a):
        if obj_id is None:
            return None
        n = node(abox, obj_id)
        if n["class"] == "CodeSet":
            return any(in_range(code, r) for r in n["ranges"])
        return membership(abox, cur, obj_id, code, trail)

    included = False
    for a in inc:
        if a["review_status"] != "accepted":
            unknown = True
            trail.append((a["id"], "판정 불가(" + a["review_status"] + ")"))
            continue
        r = contains(a["object"], a)
        if r is None:
            unknown = True
        elif r:
            included = True
            trail.append((a["id"], f"{code} ∈ {node(abox, cat_id)['label']}의 포함 범위"))
    for a in exc:
        if a["review_status"] != "accepted":
            unknown = True
            continue
        r = contains(a["object"], a)
        if r is None:
            unknown = True
        elif r:
            trail.append((a["id"], f"{code}는 {node(abox, cat_id)['label']}에서 제외"))
            return False
        else:
            trail.append((a["id"], f"{code}는 {node(abox, cat_id)['label']}의 제외 대상 아님"))
    if unknown and not included:
        return None
    if unknown:
        return None
    return included


# ---------- 일관성 제약 ----------
def check_constraints(abox):
    """abox는 view() 또는 candidate_view()의 결과."""
    cur, pool = current_assertions(abox)
    terms = terms_clauses(abox, cur)
    v = list(abox.get("_integrity", []))
    # K1
    for a in cur:
        if a["criticality"] == "C0" and a["review_status"] == "accepted":
            if a["predicate"] in STRUCTURAL:
                if not any(e["role"] == "observation" for e in a["evidence"]):
                    v.append(("K1", a["id"], "구조 주장에 관측 근거가 없음"))
                continue
            if not any(e["role"] == "basis" and e["ref"] in terms for e in a["evidence"]):
                v.append(("K1", a["id"], "C0 accepted인데 약관 본문 판에 이어진 basis 근거가 없음"))
    # K2
    for a in cur:
        if a["predicate"] == "same_benefit_as":
            docs = {terms[e["ref"]] for e in a["evidence"] if e["role"] == "basis" and e["ref"] in terms}
            if len(docs) < 2:
                v.append(("K2", a["id"], "same_benefit_as에 양쪽 약관 대조 근거가 없음"))
    # K3
    for n in abox["nodes"]:
        if n["class"] == "CodeSet":
            for k in ("code_system", "edition", "effective", "judged_as_of"):
                if not n.get(k):
                    v.append(("K3", n["id"], f"코드 집합에 {k} 없음"))
    # K4 (narrower 순환)
    edges = [(a["subject"], a["object"]) for a in cur if a["predicate"] == "scope_relation" and a.get("value") == "narrower"]
    for s, o in edges:
        if (o, s) in edges:
            v.append(("K4", s, "narrower 순환"))
    # K5
    for a in pool:
        t = a.get("time", {})
        if t.get("valid_from") and t.get("valid_to") and t["valid_from"] > t["valid_to"]:
            v.append(("K5", a["id"], "valid_from > valid_to"))
    for n in abox["nodes"]:
        if n["class"] == "Condition" and n.get("anchor") and n["anchor"] not in ANCHORS:
            v.append(("K5", n["id"], "기산 시점이 어휘에 없음"))
    # K6
    for n in abox["nodes"]:
        if n["class"] == "Condition" and n.get("duration") and n["duration"]["unit"] not in UNITS:
            v.append(("K6", n["id"], "기간 단위가 원문 단위 어휘에 없음"))
    for a in cur:
        if a["predicate"] == "same_duration_as":
            d1, d2 = node(abox, a["subject"])["duration"], node(abox, a["object"])["duration"]
            if d1["unit"] != d2["unit"]:
                v.append(("K6", a["id"], "단위가 다른 기간을 같다고 주장"))
    # K7
    for a in cur:
        if a["predicate"] == "has_condition" and a["value_state"] == "observed":
            n = node(abox, a["object"])
            if n["kind"] == "감액" and n.get("value") != "없음" and not n.get("applies_to"):
                v.append(("K7", a["id"], "감액 적용 대상 없음"))
    # K8
    blob = json.dumps({k: abox[k] for k in SECTIONS}, ensure_ascii=False)
    for p in PRIVATE_PREFIX:
        if p in blob:
            v.append(("K8", p, "공개 영역에 개인 영역 식별자"))
    # K9
    for a in cur:
        if a["predicate"] == "implemented_by" and a["review_status"] == "accepted":
            rule = json.load(open(os.path.join(ROOT, a["rule_path"]), encoding="utf-8"))
            cov = a["subject"]
            basis = set()
            covered = {cov} | {x["object"] for x in cur if x["subject"] == cov and x["predicate"] == "uses_definition"}
            frontier = list(covered)
            while frontier:  # 범주 트리까지
                s = frontier.pop()
                for x in cur:
                    if x["subject"] == s and x["predicate"] in ("includes_codes", "excludes_codes") and x["object"] and node(abox, x["object"])["class"] == "DiseaseCategory":
                        if x["object"] not in covered:
                            covered.add(x["object"]); frontier.append(x["object"])
            for x in cur:
                if x["subject"] in covered and x["criticality"] == "C0" and x["review_status"] == "accepted":
                    basis |= {e["ref"] for e in x["evidence"] if e["role"] == "basis"}
            extra = set(rule["evidence_refs"]) - basis
            if extra:
                v.append(("K9", a["id"], "규칙 근거가 담보의 C0 basis 밖: " + ",".join(sorted(extra))))
    # K10
    targets = {}
    for a in pool:
        if a.get("supersedes"):
            targets.setdefault(a["supersedes"], []).append(a["id"])
    for t, ss in targets.items():
        if len(ss) > 1 and not any(set(c.get("assertions", [])) >= set(ss) for c in abox["conflicts"]):
            v.append(("K10", t, "같은 주장을 둘이 대체하는데 충돌 기록 없음"))
    # K11
    for cov in [n["id"] for n in abox["nodes"] if n["class"] == "CoverageOccurrence"]:
        cap = abox.get("_capability_override", {}).get(cov)  # 자체 시험용
        if cap == "enabled" and not simulate_allowed(abox, cur, cov)[0]:
            v.append(("K11", cov, "hold·충돌이 있는데 simulate enabled"))
    # K12
    for a in cur:
        if a["predicate"] == "scope_relation":
            got = scope_relation(abox, cur, a["subject"], a["object"])
            if got == "not_comparable":
                if a["review_status"] == "accepted":
                    v.append(("K12", a["id"], "계산할 수 없는 쌍의 범위 관계가 accepted"))
            elif got != a.get("value"):
                v.append(("K12", a["id"], f"주장 {a.get('value')} ≠ 계산 {got}"))
    # K13 원시 관측은 조건이 비어도 보존한다. 비교 자격(comparison_eligible)을 주려면 조건·구성·기준일이 있어야 한다
    for p in abox.get("premium_observations", []):
        if p.get("comparison_eligible"):
            for k in ("conditions", "package_binding", "as_of"):
                if not p.get(k):
                    v.append(("K13", p["id"], f"비교 자격이 있는 가격 관측에 {k} 없음"))
    # K14
    segs = {s["id"]: s for s in abox["segments"]}
    for a in cur:
        if a["predicate"] == "realizes" and a["review_status"] == "accepted":
            s = segs.get(a["subject"])
            fp = (s or {}).get("fingerprint") or {}
            if not (fp.get("rule") and fp.get("sha256")):
                v.append(("K14", a["id"], "본문 지문 없는 구획으로 본문 판을 확정"))
            elif not any(e["role"] == "observation" and e["ref"] == a["subject"] for e in a["evidence"]):
                v.append(("K14", a["id"], "구획 관측 근거 없이 본문 판을 확정"))
            elif (a.get("decision") or {}).get("by") not in ("review_decision", "fixture_assumption"):
                v.append(("K14", a["id"], f"승인 결정이 검수 결정이 아님({(a.get('decision') or {}).get('by')})"))
    # K16 판의 구성과 근거 묶음(재검토 R01). 근거 묶음 = 그 판을 실현한다는 accepted realizes 전부(원본 수와 무관).
    #  - 구획 지문이 구성의 한 부분과 같은 규칙·같은 값이면 그 부분을 덮는다.
    #  - 같은 규칙에서 값이 다르면 "내용 차이 후보", 규칙이 다르면(OCR·정규화 판) "비교 불가". 둘 다 검수 결정(review_decision)
    #    없이는 같은 판으로 accepted가 될 수 없다. 다른 판이라고 확정하는 것도 검사기가 아니라 검수 결정이다.
    #  - 근거 묶음이 구성 일부를 덮지 못하면(별표 미확보) 동일성 미확인이다. 그 판의 realizes는 accepted일 수 없다(hold).
    for ed_id, st in edition_status(abox, cur).items():
        for aid, why in st["unreviewed_mismatch"]:
            v.append(("K16", aid, why + ": 검수 결정 없이 같은 판으로 승인할 수 없음"))
        if st["accepted_realizes"] and st["missing"]:
            v.append(("K16", ed_id, f"근거 묶음이 판의 구성 {len(st['missing'])}개를 덮지 못함(동일성 미확인, hold여야 함)"))
    return v


# ---------- 범위 관계(코드 집합에서 계산) ----------
def universe():
    codes = [f"C{n:02d}" for n in range(0, 98)] + [f"D{n:02d}" for n in range(0, 49)]
    codes += [f"D47.{k}" for k in range(10)] + ["C16.2", "D00.2"]
    return codes


def scope_relation(abox, cur, c1, c2):
    a, b = set(), set()
    for code in universe():
        m1 = membership(abox, cur, c1, code, [])
        m2 = membership(abox, cur, c2, code, [])
        if m1 is None or m2 is None:
            return "not_comparable"
        if m1: a.add(code)
        if m2: b.add(code)
    if a == b: return "same_scope"
    if a < b: return "narrower"
    if a > b: return "broader"
    if a & b: return "overlaps"
    return "disjoint"


# ---------- capability ----------
def related_c0(abox, cur, cov):
    ids = {cov}
    cats = [a["object"] for a in cur if a["subject"] == cov and a["predicate"] == "uses_definition"]
    stack = list(cats)
    while stack:
        c = stack.pop()
        if c in ids: continue
        ids.add(c)
        for a in cur:
            if a["subject"] == c and a["predicate"] in ("includes_codes", "excludes_codes") and a["object"] and node(abox, a["object"])["class"] == "DiseaseCategory":
                stack.append(a["object"])
    return [a for a in cur if a["subject"] in ids and a["criticality"] == "C0"]


def simulate_allowed(abox, cur, cov):
    bad = [a["id"] + ":" + a["review_status"] for a in related_c0(abox, cur, cov) if a["review_status"] != "accepted"]
    if not any(a["subject"] == cov and a["predicate"] == "implemented_by" and a["review_status"] == "accepted" for a in cur):
        bad.append("implemented_by 없음")
    conflicted = [c for c in abox["conflicts"] if c.get("state") != "resolved" and any(x["subject"] == cov for x in cur if x["id"] in c.get("assertions", []))]
    if conflicted:
        bad.append("미해소 충돌")
    return (not bad), bad


def applicable_links(abox, cur, configs, contract_date):
    """가입일에 적용되는 (판매 구성, uses_edition 주장) 전부. 후보 목록 순서와 무관하도록 정렬해 돌려준다."""
    hits = []
    for sc in sorted(set(configs)):
        for a in cur:
            if a["subject"] == sc and a["predicate"] == "uses_edition":
                t = a.get("time", {})
                if (not t.get("valid_from") or t["valid_from"] <= contract_date) and (not t.get("valid_to") or contract_date <= t["valid_to"]):
                    hits.append((sc, a))
    return hits


# ---------- 질문 → 조회 → 실행 → 설명 ----------
QUESTIONS = [
    {"id": "Q1", "text": "가입 2026-08-20, 2027-04-20 위암(C16) 진단, 처음 받는 진단금. 하나 2-1은?", "configs": ["sc:hana_2601_3d_v20260701", "sc:hana_2601_3d_v20260101"], "cov": "cov:hana_2_1",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2027-04-20", "dx_code": "C16"}, "assume": {"policy_end_date": "2046-08-20", "already_paid": False, "is_initial_contract": True, "renewal_date": None, "insured_amount_krw": 10000000},
     "expect": {"kind": "payable", "krw": 5000000}},
    {"id": "Q2", "text": "같은 계약, 2028-08-20(가입 후 2년) 진단", "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2028-08-20", "dx_code": "C16"}, "assume": {"policy_end_date": "2046-08-20", "already_paid": False, "is_initial_contract": True, "renewal_date": None, "insured_amount_krw": 10000000},
     "expect": {"kind": "payable", "krw": 10000000}},
    {"id": "Q3", "text": "같은 계약, 2026-11-17 진단(계약일 포함 90일째, 보장개시 전날)", "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2026-11-17", "dx_code": "C16"}, "assume": {"policy_end_date": "2046-08-20", "already_paid": False, "is_initial_contract": True, "renewal_date": None, "insured_amount_krw": 10000000},
     "expect": {"kind": "not_payable"}, "note_gap": "제5조: 보장개시 전 진단이면 보장 무효·보험료 반환(계약 효과). rule-0.1은 계약 효과를 표현하지 못한다(G23)"},
    {"id": "Q3b", "text": "같은 계약, 2026-11-18 진단(보장개시일 당일)", "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2026-11-18", "dx_code": "C16"}, "assume": {"policy_end_date": "2046-08-20", "already_paid": False, "is_initial_contract": True, "renewal_date": None, "insured_amount_krw": 10000000},
     "expect": {"kind": "payable", "krw": 5000000}},
    {"id": "Q4", "text": "같은 계약, 2027-04-20 유방암(C50) 진단", "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2027-04-20", "dx_code": "C50"}, "assume": {"policy_end_date": "2046-08-20", "already_paid": False, "is_initial_contract": True, "renewal_date": None, "insured_amount_krw": 10000000},
     "expect": {"kind": "not_payable"}},
    {"id": "Q5", "text": "같은 계약, 2027-04-20 위 쪽 암이라고 들었지만 코드 모름", "configs": ["sc:hana_2601_3d_v20260701"], "cov": "cov:hana_2_1",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2027-04-20", "dx_code": None}, "assume": {"policy_end_date": "2046-08-20", "already_paid": False, "is_initial_contract": True, "renewal_date": None, "insured_amount_krw": 10000000},
     "expect": {"kind": "undetermined", "krw": 5000000}},
    {"id": "Q6", "text": "가입 2026-08-20, 2027-04-20 위암(C16). 현대 2-5는?", "configs": ["sc:hi2607_general"], "cov": "cov:hi_2_5",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2027-04-20", "dx_code": "C16"}, "assume": {"policy_end_date": "2126-08-20", "already_paid": False, "insured_amount_krw": 10000000},
     "expect": {"kind": "payable", "krw": 10000000}},
    {"id": "Q7", "text": "현대 2-5, 위 제자리암(D00.2)", "configs": ["sc:hi2607_general"], "cov": "cov:hi_2_5",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2027-04-20", "dx_code": "D00.2"}, "assume": {"policy_end_date": "2126-08-20", "already_paid": False, "insured_amount_krw": 10000000},
     "expect": {"kind": "not_payable"}},
    {"id": "Q8", "text": "현대 2-5, 유방암(C50)", "configs": ["sc:hi2607_general"], "cov": "cov:hi_2_5",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2027-04-20", "dx_code": "C50"}, "assume": {"policy_end_date": "2126-08-20", "already_paid": False, "insured_amount_krw": 10000000},
     "expect": {"kind": "payable", "krw": 10000000}},
    {"id": "Q9", "text": "롯데 2604 1종 일반암진단비, 위암(C16)", "configs": ["sc:lotte_2604_type1"], "cov": "cov:lotte_general_dx",
     "facts": {"contract_date": "2026-08-20", "diagnosis_date": "2027-04-20", "dx_code": "C16"}, "assume": {},
     "expect": {"kind": "blocked"}},
    {"id": "Q10", "text": "하나 같은 이름 상품, 가입 2026-03-15(이전 판매본), 위암(C16)", "configs": ["sc:hana_2601_3d_v20260701", "sc:hana_2601_3d_v20260101"], "cov": "cov:hana_2_1",
     "facts": {"contract_date": "2026-03-15", "diagnosis_date": "2027-01-10", "dx_code": "C16"}, "assume": {},
     "expect": {"kind": "blocked"}}
]


def resolve(abox, q):
    cur, _ = current_assertions(abox)
    steps = []
    hits = applicable_links(abox, cur, q["configs"], q["facts"]["contract_date"])
    if not hits:
        steps.append("판매본: 가입일에 적용되는 판매본을 찾지 못함")
        return {"blocked": ["판매본 미확인"], "steps": steps}
    configs = sorted({sc for sc, _ in hits})
    if len(configs) > 1:
        # 모호함은 "판매 구성이 여럿"일 때다. 한 판매 구성이 여러 약관 판(보통약관·특약)을 쓰는 것은 정상이다(재검토 S01)
        steps.append("판매본: 가입일에 적용되는 판매 구성이 여럿 → 계산하지 않음(" + ", ".join(configs) + ")")
        return {"blocked": ["판매본 후보 복수: " + ",".join(configs)], "steps": steps}
    sc = configs[0]
    steps.append(f"판매본: {node(abox, sc)['label']}")
    cov_eds = sorted({a["object"] for a in cur if a["subject"] == q["cov"] and a["predicate"] == "in_edition" and a["review_status"] == "accepted"})
    used = {}
    for _, a in hits:
        used.setdefault(a.get("object"), []).append(a)
    # 요청 담보가 정의된 판 중, 이 판매 구성이 가입일에 쓰는 판
    cand = [ed for ed in cov_eds if ed in used]
    unresolved = [a for ed, links in used.items() for a in links if ed is None or a["review_status"] != "accepted"]
    if not cand:
        if unresolved:
            steps.append("  이 판매본의 약관 판이 확인되지 않음 → 계산하지 않음")
            return {"blocked": [a["id"] + ":" + a["review_status"] for a in unresolved], "steps": steps, "config": sc}
        steps.append(f"  요청한 담보 {q['cov']}가 이 판매본이 쓰는 약관 판 {sorted(k for k in used if k)}에 정의되어 있지 않음(담보의 판 {cov_eds or '없음'}) → 계산하지 않음")
        return {"blocked": [f"{q['cov']}∉{sorted(k for k in used if k)}"], "steps": steps, "config": sc}
    if len(cand) > 1:
        steps.append(f"  요청한 담보가 이 판매본이 쓰는 판 여럿에 정의됨 {cand} → 계산하지 않음")
        return {"blocked": [f"{q['cov']}: 판 후보 복수 {cand}"], "steps": steps, "config": sc}
    ed = cand[0]
    link = sorted(used[ed], key=lambda a: a["id"])[0]
    if any(a["review_status"] != "accepted" for a in used[ed]):
        bad = [a["id"] + ":" + a["review_status"] for a in used[ed] if a["review_status"] != "accepted"]
        steps.append(f"  판 {ed} 연결 주장 중 승인되지 않은 것이 있음 → 계산하지 않음")
        return {"blocked": bad, "steps": steps, "config": sc}
    steps.append(f"  적용 약관 판: {ed} ← {', '.join(a['id'] for a in sorted(used[ed], key=lambda a: a['id']))}({link['value_state']}/{link['review_status']})")
    est = edition_status(abox, cur).get(ed, {"state": "identity_unconfirmed"})
    if est["state"] != "confirmed":
        steps.append(f"  약관 판 {ed}의 동일성이 확인되지 않음(근거 묶음 부족 또는 검수 없는 지문 차이) → 계산하지 않음")
        return {"blocked": [f"{ed}:identity_unconfirmed"], "steps": steps, "config": sc}
    steps.append(f"  담보 연결: {q['cov']} ∈ {ed}")
    ok, why = simulate_allowed(abox, cur, q["cov"])
    steps.append(f"담보: {node(abox, q['cov'])['label']} · simulate {'enabled' if ok else 'blocked'}" + ("" if ok else " ← " + ", ".join(why)))
    if not ok:
        return {"blocked": why, "steps": steps, "config": sc}
    cat = next(a["object"] for a in cur if a["subject"] == q["cov"] and a["predicate"] == "uses_definition")
    trail = []
    code = q["facts"]["dx_code"]
    m = None if code is None else membership(abox, cur, cat, code, trail)
    steps.append(f"질병 범주: {node(abox, cat)['label']} · 코드 {code} → {m}")
    for aid, msg in trail:
        steps.append(f"  {msg} ← {aid}")
    rule_a = next(a for a in cur if a["subject"] == q["cov"] and a["predicate"] == "implemented_by")
    inputs = dict(q["assume"])
    inputs.update({"contract_date": q["facts"]["contract_date"], "diagnosis_date": q["facts"]["diagnosis_date"], "dx_in_category": m})
    rule = json.load(open(os.path.join(ROOT, rule_a["rule_path"]), encoding="utf-8"))
    inputs = {k: inputs.get(k) for k in rule["inputs"]}
    return {"steps": steps, "config": sc, "category": cat, "membership": m, "trail": trail, "rule_path": os.path.join(ROOT, rule_a["rule_path"]), "rule_assertion": rule_a["id"], "inputs": inputs}


def serve_block(abox, release_id, q):
    """서비스 사용 제한(운영 상태). 재현(resolve)과 별개로 작동한다."""
    hits = [n for n in abox.get("release_notices", []) if n["release"] == release_id and q["cov"] in n["affects"] and n["state"] == "restricted"]
    return [f"{n['id']}: {n['reason']}" for n in hits]


def run_engine(runner, jobs):
    p = subprocess.run([runner], input=json.dumps(jobs), capture_output=True, text=True, check=True)
    return {r["case_id"]: r for r in json.loads(p.stdout)}


def explain(abox, q, res, ev):
    cur, _ = current_assertions(abox)
    clauses = {c["id"]: c for c in abox["clauses"]}
    segs = {s["id"]: s for s in abox["segments"]}
    raws = {r["id"]: r for r in abox["raw_assets"]}
    terms = terms_clauses(abox, cur)

    def where(c):
        s = segs[c["segment"]]
        r = raws[s["raw_asset"]]
        ed = terms.get(c["id"], "본문 판 미연결")
        return f"{c['path']} · 판 {ed} · 구획 {s['id']}({s['doc_role']}) 지문 {s['fingerprint']['sha256'][:12]} · 원본 sha256 {r['sha256'][:12]} PDF {c['pdf_page']}쪽"
    lines = []
    if "blocked" in res:
        lines.append("결과: 이 상황의 지급액 확인 필요(계산하지 않음)")
        about = {res.get("config"), q["cov"]} | {a["object"] for a in cur if a["subject"] == q["cov"] and a["predicate"] == "uses_definition"}
        gaps = [g for g in abox["gaps"] if g["about"] in about]
        lines.append("  막은 것: " + ", ".join(res["blocked"]))
        for g in gaps:
            lines.append(f"  공백 {g['id']}: {g['question']} · 지식 상태 {g['knowledge_state']} · 필요한 근거: {g['needed_evidence']}")
            for t in g["tasks"]:
                tk = next(x for x in abox["acquisition_tasks"] if x["id"] == t)
                lines.append(f"    확보 작업 {t}: {tk['kind']} · {tk['state']}")
        return lines
    p = ev["payout"]
    if p["kind"] == "payable":
        amt = p["amount"]
        lines.append(f"결과: {amt['krw']:,}원 (약관 기준 계산, 가정: {', '.join(k for k in q['assume'] if k in ('already_paid','policy_end_date','insured_amount_krw'))})")
    elif p["kind"] == "not_payable":
        lines.append("결과: 이 담보에서는 지급 대상이 아님")
    else:
        ca = p["conditional_amount"]
        lines.append(f"결과: 판단 불가 · 대상이라면 {ca.get('krw', 0):,}원 · 빠진 입력 {ev['missing_inputs']}")
    lines.append(f"  규칙 {ev['rule_id']} {ev['rule_version']} 해시 {ev['rule_content_hash'][:12]} ({ev['publication_state']}) · 엔진 {ev['engine_version']} · 입력 해시 {ev['input_snapshot_hash'][:12]}")
    if res.get("trail"):
        lines.append("  입력 단계 판정(dx_in_category)의 근거:")
        seen = set()
        for aid, msg in res["trail"]:
            a = next(x for x in cur if x["id"] == aid)
            for e in a["evidence"]:
                if e["role"] != "basis" or (aid, e["ref"]) in seen:
                    continue
                seen.add((aid, e["ref"]))
                c = clauses[e["ref"]]
                lines.append(f"    {msg} ← 주장 {aid} → {where(c)}")
    lines.append("  실행 규칙의 근거:")
    for ref in ev["evidence_refs"]:
        c = clauses[ref]
        backing = [a["id"] for a in cur if any(e["ref"] == ref and e["role"] == "basis" for e in a["evidence"])]
        lines.append(f"    근거 {ref} → 주장 {','.join(backing)} → {where(c)}")
    if q.get("note_gap"):
        lines.append("  남은 공백: " + q["note_gap"])
    return lines


def outcome(res, ev):
    if "blocked" in res:
        return {"kind": "blocked"}
    p = ev["payout"]
    if p["kind"] == "payable":
        return {"kind": "payable", "krw": p["amount"].get("krw")}
    if p["kind"] == "undetermined":
        return {"kind": "undetermined", "krw": p["conditional_amount"].get("krw")}
    return {"kind": "not_payable"}


# ---------- 자체 시험(변조) ----------
def mutations():
    """제약마다 일부러 깨뜨린 저장소. 릴리스 후보(candidate_view)로 검사한다."""
    M = []
    def m(cid, f):
        a = copy.deepcopy(ABOX); f(a); M.append((cid, a))
    def set_a(a, aid, **kw):
        next(x for x in a["assertions"] if x["id"] == aid).update(kw)
    def seg(a, sid):
        return next(x for x in a["segments"] if x["id"] == sid)
    m("K1", lambda a: set_a(a, "a:lotte_cov_def", review_status="accepted"))
    m("K2", lambda a: a["assertions"].append({"id": "a:bad_same", "subject": "cov:hana_2_1", "predicate": "same_benefit_as", "object": "cov:hi_2_5", "criticality": "C0", "evidence": [{"ref": "hana_2601_3d#c_2_1_art1_1", "role": "basis"}], "value_state": "observed", "review_status": "accepted"}))
    m("K3", lambda a: next(n for n in a["nodes"] if n["id"] == "codes:c44").pop("edition"))
    m("K4", lambda a: a["assertions"].extend([
        {"id": "a:n1", "subject": "cat:lotte_general_cancer", "predicate": "scope_relation", "object": "cat:hana_cancer_x_breast_genital", "value": "narrower", "criticality": "C1", "evidence": [{"ref": "lotte_2604_smry#term_general_cancer", "role": "cross_check"}], "value_state": "observed", "review_status": "hold"},
        {"id": "a:n2", "subject": "cat:hana_cancer_x_breast_genital", "predicate": "scope_relation", "object": "cat:lotte_general_cancer", "value": "narrower", "criticality": "C1", "evidence": [{"ref": "lotte_2604_smry#term_general_cancer", "role": "cross_check"}], "value_state": "observed", "review_status": "hold"}]))
    m("K5", lambda a: set_a(a, "a:hana_old_doc_link", time={"valid_from": "2026-04-01", "valid_to": "2026-03-31"}))
    m("K6", lambda a: (next(n for n in a["nodes"] if n["id"] == "cond:hi_waiting")["duration"].update(unit="calendar_month", value=3),
                       a["assertions"].append({"id": "a:same_dur", "subject": "cond:hana_waiting", "predicate": "same_duration_as", "object": "cond:hi_waiting", "criticality": "C1", "evidence": [], "value_state": "derived", "review_status": "accepted"})))
    m("K7", lambda a: next(n for n in a["nodes"] if n["id"] == "cond:hana_reduction").pop("applies_to"))
    m("K8", lambda a: set_a(a, "a:hana_cov_def", note="contract:abc123 에서 확인"))
    m("K9", lambda a: a.__setitem__("_rule_override", True))
    m("K10", lambda a: a["assertions"].append(dict(next(x for x in a["assertions"] if x["id"] == "a:lotte_cond_waiting_v2"), id="a:lotte_cond_waiting_v3")))
    m("K11", lambda a: a.__setitem__("_capability_override", {"cov:lotte_general_dx": "enabled"}))
    m("K12", lambda a: a["assertions"].append({"id": "a:wrong_scope", "subject": "cat:hana_cancer_x_breast_genital", "predicate": "scope_relation", "object": "cat:hi_cancer_x_similar", "value": "same_scope", "criticality": "C1", "evidence": [], "value_state": "derived", "review_status": "accepted"}))
    m("K13", lambda a: a.setdefault("premium_observations", []).append({"id": "p:hana_bundle", "krw": 16598, "priced_for": "sc:hana_2601_3d_v20260701", "conditions": None, "package_binding": "source_bundle", "as_of": None, "comparison_eligible": True}))
    m("K14", lambda a: set_a(a, "a:realizes_hana_r2_1", decision={"by": "fingerprint_match"}))
    m("K16", lambda a: seg(a, "seg:hana_annex12").__setitem__("fingerprint", {"rule": "fp-0.1", "sha256": "e" * 64}))
    return M


def with_bad_rule(mutated, fn):
    rp = os.path.join(ROOT, "규칙", "hana-2601-3d-cancer-dx.json")
    bad = json.loads(open(rp, encoding="utf-8").read())
    bad["evidence_refs"].append("hana_2601_3d#c_2_1_art5")
    tmp = os.path.join(ROOT, "규칙", "_tmp_bad.json")
    open(tmp, "w", encoding="utf-8").write(json.dumps(bad, ensure_ascii=False))
    try:
        next(x for x in mutated["assertions"] if x["id"] == "a:hana_rule")["rule_path"] = "규칙/_tmp_bad.json"
        return fn()
    finally:
        os.remove(tmp)


def answer(v, runner, qid):
    q = next(x for x in QUESTIONS if x["id"] == qid)
    r = resolve(v, q)
    ev = None
    if "blocked" not in r:
        ev = run_engine(runner, [{"case_id": q["id"], "rule_path": r["rule_path"], "inputs": r["inputs"]}])[q["id"]]
    return outcome(r, ev)


def run_all(v, runner):
    """모든 질문의 결과와 설명 문장. 재현 비교용."""
    jobs, res = [], {}
    for q in QUESTIONS:
        r = resolve(v, q)
        res[q["id"]] = r
        if "blocked" not in r:
            jobs.append({"case_id": q["id"], "rule_path": r["rule_path"], "inputs": r["inputs"]})
    evs = run_engine(runner, jobs) if jobs else {}
    out = {}
    for q in QUESTIONS:
        r, ev = res[q["id"]], evs.get(q["id"])
        out[q["id"]] = (outcome(r, ev), r["steps"] + explain(v, q, r, ev))
    return out


def realizes(sid, ed, by="fixture_assumption"):
    return {"id": "a:realizes_" + sid.split(":")[1], "subject": sid, "predicate": "realizes", "object": ed, "criticality": "C0",
            "evidence": [{"ref": sid, "role": "observation"}], "value_state": "observed", "review_status": "accepted", "origin": "fixture", "decision": {"by": by}}


def repack(a, tag, change=None, drop=None):
    """하나 2-1 판의 세 구획(본문·별표1·별표12)을 담은 합성 원본을 하나 더 넣는다."""
    a["raw_assets"].append({"id": f"raw:synthetic_{tag}", "class": "RawAsset", "observed_label": f"자체 시험용 합성 원본({tag})", "org": "org:hana_nonlife", "sha256": tag[0] * 64, "source": "합성", "observed_at": None})
    for k, sid in enumerate(("seg:hana_r2_1", "seg:hana_annex1", "seg:hana_annex12")):
        if sid == drop:
            continue
        base = copy.deepcopy(next(x for x in a["segments"] if x["id"] == sid))
        nid = f"seg:synthetic_{tag}_{k}"
        base.update(id=nid, raw_asset=f"raw:synthetic_{tag}", pages=[10 + k, 10 + k])
        if sid == change:
            base["fingerprint"] = {"rule": "fp-0.1", "sha256": "f" * 64}
        a["segments"].append(base)
        a["assertions"].append(realizes(nid, "ted:hana_r2_1@2607"))


def release_tests(runner):
    """릴리스 고정(K15), 재현과 사용 제한의 분리, 판의 구성(K14·K16). (이름, 종류, 통과, 설명)."""
    out = []
    frozen_cur = next(r for r in ABOX["releases"] if r["id"] == CURRENT)
    n25 = len(frozen_cur["members"]["assertions"])
    base = run_all(view(ABOX, CURRENT), runner)

    # I1 나중에 추가된 주장은 과거 릴리스에 들어가지 않는다
    a = copy.deepcopy(ABOX)
    old = next(x for x in a["assertions"] if x["id"] == "a:hana_doc_link")
    a["assertions"].append(dict(old, id="a:hana_doc_link_v2", supersedes="a:hana_doc_link", review_status="hold", hold_reason="reference_unresolved",
                                correction_reason="출처 변경", _review_note="자체 시험: 릴리스 뒤에 들어온 정정"))
    v25 = view(a, CURRENT)
    after, cand = run_all(v25, runner), run_all(candidate_view(a), runner)
    ok = len(v25["assertions"]) == n25 and not check_constraints(v25) and after == base and cand["Q1"][0] == {"kind": "blocked"}
    out.append(("I1 새 주장 추가 후 r26(결과·설명 11개 비교)", "동작", ok, f"r26 주장 {len(v25['assertions'])}개(고정 {n25}) · 결과·설명 동일 {after == base} · 후보 Q1 {cand['Q1'][0]}"))

    # I2~I4 제자리 수정·삭제·규칙 파일 교체
    a = copy.deepcopy(ABOX)
    next(x for x in a["assertions"] if x["id"] == "a:hana_cov_def")["note"] = "제자리 수정"
    vs = check_constraints(view(a, CURRENT))
    out.append(("I2 주장 제자리 수정", "동작", [x[0] for x in vs] == ["K15"], "; ".join(x[2] for x in vs) or "못 잡음"))
    a = copy.deepcopy(ABOX)
    a["assertions"] = [x for x in a["assertions"] if x["id"] != "a:hi_doc_link"]
    vs = check_constraints(view(a, CURRENT))
    out.append(("I3 구성원 삭제", "동작", bool(vs) and all(x[0] == "K15" for x in vs), "; ".join(sorted({x[2] for x in vs})) or "못 잡음"))
    a = copy.deepcopy(ABOX)
    vs = with_bad_rule(a, lambda: check_constraints(view(a, CURRENT)))
    out.append(("I4 규칙 파일 교체", "동작", any(x[0] == "K15" for x in vs), "; ".join(sorted({x[2] for x in vs if x[0] == "K15"})) or "못 잡음"))

    # I5 참조 대상(코드 집합·조건 노드·적용 관계)을 새 판으로 바꿔도 r26의 결과와 근거는 그대로다
    a = copy.deepcopy(ABOX)
    c44 = next(x for x in a["nodes"] if x["id"] == "codes:c44")
    a["nodes"].append(dict(c44, id="codes:c44@v2", ranges=["C44", "C16"], label="C44(자체 시험용 가상 개정)"))
    exc = next(x for x in a["assertions"] if x["id"] == "a:hana_cat_exc_c44")
    a["assertions"].append(dict(exc, id="a:hana_cat_exc_c44_v2", object="codes:c44@v2", supersedes="a:hana_cat_exc_c44", correction_reason="해석 개선"))
    hw = next(x for x in a["nodes"] if x["id"] == "cond:hi_waiting")
    a["nodes"].append(dict(hw, id="cond:hi_waiting@v2", duration={"value": 30, "unit": "day"}))
    hc = next(x for x in a["assertions"] if x["predicate"] == "has_condition" and x["object"] == "cond:hi_waiting")
    a["assertions"].append(dict(hc, id=hc["id"] + "_v2", object="cond:hi_waiting@v2", supersedes=hc["id"], correction_reason="해석 개선"))
    hl = next(x for x in a["assertions"] if x["id"] == "a:hi_doc_link")
    a["assertions"].append(dict(hl, id="a:hi_doc_link_v2", time=dict(hl["time"], valid_to="2026-08-10"), supersedes="a:hi_doc_link", correction_reason="출처 변경"))
    v25 = view(a, CURRENT)
    after, cand = run_all(v25, runner), run_all(candidate_view(a), runner)
    changed = [k for k in cand if cand[k] != base[k]]
    ok = not check_constraints(v25) and after == base and cand["Q1"][0] == {"kind": "not_payable"} and cand["Q6"][0] == {"kind": "blocked"}
    out.append(("I5 코드 집합·조건 노드·적용 관계를 새 판으로 교체", "동작", ok, f"r26 결과·설명 동일 {after == base} · 후보에서 달라진 질문 {changed}"))

    # I6 참조 노드를 제자리에서 바꾸면 잡는다
    a = copy.deepcopy(ABOX)
    next(x for x in a["nodes"] if x["id"] == "codes:c44")["ranges"] = ["C44", "C16"]
    vs = check_constraints(view(a, CURRENT))
    out.append(("I6 참조 노드(코드 집합) 제자리 수정", "동작", [x[0] for x in vs] == ["K15"], "; ".join(x[2] for x in vs) or "못 잡음"))

    # I7 재현과 사용 제한은 따로 작동한다
    a = copy.deepcopy(ABOX)
    a["release_notices"] = [{"id": "notice:t1", "release": CURRENT, "affects": ["cov:hana_2_1"], "state": "restricted", "reason": "자체 시험: r26의 하나 2-1 해석 오류 확인"}]
    v25 = view(a, CURRENT)
    repro = run_all(v25, runner)
    q1 = next(q for q in QUESTIONS if q["id"] == "Q1")
    q6 = next(q for q in QUESTIONS if q["id"] == "Q6")
    ok = repro == base and serve_block(a, CURRENT, q1) and not serve_block(a, CURRENT, q6) and not v25["_integrity"]
    out.append(("I7 사용 제한 공지: 재현은 유지, 영향 담보만 서비스 차단", "동작", bool(ok), f"재현 결과 동일 {repro == base} · Q1 서비스 {serve_block(a, 'rel:case-r26', q1) or '허용'} · Q6 서비스 {serve_block(a, 'rel:case-r26', q6) or '허용'}"))

    # D1 같은 판의 구성 전부를 담은 다른 원본
    a = copy.deepcopy(ABOX)
    repack(a, "repack")
    cv = candidate_view(a)
    cur, _ = current_assertions(cv)
    segs = {x["id"]: x for x in cv["segments"]}
    raws_of = {segs[x["subject"]]["raw_asset"] for x in cur if x["predicate"] == "realizes" and x["object"] == "ted:hana_r2_1@2607"}
    q1 = run_all(cv, runner)["Q1"][0]
    ok = not check_constraints(cv) and len(raws_of) == 2 and q1 == base["Q1"][0]
    out.append(("D1 다른 원본이 판의 구성 전부를 같은 지문으로 담음", "동작", ok, f"판을 담은 원본 {len(raws_of)}개 · 위반 {len(check_constraints(cv))} · Q1 {q1}"))

    # D2 원본 해시만으로 판 확정
    a = copy.deepcopy(ABOX)
    a["assertions"].append({"id": "a:realizes_by_hash", "subject": "seg:hana_annex12", "predicate": "realizes", "object": "ted:hi_r2_5@2608", "criticality": "C0",
                            "evidence": [{"ref": "raw:hana_fd9c0133", "role": "observation"}], "value_state": "observed", "review_status": "accepted", "origin": "fixture", "decision": {"by": "fixture_assumption"}})
    vs = check_constraints(candidate_view(a))
    out.append(("D2 원본 해시만으로 판 확정", "동작", any(x[0] == "K14" for x in vs), "; ".join(x[2] for x in vs if x[0] == "K14") or "못 잡음"))

    # D3 지문 일치를 승인 결정으로 씀
    a = copy.deepcopy(ABOX)
    repack(a, "auto")
    for x in a["assertions"]:
        if x["id"].startswith("a:realizes_synthetic_auto"):
            x["decision"] = {"by": "fingerprint_match"}
    vs = check_constraints(candidate_view(a))
    out.append(("D3 지문 일치를 자동 승인으로 씀", "동작", bool(vs) and all(x[0] == "K14" for x in vs), "; ".join(sorted({x[2] for x in vs})) or "못 잡음"))

    # D4 본문은 같고 참조 별표 내용이 다름(같은 정규화 규칙에서 지문 다름) → 내용 차이 후보. 검수 결정 없이 같은 판 불가
    a = copy.deepcopy(ABOX)
    repack(a, "annexdiff", change="seg:hana_annex12")
    vs = check_constraints(candidate_view(a))
    out.append(("D4 참조 별표 내용 변경(같은 규칙·다른 지문)", "동작", bool(vs) and all(x[0] == "K16" for x in vs) and "내용 차이 후보" in vs[0][2], "; ".join(x[2] for x in vs) or "못 잡음"))

    # D5 재검토 R01 재현: 별표12 구획만 별도 원본으로 옮김 → 근거 묶음이 구성 전부를 덮으므로 위반 없음, 결과 동일
    a = copy.deepcopy(ABOX)
    a["raw_assets"].append({"id": "raw:annex_only", "class": "RawAsset", "observed_label": "자체 시험용 별표 분리 파일", "org": "org:hana_nonlife", "sha256": "9" * 64, "source": "합성", "observed_at": None})
    next(x for x in a["segments"] if x["id"] == "seg:hana_annex12")["raw_asset"] = "raw:annex_only"
    cv = candidate_view(a)
    q1 = run_all(cv, runner)["Q1"][0]
    out.append(("D5 본문·별표가 다른 원본에 나뉨(재검토 R01 재현)", "동작", not check_constraints(cv) and q1 == base["Q1"][0], f"위반 {[x[2] for x in check_constraints(cv)] or 0} · Q1 {q1}"))

    # D8 별표 미확보: accepted로 두면 동일성 미확인 위반, hold로 두면 위반 없이 계산 보류(엔진 호출 0)
    a = copy.deepcopy(ABOX)
    a["assertions"] = [x for x in a["assertions"] if x["id"] != "a:realizes_hana_annex1"]
    vs_acc = check_constraints(candidate_view(a))
    for x in a["assertions"]:
        if x["predicate"] == "realizes" and x["object"] == "ted:hana_r2_1@2607":
            x["review_status"] = "hold"; x["hold_reason"] = "reference_unresolved"
    cv = candidate_view(a)
    res = resolve(cv, next(q for q in QUESTIONS if q["id"] == "Q1"))
    ok = any(x[0] == "K16" and "동일성 미확인" in x[2] for x in vs_acc) and "blocked" in res and any("identity_unconfirmed" in b for b in res["blocked"])
    out.append(("D8 참조 별표 미확보 → 동일성 미확인(다른 판으로 확정하지 않음)", "동작", ok, f"accepted 유지 시 {[x[2] for x in vs_acc if x[0] == 'K16']} · hold 시 Q1 {res.get('blocked')} · 엔진 호출 0"))

    # D9 OCR(정규화 규칙이 다름): 검수 결정 없으면 비교 불가 위반, 검수 결정(covers 지정)이 있으면 위반 없음
    a = copy.deepcopy(ABOX)
    seg_ocr = copy.deepcopy(next(x for x in a["segments"] if x["id"] == "seg:hana_annex1"))
    seg_ocr.update(id="seg:synthetic_ocr_annex1", raw_asset="raw:hana_fd9c0133", fingerprint={"rule": "fp-ocr-0.1", "sha256": "7" * 64})
    a["segments"].append(seg_ocr)
    a["assertions"].append(realizes("seg:synthetic_ocr_annex1", "ted:hana_r2_1@2607"))
    vs_no = check_constraints(candidate_view(a))
    ed = next(x for x in a["terms_editions"] if x["id"] == "ted:hana_r2_1@2607")
    p1 = next(pp for pp in ed["parts"] if pp["fingerprint"]["sha256"].startswith("f3e220"))
    x = next(x for x in a["assertions"] if x["id"] == "a:realizes_synthetic_ocr_annex1")
    x["decision"] = {"by": "review_decision", "covers": [p1["fingerprint"]["rule"], p1["fingerprint"]["sha256"]], "note": "자체 시험: OCR 판과 텍스트 판이 같은 별표임을 검수 결정으로 확인"}
    vs_yes = check_constraints(candidate_view(a))
    out.append(("D9 정규화 규칙이 다른 지문(OCR)", "동작", any("비교 불가" in v[2] for v in vs_no) and not vs_yes, f"검수 없음 → {[v[2] for v in vs_no]} · 검수 결정 → 위반 {len(vs_yes)}"))

    # E1~E4 재검토 R02: 판매 구성 → 판 → 담보 → 규칙 연결. 연결이 없거나 모호하면 보류, 엔진 호출 0
    def calls(v, q):
        r = resolve(v, q)
        return r, (0 if "blocked" in r else 1)
    cv = view(ABOX, CURRENT)
    q1 = next(q for q in QUESTIONS if q["id"] == "Q1")
    r, n = calls(cv, dict(q1, cov="cov:hi_2_5"))
    out.append(("E1 하나 판매 구성에 현대 담보(재검토 R02 재현)", "동작", "blocked" in r and n == 0, f"blocked {r.get('blocked')} · 엔진 호출 {n}"))
    a = copy.deepcopy(ABOX)
    a["nodes"].append({"id": "cov:synthetic_other_edition", "class": "CoverageOccurrence", "label": "자체 시험용 다른 판 담보"})
    a["assertions"].append({"id": "a:synthetic_in_other", "subject": "cov:synthetic_other_edition", "predicate": "in_edition", "object": "ted:hi_r2_5@2608", "criticality": "C0",
                            "evidence": [{"ref": "hi2607#c_2_5_art1", "role": "basis"}], "value_state": "observed", "review_status": "accepted"})
    r, n = calls(candidate_view(a), dict(q1, cov="cov:synthetic_other_edition"))
    out.append(("E2 같은 판매 구성에 다른 판의 담보", "동작", "blocked" in r and n == 0, f"blocked {r.get('blocked')} · 엔진 호출 {n}"))
    a = copy.deepcopy(ABOX)
    a["nodes"].append({"id": "sc:synthetic_overlap", "class": "SalesConfiguration", "label": "자체 시험용 겹치는 판매 구성"})
    hl = next(x for x in a["assertions"] if x["id"] == "a:hana_doc_link")
    a["assertions"].append(dict(hl, id="a:synthetic_overlap_link", subject="sc:synthetic_overlap"))
    r, n = calls(candidate_view(a), dict(q1, configs=q1["configs"] + ["sc:synthetic_overlap"]))
    out.append(("E3 가입일에 적용 후보가 여럿", "동작", "blocked" in r and n == 0 and "복수" in r["blocked"][0], f"blocked {r.get('blocked')} · 엔진 호출 {n}"))
    rev = [run_all(cv, runner)[k] for k in ("Q1", "Q10")]
    qs_rev = [dict(q, configs=list(reversed(q["configs"]))) for q in QUESTIONS if q["id"] in ("Q1", "Q10")]
    got = [outcome(resolve(cv, q), None)["kind"] if "blocked" in resolve(cv, q) else "ran" for q in qs_rev]
    out.append(("E4 후보 목록 순서 변경", "동작", got == ["ran", "blocked"] and rev[0][0]["kind"] == "payable", f"뒤집은 순서 Q1 {got[0]} · Q10 {got[1]} (원래 Q1 payable, Q10 blocked)"))

    # S01 재검토(e02755a): 한 판매 구성이 여러 약관 판을 쓰는 정상 구성, 같은 연결의 근거 주장 추가는 막지 않는다
    a = copy.deepcopy(ABOX)
    hl = next(x for x in a["assertions"] if x["id"] == "a:hana_doc_link")
    a["assertions"].append(dict(hl, id="a:hana_doc_link_more_evidence", _review_note="자체 시험: 같은 연결의 근거 주장 추가"))
    r1 = run_all(candidate_view(a), runner)["Q1"][0]
    a = copy.deepcopy(ABOX)
    a["terms_editions"].append(dict(copy.deepcopy(next(x for x in a["terms_editions"] if x["id"] == "ted:hana_r2_1@2607")), id="ted:synthetic_main@2607", label="자체 시험용 보통약관 판", parts=[]))
    hl = next(x for x in a["assertions"] if x["id"] == "a:hana_doc_link")
    a["assertions"].append(dict(hl, id="a:synthetic_main_link", object="ted:synthetic_main@2607"))
    a["terms_editions"].append(dict(copy.deepcopy(next(x for x in a["terms_editions"] if x["id"] == "ted:hana_r2_1@2607")), id="ted:synthetic_rider2@2607", label="자체 시험용 다른 특약 판", parts=[]))
    a["assertions"].append(dict(hl, id="a:synthetic_rider2_link", object="ted:synthetic_rider2@2607", review_status="hold", hold_reason="reference_unresolved"))
    cv = candidate_view(a)
    r2 = run_all(cv, runner)["Q1"][0]
    out.append(("S01 한 판매 구성의 여러 약관 판·같은 연결의 근거 추가(재검토 e02755a 재현)", "동작", r1 == base["Q1"][0] and r2 == base["Q1"][0],
                f"근거 주장 추가 → Q1 {r1} · 보통약관 판 + 미확인 다른 특약 판 함께 연결 → Q1 {r2}(요청 담보와 무관한 판의 미확인은 막지 않음)"))
    # S01b 요청 담보의 판 연결 자체가 미확인이면 막는다
    a = copy.deepcopy(ABOX)
    hl = next(x for x in a["assertions"] if x["id"] == "a:hana_doc_link")
    a["assertions"].append(dict(hl, id="a:hana_doc_link_dup_hold", review_status="hold", hold_reason="reference_unresolved"))
    r, = [resolve(candidate_view(a), next(q for q in QUESTIONS if q["id"] == "Q1"))]
    out.append(("S01b 요청 담보의 판 연결에 미승인 주장이 섞임", "동작", "blocked" in r, f"blocked {r.get('blocked')} · 엔진 호출 0"))

    # P1 재검토 R06①: 조건이 빈 원시 가격 관측은 보존(위반 없음), 비교 자격을 주면 K13
    a = copy.deepcopy(ABOX)
    a["premium_observations"] = [{"id": "p:raw_bundle", "krw": 16598, "priced_for": "sc:hana_2601_3d_v20260701", "conditions": None, "package_binding": "source_bundle", "as_of": None, "comparison_eligible": False}]
    vs_raw = check_constraints(candidate_view(a))
    a["premium_observations"][0]["comparison_eligible"] = True
    vs_cmp = check_constraints(candidate_view(a))
    out.append(("P1 원시 가격 관측 보존과 비교 자격 분리", "동작", not vs_raw and [x[0] for x in vs_cmp] and all(x[0] == "K13" for x in vs_cmp), f"보존 → 위반 {len(vs_raw)} · 비교 자격 → {sorted({x[0] for x in vs_cmp})}"))
    # D6 통합약관 안의 구획과 개별 특약 파일이 같은 판(다른 특약이 함께 든 통합 원본 + 이 특약만 든 개별 원본)
    a = copy.deepcopy(ABOX)
    repack(a, "separate")  # 개별 특약 파일: 이 특약의 구성만 담음
    a["raw_assets"].append({"id": "raw:synthetic_integrated", "class": "RawAsset", "observed_label": "자체 시험용 합성 통합약관", "org": "org:hana_nonlife", "sha256": "1" * 64, "source": "합성", "observed_at": None})
    for k, sid in enumerate(("seg:hana_r2_1", "seg:hana_annex1", "seg:hana_annex12")):
        sg = copy.deepcopy(next(x for x in a["segments"] if x["id"] == sid))
        sg.update(id=f"seg:synthetic_integrated_{k}", raw_asset="raw:synthetic_integrated", pages=[400 + k, 400 + k])
        a["segments"].append(sg)
        a["assertions"].append(realizes(sg["id"], "ted:hana_r2_1@2607"))
    other = copy.deepcopy(next(x for x in a["segments"] if x["id"] == "seg:hana_r2_1"))
    other.update(id="seg:synthetic_integrated_other", raw_asset="raw:synthetic_integrated", pages=[10, 11], fingerprint={"rule": "fp-0.1", "sha256": "2" * 64}, note="같은 통합 파일 안의 다른 특약(판 연결 없음)")
    a["segments"].append(other)
    cv = candidate_view(a)
    cur, _ = current_assertions(cv)
    segs = {x["id"]: x for x in cv["segments"]}
    raws_of = {segs[x["subject"]]["raw_asset"] for x in cur if x["predicate"] == "realizes" and x["object"] == "ted:hana_r2_1@2607"}
    ok = not check_constraints(cv) and len(raws_of) == 3
    out.append(("D6 통합약관 구획과 개별 특약 파일이 같은 판", "동작", ok, f"판을 담은 원본 {len(raws_of)}개(원래·개별·통합) · 위반 {len(check_constraints(cv))}"))

    # D7 통합 파일 안의 특약 하나만 개정: 개정된 구성은 기존 판이 아니라 새 판(같은 계열)으로만 이어진다
    a = copy.deepcopy(ABOX)
    a["raw_assets"].append({"id": "raw:synthetic_rev", "class": "RawAsset", "observed_label": "자체 시험용 합성 개정 통합약관", "org": "org:hana_nonlife", "sha256": "3" * 64, "source": "합성", "observed_at": None})
    new_parts = []
    for k, sid in enumerate(("seg:hana_r2_1", "seg:hana_annex1", "seg:hana_annex12")):
        sg = copy.deepcopy(next(x for x in a["segments"] if x["id"] == sid))
        sg.update(id=f"seg:synthetic_rev_{k}", raw_asset="raw:synthetic_rev", pages=[50 + k, 50 + k])
        if sid == "seg:hana_r2_1":
            sg["fingerprint"] = {"rule": "fp-0.1", "sha256": "4" * 64}  # 본문 개정
        a["segments"].append(sg)
        new_parts.append({"role": "본문" if k == 0 else "참조 별표", "label": sg["doc_role"], "fingerprint": sg["fingerprint"]})
    wrong = copy.deepcopy(a)
    for k in range(3):
        wrong["assertions"].append(realizes(f"seg:synthetic_rev_{k}", "ted:hana_r2_1@2607"))
    vs_wrong = check_constraints(candidate_view(wrong))
    ed0 = next(x for x in a["terms_editions"] if x["id"] == "ted:hana_r2_1@2607")
    a["terms_editions"].append(dict(copy.deepcopy(ed0), id="ted:hana_r2_1@rev", parts=new_parts, label="자체 시험용 개정 판"))
    for k in range(3):
        a["assertions"].append(realizes(f"seg:synthetic_rev_{k}", "ted:hana_r2_1@rev"))
    cv = candidate_view(a)
    eds = {x["id"]: x for x in cv["terms_editions"]}
    ok = any(x[0] == "K16" for x in vs_wrong) and not check_constraints(cv) and eds["ted:hana_r2_1@rev"]["lineage"] == eds["ted:hana_r2_1@2607"]["lineage"] and run_all(view(ABOX, CURRENT), runner) == base
    out.append(("D7 통합 파일 안 특약 하나 개정 → 새 판(같은 계열)", "동작", ok, f"기존 판에 잇기 → {sorted({x[0] for x in vs_wrong})} · 새 판에 잇기 → 위반 {len(check_constraints(cv))} · 같은 계열 · r26 결과 불변"))
    return out


def main():
    runner = sys.argv[1]
    out = []
    p = out.append
    p("# 온톨로지 사례 검증 결과")
    p("")
    p("## 릴리스 고정")
    for rel in ABOX["releases"]:
        v = view(ABOX, rel["id"])
        counts = " · ".join(f"{k} {len(rel['members'][k])}" for k in SECTIONS if rel["members"][k])
        p(f"- {rel['id']}: 내용 해시 {rel['content_sha256'][:16]} · 무결성 {'일치' if not v['_integrity'] else '불일치'} · {counts}")
    p("")
    res = {}
    for rel in ("rel:case-r24", "rel:case-r25", CURRENT):
        vs = check_constraints(view(ABOX, rel))
        res[rel] = vs
        p(f"## 일관성 제약 · {rel}: 위반 {len(vs)}건")
        for x in vs:
            p(f"- {x[0]} {x[1]}: {x[2]}")
        p("")
    vs24, vs25 = res["rel:case-r24"], res["rel:case-r25"]
    ok_r24 = [x[0] for x in vs24] == ["K1"] and vs24[0][1] == "a:lotte_cond_waiting_v1"
    ok_r25 = not vs25 and not res[CURRENT]
    v25 = view(ABOX, CURRENT)

    cur, _ = current_assertions(v25)
    sr = scope_relation(v25, cur, "cat:hana_cancer_x_breast_genital", "cat:hi_cancer_x_similar")
    p(f"## 범위 관계(코드 집합에서 계산): 하나 2-1 범주 대 현대 2-5 범주 = {sr}")
    p("")

    jobs, resolved = [], {}
    for q in QUESTIONS:
        r = resolve(v25, q)
        resolved[q["id"]] = r
        if "blocked" not in r:
            jobs.append({"case_id": q["id"], "rule_path": r["rule_path"], "inputs": r["inputs"]})
    evs = run_engine(runner, jobs) if jobs else {}
    passed = 0
    p(f"## 질문 → 지식 조회 → 규칙 실행 → 설명·근거 ({CURRENT})")
    for q in QUESTIONS:
        r = resolved[q["id"]]
        ev = evs.get(q["id"])
        got = outcome(r, ev)
        good = got == q["expect"]
        passed += good
        p("")
        p(f"### {q['id']} {'PASS' if good else 'FAIL'} · {q['text']}")
        p(f"기대 {q['expect']} · 실제 {got}")
        for s in r["steps"]:
            p("- " + s)
        if ev:
            p(f"- 엔진 입력: {json.dumps(r['inputs'], ensure_ascii=False)}")
        for line in explain(v25, q, r, ev):
            p("  " + line if line.startswith("  ") else "- " + line)

    p("")
    p("## 정정 이력 재현")
    for rel in ("rel:case-r24", "rel:case-r25", CURRENT):
        c, _ = current_assertions(view(ABOX, rel))
        a = next(x for x in c if x["object"] == "cond:lotte_waiting")
        p(f"- {rel}: 롯데 보장개시 조건 주장 {a['id']} review_status={a['review_status']}" + (f" · 대체 사유: {a['correction_reason']}" if a.get("correction_reason") else ""))

    p("")
    p("## 자체 시험 1: 제약마다 일부러 깨뜨린 저장소(릴리스 후보로 검사)")
    st_ok = 0
    muts = mutations()
    for cid, mutated in muts:
        if mutated.get("_rule_override"):
            vs = with_bad_rule(mutated, lambda: check_constraints(candidate_view(mutated)))
        else:
            vs = check_constraints(candidate_view(mutated))
        hit = [x for x in vs if x[0] == cid]
        others = [x for x in vs if x[0] != cid]
        good = bool(hit) and not others
        st_ok += good
        p(f"- {cid}: {'잡음' if good else '못 잡음'} · {hit[0][2] if hit else '-'}" + (f" · 다른 위반 {others}" if others else ""))

    p("")
    p("## 자체 시험 2: 릴리스 고정과 문서 모델")
    rt = release_tests(runner)
    for name, kind, good, msg in rt:
        p(f"- {name} [{kind} 검증]: {'통과' if good else '실패'} · {msg}")
    rt_ok = sum(1 for _, _, g, _ in rt if g)

    total_ok = ok_r24 and ok_r25 and sr == "narrower" and passed == len(QUESTIONS) and st_ok == len(muts) and rt_ok == len(rt)
    p("")
    p(f"## 요약: r24 K1 위반 재현 {ok_r24} · r25·r26 위반 0 {ok_r25} · 범위 관계 narrower {sr == 'narrower'} · 질문 {passed}/{len(QUESTIONS)} · 제약 자체 시험 {st_ok}/{len(muts)} · 릴리스·문서 모델 시험 {rt_ok}/{len(rt)} · 전체 {'통과' if total_ok else '실패'}")
    print("\n".join(out))
    sys.exit(0 if total_ok else 1)


if __name__ == "__main__":
    main()
