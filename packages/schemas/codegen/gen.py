#!/usr/bin/env python3
"""Generate everything derived from the vocabulary and the JSON Schemas.

  python3 -I packages/schemas/codegen/gen.py --write   # regenerate
  python3 -I packages/schemas/codegen/gen.py --check   # CI: fail if anything is stale

Outputs
  packages/schemas/json/vocabulary.schema.json   every enum, from vocabulary.json
  packages/schemas/src/generated/                Rust (serde)
  packages/schemas/codegen/generated/ts/         TypeScript
  packages/schemas/codegen/generated/dart/       Dart

Enum arrays are produced only here, only from packages/schemas/vocabulary.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import emit_dart  # noqa: E402
import emit_rust  # noqa: E402
import emit_ts  # noqa: E402
import schema_model as sm  # noqa: E402

RUST_DIR = sm.SCHEMAS_DIR / "src" / "generated"
TS_DIR = sm.SCHEMAS_DIR / "codegen" / "generated" / "ts"
DART_DIR = sm.SCHEMAS_DIR / "codegen" / "generated" / "dart"
VOCAB_SCHEMA = sm.JSON_DIR / sm.VOCAB_FILE


def vocabulary_schema_text(vocab: dict) -> str:
    return json.dumps(sm.vocabulary_schema(vocab), ensure_ascii=False, indent=2) + "\n"


def expected_outputs(json_dir: Path = sm.JSON_DIR, vocab_path: Path = sm.VOCAB_PATH, version: str | None = None) -> dict:
    """Map absolute path -> expected text. The vocabulary schema is generated first so lint passes."""
    vocab = sm.load_vocab(vocab_path)
    if version is None:
        version = sm.contracts_version(sm.SCHEMAS_DIR / "Cargo.toml")
    files = sm.read_schema_files(json_dir)
    files[sm.VOCAB_FILE] = sm.vocabulary_schema(vocab)
    model = sm._Loader(files, vocab).run()
    if model.errors:
        raise sm.SchemaError("schema lint failed:\n  " + "\n  ".join(model.errors))
    out = {json_dir / sm.VOCAB_FILE: vocabulary_schema_text(vocab)}
    for rel, text in emit_rust.emit(model).items():
        out[RUST_DIR / rel] = text
    for rel, text in emit_ts.emit(model, version).items():
        out[TS_DIR / rel] = text
    for rel, text in emit_dart.emit(model, version).items():
        out[DART_DIR / rel] = text
    return out


def generated_dirs():
    return [RUST_DIR, TS_DIR, DART_DIR]


def stale(outputs: dict) -> list:
    problems = []
    for path, text in outputs.items():
        if not path.exists():
            problems.append(f"missing {path.relative_to(sm.SCHEMAS_DIR)}")
        elif path.read_text(encoding="utf-8") != text:
            problems.append(f"stale   {path.relative_to(sm.SCHEMAS_DIR)}")
    expected = set(outputs)
    for d in generated_dirs():
        if d.exists():
            for p in sorted(d.rglob("*")):
                if p.is_file() and p not in expected:
                    problems.append(f"orphan  {p.relative_to(sm.SCHEMAS_DIR)}")
    return problems


def main(argv: list) -> int:
    mode = argv[1] if len(argv) > 1 else "--check"
    if mode not in ("--write", "--check"):
        print(__doc__)
        return 2
    try:
        outputs = expected_outputs()
    except sm.SchemaError as e:
        print(e, file=sys.stderr)
        return 1
    if mode == "--write":
        for d in generated_dirs():
            if d.exists():
                for p in sorted(d.rglob("*"), reverse=True):
                    if p.is_file() and p not in outputs:
                        p.unlink()
        for path, text in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
                print(f"wrote {path.relative_to(sm.SCHEMAS_DIR)}")
        return 0
    problems = stale(outputs)
    if problems:
        print("generated files are not up to date (run: bash packages/schemas/codegen/gen.sh):", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print(f"ok: {len(outputs)} generated files are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
