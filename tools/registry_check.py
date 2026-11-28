#!/usr/bin/env python3
"""Read-only registry, access and supervisory evidence checks (stdlib only).

Usage (repository root): python3 -I tools/registry_check.py
Add --denominator to emit the validated institution IDs, one per line.
Add --access-digests to emit the evidence for reachable HTTP 200 observations.
Only homepage, homepage_redirect and disclosure purposes identify entities.
The dated supervisory snapshot has its own recorded list artifact names.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry_normalize as rn
import vocab_check as vc

ROOT = Path(__file__).resolve().parents[1]
INSURERS = "insurers.csv"
OTHER_INSTITUTIONS = "cooperatives_and_others.csv"
SCOPE_TABLES = (INSURERS, OTHER_INSTITUTIONS)
ENTITY_TABLES = (*SCOPE_TABLES, "excluded_or_historical.csv")
SOURCES = "sources.csv"
ACCESS_LOG = "access_log.csv"
SCOPE_COLUMNS = {"in_denominator", "scope_adr"}
SCOPE_ADR = "ADR-0018"
EPOST = "public-epost"
PREFIXES = ("homepage_redirect", "homepage", "disclosure")
CROSSCHECK_DATE = "2026-11-10"
CROSSCHECK = f"authority_crosscheck_{CROSSCHECK_DATE}.csv"
SUPERVISORY_REQUESTS = "tools/evidence/audit5-registry-readme-sync/requests.tsv"
SHA256 = re.compile(r"[0-9a-f]{64}")
ENTITY_ROW_COUNTS = {INSURERS: 53, OTHER_INSTITUTIONS: 16, "excluded_or_historical.csv": 49}
OBSERVATION_ROW_COUNTS = {
    SOURCES: ("retrieved_at", {"2026-10-09": 66, CROSSCHECK_DATE: 9}),
    ACCESS_LOG: ("attempted_at", {"2026-10-09": 98, CROSSCHECK_DATE: 14}),
}
# These five original probes have no recorded response body digest. Pin the
# exact access records so missing hashes on other requests fail validation.
LEGACY_ACCESS_RECORD_DIGESTS = {
    "b9a144f0f96a82f6dcf67a89daeeb5051d45fef1d18b1ffeec738873bff036ad",  # DART home
    "e642ab7d7b31b42d4d3d917b03715c34a94c6a03077cfb2ecf22bfd60454f6bd",  # KFPA home
    "143e132e15087f43d51713ff1602177df58953f78c29369978473f75c4a215a8",  # FSC home
    "c3f51a39556d781f65e4b5fd1e19ec4b3e8e23c5b54f872843c5f9a3332095c0",  # Wikipedia home
    "b9b73272501aeeb089821eada07f52d5750d935146677a6f3293355ae530f71a",  # First DART form request
}
ACCESS_DIGEST_COLUMNS = ("line", "attempted_at", "purpose", "url", "final_url",
                         "digest_kind", "sha256", "evidence")
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
    SOURCES: {"source_id", "url", "retrieved_at", "http_status", "sha256"},
    ACCESS_LOG: {"purpose", "url", "attempted_at", "result", "host_access", "host",
                 "http_code", "curl_exit", "final_url", "detail"},
    CROSSCHECK: {"category", "fisis_id", "fine_id", "registry_table", "registry_id",
                 "registry_name", "comparison", "fisis_source_id", "fine_source_ids"},
}
for name in SCOPE_TABLES:
    REQUIRED[name].update(SCOPE_COLUMNS)


def check(root=ROOT):
    """Return path/physical-line diagnostics; never normalize or write inputs."""
    problems, _, _ = _inspect(root)
    return problems


def read_table(root, path, required, problems, delimiter=","):
    rows = []
    kind = "CSV" if delimiter == "," else "TSV"
    try:
        with (root / path).open(encoding="utf-8", newline="") as f:
            reader = csv.reader(f, delimiter=delimiter, strict=True)
            fields = next(reader, [])
            if not fields or len(fields) != len(set(fields)):
                problems.append(f"{path}:1: missing or duplicate CSV header")
                return rows
            missing = required - set(fields)
            if missing:
                problems.append(f"{path}:1: missing required columns: {', '.join(sorted(missing))}")
                return rows
            for cells in reader:
                if len(cells) != len(fields):
                    problems.append(f"{path}:{reader.line_num}: expected {len(fields)} cells, got {len(cells)}")
                    continue
                rows.append((reader.line_num, dict(zip(fields, cells))))
    except (OSError, UnicodeError) as exc:
        problems.append(f"{path}:1: cannot read {kind}: {exc}")
    except csv.Error as exc:
        problems.append(f"{path}:{reader.line_num}: invalid {kind}: {exc}")
    return rows


def _inspect(root):
    root = Path(root)
    problems = []

    def fail(name, line, message):
        problems.append(f"data/registry/{name}:{line}: {message}")

    tables = {name: read_table(root, f"data/registry/{name}", required, problems)
              for name, required in REQUIRED.items()}
    manifest = read_table(root, SUPERVISORY_REQUESTS,
                          {"started_at", "method", "host", "url", "post_data", "http_code",
                           "curl_exit", "sha256", "final_url"}, problems, delimiter="\t")

    # Stop before foreign-key checks if the input structure is incomplete.
    if problems:
        return problems, [], []
    vocab = json.loads((root / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))
    problems.extend(vc.lint_registry(vocab, root=root))
    check_snapshot_counts(tables, fail)

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
    sources = index((SOURCES,), "source_id")
    denominator_ids = check_scope(tables, fail)
    for name in ENTITY_TABLES:
        for line, row in tables[name]:
            # These CSVs track access evidence. Archival requires a verified archive record.
            if row.get("disclosure_status") == "archived":
                fail(name, line, "disclosure_status='archived' is unsupported in the access registry "
                     f"for {row['insurer_id']!r}")
            listed_in = row["listed_in"]
            if not listed_in and row.get("entity_evidence") != "seed":
                fail(name, line, f"listed_in is empty for non-seed {row['insurer_id']!r}")
            for source in listed_in.split(";") if listed_in else ():
                if source not in sources:
                    fail(name, line, f"listed_in references unknown source_id {source!r}")
            for column in ("home_access", "disclosure_access"):
                detail = row.get(f"{column}_detail", "")
                if detail:
                    access_matches(name, line, column, row[column], detail, fail)

    observations = {}
    for line, row in tables[ACCESS_LOG]:
        access_matches(ACCESS_LOG, line, "host_access", row["host_access"], row["result"], fail)
        prefix, _, key = row["purpose"].partition(":")
        if prefix in PREFIXES:
            if key not in entities:
                fail(ACCESS_LOG, line, f"purpose references unknown insurer_id {key!r}")
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
                       for _, attempt in tables[ACCESS_LOG]):
                fail(name, line, f"no matching access_log observation for {purpose!r}")
            break
    check_authority_crosscheck(tables, entities, sources, fail)
    digests = check_access_digests(tables, manifest, fail, problems)
    return problems, denominator_ids, digests


def check_snapshot_counts(tables, fail):
    for name, expected in ENTITY_ROW_COUNTS.items():
        if len(tables[name]) != expected:
            fail(name, 1, f"expected {expected} data rows, got {len(tables[name])}")
    for name, (column, expected) in OBSERVATION_ROW_COUNTS.items():
        counts = Counter(row[column][:10] for _, row in tables[name])
        for date in sorted(counts.keys() | expected.keys()):
            if counts[date] != expected.get(date, 0):
                fail(name, 1, f"{date!r}: expected {expected.get(date, 0)} data rows, got {counts[date]}")


def check_access_digests(tables, manifest, fail, problems):
    sources_by_request = {}
    for line, row in tables[SOURCES]:
        if not SHA256.fullmatch(row["sha256"]):
            fail(SOURCES, line, f"invalid SHA-256 for source_id {row['source_id']!r}")
        if row["http_status"] == "200":
            key = (row["retrieved_at"], row["url"])
            if key in sources_by_request:
                fail(SOURCES, line, f"duplicate HTTP 200 source observation for {key!r}")
            sources_by_request[key] = row

    manifest_by_request = {}
    for line, row in manifest:
        key = (row["started_at"], row["url"])
        if key in manifest_by_request:
            problems.append(f"{SUPERVISORY_REQUESTS}:{line}: duplicate request for {key!r}")
        manifest_by_request[key] = line, row

    seen = set()
    digests = []
    for line, row in tables[ACCESS_LOG]:
        key = (row["attempted_at"], row["url"])
        if key in seen:
            fail(ACCESS_LOG, line, f"duplicate access observation for {key!r}")
        seen.add(key)

        reachable_200 = row["http_code"] == "200" and row["host_access"] == "reachable"
        if not reachable_200 and row["result"] != "200":
            continue
        if not reachable_200 or row["result"] != "200" or row["curl_exit"] != "0":
            fail(ACCESS_LOG, line, f"inconsistent reachable HTTP 200 observation for {row['purpose']!r}")
            continue

        source = sources_by_request.get(key)
        digest_kind = "response_body"
        if row["attempted_at"].startswith(CROSSCHECK_DATE + "T"):
            manifest_line, request = manifest_by_request.get(key, (None, None))
            if request is None or not matches_manifest_request(row, request):
                fail(ACCESS_LOG, line, f"no matching supervisory request for {row['purpose']!r}")
                continue
            digest = request["sha256"]
            evidence = f"{SUPERVISORY_REQUESTS}:{manifest_line}"
            if source is not None and digest != source["sha256"]:
                fail(ACCESS_LOG, line, f"conflicting response SHA-256 in {evidence} and {source['source_id']!r}")
        elif source is not None:
            digest = source["sha256"]
            evidence = f"data/registry/{SOURCES}#{source['source_id']}"
        else:
            payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest = hashlib.sha256(payload).hexdigest()
            if digest not in LEGACY_ACCESS_RECORD_DIGESTS:
                fail(ACCESS_LOG, line, f"no matching response SHA-256 for {row['purpose']!r}")
                continue
            digest_kind = "access_record_only"
            evidence = f"data/registry/{ACCESS_LOG}:{line}"
        if not SHA256.fullmatch(digest):
            fail(ACCESS_LOG, line, f"invalid response SHA-256 in {evidence}")
            continue
        digests.append({"line": line, "attempted_at": row["attempted_at"], "purpose": row["purpose"],
                        "url": row["url"], "final_url": row["final_url"], "digest_kind": digest_kind,
                        "sha256": digest, "evidence": evidence})
    return digests


def matches_manifest_request(row, request):
    if request["method"] == "GET" and not request["post_data"]:
        detail = ""
    elif request["method"] == "POST":
        detail = f"POST {request['post_data']}"
    else:
        return False
    return (row["detail"] == detail
            and all(row[field] == request[field] for field in ("host", "final_url", "http_code", "curl_exit")))


def check_scope(tables, fail):
    """Validate ADR-0018 and select the institution IDs from both scope inputs."""
    if not any(row["insurer_id"] == EPOST for _, row in tables[OTHER_INSTITUTIONS]):
        fail(OTHER_INSTITUTIONS, 1, f"{SCOPE_ADR} requires {EPOST!r}")

    included = []
    for name in SCOPE_TABLES:
        for line, row in tables[name]:
            key = row["insurer_id"]
            # Track all current insurers. Of the separately listed institutions,
            # ADR-0018 includes EPOST and excludes mutual aid and K-SURE.
            expected = "true" if name == INSURERS or key == EPOST else "false"
            flag = row["in_denominator"]
            if flag != expected:
                fail(name, line, f"in_denominator={flag!r} for {key!r}, expected {expected!r} under {SCOPE_ADR}")
            if row["scope_adr"] != SCOPE_ADR:
                fail(name, line, f"scope_adr={row['scope_adr']!r} for {key!r}, expected {SCOPE_ADR!r}")
            if flag == "true":
                included.append(key)
    return included


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
                or not SHA256.fullmatch(source["sha256"])):
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
        comparison = {"insurers.csv": "matched", "excluded_or_historical.csv": "excluded", "": "missing"}
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
    parser = argparse.ArgumentParser(description="Validate the institution registry.")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--denominator", action="store_true", help="print the validated institution IDs")
    output.add_argument("--access-digests", action="store_true", help="print the validated access digest CSV")
    args = parser.parse_args()
    problems, denominator_ids, digests = _inspect(ROOT)
    if problems:
        print("registry check failed:\n  " + "\n  ".join(problems),
              file=sys.stderr if args.denominator or args.access_digests else sys.stdout)
        return 1
    if args.denominator:
        print("\n".join(denominator_ids))
    elif args.access_digests:
        writer = csv.DictWriter(sys.stdout, fieldnames=ACCESS_DIGEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(digests)
    else:
        kinds = Counter(row["digest_kind"] for row in digests)
        print(f"registry check passed ({len(digests)} reachable HTTP 200 observations: "
              f"{kinds['response_body']} response body digests, {kinds['access_record_only']} access record digests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
