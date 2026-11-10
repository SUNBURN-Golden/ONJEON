"""Audit 5: the decisions ledger must reflect settled decisions and namespaces.

Finding: ``DECISIONS.md`` still showed O01 as open although ADR-0018 settled
it, ``cooperatives_and_others.csv`` still said "범위 결정 대기", the O16 row
still read as an open decision although DEC-D-12 settled the consumer-app
display question, DEC-* records had no ledger rows, and the legacy ledger IDs
D02/D04 could be confused with DEC-D-02/DEC-D-04.

Audit 2 and Audit 4 already repaired O01, the registry notes and the DEC index.
This test keeps those repairs in place and pins the remaining O16 wording and
the ID-namespace disambiguation so a later edit cannot reopen the finding.
"""
import csv
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
REGISTRY = ROOT / "data/registry"
ADR0018 = ROOT / "docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md"
AUDIT = ROOT / "docs/blueprint/audits/2026-11-10_decisions_ledger_sync.md"
EVIDENCE = ROOT / "tools/evidence/audit5-decisions-ledger-sync/README.md"

MAPPING_START = "<!-- blueprint-decision-id-mapping:start -->"
MAPPING_END = "<!-- blueprint-decision-id-mapping:end -->"
PENDING_SCOPE = ("범위 결정 대기", "범위 결정 필요")
# Bare two-digit ledger IDs outside the historical mapping table are stale.
LEGACY_ID = re.compile(r"(?<![A-Za-z0-9_-])D(?:0[1-9]|1[0-9]|20)(?![A-Za-z0-9_])")


def read(path):
    return path.read_text(encoding="utf-8")


def one_row(text, prefix):
    rows = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise AssertionError(f"expected one {prefix!r}, got {len(rows)}")
    return rows[0]


class Audit5DecisionsLedgerSync(unittest.TestCase):
    def setUp(self):
        self.ledger = read(LEDGER)
        self.mapping = self.ledger.split(MAPPING_START, 1)[1].split(MAPPING_END, 1)[0]
        self.section1 = self.ledger.split("## 1. ", 1)[1].split("### 1.1 ", 1)[0]
        self.section2 = self.ledger.split("## 2. ", 1)[1].split("## 3. ", 1)[0]
        self.section31 = self.ledger.split("### 3.1 ", 1)[1].split("## 4. ", 1)[0]

    def test_o01_is_closed_by_adr0018_not_left_open(self):
        row = one_row(self.ledger, "| O01 |")
        for phrase in ("해결", "ADR-0018", "BP-D-19", "우체국보험 포함",
                       "기관 유형은 구분", "공제 제외", "확보율 분모에서도 제외",
                       "2026-10-10", "범위 재결정을 기다리지 않음"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)
        for stale in ("범위 결정 대기", "범위 결정 필요", "포함 여부", "미해결"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, row)
        adr = read(ADR0018)
        self.assertIn("상태: 확정(사용자 결정, 2026-10-10)", adr)
        self.assertIn("| 우체국보험 | **포함.**", adr)
        self.assertIn("| 공제 | **제외.**", adr)

    def test_registry_cells_no_longer_wait_for_a_scope_decision(self):
        for path in sorted(REGISTRY.glob("*.csv")):
            with path.open(encoding="utf-8", newline="") as handle:
                for line, record in enumerate(csv.DictReader(handle), start=2):
                    for column, cell in record.items():
                        for phrase in PENDING_SCOPE:
                            with self.subTest(file=path.name, line=line,
                                              column=column, phrase=phrase):
                                self.assertNotIn(phrase, cell or "")
        with (REGISTRY / "cooperatives_and_others.csv").open(
                encoding="utf-8", newline="") as handle:
            epost = next(record for record in csv.DictReader(handle)
                         if record["insurer_id"] == "public-epost")
        self.assertIn("ADR-0018: 범위 포함", epost["notes"])
        self.assertIn("기관 유형은 보험사와 구분", epost["notes"])

    def test_o16_records_dec_d12_settlement_and_separates_residual_conditions(self):
        row = one_row(self.ledger, "| O16 |")
        self.assertRegex(row, r"^\| O16 \| 해결")
        for phrase in ("DEC-D-12", "소비자 앱의 원문 이미지·발췌 표시 허용",
                       "선택 C", "외부 검토 없음", "법적 위험은 소유자가 감수",
                       "기존 발췌·Git 이력 유지", "결정 질문은 해결",
                       "남은 조건", "새 원문 발췌 추가", "승인하지 않음"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)
        for stale in ("부분 해결", "미해결", "범위 결정 대기"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, row)
        index_row = one_row(self.ledger, "| [DEC-D-12](")
        self.assertIn("소유자 직접 결정", index_row)
        self.assertIn("2026-10-14 07:23 KST", index_row)

    def test_every_dec_record_has_exactly_one_ledger_row(self):
        indexed = re.findall(r"^\| \[(DEC-[^]]+)\]\(([^)]+)\)", self.section31, re.M)
        records = {path.stem for path in (ROOT / "docs/decisions").glob("DEC-*.md")}
        self.assertTrue(records)
        self.assertEqual(sorted(name for name, _ in indexed), sorted(records))
        self.assertEqual(len(indexed), len(records), "no duplicate DEC index rows")
        for name, target in indexed:
            with self.subTest(record=name):
                self.assertEqual(target, f"../decisions/{name}.md")
                self.assertTrue((ROOT / "docs/decisions" / f"{name}.md").is_file())
                row = one_row(self.section31, f"| [{name}](")
                cells = [cell.strip() for cell in row.strip("|").split("|")]
                self.assertEqual(len(cells), 4, "status, scope and remaining conditions")
                self.assertTrue(all(cells), f"empty DEC summary cell in {name}")

    def test_legacy_ledger_ids_do_not_collide_with_dec_gate_ids(self):
        pairs = re.findall(r"^\| (D\d+) \| (BP-D-\d+) \|", self.mapping, re.M)
        self.assertEqual(pairs, [(f"D{i:02}", f"BP-D-{i:02}") for i in range(1, 21)])
        self.assertEqual(
            dict(pairs)["D02"], "BP-D-02", "old ledger D02 must be the direction, not a gate")
        self.assertEqual(
            dict(pairs)["D04"], "BP-D-04", "old ledger D04 must be the direction, not a gate")
        # Outside the historical mapping, only the namespaced IDs may appear.
        outside_mapping = self.ledger.replace(self.mapping, "")
        self.assertEqual(LEGACY_ID.findall(outside_mapping), [])
        self.assertIn("이전 원장 표기", self.section1)
        self.assertIn("DEC-D-02", self.section2)
        self.assertIn("DEC-D-04", self.section2)
        self.assertIn("같은 번호", self.ledger)
        for name in ("DEC-D-02", "DEC-D-04"):
            row = one_row(self.section31, f"| [{name}](")
            self.assertTrue(row)

    def test_audit_and_evidence_records_exist_and_are_linked(self):
        self.assertTrue(AUDIT.is_file(), "audit record must exist")
        self.assertTrue(EVIDENCE.is_file(), "evidence README must exist")
        self.assertIn("audits/2026-11-10_decisions_ledger_sync.md", self.section31)
        self.assertIn("../../tools/evidence/audit5-decisions-ledger-sync/README.md",
                      self.section31)
        for path in (LEDGER, AUDIT, EVIDENCE):
            for link in re.findall(r"\]\(([^)]+)\)", read(path)):
                if "://" in link or link.startswith("#"):
                    continue
                with self.subTest(path=path.name, link=link):
                    target = (path.parent / link.split("#", 1)[0]).resolve()
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.exists(), f"missing target: {link}")


if __name__ == "__main__":
    unittest.main()
