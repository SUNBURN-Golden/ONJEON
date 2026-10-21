#!/usr/bin/env python3
"""Single source of truth for ONJEON state vocabulary.

- validates packages/schemas/vocabulary.json
- generates docs/blueprint/VOCABULARY.md (--write) or checks it is up to date
- lints contract documents for deprecated or forbidden status names in backticks

Usage:
  python3 tools/vocab_check.py          # check (CI)
  python3 tools/vocab_check.py --write  # regenerate VOCABULARY.md
  python3 tools/vocab_check.py --additive-since <baseline vocabulary.json>
      # canon-change gate: every axis and value of the baseline must still exist
      # with the same definition, screen text and aliases (no delete/rename/
      # rewording), and the version must have moved if anything was added.

Background documents (masterplan v0.3, part 3, review, ADR history) are not
linted: they are historical records. Contract documents are.
A line may opt out with the marker  <!-- vocab:allow -->  when it quotes an
old name on purpose (for example in a migration note).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOCAB = ROOT / "packages/schemas/vocabulary.json"
DOC = ROOT / "docs/blueprint/VOCABULARY.md"
CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

CONTRACT_DOCS = [
    "docs/BLUEPRINT.md",
    "docs/PRINCIPLES.md",
    "docs/blueprint/*.md",
    "docs/blueprint/validation/*.md",
    "docs/data/*.md",
    "docs/design/*.md",
    "docs/masterplan/가격_수집_명세.md",
    "data/registry/README.md",
]


def load():
    return json.loads(VOCAB.read_text(encoding="utf-8"))


AXIS_TEXT = ("name_ko", "applies_to", "layer", "concept_ko")


def validate(v):
    errors = []
    ids = [a["id"] for a in v["axes"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate axis id")
    for a in v["axes"]:
        if not CODE_RE.match(a.get("id") or ""):
            errors.append(f"axis `{a.get('id')}`: id must be lower snake_case")
        for k in AXIS_TEXT:
            if not isinstance(a.get(k), str) or not a[k].strip():
                errors.append(f"{a.get('id')}: axis `{k}` must be a non-empty string")
        for x in a["values"]:
            # Every value carries a definition. screen_ko is always present: a non-empty string,
            # or null as the explicit "not shown on screen" marker. A missing key or "" is a mistake.
            if not isinstance(x.get("concept_ko"), str) or not x["concept_ko"].strip():
                errors.append(f"{a.get('id')}.{x.get('code')}: concept_ko (definition) must be a non-empty string")
            if "screen_ko" not in x or not (x["screen_ko"] is None or (isinstance(x["screen_ko"], str) and x["screen_ko"].strip())):
                errors.append(f"{a.get('id')}.{x.get('code')}: screen_ko must be a non-empty string or null (not shown)")
            if not isinstance(x.get("deprecated_aliases"), list):
                errors.append(f"{a.get('id')}.{x.get('code')}: deprecated_aliases must be a list")
    groups = None
    acq = set()
    for a in v["axes"]:
        if a["id"] == "diff_group":
            groups = {x["code"] for x in a["values"]}
        if a["id"] == "acquisition_status":
            acq = {x["code"] for x in a["values"]}
    for a in v["axes"]:
        codes = [x["code"] for x in a["values"]]
        if len(codes) != len(set(codes)):
            errors.append(f"{a['id']}: duplicate code")
        for x in a["values"]:
            if not CODE_RE.match(x["code"]):
                errors.append(f"{a['id']}.{x['code']}: code must be lower snake_case")
            for al in x.get("deprecated_aliases", []):
                if al in codes:
                    errors.append(f"{a['id']}.{x['code']}: alias `{al}` is also a live code in the same axis")
            if "maps_to" in x and x["maps_to"] not in acq:
                errors.append(f"{a['id']}.{x['code']}: maps_to must be an acquisition_status code")
            if a["id"] == "diff_type" and x.get("group") not in (groups or set()):
                errors.append(f"diff_type.{x['code']}: group must be a diff_group code")
        for f in a.get("forbidden_codes", []):
            if f in codes:
                errors.append(f"{a['id']}: forbidden code `{f}` is present")
    return errors


VALUE_KEYS = ("concept_ko", "screen_ko", "deprecated_aliases", "group", "maps_to")
AXIS_KEYS = AXIS_TEXT + ("field_aliases", "forbidden_codes")


def _version(s):
    try:
        return tuple(int(x) for x in s.split("."))
    except (AttributeError, ValueError):
        return None


def additive_since(base, v):
    """Errors if `v` is not a pure extension of `base` (the canon rule for vocabulary changes:
    existing axes and values are never deleted, renamed or reworded; only additions, with a version bump)."""
    errors = []
    axes = {a["id"]: a for a in v["axes"]}
    for ba in base["axes"]:
        a = axes.get(ba["id"])
        if a is None:
            errors.append(f"axis `{ba['id']}` was removed or renamed")
            continue
        for k in AXIS_KEYS:
            if ba.get(k) != a.get(k):
                errors.append(f"axis `{ba['id']}`: `{k}` changed")
        values = {x["code"]: x for x in a["values"]}
        for bx in ba["values"]:
            x = values.get(bx["code"])
            if x is None:
                errors.append(f"{ba['id']}.{bx['code']} was removed or renamed")
                continue
            for k in VALUE_KEYS:
                if bx.get(k) != x.get(k):
                    errors.append(f"{ba['id']}.{bx['code']}: `{k}` changed")
    stamps = {t["field"]: t for t in v["timestamps"]}
    for bt in base["timestamps"]:
        if stamps.get(bt["field"]) != bt:
            errors.append(f"timestamp `{bt['field']}` removed or changed")
    base_rules = base.get("rules", [])
    if v.get("rules", [])[: len(base_rules)] != base_rules:
        errors.append("an existing rule line was removed or reworded")
    changed = json.dumps(base, sort_keys=True) != json.dumps(v, sort_keys=True)
    bv, nv = _version(base.get("version")), _version(v.get("version"))
    if bv is None or nv is None:
        errors.append("version must be MAJOR.MINOR.PATCH")
    elif changed and not nv > bv:
        errors.append(f"content changed but version did not move ({base.get('version')} -> {v.get('version')})")
    elif not changed and nv != bv:
        errors.append("version moved without any content change")
    return errors


def render(v):
    out = [
        "# 상태 어휘 (생성 문서)",
        "",
        f"버전 {v['version']} | {v['updated']} | 정본: `packages/schemas/vocabulary.json`",
        "",
        "> 이 문서는 `python3 tools/vocab_check.py --write`로 생성한다. 직접 고치지 않는다.",
        "",
        "## 규칙",
        "",
    ]
    out += [f"- {r}" for r in v["rules"]]
    out += ["", "## 축 목록", "", "| 축 | 이름 | 적용 대상 | 계층 |", "|---|---|---|---|"]
    for a in v["axes"]:
        out.append(f"| `{a['id']}` | {a['name_ko']} | {a['applies_to']} | {a['layer']} |")
    for a in v["axes"]:
        out += ["", f"## `{a['id']}` {a['name_ko']}", "", a["concept_ko"], ""]
        if a.get("field_aliases"):
            out += [f"과거 필드 이름: {', '.join('`'+f+'`' for f in a['field_aliases'])} → `{a['id']}`", ""]
        has_group = any("group" in x for x in a["values"])
        has_map = any("maps_to" in x for x in a["values"])
        head = "| 저장값 | 개념 | 화면 문구 | 폐기된 표기 |" + (" 묶음 |" if has_group else "") + (" 수집 상태로 |" if has_map else "")
        sep = "|---|---|---|---|" + ("---|" if has_group else "") + ("---|" if has_map else "")
        out += [head, sep]
        for x in a["values"]:
            screen = x["screen_ko"] if x.get("screen_ko") else "(화면에 직접 표시 안 함)"
            aliases = ", ".join(x.get("deprecated_aliases", [])) or "-"
            row = f"| `{x['code']}` | {x['concept_ko']} | {screen} | {aliases} |"
            if has_group:
                row += f" `{x.get('group', '')}` |"
            if has_map:
                row += f" `{x.get('maps_to', '')}` |"
            out.append(row)
        if a.get("forbidden_codes"):
            out += ["", "쓰지 않는 값: " + ", ".join(a["forbidden_codes"])]
    out += ["", "## 시각 필드", "", "| 필드 | 개념 | 폐기된 표기 |", "|---|---|---|"]
    for t in v["timestamps"]:
        out.append(f"| `{t['field']}` | {t['concept_ko']} | {', '.join(t['deprecated_aliases']) or '-'} |")
    return "\n".join(out) + "\n"


def lint(v):
    live = set()
    deprecated = {}
    for a in v["axes"]:
        for x in a["values"]:
            live.add(x["code"])
        for f in a.get("forbidden_codes", []):
            deprecated.setdefault(f, f"forbidden in {a['id']}")
    for a in v["axes"]:
        for x in a["values"]:
            for al in x.get("deprecated_aliases", []):
                if al not in live:
                    deprecated.setdefault(al, f"{a['id']}.{x['code']}")
        for fa in a.get("field_aliases", []):
            deprecated.setdefault(fa, f"field {a['id']}")
    for t in v["timestamps"]:
        for al in t["deprecated_aliases"]:
            deprecated.setdefault(al, f"timestamp {t['field']}")
    problems = []
    files = []
    for pattern in CONTRACT_DOCS:
        files += sorted(ROOT.glob(pattern))
    for f in files:
        if f == DOC:
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "vocab:allow" in line:
                continue
            seen = set()
            # backticked names, any case
            for m in re.finditer(r"`([A-Za-z][A-Za-z0-9_]*)`", line):
                seen.add(m.group(1))
            # bare lower-case snake_case names in tables and prose (ASCII words are rare in Korean text)
            for m in re.finditer(r"(?<![A-Za-z0-9_./-])([a-z][a-z0-9]*(?:_[a-z0-9]+)+|[a-z]{4,})(?![A-Za-z0-9_])", line):
                seen.add(m.group(1))
            for tok in sorted(seen):
                if tok in deprecated:
                    problems.append(f"{f.relative_to(ROOT)}:{i}: `{tok}` -> use {deprecated[tok]}")
    return problems


def main():
    v = load()
    errors = validate(v)
    if errors:
        print("vocabulary.json invalid:\n  " + "\n  ".join(errors))
        return 1
    if "--additive-since" in sys.argv:
        base_path = Path(sys.argv[sys.argv.index("--additive-since") + 1])
        base = json.loads(base_path.read_text(encoding="utf-8"))
        errors = additive_since(base, v)
        if errors:
            print(f"vocabulary.json is not a pure extension of {base_path}:\n  " + "\n  ".join(errors))
            return 1
        added_axes = len(v["axes"]) - len(base["axes"])
        added_values = sum(len(a["values"]) for a in v["axes"]) - sum(len(a["values"]) for a in base["axes"])
        print(f"additive since {base.get('version')}: +{added_axes} axes, +{added_values} values, nothing removed/renamed/reworded")
    rendered = render(v)
    if "--write" in sys.argv:
        DOC.write_text(rendered, encoding="utf-8")
        print(f"wrote {DOC.relative_to(ROOT)}")
    elif not DOC.exists() or DOC.read_text(encoding="utf-8") != rendered:
        print("docs/blueprint/VOCABULARY.md is out of date: run python3 tools/vocab_check.py --write")
        return 1
    problems = lint(v)
    if problems:
        print("deprecated status names in contract documents:\n  " + "\n  ".join(problems))
        return 1
    n = sum(len(a["values"]) for a in v["axes"])
    print(f"vocabulary ok: {len(v['axes'])} axes, {n} values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
