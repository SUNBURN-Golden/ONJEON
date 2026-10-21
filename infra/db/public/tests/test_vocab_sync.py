"""SQL 어휘 도메인이 정본(packages/schemas/vocabulary.json)과 같은 값을 갖는지, 노드 종류가 온톨로지 tbox의 클래스인지 대조한다.

사용: python3 -I test_vocab_sync.py [<저장소 루트>]   (생략하면 이 파일 위치에서 저장소 루트를 계산한다)
SQL의 `CREATE DOMAIN vocab_<축> AS text CHECK (VALUE IN (...))`가 어휘 축 <축>의 값 집합과 정확히 같아야 한다(추가·누락 모두 실패).
정본을 이 파일에서 고치지 않는다. 어휘 값이 바뀌면 마이그레이션을 새 판으로 낸다.
"""
import json
import re
import sys
from pathlib import Path

root = (Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[4]).resolve()
db = root / "infra" / "db"
vocab = {a["id"]: {v["code"] for v in a["values"]} for a in json.loads((root / "packages/schemas/vocabulary.json").read_text())["axes"]}

domain_re = re.compile(r"CREATE DOMAIN vocab_(\w+) AS text CHECK \(VALUE IN \(([^)]*)\)\)")
problems = []
seen = {}
for f in sorted(db.glob("*/*.sql")):
    for axis, body in domain_re.findall(f.read_text()):
        values = set(re.findall(r"'([^']*)'", body))
        seen.setdefault(axis, []).append((f.relative_to(root).as_posix(), values))
        if axis not in vocab:
            problems.append(f"{f.name}: vocab_{axis} has no axis in vocabulary.json")
        elif values != vocab[axis]:
            problems.append(f"{f.name}: vocab_{axis} differs: only-in-sql={sorted(values - vocab[axis])} only-in-vocab={sorted(vocab[axis] - values)}")

# 같은 축이 두 DB에 중복되면 값이 서로 같아야 한다(위 검사가 정본과의 일치를 이미 보장한다).
required = {
    "public": {"review_status", "criticality", "value_state", "hold_reason", "correction_reason", "assertion_origin", "evidence_role", "doc_role", "price_basis", "acquisition_status"},
    "criteria": {"criterion_source_kind"},
    "personal": {"fact_source", "fact_kind", "confirm_party", "contract_version_match", "freshness", "knowledge_freshness", "usage_restriction", "sensitivity", "plan_action"},
}
for zone, axes in required.items():
    have = {a for a, defs in seen.items() for path, _ in defs if f"/{zone}/" in path}
    if axes - have:
        problems.append(f"{zone}: missing domains for {sorted(axes - have)}")

# node.kind ⊆ tbox 클래스. tbox가 문서 폴더에 있는 동안만 대조한다(옮겨지면 경로를 갱신해야 이 검사가 실패로 알려준다).
tbox_path = root / "docs/blueprint/proposals/온톨로지/tbox.json"
if not tbox_path.exists():
    problems.append(f"tbox not found at {tbox_path.relative_to(root)}; update this path when the ontology moves")
else:
    classes = {c["id"] for c in json.loads(tbox_path.read_text())["classes"]}
    m = re.search(r"kind\s+text NOT NULL CHECK \(kind IN \(([^)]*)\)\)", (db / "public/01_schema.sql").read_text(), re.S)
    kinds = set(re.findall(r"'([^']*)'", m.group(1))) if m else set()
    if not kinds:
        problems.append("node.kind list not found in 01_schema.sql")
    elif kinds - classes:
        problems.append(f"node kinds not in tbox classes: {sorted(kinds - classes)}")

for p in problems:
    print("vocab-sync:", p)
print(f"vocab-sync: {len(seen)} axes checked, {len(problems)} problem(s)")
sys.exit(1 if problems else 0)
