#!/usr/bin/env python3
"""Normalize data/registry CSVs to the canonical vocabulary (packages/schemas/vocabulary.json).

- `status` -> `entity_evidence` (two_or_more_sources | one_source | seed)
- raw access results -> `host_access` codes, raw text kept in `*_detail`
- adds `disclosure_status` (acquisition_status) and `disclosure_gap_reason`
  Access checks alone never prove archival; reachable URLs remain unqueried
  for immutable preservation, with their host_access evidence retained.
- adds `product_list_status` / `product_list_reason` so the lower denominator
  (products and riders per insurer) is tracked even before it is enumerated
- adds `product_list_reason_codes` (`;`-separated, see PRODUCT_LIST_REASON_CODES)
  while `product_list_status = unqueried`

Idempotent: running it twice gives the same files.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data/registry"
VOCAB = json.loads((ROOT / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))


def axis(axis_id):
    return next(a for a in VOCAB["axes"] if a["id"] == axis_id)


HOST = axis("host_access")
HOST_CODES = {x["code"]: x for x in HOST["values"]}
ALIAS = {al: x["code"] for x in HOST["values"] for al in x["deprecated_aliases"]}
EVID = {al: x["code"] for x in axis("entity_evidence")["values"] for al in x["deprecated_aliases"]}
EVID_CODES = {x["code"] for x in axis("entity_evidence")["values"]}


def host_code(raw):
    """Map a raw access result (possibly 'A -> B (url)') to a host_access code."""
    raw = (raw or "").strip()
    if not raw:
        return "not_checked"
    if raw in HOST_CODES:
        return raw
    final = raw.split("->")[-1].strip()
    final = re.sub(r"\s*\(.*\)$", "", final).strip()
    if final in HOST_CODES:
        return final
    if final in ALIAS:
        return ALIAS[final]
    if final in ("200", "301", "302", "307"):
        return "reachable"
    if final == "403":
        return "origin_denied"
    if final == "429":
        return "rate_limited"
    if final in ("502", "503", "504"):
        return "proxy_error"
    raise SystemExit(f"unmapped access result: {raw!r} -- add it to host_access in vocabulary.json")


def disclosure_entry_reachable(row):
    return bool(row.get("disclosure_url", "").strip()) and row.get("disclosure_access") == "reachable"


def disclosure(row):
    if disclosure_entry_reachable(row):
        # The registry records access observations, not verified immutable assets.
        # Do not infer archived from host_access.maps_to or a legacy status claim.
        return "unqueried", "공시 URL 접근 확인(reachable). 원문 무결성 검사·불변 보관 전"
    home = row.get("home_access", "not_checked")
    maps_to = HOST_CODES[home]["maps_to"]
    if home in ("reachable", "js_shell"):
        return "failed", "홈페이지는 열리나 정적 HTML에서 공시실 진입점을 찾지 못함(JS 메뉴 등)"
    if maps_to == "unqueried":
        return "unqueried", "아직 홈페이지·공시실을 조회하지 않음"
    return maps_to, f"홈페이지 접근 결과: {home}"


PRODUCT_LIST_REASON_CODES = {
    "awaiting_T-DT-04": "상품·특약 목록 열거는 T-DT-04 몫이고 아직 실행 전",
    "awaiting_domestic_env": "실데이터 열거는 국내 IP 수집 실행 환경(O19) 준비 전",
    "disclosure_entry_missing": "공시 URL이 없거나 disclosure_access가 reachable이 아님",
    "foreign_sandbox_geo_blocked": "해외 IP 샌드박스에서 홈페이지·공시실이 해외 IP 차단됨",
}


def product_list_codes(row):
    """Reason codes for a product list that has not been enumerated yet ('' once it has a status)."""
    if row.get("product_list_status") != "unqueried":
        return row.get("product_list_reason_codes", "")
    codes = ["awaiting_T-DT-04", "awaiting_domestic_env"]
    if not disclosure_entry_reachable(row):
        codes.append("disclosure_entry_missing")
    if "geo_blocked" in (row.get("home_access"), row.get("disclosure_access")):
        codes.append("foreign_sandbox_geo_blocked")
    return ";".join(codes)


def normalize(path, has_disclosure=True):
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return 0
    out = []
    for r in rows:
        r = dict(r)
        if "status" in r:
            s = r.pop("status")
            r["entity_evidence"] = EVID.get(s, s)
        if r.get("entity_evidence") not in EVID_CODES:
            raise SystemExit(f"{path.name}: bad entity_evidence {r.get('entity_evidence')!r}")
        for col in ("disclosure_access", "home_access"):
            if col in r:
                raw = r[col]
                code = host_code(raw)
                if f"{col}_detail" not in r:
                    r[f"{col}_detail"] = "" if raw == code else raw
                r[col] = code
        if has_disclosure:
            st, why = disclosure(r)
            r["disclosure_status"] = st
            r["disclosure_gap_reason"] = why
            r.setdefault("product_list_status", "unqueried")
            r.setdefault("product_list_reason", "상품·특약 목록 열거 전(M3 어댑터 단계). 표본 검증과 무관하게 전 대상을 추적")
            r["product_list_reason_codes"] = product_list_codes(r)
        out.append(r)
    order = list(out[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=order)
        w.writeheader()
        w.writerows(out)
    return len(out)


def normalize_access_log(path):
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for r in rows:
        if "host_access" not in r:
            r["host_access"] = host_code(r.get("result", ""))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    print("insurers", normalize(REG / "insurers.csv"))
    print("cooperatives_and_others", normalize(REG / "cooperatives_and_others.csv"))
    print("access_log", normalize_access_log(REG / "access_log.csv"))
