"""Audit 5: keep BLUEPRINT §11 current and reject the reported stale facts.

The generated counts table is checked by ``tools/blueprint_counts.py`` in CI.
This focused regression covers the remaining Audit 5 prose/staleness items:
hand-written counts, the bare ``BUDGET.md`` reference, the superseded S3
remaining-condition text, the ledger range, the §11 revision date and the
evidence link. It intentionally does not hard-code today's live totals.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import blueprint_counts as counts
import validation_check

BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
GAP_REPORT = ROOT / "docs/blueprint/validation/GAP_REPORT.md"
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
AUDIT = ROOT / "docs/blueprint/audits/2026-11-10_blueprint_s11_refresh.md"

HEADING = re.compile(r"^## 11\. 현재 위치 \((\d{4}-\d{2}-\d{2})\)$", re.MULTILINE)
HANDWRITTEN_AXIS_COUNT = re.compile(r"(\d+)\s*개의?\s*축")
STALE_PHRASES = ("31개 축", "O01~O12", "S3 실제 보존", "S3 버킷 정의(미배포)")


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


class S11Refresh(unittest.TestCase):
    def setUp(self):
        self.text = read(BLUEPRINT)
        self.heading = HEADING.search(self.text)
        self.assertIsNotNone(self.heading, "§11 heading with a UTC date is required")
        self.inventory = section(self.text, "## 11.", "## 12.")

    def test_top_date_records_the_same_s11_revision(self):
        header = "\n".join(self.text.splitlines()[:4])
        self.assertIn("2026-10-09 최초 작성", header)
        self.assertIn(f"{self.heading.group(1)} 현황 갱신", header)

    def test_historical_engine_counts_are_labelled_and_point_to_generated_table(self):
        code = next(line for line in self.inventory.splitlines() if line.startswith("| 코드 |"))
        self.assertIn("2026-10-09 당시", code)
        self.assertIn("합계 42건", code)
        self.assertIn("아래 자동 생성 표", code)
        self.assertIn("현재 등록 수", code)

    def test_no_stale_audit_phrases_or_bare_budget_path(self):
        for phrase in STALE_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.text)
        budget_lines = [line for line in self.text.splitlines() if "BUDGET.md" in line]
        self.assertTrue(budget_lines)
        for line in budget_lines:
            with self.subTest(line=line[:60]):
                self.assertIn("infra/r2/BUDGET.md", line)

    def test_no_handwritten_axis_count_in_the_inventory(self):
        self.assertEqual(HANDWRITTEN_AXIS_COUNT.findall(self.inventory), [])

    def test_ledger_range_and_open_decision_table_reach_o19(self):
        ledger = read(LEDGER)
        for oid in ("O17", "O18", "O19"):
            with self.subTest(oid=oid):
                self.assertIn(f"| {oid} |", ledger)
        decisions = section(self.text, "## 12.", "## 13.")
        for oid in ("O17", "O19"):
            with self.subTest(oid=oid):
                self.assertIn(oid, decisions)

    def test_v1_and_gap_report_keep_the_r2_decision(self):
        v1 = next(line for line in self.text.splitlines() if line.startswith("| V1 |"))
        self.assertIn("Cloudflare R2", v1)
        self.assertIn("ADR-0016", v1)
        remaining = v1.split("남은 조건:", 1)[1]
        for phrase in ("S3", "S3 실제 보존", "S3 버킷"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, remaining)
        gap = next(line for line in read(GAP_REPORT).splitlines() if "원본 보관소" in line)
        self.assertIn("Cloudflare R2", gap)
        self.assertIn("ADR-0016", gap)

    def test_generated_table_cheap_sources_match_live_inventory(self):
        block = self.text.split(counts.START, 1)[1].split(counts.END, 1)[0]
        rules = [path for path in (ROOT / "packages/fixtures/rules/real").glob("*.json")
                 if not path.name.endswith(".cases.json")]
        vocabulary = json.loads((ROOT / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))
        for label, expected in (
            ("실제 조항 규칙(fixture_only)", len(rules)),
            ("검증 자료 변조 시험", len(validation_check.mutations())),
            ("공유 어휘 축", len(vocabulary["axes"])),
        ):
            with self.subTest(label=label):
                row = next(line for line in block.splitlines() if line.startswith(f"| {label} |"))
                self.assertEqual(int(row.strip("|").split("|")[1]), expected)

    def test_audit_evidence_is_linked_and_present(self):
        self.assertTrue(AUDIT.is_file())
        self.assertIn("blueprint/audits/2026-11-10_blueprint_s11_refresh.md", self.inventory)

    def test_dev_tools_remain_in_the_inventory(self):
        self.assertIn("tools/daemon/", self.inventory)
        self.assertIn("tools/daemon/runner_verify/", self.inventory)


if __name__ == "__main__":
    unittest.main()
