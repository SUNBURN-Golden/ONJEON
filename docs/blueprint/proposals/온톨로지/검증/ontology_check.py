#!/usr/bin/env python3
"""온톨로지 사례 검증(토의 자료용, 시험 전용).

1. 일관성 제약 K1~K13을 A-box에 검사한다(릴리스별).
2. 질문 → 지식 조회 → 입력 단계 판정 → 규칙 엔진 실행(Rust 실행기) → 설명·근거 사슬을 만든다.
3. 제약마다 일부러 깨뜨린 A-box를 넣어 검사기가 의도한 이유로 실패하는지 확인한다(자체 시험).

계산은 규칙 엔진만 한다. 이 스크립트는 지식 조회, 코드 소속 판정(입력 단계), 결과 설명만 한다.
사용: python3 -I ontology_check.py <runner 실행 파일>
"""
import copy
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


# ---------- 릴리스와 현재 주장 ----------
def current_assertions(abox, release_id):
    rel = next(r for r in abox["releases"] if r["id"] == release_id)
    excluded = set(rel.get("assertions_exclude", []))
    pool = [a for a in abox["assertions"] if a["id"] not in excluded]
    superseded = {a["supersedes"] for a in pool if a.get("supersedes")}
    return [a for a in pool if a["id"] not in superseded], pool


def clause_doc_kind(abox):
    docs = {d["id"]: d["kind"] for d in abox["documents"]}
    return {c["id"]: docs[c["doc"]] for c in abox["clauses"]}


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
def check_constraints(abox, release_id):
    cur, pool = current_assertions(abox, release_id)
    kinds = clause_doc_kind(abox)
    v = []
    # K1
    for a in cur:
        if a["criticality"] == "C0" and a["review_status"] == "accepted":
            if not any(e["role"] == "basis" and kinds.get(e["ref"]) == "약관" for e in a["evidence"]):
                if a["predicate"] == "uses_document" and any(e["role"] == "observation" for e in a["evidence"]):
                    continue  # 판매본-문서 대응은 목록 관측이 근거(약관 내용 주장이 아님)
                v.append(("K1", a["id"], "C0 accepted인데 약관 basis 근거가 없음"))
    # K2
    for a in cur:
        if a["predicate"] == "same_benefit_as":
            refs = [e for e in a["evidence"] if e["role"] == "basis" and kinds.get(e["ref"]) == "약관"]
            docs = {next(c["doc"] for c in abox["clauses"] if c["id"] == e["ref"]) for e in refs}
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
    blob = json.dumps({k: abox[k] for k in ("nodes", "assertions", "clauses", "documents")}, ensure_ascii=False)
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
        cap = abox.get("_capability_override", {}).get(cov)
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
    # K13
    for p in abox.get("premium_observations", []):
        for k in ("conditions", "package_binding", "as_of"):
            if not p.get(k):
                v.append(("K13", p["id"], f"가격 관측에 {k} 없음"))
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


def applicable_config(abox, cur, configs, contract_date):
    for sc in configs:
        for a in cur:
            if a["subject"] == sc and a["predicate"] == "uses_document":
                t = a.get("time", {})
                if (not t.get("valid_from") or t["valid_from"] <= contract_date) and (not t.get("valid_to") or contract_date <= t["valid_to"]):
                    return sc, a
    return None, None


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


def resolve(abox, release, q):
    cur, _ = current_assertions(abox, release)
    steps = []
    sc, link = applicable_config(abox, cur, q["configs"], q["facts"]["contract_date"])
    if not sc:
        steps.append("판매본: 가입일에 적용되는 판매본을 찾지 못함")
        return {"blocked": ["판매본 미확인"], "steps": steps}
    steps.append(f"판매본: {node(abox, sc)['label']} ← {link['id']}({link['value_state']}/{link['review_status']})")
    if link["review_status"] != "accepted" or not link.get("object"):
        steps.append(f"  이 판매본의 약관 판이 확인되지 않음 → 계산하지 않음")
        return {"blocked": [link["id"] + ":" + link["review_status"]], "steps": steps, "config": sc}
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


def run_engine(runner, jobs):
    p = subprocess.run([runner], input=json.dumps(jobs), capture_output=True, text=True, check=True)
    return {r["case_id"]: r for r in json.loads(p.stdout)}


def explain(abox, release, q, res, ev):
    cur, _ = current_assertions(abox, release)
    clauses = {c["id"]: c for c in abox["clauses"]}
    docs = {d["id"]: d for d in abox["documents"]}
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
                lines.append(f"    {msg} ← 주장 {aid} → {c['path']} · {docs[c['doc']]['kind']} sha256 {docs[c['doc']]['sha256'][:12]} · PDF {c['pdf_page']}쪽")
    lines.append("  실행 규칙의 근거:")
    for ref in ev["evidence_refs"]:
        c = clauses[ref]
        backing = [a["id"] for a in cur if any(e["ref"] == ref and e["role"] == "basis" for e in a["evidence"])]
        lines.append(f"    근거 {ref} → 주장 {','.join(backing)} → {c['path']} · {docs[c['doc']]['kind']} sha256 {docs[c['doc']]['sha256'][:12]} · PDF {c['pdf_page']}쪽")
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
    M = []
    def m(cid, f):
        a = copy.deepcopy(ABOX); f(a); M.append((cid, a))
    def set_a(a, aid, **kw):
        next(x for x in a["assertions"] if x["id"] == aid).update(kw)
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
    m("K13", lambda a: a.setdefault("premium_observations", []).append({"id": "p:hana_bundle", "krw": 16598, "priced_for": "sc:hana_2601_3d_v20260701", "conditions": None, "package_binding": "source_bundle", "as_of": None}))
    return M


def main():
    runner = sys.argv[1]
    out = []
    p = out.append
    p("# 온톨로지 사례 검증 결과")
    p("")
    for rel in ("rel:case-r24", "rel:case-r25"):
        vs = check_constraints(ABOX, rel)
        p(f"## 일관성 제약 · {rel}: 위반 {len(vs)}건")
        for x in vs:
            p(f"- {x[0]} {x[1]}: {x[2]}")
        p("")
    vs25 = check_constraints(ABOX, "rel:case-r25")
    vs24 = check_constraints(ABOX, "rel:case-r24")
    ok_r24 = [x[0] for x in vs24] == ["K1"] and vs24[0][1] == "a:lotte_cond_waiting_v1"
    ok_r25 = not vs25

    cur, _ = current_assertions(ABOX, "rel:case-r25")
    sr = scope_relation(ABOX, cur, "cat:hana_cancer_x_breast_genital", "cat:hi_cancer_x_similar")
    p(f"## 범위 관계(코드 집합에서 계산): 하나 2-1 범주 대 현대 2-5 범주 = {sr}")
    p("")

    jobs, resolved = [], {}
    for q in QUESTIONS:
        r = resolve(ABOX, "rel:case-r25", q)
        resolved[q["id"]] = r
        if "blocked" not in r:
            jobs.append({"case_id": q["id"], "rule_path": r["rule_path"], "inputs": r["inputs"]})
    evs = run_engine(runner, jobs) if jobs else {}
    passed = 0
    p("## 질문 → 지식 조회 → 규칙 실행 → 설명·근거")
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
        for line in explain(ABOX, "rel:case-r25", q, r, ev):
            p("  " + line if line.startswith("  ") else "- " + line)

    p("")
    p("## 정정 이력 재현")
    for rel in ("rel:case-r24", "rel:case-r25"):
        c, _ = current_assertions(ABOX, rel)
        a = next(x for x in c if x["object"] == "cond:lotte_waiting")
        p(f"- {rel}: 롯데 보장개시 조건 주장 {a['id']} review_status={a['review_status']}" + (f" · 대체 사유: {a['correction_reason']}" if a.get("correction_reason") else ""))

    p("")
    p("## 자체 시험(제약마다 일부러 깨뜨린 A-box)")
    st_ok = 0
    muts = mutations()
    for cid, mutated in muts:
        if mutated.get("_rule_override"):
            rp = os.path.join(ROOT, "규칙", "hana-2601-3d-cancer-dx.json")
            orig = open(rp, encoding="utf-8").read()
            bad = json.loads(orig); bad["evidence_refs"].append("hana_2601_3d#c_2_1_art5")
            tmp = os.path.join(ROOT, "규칙", "_tmp_bad.json")
            open(tmp, "w", encoding="utf-8").write(json.dumps(bad, ensure_ascii=False))
            next(x for x in mutated["assertions"] if x["id"] == "a:hana_rule")["rule_path"] = "규칙/_tmp_bad.json"
            vs = check_constraints(mutated, "rel:case-r25")
            os.remove(tmp)
        else:
            vs = check_constraints(mutated, "rel:case-r25")
        hit = [x for x in vs if x[0] == cid]
        others = [x for x in vs if x[0] != cid]
        good = bool(hit) and not others
        st_ok += good
        p(f"- {cid}: {'잡음' if good else '못 잡음'} · {hit[0][2] if hit else '-'}" + (f" · 다른 위반 {others}" if others else ""))

    total_ok = ok_r24 and ok_r25 and sr == "narrower" and passed == len(QUESTIONS) and st_ok == len(muts)
    p("")
    p(f"## 요약: r24 K1 위반 재현 {ok_r24} · r25 위반 0 {ok_r25} · 범위 관계 narrower {sr == 'narrower'} · 질문 {passed}/{len(QUESTIONS)} · 자체 시험 {st_ok}/{len(muts)} · 전체 {'통과' if total_ok else '실패'}")
    print("\n".join(out))
    sys.exit(0 if total_ok else 1)


if __name__ == "__main__":
    main()
