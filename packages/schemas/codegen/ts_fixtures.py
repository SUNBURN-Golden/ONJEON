#!/usr/bin/env python3
"""Write fixtures_check.ts into a scratch copy of generated/ts: every fixture as a typed constant.

  python3 -I ts_fixtures.py <scratch ts dir>

`tsc` then proves the generated interfaces accept real documents (excess-property and
enum-literal checks apply), and that an unknown vocabulary value is a type error
(`@ts-expect-error` fails the build if it is not).
"""
import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"


def main(out_dir: str) -> int:
    out = Path(out_dir)
    names = sorted(p for p in FIXTURES.glob("*.fixture.json"))
    types = sorted({p.name.split(".")[0] for p in names})
    lines = [f'import type {{ {", ".join(types)} }} from "./types";', ""]
    for n, p in enumerate(names):
        t = p.name.split(".")[0]
        lines.append(f"export const f{n}: {t} = {json.dumps(json.loads(p.read_text(encoding='utf-8')), ensure_ascii=False)};")
    base = json.loads((FIXTURES / "Assertion.relation.fixture.json").read_text(encoding="utf-8"))
    bad = dict(base, criticality="c9")
    lines += ["", "// @ts-expect-error unknown vocabulary value must not type-check",
              f"export const badEnum: Assertion = {json.dumps(bad, ensure_ascii=False)};"]
    missing = {k: v for k, v in base.items() if k != "evidence"}
    lines += ["", "// @ts-expect-error missing required field must not type-check",
              f"export const badMissing: Assertion = {json.dumps(missing, ensure_ascii=False)};", ""]
    (out / "fixtures_check.ts").write_text("\n".join(lines), encoding="utf-8")
    cfg = json.loads((out / "tsconfig.json").read_text(encoding="utf-8"))
    cfg["files"].append("fixtures_check.ts")
    (out / "tsconfig.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
