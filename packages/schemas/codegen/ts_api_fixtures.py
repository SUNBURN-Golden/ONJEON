#!/usr/bin/env python3
"""Write fixtures_check.ts into a scratch copy of generated/ts-api: every API fixture as a typed constant.

  python3 -I ts_api_fixtures.py <scratch ts-api dir>

`tsc` then proves the generated API interfaces accept real documents, that a body without release_id
and an unknown vocabulary value are type errors, and that index.ts does not export the skeleton
(each @ts-expect-error fails the build if the error does not occur).
"""
import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "tests" / "api_fixtures"


def main(out_dir: str) -> int:
    out = Path(out_dir)
    names = sorted(FIXTURES.glob("*.fixture.json"))
    types = sorted({p.name.split(".")[0] for p in names})
    lines = [f'import type {{ {", ".join(types)} }} from "./types";', 'import * as api from "./index";', ""]
    for n, p in enumerate(names):
        t = p.name.split(".")[0]
        lines.append(f"export const f{n}: {t} = {json.dumps(json.loads(p.read_text(encoding='utf-8')), ensure_ascii=False)};")
    base = json.loads((FIXTURES / "CurrentReleaseResponse.fixture.json").read_text(encoding="utf-8"))
    missing = {k: v for k, v in base.items() if k != "release_id"}
    lines += ["", "// @ts-expect-error a body without release_id must not type-check",
              f"export const noRelease: CurrentReleaseResponse = {json.dumps(missing, ensure_ascii=False)};"]
    prods = json.loads((FIXTURES / "ProductListResponse.fixture.json").read_text(encoding="utf-8"))
    prods["items"][0]["sale_status"] = "on_sale_maybe"
    lines += ["", "// @ts-expect-error unknown vocabulary value must not type-check",
              f"export const badEnum: ProductListResponse = {json.dumps(prods, ensure_ascii=False)};"]
    lines += ["", "// @ts-expect-error the default entry point does not export the skeleton",
              "export const leaked = api.skeletonOperations;", ""]
    (out / "fixtures_check.ts").write_text("\n".join(lines), encoding="utf-8")
    cfg = json.loads((out / "tsconfig.json").read_text(encoding="utf-8"))
    cfg["files"].append("fixtures_check.ts")
    (out / "tsconfig.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
