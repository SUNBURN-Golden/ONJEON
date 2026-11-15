#!/usr/bin/env python3
"""Read-only registry ID, vocabulary and access-evidence checks (stdlib only).

Usage (repository root): python3 -I tools/registry_check.py
Source/probe filenames in access_log.purpose are historical artifact names, not
source_id references. Only homepage, homepage_redirect and disclosure identify
entities; their sources.csv equivalents use an underscore after the prefix.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry_normalize as rn
import vocab_check as vc

ROOT = Path(__file__).resolve().parents[1]
ENTITY_TABLES = ("insurers.csv", "cooperatives_and_others.csv", "excluded_or_historical.csv")
PREFIXES = ("homepage_redirect", "homepage", "disclosure")
REQUIRED = {
    **{name: {"insurer_id", "listed_in", "home_access", "disclosure_access"}
       for name in ENTITY_TABLES},
    "sources.csv": {"source_id", "url", "retrieved_at", "http_status"},
    "access_log.csv": {"purpose", "url", "attempted_at", "result", "host_access"},
}


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
    return problems


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
    print("registry check passed (IDs, vocabulary, access evidence)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
