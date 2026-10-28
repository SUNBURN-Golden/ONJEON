#!/usr/bin/env python3
"""Read-only cross-reference checks for the V0 registry (no network requests).

Entity IDs are canonical across the three institution tables. listed_in refers
to sources.source_id; homepage/disclosure source IDs and access purposes refer
to entities. source:* access purposes name original scratch files, not source IDs.
Vocabulary columns are checked separately by tools/vocab_check.py.
"""
import argparse
import csv
from pathlib import Path

REG = Path(__file__).resolve().parents[1] / "data/registry"
ENTITY_FILES = ("insurers.csv", "cooperatives_and_others.csv", "excluded_or_historical.csv")
KINDS = ("homepage_redirect", "homepage", "disclosure")


def read_table(path, required, problems):
    """Return (physical line, row) pairs, rejecting malformed or missing inputs."""
    rows = []
    try:
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.reader(f, strict=True)
            fields = next(reader, [])
            if not fields or any(not field.strip() for field in fields):
                problems.append(f"{path.name}:1: missing or empty CSV header")
                return rows
            if len(fields) != len(set(fields)):
                problems.append(f"{path.name}:1: duplicate CSV column")
                return rows
            missing = set(required) - set(fields)
            if missing:
                problems.append(f"{path.name}:1: missing required columns: {', '.join(sorted(missing))}")
                return rows
            for cells in reader:
                if len(cells) != len(fields):
                    problems.append(f"{path.name}:{reader.line_num}: expected {len(fields)} cells, got {len(cells)}")
                    continue
                rows.append((reader.line_num, dict(zip(fields, cells))))
    except (OSError, UnicodeError) as exc:
        problems.append(f"{path.name}: cannot read CSV ({type(exc).__name__})")
    except csv.Error as exc:
        problems.append(f"{path.name}:{reader.line_num}: invalid CSV: {exc}")
    return rows


def add_id(value, location, field, index, problems):
    if not value or value != value.strip():
        problems.append(f"{location}: {field} must be non-empty without surrounding whitespace")
    elif value in index:
        problems.append(f"{location}: duplicate {field} {value!r} (first at {index[value]})")
    else:
        index[value] = location


def check(registry_dir=REG):
    problems = []
    entities = {}
    tables = {}
    for name in ENTITY_FILES:
        tables[name] = read_table(registry_dir / name, ("insurer_id", "listed_in"), problems)
        for line, row in tables[name]:
            add_id(row["insurer_id"], f"{name}:{line}", "insurer_id", entities, problems)

    sources = read_table(registry_dir / "sources.csv", ("source_id",), problems)
    source_ids = {}
    for line, row in sources:
        add_id(row["source_id"], f"sources.csv:{line}", "source_id", source_ids, problems)

    for name, rows in tables.items():
        for line, row in rows:
            # An empty list is legitimate for an unverified seed institution.
            if row["listed_in"]:
                for source_id in row["listed_in"].split(";"):
                    if source_id not in source_ids:
                        problems.append(f"{name}:{line}: listed_in references unknown source_id {source_id!r}")

    def entity_reference(value, separator, location, field):
        for kind in KINDS:
            prefix = kind + separator
            if value.startswith(prefix):
                entity_id = value[len(prefix):]
                if entity_id not in entities:
                    problems.append(f"{location}: {field} {value!r} references unknown insurer_id {entity_id!r}")
                break

    for line, row in sources:
        entity_reference(row["source_id"], "_", f"sources.csv:{line}", "source_id")
    access = read_table(registry_dir / "access_log.csv", ("purpose",), problems)
    for line, row in access:
        entity_reference(row["purpose"], ":", f"access_log.csv:{line}", "purpose")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-dir", type=Path, default=REG)
    args = parser.parse_args(argv)
    problems = check(args.registry_dir)
    if problems:
        print("registry cross-reference errors:\n  " + "\n  ".join(problems))
        return 1
    print("registry cross-references ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
