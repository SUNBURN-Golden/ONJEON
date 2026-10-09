#!/usr/bin/env python3
"""Internal consistency check of the V1 design-validation set (docs/blueprint/validation).

What this checks (extracts and metadata only):
- a clause anchor is a verbatim quote on the clause's own document and page
  (whitespace-insensitive, inside one quoted passage of the extract; HTML documents have no page)
- a field raw_value, and a price observation's amount, sit inside the quoted passage of one of
  the clauses it cites as evidence (not merely somewhere in the product family)
- every state value is a vocabulary code; every reference, gap id and rule file resolves
- every money amount written on a screen line is declared with a source, and the source agrees:
  price observations, candidate insured amounts and clause text are checked here; engine
  scenario amounts are checked by `cargo test --test real_clauses`
- a price shown against a user's profile states which conditions match and which are not stated in the source

What this does NOT check: the original files. Hashes here are compared string to string with
samples.csv. Re-downloading, re-hashing and re-extracting the originals is tools/verify_sources.py.
Whether a cited clause means what the field says is a review question, not a code check.

Usage:
  python3 tools/validation_check.py            # check
  python3 tools/validation_check.py --selftest # mutate the data in memory and require failures
"""
import copy
import csv
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "docs/blueprint/validation"
VOCAB = json.loads((ROOT / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))
CODES = {a["id"]: {x["code"] for x in a["values"]} for a in VOCAB["axes"]}
FORBIDDEN = {a["id"]: set(a.get("forbidden_codes", [])) for a in VOCAB["axes"]}
STATUS = {"data_kind": "design_validation", "interpretation": "ai_unreviewed", "service_use": "forbidden"}
AXES = {"identity", "period", "event", "payout_method", "constraint", "relation", "lifecycle"}
RULE_STATUS = {"expressed", "partially_expressed", "not_expressible"}
VOCAB_KEYS = {
    "value_state": "value_state", "review_status": "review_status", "hold_reason": "hold_reason",
    "criticality": "criticality", "amount_form": "amount_form", "clause_path_basis": "clause_path_basis",
    "relation_type": "relation_type", "doc_role": "doc_role", "sale_status": "sale_status",
    "price_basis": "price_basis", "price_unavailable_reason": "price_unavailable_reason",
    "display_status": "display_status", "plan_action": "plan_action", "row_label": "row_label",
    "diff_type": "diff_type", "diff_group": "diff_group", "capability": "capability",
    "capability_state": "capability_state", "publication_state": "publication_state",
    "freshness": "freshness", "policy_holdings_status": "policy_holdings_status", "payout": "payout",
}
UNKNOWN_STATES = {"not_found", "unreadable", "conflicting", "not_disclosed"}
TEXT_KEYS = ("line", "subtitle", "summary_line", "chip", "man_display", "label", "question", "note", "reason")
# Money must be written as digits + 원 / 만원. Other money notations would bypass the amount check.
FORBIDDEN_MONEY = [
    (re.compile(r"₩|\\|KRW", re.I), "currency sign"),
    (re.compile(r"\d\s*억|\d\s*천\s*원|\d\s*천만"), "억/천 unit"),
    (re.compile(r"[일이삼사오육칠팔구십백천]+\s*만\s*원|[일이삼사오육칠팔구십백천]+\s*원(?![가-힣])"), "Korean numerals"),
    (re.compile(r"\d\s*만(?!\s*원)(?=[\s·,)]|$)"), "만 without 원"),
]
# Numbers with these units must appear in the text of what the line cites (clause, field, price).
UNIT_RE = re.compile(r"(\d[\d,.]*)\s*(%|개월|시간|일|년|세|회|종)")
# "1,500만원", "51,290원", "0원". Display shorthand "5.1만" (no 원) is only allowed in man_display.
MONEY_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(만\s*원|원)")
SEX_KO = {"male": "남", "female": "여"}


def norm(s):
    return re.sub(r"\s+", "", s)


def passages(md):
    """Split the quoted code blocks of an extract into (page, normalized passage) pairs.

    A new passage starts at every `[PDF p.N]` marker and at every `...` omission line, so a quote
    can never be matched across an omission or across pages. Lines before any marker (HTML
    extracts) have page None.
    """
    out = []
    for block in re.findall(r"```text\n(.*?)```", md, re.S):
        page, buf = None, []
        def flush():
            if buf:
                out.append((page, norm("\n".join(buf))))
        for line in block.splitlines():
            m = re.match(r"\s*\[PDF p\.(\d+)\]\s*$", line)
            if m:
                flush()
                buf, page = [], int(m.group(1))
            elif line.strip() == "...":
                flush()
                buf = []
            else:
                buf.append(line)
        flush()
    return out


def unit_tokens(text):
    return [num + unit for num, unit in UNIT_RE.findall(text)]


def money_tokens(text):
    vals = []
    for num, unit in MONEY_RE.findall(text):
        n = Decimal(num.replace(",", ""))
        vals.append(int(n * 10000) if "만" in unit else int(n))
    return sorted(vals)


def fmt_krw(won):
    if won and won % 10000 == 0:
        return f"{won // 10000:,}만원"
    return f"{won:,}원"


def man_display(won):
    man = (Decimal(won) / Decimal(10000)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"월 {man}만"


def walk_vocab(obj, where, errors):
    if isinstance(obj, dict):
        for k, v in obj.items():
            axis = VOCAB_KEYS.get(k)
            if axis == "payout" and isinstance(v, dict):
                for sub in ("amount", "conditional_amount"):
                    inner = v.get(sub)
                    if isinstance(inner, dict) and inner.get("kind") not in CODES["amount_kind"]:
                        errors.append(f"{where}: `{k}.{sub}.kind` is not an amount_kind code")
                v = v.get("kind")
            if axis and v is not None:
                for item in v if isinstance(v, list) else [v]:
                    if not isinstance(item, str) or item not in CODES[axis] or item in FORBIDDEN[axis]:
                        errors.append(f"{where}: `{k}`={item!r} is not a {axis} code")
            walk_vocab(obj[k], where, errors)
    elif isinstance(obj, list):
        for x in obj:
            walk_vocab(x, where, errors)


def load():
    data = {"samples": [], "gaps": set(), "families": {}, "screens": {}, "extracts": {}, "rules": {}}
    data["samples"] = list(csv.DictReader((VAL / "samples.csv").open(encoding="utf-8")))
    gap = VAL / "GAP_REPORT.md"
    if gap.exists():
        data["gaps"] = set(re.findall(r"^\| (G\d\d) \|", gap.read_text(encoding="utf-8"), re.M))
    for p in sorted((VAL / "encoded").glob("*.json")):
        data["families"][p.stem] = json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((VAL / "screen").glob("*.json")) if (VAL / "screen").exists() else []:
        data["screens"][p.name] = json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((VAL / "extracts").glob("*.md")):
        data["extracts"][f"extracts/{p.name}"] = p.read_text(encoding="utf-8")
    for p in sorted((ROOT / "packages/fixtures/rules/real").glob("*.json")):
        if not p.name.endswith(".cases.json"):
            data["rules"][str(p.relative_to(ROOT))] = json.loads(p.read_text(encoding="utf-8"))
    return data


def check_family(fam, d, data, samples, errors, index):
    where = f"encoded/{fam}.json"
    gaps = data["gaps"]
    if d.get("status") != STATUS:
        errors.append(f"{where}: status must be {STATUS}")
    if d.get("family") != fam:
        errors.append(f"{where}: family must equal file stem")
    walk_vocab(d, where, errors)
    # No cross-family review has happened (ADR-0006): nothing in this set may be service-approved.
    def no_accepted(o, path):
        if isinstance(o, dict):
            if o.get("review_status") == "accepted":
                errors.append(f"{where}: {path} is review_status=accepted, but no cross-family review record exists (ai_unreviewed set)")
            for k, v in o.items():
                no_accepted(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, x in enumerate(o):
                no_accepted(x, f"{path}[{i}]")
    no_accepted(d, "$")
    doc_passages = {}
    for doc in d["documents"]:
        s = samples.get(doc["sample_id"])
        if not s:
            errors.append(f"{where}: {doc['doc_id']} sample `{doc['sample_id']}` not in samples.csv")
        elif s["sha256"] != doc["sha256"]:
            errors.append(f"{where}: {doc['doc_id']} sha256 string differs from samples.csv")
        md = data["extracts"].get(doc["extract"])
        if md is None:
            errors.append(f"{where}: missing extract {doc['extract']}")
            continue
        doc_passages[doc["doc_id"]] = passages(md)
    ids = {}
    clause_passages = {}
    for c in d["clauses"]:
        cid = c["clause_id"]
        if cid in ids:
            errors.append(f"{where}: duplicate id {cid}")
        ids[cid] = "clause"
        ps = doc_passages.get(c["doc_id"])
        if ps is None:
            errors.append(f"{where}: {cid} names unknown doc {c['doc_id']}")
            continue
        a = norm(c["anchor"])
        hits = [t for pg, t in ps if pg == c["page"] and a in t]
        if not hits:
            elsewhere = sorted({pg for pg, t in ps if a in t}, key=str)
            msg = f" (found on page {elsewhere})" if elsewhere else ""
            errors.append(f"{where}: {cid} anchor is not on {c['doc_id']} page {c['page']}{msg}: {c['anchor'][:40]}")
        clause_passages[cid] = hits

    def refs_ok(owner, refs):
        if not refs:
            errors.append(f"{where}: {owner} has no evidence_refs")
        for r in refs:
            if ids.get(r) != "clause":
                errors.append(f"{where}: {owner} evidence `{r}` is not a clause of this family")

    def in_cited(owner, needle, refs, what):
        n = norm(needle)
        if not any(n in t for r in refs for t in clause_passages.get(r, [])):
            errors.append(f"{where}: {owner} {what} is not inside the quoted passage of any cited clause {refs}")

    def gaps_ok(owner, gs):
        for g in gs or []:
            if g not in gaps:
                errors.append(f"{where}: {owner} gap {g} is not in GAP_REPORT.md register")

    def hold_ok(owner, x):
        if (x.get("review_status") == "hold") != bool(x.get("hold_reason")):
            errors.append(f"{where}: {owner} hold_reason must be set exactly when review_status=hold")

    for f in d["fields"]:
        fid = f["field_id"]
        if fid in ids:
            errors.append(f"{where}: duplicate id {fid}")
        ids[fid] = "field"
        if f["axis"] not in AXES:
            errors.append(f"{where}: {fid} axis `{f['axis']}` not in {sorted(AXES)}")
        refs_ok(fid, f["evidence_refs"])
        gaps_ok(fid, f.get("gaps"))
        hold_ok(fid, f)
        if f.get("raw_value") is not None:
            in_cited(fid, f["raw_value"], f["evidence_refs"], "raw_value")
        if f["value_state"] in UNKNOWN_STATES and not f.get("unknown_reason"):
            errors.append(f"{where}: {fid} value_state={f['value_state']} needs unknown_reason")
        if f["value_state"] in {"observed", "derived"} and f.get("normalized_value") is None:
            errors.append(f"{where}: {fid} observed/derived value needs normalized_value")
    for r in d.get("relations", []):
        if r["relation_id"] in ids:
            errors.append(f"{where}: duplicate id {r['relation_id']}")
        ids[r["relation_id"]] = "relation"
        refs_ok(r["relation_id"], r["evidence_refs"])
        gaps_ok(r["relation_id"], r.get("gaps"))
        hold_ok(r["relation_id"], r)
    for r in d.get("rules", []):
        owner = r.get("rule_id") or r.get("benefit")
        if r["status"] not in RULE_STATUS:
            errors.append(f"{where}: rule {owner} status must be one of {sorted(RULE_STATUS)}")
        gaps_ok(owner, r.get("gaps"))
        if r["status"] == "not_expressible":
            if not r.get("reason"):
                errors.append(f"{where}: not_expressible {owner} needs a reason")
            continue
        rule = data["rules"].get(r["file"])
        if rule is None:
            errors.append(f"{where}: rule file {r['file']} missing")
            continue
        ids[r["rule_id"]] = "rule"
        if rule.get("publication_state") != "fixture_only":
            errors.append(f"{where}: {r['rule_id']} must stay fixture_only")
        index.setdefault("_rule_refs", []).append((where, r["rule_id"], rule.get("evidence_refs", [])))
    premiums = {}
    for p in d.get("premium_observations", []):
        pid = p["observation_id"]
        if pid in ids:
            errors.append(f"{where}: duplicate id {pid}")
        ids[pid] = "premium"
        premiums[pid] = p
        refs_ok(pid, p["evidence_refs"])
        gaps_ok(pid, p.get("gaps"))
        hold_ok(pid, p)
        amt = p.get("amount_krw")
        if amt is None:
            if not p.get("price_unavailable_reason"):
                errors.append(f"{where}: {pid} without amount needs price_unavailable_reason")
        elif not isinstance(amt, int) or isinstance(amt, bool) or amt <= 0:
            errors.append(f"{where}: {pid} amount_krw must be a positive integer (0 is never a missing price)")
        elif p.get("value_state") == "derived":
            if not p.get("derivation"):
                errors.append(f"{where}: {pid} derived amount needs a derivation")
        else:
            # the amount must appear as a whole number (not as digits inside a longer number)
            tok = re.compile(rf"(?<![\d,.]){re.escape(f'{amt:,}')}(?![\d,.])")
            if not any(tok.search(t) for r in p["evidence_refs"] for t in clause_passages.get(r, [])):
                errors.append(f"{where}: {pid} amount {amt:,} is not inside the quoted passage of any cited clause {p['evidence_refs']}")
        if not p.get("comparison_basis_id"):
            errors.append(f"{where}: {pid} needs comparison_basis_id")
        cond = p.get("conditions", {})
        for dim in ("age", "sex"):
            if dim not in cond and dim not in missing_keys(p):
                errors.append(f"{where}: {pid} must state `{dim}` or list it in missing_dimensions")
        if p.get("pay_cycle") not in {"monthly", "annual", "single", None}:
            errors.append(f"{where}: {pid} pay_cycle must be monthly|annual|single")
    entities = {c["clause_id"]: c for c in d["clauses"]}
    entities.update({f["field_id"]: f for f in d["fields"]})
    entities.update({r["relation_id"]: r for r in d.get("relations", [])})
    entities.update(premiums)
    index[fam] = {"ids": ids, "premiums": premiums, "clauses": {c["clause_id"]: c for c in d["clauses"]}, "entities": entities}


def missing_keys(p):
    return {re.split(r"[\s(]", m, maxsplit=1)[0] for m in p.get("missing_dimensions", [])}


def resolve(index, ref):
    fam, _, rid = ref.partition("#")
    return index.get(fam, {}).get("ids", {}).get(rid), fam, rid


def check_screen(name, d, index, gaps, errors):
    where = f"screen/{name}"
    if d.get("status") != STATUS:
        errors.append(f"{where}: status must be {STATUS}")
    walk_vocab(d, where, errors)
    profile = d.get("profile", {})
    scenarios = {s["id"] for s in d.get("scenarios", [])}
    candidate = {c["scope"]: c for c in d.get("candidate", {}).get("components", [])}

    def premium(ref):
        kind, fam, rid = resolve(index, ref)
        return index[fam]["premiums"][rid] if kind == "premium" else None

    def check_amount_source(owner, a):
        src, won = a.get("source", ""), a.get("krw")
        kind, _, ref = src.partition(":")
        if kind == "scenario":
            if ref not in scenarios:
                errors.append(f"{where}: {owner} amount source `{src}` names no scenario")
        elif kind in ("premium", "premium_insured"):
            p = premium(ref)
            if p is None:
                errors.append(f"{where}: {owner} amount source `{src}` is not a price observation")
            else:
                actual = p["amount_krw"] if kind == "premium" else p["components"][0].get("insured_amount_krw")
                if actual != won:
                    errors.append(f"{where}: {owner} shows {won} but {src} is {actual}")
        elif kind == "candidate":
            c = candidate.get(ref)
            if c is None or c.get("insured_amount_krw") != won:
                errors.append(f"{where}: {owner} shows {won} but candidate `{ref}` is {c and c.get('insured_amount_krw')}")
        elif kind == "clause":
            k, fam, rid = resolve(index, ref)
            if k != "clause":
                errors.append(f"{where}: {owner} amount source `{src}` is not a clause")
            elif norm(fmt_krw(won)) not in norm(index[fam]["clauses"][rid]["anchor"]):
                errors.append(f"{where}: {owner} {fmt_krw(won)} is not in the text of {ref}")
        else:
            errors.append(f"{where}: {owner} amount needs source scenario:|premium:|premium_insured:|candidate:|clause:")

    def check_condition_match(owner, cm):
        p = premium(cm.get("premium_ref", ""))
        if p is None:
            errors.append(f"{where}: {owner} condition_match needs a premium_ref")
            return
        cond = p.get("conditions", {})
        for dim in cm.get("matched", []):
            if dim not in profile or dim not in cond or profile[dim] != cond[dim]:
                errors.append(f"{where}: {owner} claims `{dim}` matches but profile={profile.get(dim)!r} price={cond.get(dim)!r}")
        for dim in profile:
            if dim in cond and profile[dim] != cond[dim] and dim not in cm.get("mismatched", []):
                errors.append(f"{where}: {owner} must list `{dim}` as mismatched")
        missing = missing_keys(p)
        if not missing <= set(cm.get("not_in_source", [])):
            errors.append(f"{where}: {owner} must list not_in_source conditions {sorted(missing - set(cm.get('not_in_source', [])))}")
        if cm.get("not_in_source") and "미확인" not in cm.get("line", ""):
            errors.append(f"{where}: {owner} line must say the remaining conditions are not stated in the source (미확인)")

    def ref_text(refs):
        out = []
        for r in refs:
            kind, fam, rid = resolve(index, r)
            ent = index.get(fam, {}).get("entities", {}).get(rid)
            if ent is None:
                continue
            if kind == "clause":
                out.append(ent["anchor"])
            elif kind == "field":
                out += [ent.get("raw_value") or "", json.dumps(ent.get("normalized_value"), ensure_ascii=False)]
            elif kind == "premium":
                out.append(json.dumps({k: ent.get(k) for k in ("conditions", "components", "amount_krw")}, ensure_ascii=False))
            elif kind == "relation":
                out.append(ent.get("predicate") or "")
        return norm(" ".join(out))

    scenario_inputs = {s["id"]: s.get("inputs", {}) for s in d.get("scenarios", [])}

    def check_units(path, o):
        for key in TEXT_KEYS:
            text = o.get(key)
            if not isinstance(text, str) or key in ("man_display", "chip"):
                continue
            if key == "question":
                m = re.search(r"가입\s*(\d+)일\s*뒤", text)
                inp = scenario_inputs.get(o.get("id"), {})
                if m and inp.get("contract_date") and inp.get("diagnosis_date"):
                    import datetime as _dt
                    days = (_dt.date.fromisoformat(inp["diagnosis_date"]) - _dt.date.fromisoformat(inp["contract_date"])).days
                    if days != int(m.group(1)):
                        errors.append(f"{where}: {path} question says {m.group(1)}일 but inputs differ by {days} days")
                continue
            refs = o.get("subtitle_refs" if key == "subtitle" else "refs", [])
            if key == "subtitle" and not refs and unit_tokens(text):
                errors.append(f"{where}: {path} subtitle has numbers {unit_tokens(text)} but no subtitle_refs")
                continue
            haystack = ref_text(refs)
            for tok in unit_tokens(text):
                if norm(tok) not in haystack:
                    errors.append(f"{where}: {path}.{key} `{tok}` is not in the text of its refs {refs}")

    def visit(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and k != "man_display":  # man_display is checked against the price exactly
                    for pat, what in FORBIDDEN_MONEY:
                        if pat.search(v):
                            errors.append(f"{where}: {path}.{k} uses {what} for money: {v[:40]!r} (write digits + 원/만원)")
            check_units(path, o)
            texts = [o[k] for k in TEXT_KEYS if isinstance(o.get(k), str) and k != "man_display"]
            shown = sorted(t for s in texts for t in money_tokens(s))
            declared = sorted(a.get("krw") for a in o.get("amounts", []))
            if shown != declared:
                errors.append(f"{where}: {path} shows amounts {shown} but declares {declared}")
            for a in o.get("amounts", []):
                check_amount_source(path, a)
            if "won" in o and o.get("won") is not None:
                ps = [r for r in o.get("refs", []) if resolve(index, r)[0] == "premium"]
                if len(ps) != 1 or premium(ps[0])["amount_krw"] != o["won"]:
                    errors.append(f"{where}: {path} price {o['won']} does not equal its one price observation {ps}")
                elif "man_display" in o and o["man_display"] != man_display(o["won"]):
                    errors.append(f"{where}: {path} man_display {o['man_display']!r} != {man_display(o['won'])!r}")
                if "chip" in o and ps:
                    p = premium(ps[0])
                    want = [f"{p['conditions'].get('age')}세", SEX_KO.get(p["conditions"].get("sex"), "?"), (p.get("source_as_of") or "")[5:]]
                    for w in want:
                        if w not in o["chip"]:
                            errors.append(f"{where}: {path} chip {o['chip']!r} must state `{w}` from {ps[0]}")
            if "condition_match" in o:
                check_condition_match(path, o["condition_match"])
            for k, v in o.items():
                if k in ("refs", "evidence") and isinstance(v, list):
                    for r in v:
                        if resolve(index, r)[0] is None:
                            errors.append(f"{where}: ref `{r}` does not resolve to an encoded id")
                elif k == "gaps" and isinstance(v, list):
                    for g in v:
                        if g not in gaps:
                            errors.append(f"{where}: gap {g} is not in the register")
                visit(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, x in enumerate(o):
                visit(x, f"{path}[{x.get('id', i) if isinstance(x, dict) else i}]")
    visit(d, "$")


def check(data):
    errors = []
    samples = {}
    for r in data["samples"]:
        if r["sample_id"] in samples:
            errors.append(f"samples.csv: duplicate sample_id {r['sample_id']}")
        samples[r["sample_id"]] = r
    if not data["gaps"]:
        errors.append("GAP_REPORT.md: no gap register rows (| Gnn |)")
    index = {}
    for fam, d in data["families"].items():
        check_family(fam, d, data, samples, errors, index)
    for where, rid, refs in index.pop("_rule_refs", []):
        for ref in refs:
            if resolve(index, ref)[0] != "clause":
                errors.append(f"{where}: rule {rid} evidence `{ref}` does not resolve to a clause")
    for name, d in data["screens"].items():
        check_screen(name, d, index, data["gaps"], errors)
    return errors, index


def mutations():
    """Tampering that must fail, each with the error text it must produce (not just any error).

    Mirrors the review findings of 2026-10-09 plus evasions found while re-verifying 87a19c5.
    """
    def scen(data, sid):
        return next(s for s in data["screens"]["coverage_detail.cancer.json"]["scenarios"] if s["id"] == sid)
    def field(data, fam, fid):
        return next(f for f in data["families"][fam]["fields"] if f["field_id"] == fid)
    def clause(data, fam, cid):
        return next(c for c in data["families"][fam]["clauses"] if c["clause_id"] == cid)
    def prem(data, fam, pid):
        return next(p for p in data["families"][fam]["premium_observations"] if p["observation_id"] == pid)
    detail = lambda data: data["screens"]["coverage_detail.cancer.json"]
    listing = lambda data: data["screens"]["my_design.real_sample.json"]["groups"][0]
    why = lambda data: detail(data)["sections"]["why_this_price"]
    def edit(obj, key, old, new):
        assert old in obj[key], (key, old)
        obj[key] = obj[key].replace(old, new)
    return {
        # screen amounts and prices
        "scenario line 1,500만원 → 9,999만원": (lambda d: edit(scen(d, "sc2")["display"], "line", "1,500만원", "9,999만원"), "shows amounts [99990000] but declares [15000000]"),
        "detail price 51,290 → 1": (lambda d: why(d)["price_line"].update(won=1), "price 1 does not equal its one price observation"),
        "list price 51,290 → 1": (lambda d: listing(d)["price_line"].update(won=1), "price 1 does not equal its one price observation"),
        "list display 월 5.1만 → 월 0.1만": (lambda d: listing(d)["price_line"].update(man_display="월 0.1만"), "man_display '월 0.1만' != '월 5.1만'"),
        "when_not_paid 1,500만원 → 1,600만원": (lambda d: edit(detail(d)["sections"]["when_not_paid"][1], "line", "1,500만원", "1,600만원"), "shows amounts [16000000] but declares [15000000]"),
        "amount source points at another price": (lambda d: why(d)["breakdown"][0]["amounts"][0].update(source="premium:kyobo_cancer#p_sum_f_main"), "shows 50790 but premium:kyobo_cancer#p_sum_f_main is 33240"),
        "candidate amount changed": (lambda d: detail(d)["candidate"]["components"][0].update(insured_amount_krw=50000000), "but candidate `main` is 50000000"),
        "price chip says 여 for a male price": (lambda d: why(d)["price_line"].update(chip="공시 예시 · 40세 여 · 기준일 06-29"), "must state `남`"),
        "money written with ₩": (lambda d: edit(why(d)["breakdown"][0], "line", "50,790원", "50,790원(₩99,999)"), "uses currency sign for money"),
        "money written with 억": (lambda d: edit(detail(d)["sections"]["what_is_covered"][0], "line", "(처음 1번)", "(최대 3억원)"), "uses 억/천 unit for money"),
        "money in Korean numerals": (lambda d: edit(detail(d)["sections"]["what_is_covered"][0], "line", "(처음 1번)", "(최대 삼천만원)"), "uses Korean numerals for money"),
        "money hidden in a note": (lambda d: detail(d)["sections"]["what_is_covered"][2].update(note="9,999만원 지급"), "shows amounts [99990000] but declares []"),
        "money hidden in a capability reason": (lambda d: detail(d)["capabilities"][0].update(reason="9,999만원"), "shows amounts [99990000] but declares []"),
        # numbers other than money
        "percent changed in a line": (lambda d: edit(detail(d)["sections"]["when_not_paid"][1], "line", "절반", "30%"), "`30%` is not in the text of its refs"),
        "waiting days 90일 → 30일": (lambda d: edit(detail(d)["sections"]["when_not_paid"][0], "line", "90일", "30일"), "`30일` is not in the text of its refs"),
        "list subtitle 90일 → 60일": (lambda d: edit(listing(d), "subtitle", "90일", "60일"), "`60일` is not in the text of its refs"),
        "scenario question days ≠ inputs": (lambda d: edit(scen(d, "sc2"), "question", "200일", "300일"), "question says 300일 but inputs differ by 200 days"),
        # evidence location
        "cancer event evidence → sex criteria clause": (lambda d: field(d, "kyobo_cancer", "f_main_event").update(evidence_refs=["c_klia_crit_sex"]), "f_main_event raw_value is not inside the quoted passage of any cited clause"),
        "waiting raw_value from the reduction clause": (lambda d: field(d, "kyobo_cancer", "f_main_waiting").update(raw_value=field(d, "kyobo_cancer", "f_main_reduction")["raw_value"]), "f_main_waiting raw_value is not inside the quoted passage"),
        "art.7 clause page 47 → 48": (lambda d: clause(d, "kyobo_cancer", "c_main_art7").update(page=48), "c_main_art7 anchor is not on d_terms page 48 (found on page [47])"),
        "clause moved to another document": (lambda d: clause(d, "kyobo_cancer", "c_main_art7").update(doc_id="d_sum"), "c_main_art7 anchor is not on d_sum page 47"),
        "price observation 50,790 → 1": (lambda d: prem(d, "kyobo_cancer", "p_sum_m_main").update(amount_krw=1), "p_sum_m_main amount 1 is not inside the quoted passage"),
        "price evidence → unrelated clause": (lambda d: prem(d, "kyobo_cancer", "p_sum_f_main").update(evidence_refs=["c_main_art7"]), "p_sum_f_main amount 33,240 is not inside the quoted passage"),
        # review state
        "field promoted to accepted without review": (lambda d: field(d, "kyobo_cancer", "f_main_waiting").update(review_status="accepted"), "review_status=accepted, but no cross-family review record exists"),
        # price conditions
        "condition match drops not_in_source": (lambda d: why(d)["condition_match"].update(not_in_source=[]), "must list not_in_source conditions"),
        "condition match claims pay_term": (lambda d: why(d)["condition_match"]["matched"].append("pay_term"), "claims `pay_term` matches"),
        "profile sex differs but still matched": (lambda d: detail(d)["profile"].update(sex="female"), "claims `sex` matches but profile='female' price='male'"),
        "condition line hides 미확인": (lambda d: why(d)["condition_match"].update(line="나이·성별 일치 · 조건 같음"), "line must say the remaining conditions are not stated in the source"),
    }


def selftest():
    base = load()
    errors, _ = check(base)
    if errors:
        print("selftest needs a clean baseline:\n  " + "\n  ".join(errors))
        return 1
    bad = []
    for name, (fn, expected) in mutations().items():
        data = copy.deepcopy(base)
        fn(data)
        errs, _ = check(data)
        hit = [e for e in errs if expected in e]
        state = "caught" if hit else ("WRONG REASON" if errs else "MISSED")
        print(f"  {state}: {name}" + (f" -> {(hit or errs)[0][:100]}" if errs else ""))
        if not hit:
            bad.append(name)
    if bad:
        print(f"selftest failed: {len(bad)} mutation(s) not caught for the intended reason")
        return 1
    print(f"selftest ok: {len(mutations())} mutations, each caught for its intended reason")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    data = load()
    errors, index = check(data)
    if errors:
        print("validation set invalid:\n  " + "\n  ".join(errors))
        return 1
    count = lambda kind: sum(sum(1 for v in x["ids"].values() if v == kind) for x in index.values())
    print(
        f"internal consistency ok (extracts and metadata; originals not re-verified): "
        f"{len(data['samples'])} samples, {len(data['families'])} families, {count('clause')} clauses, "
        f"{count('field')} fields, {count('premium')} price observations, {len(data['screens'])} screen models, "
        f"{len(data['gaps'])} gaps"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
