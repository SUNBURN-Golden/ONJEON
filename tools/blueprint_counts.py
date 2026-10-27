#!/usr/bin/env python3
"""Compare BLUEPRINT §11 counts with Cargo discovery and canonical repository data.

--write refreshes only the generated inventory, never status or release gates.
Discovery counts registered tests (including ignored tests), not passing tests.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validation_check

START = "<!-- blueprint-counts:start -->"
END = "<!-- blueprint-counts:end -->"
CARGO = ["cargo", "test", "--locked", "--color", "never", "-p",
         "onjeon-rules-engine", "--", "--list"]


def cargo_counts(output):
    """Require a complete Cargo listing; do not silently interpret failures as zero."""
    totals = {"rust_tests": 0, "rust_doctests": 0}
    kind = None
    listed = 0
    sections = set()
    for line in output.splitlines():
        if re.match(r"\s+(?:Running|Doc-tests) ", line):
            if kind is not None:
                raise ValueError("incomplete Cargo test listing")
            kind = "rust_doctests" if line.lstrip().startswith("Doc-tests ") else "rust_tests"
            listed = 0
        elif line.endswith(": test"):
            if kind is None:
                raise ValueError("Cargo test entry without a suite")
            listed += 1
        elif match := re.fullmatch(r"(\d+) tests?, (\d+) benchmarks?", line):
            if kind is None or int(match[1]) != listed or int(match[2]) != 0:
                raise ValueError("Cargo test listing summary mismatch")
            totals[kind] += listed
            sections.add(kind)
            kind = None
    if kind is not None or sections != set(totals) or not all(totals.values()):
        raise ValueError("missing or incomplete Cargo test/doctest listing")
    return totals


def collect(root, listing):
    counts = cargo_counts(listing)
    axes = json.loads((root / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))["axes"]
    rules = []
    for path in sorted((root / "packages/fixtures/rules/real").glob("*.json")):
        if path.name.endswith(".cases.json"):
            continue
        rule = json.loads(path.read_text(encoding="utf-8"))
        if not rule.get("rule_id") or rule.get("publication_state") != "fixture_only":
            raise ValueError(f"invalid real-clause fixture: {path.name}")
        rules.append(rule["rule_id"])
    if not rules or len(set(rules)) != len(rules) or not axes:
        raise ValueError("missing vocabulary/rules or duplicate rule IDs")
    counts.update(real_clause_rules=len(rules), vocabulary_axes=len(axes),
                  tamper_tests=len(validation_check.mutations()))
    if not counts["tamper_tests"]:
        raise ValueError("no validation checker mutations")
    return counts


def render(counts):
    return "\n".join([
        START,
        "현재 저장소의 등록 수(자동 생성). Rust는 `onjeon-rules-engine`만 세며, "
        "단위·통합 시험과 doctest를 구분한다. 무시된 시험도 등록 수에 포함하며 "
        "통과·출시 판정은 실행 증거에서 확인한다.",
        "",
        "| 항목 | 등록 수 | 대조 원천 |",
        "|---|---:|---|",
        f"| Rust 단위·통합 시험 | {counts['rust_tests']} | `cargo test -p onjeon-rules-engine -- --list` |",
        f"| Rust 문서 시험(doctest) | {counts['rust_doctests']} | 같은 Cargo 목록의 `Doc-tests` |",
        f"| 실제 조항 규칙(fixture_only) | {counts['real_clause_rules']} | `packages/fixtures/rules/real/*.json` (`*.cases.json` 제외) |",
        f"| 검증 자료 변조 시험 | {counts['tamper_tests']} | `tools/validation_check.py`의 `mutations()` |",
        f"| 공유 어휘 축 | {counts['vocabulary_axes']} | `packages/schemas/vocabulary.json`의 `axes` |",
        END,
    ])


def bounds(text):
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("expected exactly one generated counts block")
    start, end = text.index(START), text.index(END) + len(END)
    section = re.search(r"^## 11\. .*?(?=^## |\Z)", text, re.M | re.S)
    if end <= start or section is None or not (section.start() < start < end <= section.end()):
        raise ValueError("counts block must be ordered and inside §11")
    return start, end


def refresh(text, counts):
    start, end = bounds(text)
    return text[:start] + render(counts) + text[end:]


def check(text, counts):
    try:
        expected = refresh(text, counts)
    except ValueError as exc:
        return [str(exc)]
    return [] if text == expected else ["§11 counts are stale; review and run python3 -I tools/blueprint_counts.py --write"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = subprocess.run(CARGO, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, check=True)
        counts = collect(ROOT, result.stdout)
        path = ROOT / "docs/BLUEPRINT.md"
        text = path.read_text(encoding="utf-8")
        if args.write:
            text = refresh(text, counts)
            path.write_text(text, encoding="utf-8")
        problems = check(text, counts)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"BLUEPRINT-COUNTS: {exc}")
        return 2
    if problems:
        for problem in problems:
            print(f"BLUEPRINT-COUNTS: {problem}")
        return 1
    print("BLUEPRINT-COUNTS: " + json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
