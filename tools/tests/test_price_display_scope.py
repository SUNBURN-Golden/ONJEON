"""Public price display: scope vs. enable gate (audit2-price-display-scope).

ADR-0010 → BLUEPRINT §7.1 / DECISIONS D08 / README decide that public price
collection, display and comparison are first-release scope. DECISIONS §3 (O04,
O10) decides when the price column may be shown publicly, and 09 P02/P09 point at
those gates. The audit found the two read as a conflict because the recorded
decisions DEC-O04 and DEC-D-18 were not referenced from the ledger, and "D-18"
collides with §1 D18 (R2 operations). These tests pin the reconciled wording.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
README = ROOT / "README.md"
PURPOSE = ROOT / "docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md"
REPORT = ROOT / "docs/blueprint/audits/2026-10-27_price_display_scope.md"
EVIDENCE_DIR = "tools/evidence/audit2-price-display-scope/"

# One gate sentence fragment shared by every place that mentions price display.
GATE = "가격 열 대외 공개 표시는 D-18(O10) 외부 검토 담당 지정 뒤"
O04_RESOLVED = "O04는 DEC-O04로 해결"

# Old 09 notes that made O04 look pending.
STALE = ("가격 표시는 D-18·O04 뒤", "가격 열 노출은 O04·D-18 뒤")


def one_row(text, prefix):
    rows = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise AssertionError(f"expected one row starting {prefix!r}, got {len(rows)}")
    return rows[0]


def cells(row):
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def dec_links(text):
    return set(re.findall(r"\[(DEC-[A-Z0-9-]+)\]\(", text))


class PriceDisplayScope(unittest.TestCase):
    def setUp(self):
        self.blueprint = BLUEPRINT.read_text(encoding="utf-8")
        self.scope = self.blueprint.split("### 7.1 ", 1)[1].split("### 7.2 ", 1)[0]
        self.open_decisions = self.blueprint.split("## 12. ", 1)[1].split("## 13. ", 1)[0]
        ledger = LEDGER.read_text(encoding="utf-8")
        self.directions = ledger.split("## 1. ", 1)[1].split("## 2. ", 1)[0]
        self.section = ledger.split("## 3. ", 1)[1].split("## 4. ", 1)[0]
        self.open_items = self.section.split("### 3.1 ", 1)[0]
        self.index = self.section.split("### 3.1 ", 1)[1]
        self.readme = README.read_text(encoding="utf-8")
        self.purpose = PURPOSE.read_text(encoding="utf-8")

    def index_row(self, record_id):
        row = cells(one_row(self.index, f"| [{record_id}]("))
        self.assertEqual(len(row), 4)
        target = re.fullmatch(r"\[[^]]+\]\(([^)]+)\)", row[0]).group(1)
        self.assertEqual((LEDGER.parent / target).resolve(),
                         ROOT / f"docs/decisions/{record_id}.md")
        return row

    # --- scope source: price display stays in the first release ---------------

    def test_scope_sources_keep_public_price_in_first_release(self):
        self.assertIn("공개 가격도 수집·표시·비교", one_row(self.directions, "| D08 |"))
        row = one_row(self.scope, "| 첫 출시 데이터 |")
        self.assertIn("공개 가격", row)
        self.assertTrue(row.endswith("| ADR-0008·0010 |"))
        self.assertIn("공개 가격 수집·표시·예산 비교는 첫 출시 범위", self.readme)

    def test_gate_wording_is_shared_by_scope_docs_ledger_and_09(self):
        places = {
            "BLUEPRINT §7.1": one_row(self.scope, "| 첫 출시 데이터 |"),
            "BLUEPRINT §12": one_row(self.open_decisions, "| 외부 검토 담당 지정(D-18·O10)"),
            "README": next(p for p in self.readme.split("\n\n") if "ADR-0010." in p),
            "DECISIONS O04": one_row(self.open_items, "| O04 |"),
            "DECISIONS O10": one_row(self.open_items, "| O10 |"),
            "09 P02": one_row(self.purpose, "| P02 |"),
            "09 P09": one_row(self.purpose, "| P09 |"),
        }
        for name, text in places.items():
            with self.subTest(place=name):
                self.assertIn(GATE, text)
                self.assertIn("DEC-D-18", text)

    def test_gate_is_not_a_scope_cut(self):
        for prefix in ("| P02 |", "| P09 |"):
            row = one_row(self.purpose, prefix)
            with self.subTest(row=prefix):
                self.assertIn(O04_RESOLVED, row)
                self.assertIn("축소 아님", row)
                for stale in STALE:
                    self.assertNotIn(stale, row)
        row = one_row(self.scope, "| 첫 출시 데이터 |")
        self.assertIn("범위 안", row)

    # --- ledger: the two recorded decisions are referenced ----------------------

    def test_o04_row_is_resolved_by_dec_o04_and_keeps_its_limits(self):
        row = one_row(self.open_items, "| O04 |")
        for phrase in ("해결", "[DEC-O04](../decisions/DEC-O04.md)", "사용자 확정 아님",
                       "가역", "T-KN-09", "compare_price", "I7", "I8", "K13", "묶음",
                       "근거 없는 합계·절감액 금지"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)

    def test_o10_row_records_dec_d18_and_keeps_the_reviewer_condition(self):
        row = one_row(self.open_items, "| O10 |")
        for phrase in ("[DEC-D-18](../decisions/DEC-D-18.md)", "위임 결정",
                       "외부 검토 담당은 아직 지정되지 않았다", "법적 판단이 아니다",
                       "상담을 안 하면 자동 적법하다는 전제 금지"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)

    def test_index_has_rows_for_dec_d18_and_dec_o04(self):
        d18 = self.index_row("DEC-D-18")
        self.assertIn("위임 결정", d18[1])
        self.assertIn("2026-10-15", d18[1])
        for phrase in ("O10", "외부 검토 담당", "§1 D18(R2 초기 운영)과 다른 항목"):
            self.assertIn(phrase, d18[2])
        self.assertIn("아직 지정되지 않았다", d18[3])
        self.assertIn(GATE, d18[3])
        o04 = self.index_row("DEC-O04")
        self.assertIn("사용자 확정 아님", o04[1])
        for phrase in ("O04", "동일 조건", "묶음"):
            self.assertIn(phrase, o04[2])
        for phrase in ("T-KN-09", "compare_price", GATE):
            self.assertIn(phrase, o04[3])

    def test_every_dec_cited_by_a_gate_row_is_indexed(self):
        """A DEC record that a §3 O row or a BLUEPRINT §12 row relies on must have
        a §3.1 row; §3.1 itself stays a partial index of all DEC files."""
        cited = dec_links(self.open_items) | dec_links(self.open_decisions)
        self.assertTrue({"DEC-D-18", "DEC-O04"} <= cited)
        missing = cited - dec_links(self.index)
        self.assertEqual(missing, set())

    def test_index_check_rejects_a_dropped_row(self):
        mutated = "\n".join(line for line in self.index.splitlines()
                            if not line.startswith("| [DEC-O04]("))
        cited = dec_links(self.open_items) | dec_links(self.open_decisions)
        self.assertEqual(cited - dec_links(mutated), {"DEC-O04"})

    def test_d18_is_never_cited_as_the_r2_operations_direction(self):
        self.assertIn("R2 초기 운영", one_row(self.directions, "| D18 |"))
        row = one_row(self.open_decisions, "| 외부 검토 담당 지정(D-18·O10)")
        for text in (row, one_row(self.scope, "| 첫 출시 데이터 |"),
                     one_row(self.purpose, "| P09 |")):
            self.assertNotRegex(text, r"(?<![-\w])D18(?!\w)")

    def test_s12_row_names_milestone_and_what_stays_allowed(self):
        row = cells(one_row(self.open_decisions, "| 외부 검토 담당 지정(D-18·O10)"))
        self.assertEqual(len(row), 3)
        self.assertEqual(row[1], "대외 출시")
        for phrase in ("[DEC-D-18](decisions/DEC-D-18.md)", "아직 지정되지 않았다",
                       "저장·비교 자격 판정·내부 개발 화면은 허용",
                       "[DEC-O04](decisions/DEC-O04.md)"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row[2])

    # --- report ----------------------------------------------------------------

    def test_report_links_resolve_and_point_at_evidence(self):
        self.assertTrue(REPORT.is_file())
        links = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", REPORT.read_text(encoding="utf-8"))
        self.assertTrue(links)
        for link in links:
            target = (REPORT.parent / link).resolve()
            with self.subTest(link=link):
                self.assertTrue(target.is_relative_to(ROOT))
                self.assertTrue(target.exists(), f"missing report target: {link}")
        evidence = [l for l in links if EVIDENCE_DIR in l]
        self.assertTrue(any(l.endswith("before.log") for l in evidence))
        self.assertTrue(any(l.endswith("python-tests.log") for l in evidence))

    def test_report_records_the_answer_and_its_limits(self):
        text = REPORT.read_text(encoding="utf-8")
        for phrase in ("audit2-price-display-scope", "범위의 정본", "활성화 시점의 정본",
                       "DEC-D-18", "DEC-O04", "새 D-18 결정을 만들지 않았다",
                       "법적 판단이 아니다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
