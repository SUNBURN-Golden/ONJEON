"""Audit 6: recorded O decisions are distinct from their outstanding conditions."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"

# Stable O IDs, their actual decision evidence, and the §12.1 row summarizing it.
# A record settles only its stated scope; it does not complete implementation.
RECORDED = {
    "O01": ("ADR-0018-보험-데이터-지식-기반의-정체성과-범위", "대상 기관 범위(O01)"),
    "O02": ("DEC-O02", "소스별 수집·재사용 조건(O02)"),
    "O04": ("DEC-O04", "동일 조건·묶음 가격 비교(O04)"),
    "O05": ("DEC-D-08", '"필요한 돈" 기본값 출처'),
    "O07": ("DEC-D-16", "소비자 이해도 시험(O07)"),
    "O08": ("DEC-D-17", "개인자료 외부 AI·삭제 정책(O08·O09)"),
    "O09": ("DEC-D-17", "개인자료 외부 AI·삭제 정책(O08·O09)"),
    "O10": ("DEC-D-18", "외부 검토 담당 지정(D-18·O10)"),
    "O12": ("DEC-O12", "DSL 의미론(O12)"),
    "O13": ("DEC-D-04", "R2 기존 토큰 사용"),
    "O14": ("DEC-O14", "R2 버킷 잠금"),
    "O16": ("DEC-D-12", "저장소 공개 범위"),
    "O17": ("DEC-O17", "대량 자동 수집 관문(O17)"),
}
UNDECIDED = {"O03", "O06", "O11", "O15", "O18", "O19"}
RESOLVED = {"O01", "O04", "O12", "O13", "O16"}


def section(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


def one_row(text, prefix):
    matches = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one row: {prefix!r}")
    return matches[0]


def check_sync(ledger, blueprint):
    """Assert both summaries classify every stable O ID without reopening records."""
    overview = section(ledger, "## 3. ", "### 3.1 ")
    settled = section(blueprint, "### 12.1 ", "### 12.2 ")
    pending = section(blueprint, "### 12.2 ", "## 13. ")
    ids = re.findall(r"^\| (O\d+) \|", overview, re.M)
    assert sorted(ids) == [f"O{i:02}" for i in range(1, 20)], ids
    for identifier in ids:
        row = one_row(overview, f"| {identifier} |")
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 6, (identifier, "explicit decision status required")
        if identifier in UNDECIDED:
            assert cells[-1] == "미정", identifier
            assert re.search(rf"^\| [^|]*\({identifier}\) \|", pending, re.M), identifier
            continue
        record, label = RECORDED[identifier]
        expected = "해결(기록 범위)" if identifier in RESOLVED else "기록(조건 잔여)"
        assert cells[-1] == expected, identifier
        assert f"](../decisions/{record}.md)" in row, identifier
        summary = one_row(settled, f"| {label}")
        assert f"](decisions/{record}.md)" in summary, identifier
        assert not re.search(rf"^\| [^|]*\({identifier}\) \|", pending, re.M), identifier
        assert not re.search(rf"^\| {re.escape(label)}", pending, re.M), label


class Audit6BlueprintDecisionsSync(unittest.TestCase):
    def setUp(self):
        self.ledger = LEDGER.read_text(encoding="utf-8")
        self.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_all_nineteen_o_items_agree_across_summaries(self):
        self.assertEqual(set(RECORDED) | UNDECIDED, {f"O{i:02}" for i in range(1, 20)})
        self.assertFalse(set(RECORDED) & UNDECIDED)
        check_sync(self.ledger, self.blueprint)

    def test_heading_does_not_classify_recorded_decisions_as_undecided(self):
        self.assertIn("## 3. 결정 상태와 남은 차단 조건", self.ledger)
        self.assertNotIn("## 3. 구현 전 미정 사항", self.ledger)
        # Keep existing deep links usable after the heading correction.
        self.assertIn('<a id="3-구현-전-미정-사항과-차단-범위"></a>', self.ledger)
        for phrase in ("기록 범위", "새 결정", "사용자 확정", "실행·출시 승인"):
            self.assertIn(phrase, section(self.ledger, "## 3. ", "| ID |"))

    def test_every_evidence_link_resolves_to_an_existing_record(self):
        for record, _ in RECORDED.values():
            with self.subTest(record=record):
                self.assertTrue((ROOT / f"docs/decisions/{record}.md").is_file())

    def test_finding_evidence_is_reachable_from_summaries_and_product_criteria(self):
        audit = "2026-11-16_blueprint_s12_decisions_sync.md"
        purpose = ROOT / "docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md"
        self.assertIn(f"](blueprint/audits/{audit})", self.blueprint)
        self.assertIn(f"](audits/{audit})", self.ledger)
        self.assertIn(f"](../../audits/{audit})", purpose.read_text(encoding="utf-8"))
        report = ROOT / "docs/blueprint/audits" / audit
        text = report.read_text(encoding="utf-8")
        self.assertIn("문서 정합성 finding의 완료 증거", text)
        self.assertIn("완료 증거를 대신하지 않는다", text)
        evidence = ROOT / "tools/evidence/audit6-blueprint-s12-decisions-sync/README.md"
        for path in (report, evidence):
            for link in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                with self.subTest(path=path.name, link=link):
                    target = (path.parent / link.split("#", 1)[0]).resolve()
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.exists(), link)

    def test_reopening_any_recorded_o_item_is_detected(self):
        for identifier in RECORDED:
            with self.subTest(identifier=identifier):
                row = one_row(self.ledger, f"| {identifier} |")
                changed = row.rsplit("|", 2)[0] + "| 미정 |"
                with self.assertRaises(AssertionError):
                    check_sync(self.ledger.replace(row, changed), self.blueprint)

    def test_losing_any_undecided_o_item_from_blueprint_is_detected(self):
        for identifier in UNDECIDED:
            with self.subTest(identifier=identifier):
                changed = re.sub(rf"^\| [^|]*\({identifier}\) \|.*\n", "",
                                 self.blueprint, flags=re.M)
                with self.assertRaises(AssertionError):
                    check_sync(self.ledger, changed)

    def test_moving_any_recorded_summary_back_to_open_is_detected(self):
        settled = section(self.blueprint, "### 12.1 ", "### 12.2 ")
        for _, label in RECORDED.values():
            with self.subTest(label=label):
                row = one_row(settled, f"| {label}")
                changed = self.blueprint.replace(row + "\n", "")
                changed = changed.replace("## 13. ", row + "\n\n## 13. ")
                with self.assertRaises(AssertionError):
                    check_sync(self.ledger, changed)


if __name__ == "__main__":
    unittest.main()
