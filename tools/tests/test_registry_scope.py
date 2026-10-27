"""Registry scope notes follow ADR-0018 (audit2-registry-epost-scope-stale).

Reads data/registry read-only. ADR-0018 (2026-10-10) settled the scope of every
row in cooperatives_and_others.csv: 우체국보험 included (institution type kept
apart from insurers), 공제 excluded, 한국무역보험공사 excluded (implementer reading).
"""
import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/registry"
ADR = ROOT / "docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md"
PENDING = ("범위 결정 대기", "범위 결정 필요")


def rows(name):
    with (REG / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class ScopeNotes(unittest.TestCase):
    def setUp(self):
        self.others = {r["insurer_id"]: r for r in rows("cooperatives_and_others")}

    def test_adr_0018_is_settled_for_these_rows(self):
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("상태: 확정(사용자 결정, 2026-10-10)", text)
        self.assertIn("| 우체국보험 | **포함.** 보험사와 기관 유형은 구분해서 관리 |", text)
        self.assertIn("| 공제 | **제외.**", text)
        self.assertIn("| 한국무역보험공사(공영보험) | 범위 밖.", text)

    def test_no_registry_cell_still_waits_for_a_scope_decision(self):
        for path in sorted(REG.glob("*.csv")):
            with path.open(encoding="utf-8", newline="") as f:
                for line, r in enumerate(csv.DictReader(f), start=2):
                    for col, cell in r.items():
                        for phrase in PENDING:
                            with self.subTest(file=path.name, line=line, column=col, phrase=phrase):
                                self.assertNotIn(phrase, cell or "")

    def test_epost_is_included_and_not_described_as_mutual_aid(self):
        notes = self.others["public-epost"]["notes"]
        self.assertIn("ADR-0018: 범위 포함", notes)
        self.assertIn("기관 유형은 보험사와 구분", notes)
        self.assertNotIn("공제", notes)
        self.assertNotIn("제외", notes)

    def test_mutual_aid_rows_record_the_exclusion(self):
        coops = [k for k in self.others if k.startswith("coop-")]
        self.assertEqual(len(coops), 13)
        for key in coops:
            with self.subTest(row=key):
                notes = self.others[key]["notes"]
                self.assertIn("ADR-0018: 공제는 범위·확보율 분모 제외", notes)
                self.assertNotIn("범위 포함", notes)

    def test_ksure_records_the_implementer_reading_as_excluded(self):
        notes = self.others["public-ksure"]["notes"]
        self.assertIn("ADR-0018 구현자 해석: 범위 제외", notes)
        self.assertIn("사용자 확인 대상", notes)
        self.assertNotIn("범위 포함", notes)

    def test_readme_scope_table_matches_the_rows(self):
        text = (REG / "README.md").read_text(encoding="utf-8")
        scope = text.split("## 범위 (ADR-0018, 2026-10-10)", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| `public-epost` 우체국보험 | **포함**.", scope)
        self.assertIn("| 공제 13곳 + 농협(구 공제) 시드 | **제외** |", scope)
        self.assertIn("| `public-ksure` 한국무역보험공사 | 제외 |", scope)
        gaps = text.split("## 알려진 공백", 1)[1].split("\n## ", 1)[0]
        item = [line for line in gaps.splitlines() if line.startswith("9. ")]
        self.assertEqual(len(item), 1)
        self.assertIn("공제는 ADR-0018로 범위·확보율 분모에서 제외", item[0])


if __name__ == "__main__":
    unittest.main()
