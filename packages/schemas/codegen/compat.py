#!/usr/bin/env python3
"""Compatibility check between two versions of packages/schemas (02_구현계약 §5).

  python3 -I compat.py --prev DIR --new DIR       # DIR = a packages/schemas directory
  python3 -I compat.py --probe DIR_OUT --prev DIR --new DIR

Breaking (needs a new major; 0.x counts the minor as major):
  type removed, field removed, field type/constraint changed, field becomes required,
  required field becomes optional, enum value removed, enum axis removed.
Compatible (needs a version bump, minor is enough):
  new type, new optional field, new enum value, new enum axis.

`--probe` additionally writes a small Rust crate that holds the PREVIOUS generated
types plus minimal documents derived from the NEW schemas; `check_compat.sh` builds
and runs it, so "the previous client still reads new documents" is compiled, not argued.

Exit: 0 compatible, 1 incompatible, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import emit_rust  # noqa: E402
import schema_model as sm  # noqa: E402


def model_of(schemas_dir: Path) -> sm.Model:
    """Model of a packages/schemas directory, using ITS vocabulary and ITS vocabulary schema."""
    return sm.build_model(schemas_dir / "json", schemas_dir / "vocabulary.json", strict=True)


def diff(prev: sm.Model, new: sm.Model) -> tuple[list, list]:
    breaking, compatible = [], []
    for axis_id, pa in prev.axes.items():
        na = new.axes.get(axis_id)
        if na is None:
            breaking.append(f"vocabulary axis removed: {axis_id}")
            continue
        old_codes = [v["code"] for v in pa.values]
        new_codes = [v["code"] for v in na.values]
        for code in old_codes:
            if code not in new_codes:
                breaking.append(f"enum value removed: {axis_id}.{code}")
        for code in new_codes:
            if code not in old_codes:
                compatible.append(f"enum value added: {axis_id}.{code}")
    for axis_id in new.axes:
        if axis_id not in prev.axes:
            compatible.append(f"vocabulary axis added: {axis_id}")
    for name, ps in prev.structs.items():
        ns = new.structs.get(name)
        if ns is None:
            breaking.append(f"type removed: {name}")
            continue
        pf = {f.name: f for f in ps.fields}
        nf = {f.name: f for f in ns.fields}
        for fname, f in pf.items():
            g = nf.get(fname)
            if g is None:
                breaking.append(f"field removed: {name}.{fname}")
                continue
            if f.type.signature() != g.type.signature():
                breaking.append(f"field type changed: {name}.{fname}: {f.type.signature()} -> {g.type.signature()}")
            if f.required and not g.required:
                breaking.append(f"field no longer required: {name}.{fname}")
            if not f.required and g.required:
                breaking.append(f"field became required: {name}.{fname}")
        for fname, g in nf.items():
            if fname not in pf:
                (breaking if g.required else compatible).append(
                    f"{'required ' if g.required else 'optional '}field added: {name}.{fname}"
                )
    for name in new.structs:
        if name not in prev.structs:
            compatible.append(f"type added: {name}")
    return breaking, compatible


def parse_version(v: str) -> tuple:
    return tuple(int(x) for x in v.split("."))


def required_bump_ok(prev_v: str, new_v: str, breaking: bool, changed: bool) -> str | None:
    """None if the version change is allowed, else the reason it is not."""
    p, n = parse_version(prev_v), parse_version(new_v)
    if n < p:
        return f"version went backwards: {prev_v} -> {new_v}"
    if breaking:
        ok = n[0] > p[0] if p[0] > 0 else n[:2] > p[:2]
        if not ok:
            need = "major" if p[0] > 0 else "minor (0.x: the minor is the major)"
            return f"breaking change needs a new {need}: {prev_v} -> {new_v}"
    elif changed and n == p:
        return f"schemas changed but the version is still {prev_v}"
    return None


# ---- probe crate -------------------------------------------------------------

def minimal_value(model: sm.Model, t: sm.Type, files: dict, depth: int = 0):
    """Smallest valid value for a type, all optional fields filled once so every field is read."""
    if t.kind == "string":
        pattern = dict(t.constraints).get("pattern")
        return sample_string(pattern, dict(t.constraints).get("format"))
    if t.kind == "integer":
        return max(int(dict(t.constraints).get("minimum", 0)), 0) + 1
    if t.kind == "number":
        return 1.5
    if t.kind == "boolean":
        return False
    if t.kind == "any":
        return {"probe": 1}
    if t.kind == "enum":
        return model.axes[t.name].values[0]["code"]
    if t.kind == "array":
        return [minimal_value(model, t.item, files, depth + 1)]
    if t.kind == "map":
        return {"k": minimal_value(model, t.item, files, depth + 1)}
    if t.kind == "ref":
        if depth > 12:
            raise RuntimeError(f"recursive type {t.name}")
        st = model.structs[t.name]
        return {f.name: minimal_value(model, f.type, files, depth + 1) for f in st.fields}
    raise AssertionError(t.kind)


def sample_string(pattern: str | None, fmt: str | None) -> str:
    """A string that satisfies the pattern. Patterns are matched by trying generated candidates."""
    import re

    ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    cands = [
        "x", "0" * 64, "rel:20260101-1", "crel:20260101-1", "2026-01-01", "2026-01-01T00:00:00Z", "0.1.0",
        f"a:{ulid}", f"rd:{ulid}", f"premium:{ulid}", f"plan:{ulid}", f"contract:{ulid}", f"person:{ulid}",
        f"upload:{ulid}", f"sc:{ulid}", f"ted:{ulid}", f"gap:{ulid}", f"cov:ted:{ulid}/art1",
        f"assume:{ulid}@1", f"assertion:{ulid}", f"eval:{ulid}", "crit:slug@1", "raw:sha256:" + "0" * 64,
        "seg:0123456789ab:p1-2:terms:v1", "clause:seg:0123456789ab:p1-2:terms:v1/art1#p1:docproc@1.0",
        f"rule:r1@1#{'0' * 12}", "obs:src:org/web/1/2026-01-01T00:00:00Z/" + "0" * 16, "fact:f1",
        "scenario:s1", "ONJ-AP-V-001", "V", "my_design", "snake_case", "0",
    ]
    if pattern is None:
        return "x"
    for c in cands:
        if re.search(pattern, c):
            return c
    raise RuntimeError(f"probe has no sample for pattern {pattern!r}; add one to the candidates in compat.sample_string")


def write_probe(out: Path, prev_dir: Path, new_dir: Path):
    prev = model_of(prev_dir)
    new = model_of(new_dir)
    (out / "src").mkdir(parents=True, exist_ok=True)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    (out / "Cargo.toml").write_text(
        '[package]\nname = "compat-probe"\nversion = "0.0.0"\nedition = "2021"\npublish = false\n\n'
        '[workspace]\n\n[dependencies]\nserde = { version = "1", features = ["derive"] }\nserde_json = "1"\n',
        encoding="utf-8",
    )
    rs = emit_rust.emit(prev)
    (out / "src" / "vocabulary.rs").write_text(rs["vocabulary.rs"], encoding="utf-8")
    types = rs["types.rs"].replace("use super::vocabulary::*;", "use crate::vocabulary::*;")
    (out / "src" / "types.rs").write_text(types, encoding="utf-8")
    roots = [s for s in new.structs.values() if s.root]
    arms = []
    for st in roots:
        if st.name not in prev.structs:
            continue  # new in this version: no previous client exists
        doc = minimal_value(new, sm.Type("ref", name=st.name), None)
        (out / "docs" / f"{st.name}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        arms.append(st.name)
    body = "\n".join(
        f'    check::<types::{n}>("{n}", include_str!("../docs/{n}.json"), &mut failed);' for n in arms
    )
    (out / "src" / "main.rs").write_text(
        "#![allow(dead_code)]\nmod types;\nmod vocabulary;\n\n"
        "fn check<T: serde::de::DeserializeOwned>(name: &str, src: &str, failed: &mut Vec<String>) {\n"
        "    match serde_json::from_str::<T>(src) {\n"
        '        Ok(_) => println!("ok   {name}"),\n'
        '        Err(e) => {\n            println!("FAIL {name}: {e}");\n            failed.push(name.to_string());\n        }\n    }\n}\n\n'
        "fn main() {\n    let mut failed = Vec::new();\n"
        f"{body}\n"
        "    if !failed.is_empty() {\n        std::process::exit(1);\n    }\n}\n",
        encoding="utf-8",
    )
    return arms


def make_mutant(src: Path, dst: Path, drop: str):
    """Copy a packages/schemas directory and delete one field (`Type.field`). Used by the self-test."""
    import shutil

    type_name, field = drop.split(".")
    shutil.copytree(src / "json", dst / "json")
    shutil.copy(src / "vocabulary.json", dst / "vocabulary.json")
    shutil.copy(src / "Cargo.toml", dst / "Cargo.toml")
    for path in (dst / "json").glob("*.schema.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        targets = [doc] if doc.get("title") == type_name else []
        targets += [d for n, d in doc.get("$defs", {}).items() if n == type_name]
        for t in targets:
            if field in t.get("properties", {}):
                del t["properties"][field]
                t["required"] = [r for r in t.get("required", []) if r != field]
                path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return
    raise ValueError(f"{drop}: no such field")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prev", type=Path, required=True)
    ap.add_argument("--new", type=Path, default=sm.SCHEMAS_DIR)
    ap.add_argument("--probe", type=Path, help="write the probe crate here instead of diffing")
    ap.add_argument("--make-mutant", type=Path, metavar="OUT", help="copy --prev to OUT with one field deleted (self-test)")
    ap.add_argument("--drop", metavar="TYPE.FIELD", help="field to delete for --make-mutant")
    args = ap.parse_args(argv[1:])
    try:
        if args.make_mutant:
            make_mutant(args.prev, args.make_mutant, args.drop)
            return 0
        if args.probe:
            names = write_probe(args.probe, args.prev, args.new)
            print(f"probe written: {len(names)} documents")
            return 0
        prev, new = model_of(args.prev), model_of(args.new)
        breaking, compatible = diff(prev, new)
        pv = sm.contracts_version(args.prev / "Cargo.toml")
        nv = sm.contracts_version(args.new / "Cargo.toml")
    except (sm.SchemaError, OSError, ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for line in breaking:
        print(f"BREAKING   {line}")
    for line in compatible:
        print(f"compatible {line}")
    problem = required_bump_ok(pv, nv, bool(breaking), bool(breaking or compatible))
    print(f"version {pv} -> {nv}: {len(breaking)} breaking, {len(compatible)} compatible change(s)")
    if problem:
        print(f"INCOMPATIBLE: {problem}", file=sys.stderr)
        return 1
    print("compatible")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
