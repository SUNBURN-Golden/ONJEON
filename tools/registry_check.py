#!/usr/bin/env python3
"""Read-only registry, access and supervisory evidence checks (stdlib only).

Usage (repository root): python3 -I tools/registry_check.py
Only homepage, homepage_redirect and disclosure purposes identify entities.
The dated supervisory snapshot has its own recorded list artifact names.
"""
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry_normalize as rn
import vocab_check as vc

ROOT = Path(__file__).resolve().parents[1]
ENTITY_TABLES = ("insurers.csv", "cooperatives_and_others.csv", rn.HISTORICAL_TABLE)
PREFIXES = ("homepage_redirect", "homepage", "disclosure")
CROSSCHECK_DATE = "2026-11-10"
CROSSCHECK = f"authority_crosscheck_{CROSSCHECK_DATE}.csv"
FISIS_BASE_MONTH = "202606"
FISIS_URL = "https://fisis.fss.or.kr/fss/wa/fsv302_getFinanceList.do"
FINE_URL = "https://fine.fss.or.kr/fine/fncco/systemFncCo/list.do"
FINE_CATEGORIES = {
    "life_domestic": ("국내생명보험회사", 2),
    "life_foreign": ("외국생명보험회사", 1),
    "nonlife_domestic": ("국내손해보험회사", 2),
    "nonlife_foreign": ("외국손해보험회사", 2),
}
REQUIRED = {
    **{name: {"insurer_id", "name_ko", "listed_in", "home_access", "disclosure_access"}
       for name in ENTITY_TABLES},
    "sources.csv": {"source_id", "url", "retrieved_at", "http_status", "sha256"},
    "access_log.csv": {"purpose", "url", "attempted_at", "result", "host_access", "host",
                       "http_code", "curl_exit", "final_url", "detail"},
    CROSSCHECK: {"category", "fisis_id", "fine_id", "registry_table", "registry_id",
                 "registry_name", "comparison", "fisis_source_id", "fine_source_ids"},
}
REQUIRED[rn.HISTORICAL_TABLE].update({
    "in_current_assoc_list", "historical_product_scope", "historical_scope_reason",
    "successor_insurer_id", "successor_evidence_url", "disclosure_gap_reason",
    "product_list_status", "product_list_reason", "product_list_reason_codes",
})


def check(root=ROOT):
    """Return path/physical-line diagnostics; never normalize or write inputs."""
    root = Path(root)
    problems = []
    tables = {}

    def fail(name, line, message):
        problems.append(f"data/registry/{name}:{line}: {message}")

    for name, required in REQUIRED.items():
        path = root / "data/registry" / name
        rows = []
        tables[name] = rows
        try:
            with path.open(encoding="utf-8", newline="") as f:
                reader = csv.reader(f, strict=True)
                fields = next(reader, [])
                if not fields or len(fields) != len(set(fields)):
                    fail(name, 1, "missing or duplicate CSV header")
                    continue
                missing = required - set(fields)
                if missing:
                    fail(name, 1, f"missing required columns: {', '.join(sorted(missing))}")
                    continue
                for cells in reader:
                    if len(cells) != len(fields):
                        fail(name, reader.line_num, f"expected {len(fields)} cells, got {len(cells)}")
                        continue
                    rows.append((reader.line_num, dict(zip(fields, cells))))
        except (OSError, UnicodeError) as exc:
            fail(name, 1, f"cannot read CSV: {exc}")
        except csv.Error as exc:
            fail(name, reader.line_num, f"invalid CSV: {exc}")

    # Stop before foreign-key checks if the input structure is incomplete.
    if problems:
        return problems
    vocab = json.loads((root / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))
    problems.extend(vc.lint_registry(vocab, root=root))

    def index(names, field):
        found = {}
        for name in names:
            for line, row in tables[name]:
                key = row[field]
                if not key or key != key.strip():
                    fail(name, line, f"empty or untrimmed {field}: {key!r}")
                elif key in found:
                    fail(name, line, f"duplicate {field}: {key!r}")
                else:
                    found[key] = (name, line, row)
        return found

    entities = index(ENTITY_TABLES, "insurer_id")
    sources = index(("sources.csv",), "source_id")
    for name in ENTITY_TABLES:
        for line, row in tables[name]:
            # These CSVs track access evidence. Archival requires a verified archive record.
            if row.get("disclosure_status") == "archived":
                fail(name, line, "disclosure_status='archived' is unsupported in the access registry "
                     f"for {row['insurer_id']!r}")
            # Empty listed_in is legitimate for an explicitly unverified seed.
            for source in row["listed_in"].split(";") if row["listed_in"] else ():
                if source not in sources:
                    fail(name, line, f"listed_in references unknown source_id {source!r}")
            for column in ("home_access", "disclosure_access"):
                detail = row.get(f"{column}_detail", "")
                if detail:
                    access_matches(name, line, column, row[column], detail, fail)

    observations = {}
    for line, row in tables["access_log.csv"]:
        access_matches("access_log.csv", line, "host_access", row["host_access"], row["result"], fail)
        prefix, _, key = row["purpose"].partition(":")
        if prefix in PREFIXES:
            if key not in entities:
                fail("access_log.csv", line, f"purpose references unknown insurer_id {key!r}")
                continue
            column = "disclosure_access" if prefix == "disclosure" else "home_access"
            observations.setdefault((key, column), []).append(row)

    # An entity summary represents the final recorded homepage/redirect result.
    # Preserve earlier attempts; a successful initial response cannot hide a
    # later TLS failure (the Hyundai finding).
    for (key, column), attempts in observations.items():
        latest = max(attempts, key=lambda row: row["attempted_at"])
        name, line, entity = entities[key]
        if entity[column] != latest["host_access"]:
            fail(name, line, f"{column}={entity[column]!r} disagrees with latest access_log "
                 f"result {latest['host_access']!r} for {key!r}")

    for key, (name, line, row) in sources.items():
        for prefix in PREFIXES:
            if not key.startswith(prefix + "_"):
                continue
            entity_id = key[len(prefix) + 1:]
            if entity_id not in entities:
                fail(name, line, f"source_id references unknown insurer_id {entity_id!r}")
            # Source IDs and purposes use different separators, but must trace
            # to the same URL, timestamp and original result.
            purpose = f"{prefix}:{entity_id}"
            if not any(attempt["purpose"] == purpose and attempt["url"] == row["url"]
                       and attempt["attempted_at"] == row["retrieved_at"]
                       and attempt["result"] == row["http_status"]
                       for _, attempt in tables["access_log.csv"]):
                fail(name, line, f"no matching access_log observation for {purpose!r}")
            break
    check_historical_scope(tables[rn.HISTORICAL_TABLE], entities, fail)
    check_authority_crosscheck(tables, entities, sources, fail)
    return problems


def check_historical_scope(rows, entities, fail):
    name = rn.HISTORICAL_TABLE
    for line, row in rows:
        scope = row["historical_product_scope"]
        if scope not in rn.HISTORICAL_SCOPES:
            fail(name, line, f"invalid historical_product_scope {scope!r}")
        if row["in_current_assoc_list"] != "false":
            fail(name, line, "historical evidence requires in_current_assoc_list=false")
        for field in ("historical_scope_reason", "disclosure_gap_reason", "product_list_reason"):
            if not row[field].strip():
                fail(name, line, f"missing {field}")

        if row["product_list_status"] == "unqueried":
            expected = rn.product_list_codes(row)
            if row["product_list_reason_codes"] != expected:
                fail(name, line, f"product_list_reason_codes must be {expected!r} for {scope!r}")
        elif scope in rn.HISTORICAL_INACTIVE_REASONS:
            fail(name, line, f"{scope!r} requires product_list_status='unqueried'")

        successor = row["successor_insurer_id"]
        evidence = row["successor_evidence_url"]
        if not successor and not evidence:
            continue
        entity = entities.get(successor)
        if successor == row["insurer_id"] or entity is None or entity[0] == "cooperatives_and_others.csv":
            fail(name, line, f"invalid successor_insurer_id {successor!r}")
        try:
            url = urlsplit(evidence)
            valid_url = (url.scheme == "https" and url.hostname and url.username is None
                         and not any(ch.isspace() for ch in evidence))
        except ValueError:
            valid_url = False
        if not valid_url:
            fail(name, line, "successor_evidence_url must be a public HTTPS source")


def check_authority_crosscheck(tables, entities, sources, fail):
    """Verify the dated list joins and their provenance using only local evidence."""
    stamp = CROSSCHECK_DATE.replace("-", "")
    requests = {}
    categories = {}
    for group, part in (("life", "H"), ("nonlife", "I")):
        source_id = f"fisis_{stamp}_{group}_list"
        requests[source_id] = (FISIS_URL, "json", f"POST partDiv={part}&baseMonth={FISIS_BASE_MONTH}")
    for category, (name, pages) in FINE_CATEGORIES.items():
        fine_ids = []
        for page in range(1, pages + 1):
            source_id = f"fine_{stamp}_{category}_p{page}"
            query = urlencode(dict(menuNo=900038, pageIndex=page, searchTyin=name))
            requests[source_id] = (f"{FINE_URL}?{query}", "html", "")
            fine_ids.append(source_id)
        group = category.split("_", 1)[0]
        categories[category] = (f"fisis_{stamp}_{group}_list", ";".join(fine_ids))

    for source_id, (url, extension, detail) in requests.items():
        if source_id not in sources:
            fail("sources.csv", 1, f"missing supervisory list source {source_id!r}")
            continue
        name, line, source = sources[source_id]
        if (source["url"] != url or source["http_status"] != "200"
                or not source["retrieved_at"].startswith(CROSSCHECK_DATE + "T")
                or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])):
            fail(name, line, f"invalid supervisory list source {source_id!r} (URL, status, date or SHA-256)")
        if not any(attempt["purpose"] == f"source:{source_id}.{extension}"
                   and attempt["host"] == urlsplit(url).hostname
                   and attempt["url"] == attempt["final_url"] == url
                   and attempt["attempted_at"] == source["retrieved_at"]
                   and attempt["http_code"] == attempt["result"] == "200"
                   and attempt["curl_exit"] == "0" and attempt["detail"] == detail
                   for _, attempt in tables["access_log.csv"]):
            fail(name, line, f"no matching successful access_log observation for {source_id!r}")

    seen = {column: set() for column in ("fisis_id", "fine_id", "registry_id")}
    matched = set()
    for line, row in tables[CROSSCHECK]:
        category = row["category"]
        if category not in categories:
            fail(CROSSCHECK, line, f"unknown supervisory category {category!r}")
            continue
        for column, ref, expected in zip(("fisis_id", "fine_id"), ("fisis_source_id", "fine_source_ids"),
                                         categories[category]):
            code = row[column]
            if code:
                if not re.fullmatch(r"[0-9]+", code) or code in seen[column]:
                    fail(CROSSCHECK, line, f"invalid or duplicate {column} {code!r}")
                seen[column].add(code)
            if row[ref] != (expected if code else ""):
                fail(CROSSCHECK, line, f"{ref} disagrees with {column} and supervisory category {category!r}")

        table, key, name = (row[column] for column in ("registry_table", "registry_id", "registry_name"))
        comparison = {"insurers.csv": "matched", rn.HISTORICAL_TABLE: "excluded", "": "missing"}
        if table not in comparison or row["comparison"] != comparison[table]:
            fail(CROSSCHECK, line, f"invalid comparison for registry_table {table!r}")
        if not row["fisis_id"] and not row["fine_id"]:
            fail(CROSSCHECK, line, "supervisory row has neither list ID")
        if not table:
            if key or name:
                fail(CROSSCHECK, line, "missing entity must have empty registry references")
            continue
        entity = entities.get(key)
        if entity is None or entity[0] != table or entity[2]["name_ko"] != name:
            fail(CROSSCHECK, line, f"invalid registry reference for {key!r} in {table!r}")
        if key in seen["registry_id"]:
            fail(CROSSCHECK, line, f"duplicate registry_id {key!r}")
        seen["registry_id"].add(key)
        if table == "insurers.csv":
            if not row["fisis_id"] or not row["fine_id"]:
                fail(CROSSCHECK, line, f"insurer {key!r} requires both FISIS and Fine IDs")
            matched.add(key)

    for line, row in tables["insurers.csv"]:
        if row["insurer_id"] not in matched:
            fail("insurers.csv", line, f"no supervisory cross-check for {row['insurer_id']!r}")


def access_matches(name, line, column, code, raw, fail):
    try:
        expected = rn.host_code(raw)
    except SystemExit:
        fail(name, line, f"unmapped raw access evidence {raw!r}")
        return
    if code != expected:
        fail(name, line, f"{column}={code!r} disagrees with raw access evidence {raw!r} ({expected})")


def main():
    problems = check()
    if problems:
        print("registry check failed:\n  " + "\n  ".join(problems))
        return 1
    print("registry check passed (IDs, vocabulary, access, historical scope and supervisory evidence)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
