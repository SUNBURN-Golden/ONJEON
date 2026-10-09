#!/usr/bin/env python3
"""Checks the V1 design-validation set in docs/blueprint/validation.

- every encoded clause anchor and field raw_value is a verbatim quote from the extract
  (whitespace-insensitive, searched only inside quoted code blocks)
- document hashes match samples.csv
- every state value is a code from packages/schemas/vocabulary.json
- every evidence reference, gap id, rule file and screen reference resolves
- the set is marked as design validation, AI interpretation, not reviewed, not service data

Usage: python3 tools/validation_check.py
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAL = ROOT / "docs/blueprint/validation"
VOCAB = json.loads((ROOT / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))
CODES = {a["id"]: {x["code"] for x in a["values"]} for a in VOCAB["axes"]}
FORBIDDEN = {a["id"]: set(a.get("forbidden_codes", [])) for a in VOCAB["axes"]}
STATUS = {"data_kind": "design_validation", "interpretation": "ai_unreviewed", "service_use": "forbidden"}
AXES = {"identity", "period", "event", "payout_method", "constraint", "relation", "lifecycle"}
RULE_STATUS = {"expressed", "partially_expressed", "not_expressible"}
# JSON key -> vocabulary axis. Lists are checked element by element.
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


def norm(s):
    return re.sub(r"\s+", "", s)


def quoted_text(md):
    return norm("".join(re.findall(r"```text\n(.*?)```", md, re.S)))


def gap_ids():
    path = VAL / "GAP_REPORT.md"
    if not path.exists():
        return set()
    return set(re.findall(r"^\| (G\d\d) \|", path.read_text(encoding="utf-8"), re.M))


def walk_vocab(obj, where, errors):
    if isinstance(obj, dict):
        for k, v in obj.items():
            axis = VOCAB_KEYS.get(k)
            if axis == "payout" and isinstance(v, dict):
                # engine result shape: {"kind": ..., "amount"|"conditional_amount": {"kind": ...}}
                v = v.get("kind")
                for sub in ("amount", "conditional_amount"):
                    inner = obj[k].get(sub)
                    if isinstance(inner, dict) and inner.get("kind") not in CODES["amount_kind"]:
                        errors.append(f"{where}: `{k}.{sub}.kind` is not an amount_kind code")
            if axis and v is not None:
                for item in v if isinstance(v, list) else [v]:
                    if not isinstance(item, str) or item not in CODES[axis] or item in FORBIDDEN[axis]:
                        errors.append(f"{where}: `{k}`={item!r} is not a {axis} code")
            walk_vocab(v, where, errors)
    elif isinstance(obj, list):
        for x in obj:
            walk_vocab(x, where, errors)


def check_family(path, samples, gaps, errors, index):
    d = json.loads(path.read_text(encoding="utf-8"))
    fam = path.stem
    where = f"encoded/{path.name}"
    if d.get("status") != STATUS:
        errors.append(f"{where}: status must be {STATUS}")
    if d.get("family") != fam:
        errors.append(f"{where}: family must equal file stem")
    walk_vocab(d, where, errors)
    texts = {}
    for doc in d["documents"]:
        s = samples.get(doc["sample_id"])
        if not s:
            errors.append(f"{where}: {doc['doc_id']} sample `{doc['sample_id']}` not in samples.csv")
        elif s["sha256"] != doc["sha256"]:
            errors.append(f"{where}: {doc['doc_id']} sha256 differs from samples.csv")
        ext = VAL / doc["extract"]
        if not ext.exists():
            errors.append(f"{where}: missing extract {doc['extract']}")
            continue
        texts[doc["doc_id"]] = quoted_text(ext.read_text(encoding="utf-8"))
    all_text = "".join(texts.values())
    ids = {}
    for c in d["clauses"]:
        cid = c["clause_id"]
        if cid in ids:
            errors.append(f"{where}: duplicate id {cid}")
        ids[cid] = "clause"
        t = texts.get(c["doc_id"])
        if t is None:
            errors.append(f"{where}: {cid} names unknown doc {c['doc_id']}")
        elif norm(c["anchor"]) not in t:
            errors.append(f"{where}: {cid} anchor is not a verbatim quote in {c['doc_id']}: {c['anchor'][:50]}")
    def refs_ok(owner, refs):
        if not refs:
            errors.append(f"{where}: {owner} has no evidence_refs")
        for r in refs:
            if ids.get(r) != "clause":
                errors.append(f"{where}: {owner} evidence `{r}` is not a clause")
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
        if f.get("raw_value") is not None and norm(f["raw_value"]) not in all_text:
            errors.append(f"{where}: {fid} raw_value is not a verbatim quote: {f['raw_value'][:50]}")
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
        if r["status"] != "not_expressible":
            rp = ROOT / r["file"]
            if not rp.exists():
                errors.append(f"{where}: rule file {r['file']} missing")
                continue
            ids[r["rule_id"]] = "rule"
            rule = json.loads(rp.read_text(encoding="utf-8"))
            if rule.get("publication_state") != "fixture_only":
                errors.append(f"{where}: {r['rule_id']} must stay fixture_only")
            cases = rp.with_name(rp.stem + ".cases.json")
            if not cases.exists() and not any(rp.parent.glob("*.cases.json")):
                errors.append(f"{where}: {r['rule_id']} has no cases")
            index.setdefault("rule_refs", []).append((where, r["rule_id"], rule.get("evidence_refs", [])))
        elif not r.get("reason"):
            errors.append(f"{where}: not_expressible {owner} needs a reason")
    for p in d.get("premium_observations", []):
        pid = p["observation_id"]
        if pid in ids:
            errors.append(f"{where}: duplicate id {pid}")
        ids[pid] = "premium"
        refs_ok(pid, p["evidence_refs"])
        gaps_ok(pid, p.get("gaps"))
        hold_ok(pid, p)
        if p.get("amount_krw") is None and not p.get("price_unavailable_reason"):
            errors.append(f"{where}: {pid} without amount needs price_unavailable_reason")
        if p.get("amount_krw") is not None and (not isinstance(p["amount_krw"], int) or p["amount_krw"] <= 0):
            errors.append(f"{where}: {pid} amount_krw must be a positive integer (0 is never a missing price)")
        if not p.get("comparison_basis_id"):
            errors.append(f"{where}: {pid} needs comparison_basis_id")
        cond = p.get("conditions", {})
        for dim in ("age", "sex"):
            if dim not in cond and not any(m.startswith(dim) for m in p.get("missing_dimensions", [])):
                errors.append(f"{where}: {pid} must state `{dim}` or list it in missing_dimensions")
        if p.get("pay_cycle") not in {"monthly", "annual", "single", None}:
            errors.append(f"{where}: {pid} pay_cycle must be monthly|annual|single")
    index[fam] = ids


def check_screen(path, index, gaps, errors):
    d = json.loads(path.read_text(encoding="utf-8"))
    where = f"screen/{path.name}"
    if d.get("status") != STATUS:
        errors.append(f"{where}: status must be {STATUS}")
    walk_vocab(d, where, errors)
    def visit(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("refs", "evidence") and isinstance(v, list):
                    for r in v:
                        fam, _, rid = r.partition("#")
                        if rid not in index.get(fam, {}):
                            errors.append(f"{where}: ref `{r}` does not resolve to an encoded id")
                elif k == "gaps" and isinstance(v, list):
                    for g in v:
                        if g not in gaps:
                            errors.append(f"{where}: gap {g} is not in the register")
                visit(v)
        elif isinstance(o, list):
            for x in o:
                visit(x)
    visit(d)


def main():
    errors = []
    samples = {}
    for r in csv.DictReader((VAL / "samples.csv").open(encoding="utf-8")):
        if r["sample_id"] in samples:
            errors.append(f"samples.csv: duplicate sample_id {r['sample_id']}")
        samples[r["sample_id"]] = r
    gaps = gap_ids()
    if not gaps:
        errors.append("GAP_REPORT.md: no gap register rows (| Gnn |)")
    index = {}
    fams = sorted((VAL / "encoded").glob("*.json"))
    for p in fams:
        check_family(p, samples, gaps, errors, index)
    for where, rid, refs in index.pop("rule_refs", []):
        for ref in refs:
            fam, _, cid = ref.partition("#")
            if index.get(fam, {}).get(cid) != "clause":
                errors.append(f"{where}: rule {rid} evidence `{ref}` does not resolve to a clause")
    screens = sorted((VAL / "screen").glob("*.json")) if (VAL / "screen").exists() else []
    for p in screens:
        check_screen(p, index, gaps, errors)
    if errors:
        print("validation set invalid:\n  " + "\n  ".join(errors))
        return 1
    n_cl = sum(sum(1 for v in ids.values() if v == "clause") for ids in index.values())
    n_f = sum(sum(1 for v in ids.values() if v == "field") for ids in index.values())
    n_p = sum(sum(1 for v in ids.values() if v == "premium") for ids in index.values())
    print(f"validation ok: {len(samples)} samples, {len(fams)} families, {n_cl} clauses, {n_f} fields, {n_p} price observations, {len(screens)} screen models, {len(gaps)} gaps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
