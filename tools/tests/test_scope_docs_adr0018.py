"""Scope docs follow ADR-0018 (audit2-scope-docs-adr0018).

ADR-0018 (2026-10-10, 사용자 결정) settled the scope that SYSTEM_CONTRACT.md §2
and BLUEPRINT.md §9.1 still left open: 보험사의 개인보험(판매 중·판매 종료·
특약·개정 이력)과 우체국보험(기관 유형 구분)은 포함, 공제는 범위·확보율 분모
모두에서 제외, 단체보험·퇴직연금·자동차보험은 후속 통합. These tests pin the
corrected wording and reject the pre-decision phrasing ("전 국내 보험사",
"별도 조사 … 포함 결정 전", a scope sentence citing only ADR-0004·0013).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
CONTRACT = ROOT / "docs/blueprint/SYSTEM_CONTRACT.md"
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
REPORT = ROOT / "docs/blueprint/audits/2026-10-27_scope_docs_adr0018.md"
EVIDENCE_DIR = "tools/evidence/audit2-scope-docs-adr0018/"

SETTLED_SCOPE = "보험사의 개인보험과 우체국보험의 전 상품·전 특약·과거 판매본"

# Phrases that only made sense while inclusion was undecided.
STALE = (
    "전 국내 보험사",
    "대상은 전 보험사·전 상품·전 특약이다(확정, ADR-0004·0013)",
    "| 별도 조사 | 공제·우체국보험 |",
    "별도 후보 분모",
    "포함 결정 전",
    "확보율 혼합 금지",
)


def contract_row(text, prefix):
    rows = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise AssertionError(f"expected one row starting {prefix!r}, got {len(rows)}")
    return rows[0]


def blueprint_scope_paragraph(text):
    parts = text.split("### 9.1 순서를 이렇게 잡는 이유", 1)
    if len(parts) != 2:
        raise AssertionError("§9.1 section heading is missing")
    paragraphs = [p for p in parts[1].split("\n### ", 1)[0].split("\n\n")
                  if p.startswith("대상은 ")]
    if len(paragraphs) != 1:
        raise AssertionError(f"expected one scope paragraph, got {len(paragraphs)}")
    return paragraphs[0]


def assert_scope_aligned(self, text):
    core = contract_row(text, "| 첫 출시 핵심 |")
    for required in (SETTLED_SCOPE, "판매 중지·개정 이력 포함", "판매중지 버전", "ADR-0018"):
        self.assertIn(required, core)
    excluded = contract_row(text, "| 범위 제외 |")
    for required in ("공제", "확보율 분모", "단체보험·퇴직연금·자동차보험", "후속 통합",
                     "우체국보험", "기관 유형", "ADR-0018"):
        self.assertIn(required, excluded)
    for phrase in STALE:
        self.assertNotIn(phrase, text)


def assert_blueprint_aligned(self, text):
    paragraph = blueprint_scope_paragraph(text)
    self.assertIn(f"대상은 {SETTLED_SCOPE}이다(확정, ADR-0004·0013·0018)", paragraph)
    self.assertIn("공제는 범위·확보율 분모에서 제외", paragraph)
    self.assertIn("단체보험·퇴직연금·자동차보험은 후속 통합", paragraph)
    for phrase in STALE:
        self.assertNotIn(phrase, paragraph)
    # The scope sentence must agree with the §7.1 decision summary.
    target_row = contract_row(text, "| 대상 |")
    self.assertIn(SETTLED_SCOPE, target_row)
    self.assertIn("ADR-0004·0018", target_row)


class AdrSettled(unittest.TestCase):
    def test_adr_0018_records_the_user_decision(self):
        text = ADR.read_text(encoding="utf-8")
        self.assertIn("상태: 확정(사용자 결정, 2026-10-10)", text)
        self.assertIn("| 우체국보험 | **포함.** 보험사와 기관 유형은 구분해서 관리 |", text)
        self.assertIn("| 공제 | **제외.** 제외 이유를 기록하고 확보율 분모에서도 제외 |", text)
        self.assertIn('BLUEPRINT §12의 열린 결정 "공제·우체국보험 포함 여부"를 닫는다', text)

    def test_decision_ledger_marks_o01_resolved(self):
        row = contract_row(LEDGER.read_text(encoding="utf-8"), "| O01 |")
        self.assertIn("ADR-0018", row)
        self.assertIn("우체국보험 포함", row)
        self.assertIn("공제 제외", row)
        self.assertIn("확정: 2026-10-10", row)
        self.assertIn("확보율 분모에서도 제외", row)


class SystemContractScope(unittest.TestCase):
    def test_scope_rows_follow_adr_0018(self):
        assert_scope_aligned(self, CONTRACT.read_text(encoding="utf-8"))

    def test_stale_rows_are_rejected(self):
        text = CONTRACT.read_text(encoding="utf-8")
        core = contract_row(text, "| 첫 출시 핵심 |")
        excluded = contract_row(text, "| 범위 제외 |")
        mutations = [
            text.replace("보험사의 개인보험과 우체국보험", "전 국내 보험사", 1),
            text.replace(core, "| 첫 출시 핵심 | 전 국내 보험사·전 상품·특약 및 기존 계약 식별에 필요한 판매중지 버전 조사 | 전 상품 조사와 전 담보 계산 가능 보증은 다름 |", 1),
            text.replace(excluded, "| 별도 조사 | 공제·우체국보험 | 별도 후보 분모, 포함 결정 전 확보율 혼합 금지 |", 1),
            text.replace("후속 통합", "별도 조사", 1),
            text.replace("기관 유형", "기관", 1),
            text.replace("확보율 분모에서도 제외", "분모에 포함", 1),
            text.replace("ADR-0018", "ADR-0004", 1),
        ]
        for n, mutation in enumerate(mutations):
            with self.subTest(mutation=n), self.assertRaises(AssertionError):
                assert_scope_aligned(self, mutation)


class BlueprintScope(unittest.TestCase):
    def test_milestone_paragraph_follows_adr_0018(self):
        assert_blueprint_aligned(self, BLUEPRINT.read_text(encoding="utf-8"))

    def test_stale_paragraph_is_rejected(self):
        text = BLUEPRINT.read_text(encoding="utf-8")
        paragraph = blueprint_scope_paragraph(text)
        mutations = [
            text.replace(SETTLED_SCOPE, "전 보험사·전 상품·전 특약", 1),
            text.replace("ADR-0004·0013·0018", "ADR-0004·0013", 1),
            text.replace("공제는 범위·확보율 분모에서 제외하고, ", "", 1),
            paragraph.replace("(확정, ADR-0004·0013·0018)", "(확정, ADR-0004·0013)"),
        ]
        for n, mutation in enumerate(mutations):
            with self.subTest(mutation=n), self.assertRaises(AssertionError):
                assert_blueprint_aligned(self, mutation)


class CorrectionReport(unittest.TestCase):
    def test_report_links_resolve_and_point_at_evidence(self):
        self.assertTrue(REPORT.is_file())
        links = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", REPORT.read_text(encoding="utf-8"))
        self.assertTrue(links, "correction report must link its sources and evidence")
        evidence = []
        for link in links:
            target = (REPORT.parent / link).resolve()
            with self.subTest(link=link):
                self.assertTrue(target.is_relative_to(ROOT), "report link leaves repository")
                self.assertTrue(target.exists(), f"missing report target: {link}")
                self.assertFalse(target.is_relative_to(ROOT / "docs/review"),
                                 "this node must keep its evidence in allowed paths")
            if target.is_relative_to(ROOT / EVIDENCE_DIR.rstrip("/")):
                evidence.append(target)
        self.assertTrue(evidence, "correction report must link executable test evidence")

    def test_report_records_the_finding_and_limits(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertIn("audit2-scope-docs-adr0018", text)
        self.assertIn("ADR-0018", text)
        self.assertIn("SYSTEM_CONTRACT.md", text)
        self.assertIn("BLUEPRINT.md", text)
        for required in ("전 국내 보험사", "별도 조사", "ADR-0004·0013"):
            self.assertIn(required, text)
        self.assertIn("대신하지 않는다", text)


if __name__ == "__main__":
    unittest.main()
