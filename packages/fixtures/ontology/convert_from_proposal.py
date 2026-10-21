#!/usr/bin/env python3
"""Regenerates packages/fixtures/ontology/ from the onto-0.2 case A-box in the design proposals.

  python3 -I packages/fixtures/ontology/convert_from_proposal.py          # write
  python3 -I packages/fixtures/ontology/convert_from_proposal.py --check  # fail if the files differ

What changes (02_구현계약 §6.1, §8.1): fixture-local raw / segment / clause ids become formal
evidence_ref strings; rule files move to rules/; release content hashes are recomputed because the
member ids changed. Every claim gets origin=fixture (the proposal marks only some).
What does not change: review_status, the _review_note and decision; every rule keeps publication_state=fixture_only. Records that cannot get a
formal ref (no source hash, or no page range) keep their local id and are listed in
`_formal_ref_exceptions`; nothing is invented for them.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SRC = REPO / "docs/blueprint/proposals/온톨로지"
SEG_RULE_VER = "manual-0.1"
EXTRACTION = "manual-case@0.1"


def canon(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def build():
    doc = json.loads((SRC / "abox_cases.json").read_text(encoding="utf-8"))
    raws = {r["id"]: r for r in doc["raw_assets"]}
    idmap, exceptions = {}, []

    for r in doc["raw_assets"]:
        if r.get("sha256"):
            idmap[r["id"]] = "raw:sha256:" + r["sha256"]
    seg_new = {}
    for s in doc["segments"]:
        raw = raws[s["raw_asset"]]
        if raw.get("sha256") and s.get("pages"):
            seg_new[s["id"]] = "seg:%s:p%d-%d:%s:%s" % (
                raw["sha256"][:12], s["pages"][0], s["pages"][1], s["doc_role"], SEG_RULE_VER)
        else:
            exceptions.append(s["id"])
    idmap.update(seg_new)
    for c in doc["clauses"]:
        if c["segment"] in seg_new and c.get("pdf_page"):
            idmap[c["id"]] = "clause:%s/%s#p%d:%s" % (
                seg_new[c["segment"]], c["id"].split("#", 1)[1], c["pdf_page"], EXTRACTION)
            c["extraction"]["edition"] = EXTRACTION
        else:
            exceptions.append(c["id"])
    for r in doc["raw_assets"]:
        if r["id"] not in idmap:
            exceptions.append(r["id"])

    rule_dir = {p: "rules/" + p.split("/")[-1] for p in
                (f"규칙/{f.name}" for f in sorted((SRC / "규칙").glob("*.json")))}
    idmap.update(rule_dir)

    def conv(o):
        if isinstance(o, str):
            return idmap.get(o, o)
        if isinstance(o, list):
            return [conv(x) for x in o]
        if isinstance(o, dict):
            return {idmap.get(k, k): conv(v) for k, v in o.items()}
        return o

    out = conv(doc)
    # every claim of this A-box is test material: the proposal marks only some, the fixture marks all
    for a in out["assertions"]:
        a["origin"] = "fixture"
    out["_status"] += ". 이 파일은 packages/fixtures/ontology/convert_from_proposal.py가 시안에서 만든다(손으로 고치지 않는다)"
    out["_clause_id_note"] = (
        "raw·구획·조항 ID는 02 §6.1 정식 evidence_ref 문법으로 바꿨다(raw:sha256:·seg:·clause:). "
        "구획 규칙 판은 manual-0.1, 추출 판은 manual-case@0.1(손 판독)이다. 옛 ID와의 대응은 id_map.json")
    out["_formal_ref_exceptions"] = sorted(set(exceptions))
    out["_formal_ref_exceptions_note"] = (
        "원본 해시가 없거나 쪽 범위가 없는 자료는 정식 문법(raw_sha12·page_from-page_to)을 채울 값이 없다. "
        "값을 지어내지 않고 지역 ID를 그대로 둔다. 이 목록 밖의 raw·구획·조항 ID는 모두 정식 형식이어야 한다")

    files = {}
    rules = {}
    for f in sorted((SRC / "규칙").glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        r["evidence_refs"] = conv(r["evidence_refs"])
        b = (json.dumps(r, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        files["rules/" + f.name] = b
        rules["rules/" + f.name] = b

    # frozen releases: members use the new ids, hashes cover members + rule files (onjeon-ontology::release)
    section_by_id = {k: {x["id"]: x for x in out.get(k, [])} for k in
                     ("raw_assets", "segments", "terms_editions", "terms_lineages", "clauses", "nodes",
                      "assertions", "conflicts", "gaps", "premium_observations")}
    for rel in out["releases"]:
        sel = {}
        for k, ids in rel["members"].items():
            rel["members"][k] = sorted(ids)
            sel[k] = sorted((section_by_id[k][i] for i in ids), key=lambda x: x["id"])
        rf = {}
        for a in sel["assertions"]:
            if "rule_path" in a:
                rf[a["rule_path"]] = sha(rules[a["rule_path"]])
        rel["rule_files"] = rf
        rel["content_sha256"] = sha(canon({"members": sel, "rule_files": rf}).encode("utf-8"))

    files["abox_cases.json"] = (json.dumps(out, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    files["id_map.json"] = (json.dumps(
        {"_note": "시안 지역 ID → 정식 ID. 감사용 대응표(시험 전용 자료)", "map": dict(sorted(idmap.items()))},
        ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return files


def main():
    files = build()
    bad = []
    for name, b in files.items():
        p = HERE / name
        if "--check" in sys.argv:
            if not p.exists() or p.read_bytes() != b:
                bad.append(name)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
    if bad:
        print("differs:", *bad)
        sys.exit(1)


main()
