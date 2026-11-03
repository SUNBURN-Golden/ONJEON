"""Audit 4: decisions must reach the ledger and the operational handoff."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
HANDOFF = DOCS / "blueprint/proposals/설계검토_결과/그록봇_인계/README.md"


def row(text, prefix):
    rows = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise AssertionError(f"expected one {prefix!r}, got {len(rows)}")
    return rows[0]


class DecisionsLedgerSync(unittest.TestCase):
    def setUp(self):
        self.ledger = (DOCS / "blueprint/DECISIONS.md").read_text()
        self.blueprint = (DOCS / "BLUEPRINT.md").read_text()
        self.section12 = self.blueprint.split("## 12. ", 1)[1].split("## 13. ", 1)[0]
        self.handoff = HANDOFF.read_text()

    def test_o01_o04_o12_close_the_decision_question_and_keep_execution_conditions(self):
        for identifier, record, conditions in (
            ("O01", "ADR-0018", ("공제 제외", "우체국보험 포함", "확보율 분모에서도 제외")),
            ("O04", "DEC-O04", ("I7·I8·K13", "D-18(O10)", "사용자 확정 아님")),
            ("O12", "DEC-O12", ("S6", "등록은 별도", "capability-blocked", "사용자 확정 아님")),
        ):
            summary = row(self.ledger, f"| {identifier} |")
            with self.subTest(identifier=identifier):
                self.assertIn("해결", summary)
                self.assertIn(record, summary)
                for condition in conditions:
                    self.assertIn(condition, summary)
                self.assertIn(identifier, self.section12)
                self.assertIn(record, self.section12)
        self.assertIn("의미론 결정은 해결", self.section12)

    def test_missing_decisions_have_substantive_ledger_summaries(self):
        expected = {
            "D-03": ("Docker Compose", "S2 실측", "운영 환경"),
            "D-06": ("PDF만", "사진 없음", "질병 코드", "별도 ADR"),
            "D-07": ("청구 서류", "기한", "공식 채널", "대행·전송·연계 금지"),
            "D-08": ("defaults_enabled=false", "user_assumption", "편집 기준", "별도 소유자 결정"),
            "D-14": ("첫 출시", "초안", "회신", "사용자 승인", "수동 발송", "자동 발송 금지"),
            "D-16": ("U1~U7", "8~12", "12명 이상", "80%", "90%", "3명", "PREREG"),
            "D-17": ("학습 미사용", "보존 최소", "처리 지역", "별도 동의", "합성 자료", "보존 기한"),
            "O02": ("소스별", "조건·한도", "기록", "제한 우회", "미확인 대량 조회 금지"),
            "O14": ("조건부 쓰기", "무기한 잠금 금지", "미정", "승인 전 적용 금지"),
            "O17": ("지정 환경 하나", "동시 1개", "수동 실행", "고정 키", "O19", "대량 자동 수집 차단"),
        }
        for gate, phrases in expected.items():
            summary = row(self.ledger, f"| [DEC-{gate}](")
            with self.subTest(gate=gate):
                self.assertIn("위임", summary)
                self.assertIn("사용자 확정 아님", summary)
                for phrase in phrases:
                    self.assertIn(phrase, summary)

    def test_bundle_index_preserves_adr0019_supersession(self):
        summary = row(self.ledger, "| [DEC-BUNDLE-STATUS](")
        for phrase in ("ADR-0019", "09·tasks.json", "한정 채택", "D-21", "묶음 전체"):
            self.assertIn(phrase, summary)

    def test_decision_directory_index_links_every_record_and_the_canonical_summaries(self):
        index_path = DOCS / "decisions/README.md"
        text = index_path.read_text()
        indexed = re.findall(r"^\| \[(DEC-[^]]+)\]\(([^)]+)\)", text, re.M)
        records = {p.stem for p in index_path.parent.glob("DEC-*.md")}
        self.assertTrue(records)
        self.assertEqual(sorted(name for name, _ in indexed), sorted(records))
        for name, target in indexed:
            self.assertEqual((index_path.parent / target).resolve(), index_path.parent / f"{name}.md")
        for target in ("../blueprint/DECISIONS.md", "../BLUEPRINT.md#12-열린-결정",
                       "../blueprint/proposals/설계검토_결과/그록봇_인계/README.md"):
            self.assertIn(f"]({target})", text)

    def test_handoff_points_to_decisions_at_the_product_gate_table(self):
        product = self.handoff.split("### 10.2 ", 1)[1].split("### 10.3 ", 1)[0]
        for target in ("../../../../decisions/README.md", "../../../DECISIONS.md",
                       "../../../../BLUEPRINT.md#12-열린-결정"):
            self.assertIn(f"]({target})", product)
        for phrase in ("결정 내용과 실행 조건", "D-02", "접근 확인", "월 한도", "O12", "S6"):
            self.assertIn(phrase, product)
        for identifier in ("CANON-T-CT-02", "D-02", "D-03", "D-04", "D-06", "D-07",
                           "D-08", "D-12", "D-14", "D-16", "D-17", "D-18", "O02", "O04", "O12"):
            self.assertIn(f"[DEC-{identifier}](../../../../decisions/DEC-{identifier}.md)", product)
        self.assertNotIn("결정이 날 때까지 해당 관문에서 멈춘다", self.handoff)
        self.assertNotIn("D-04(R2 토큰 폐기 등)", product)

    def test_product_purpose_links_the_finding_without_claiming_product_completion(self):
        purpose = (DOCS / "blueprint/proposals/설계검토_결과/09_제품목적_대응표.md").read_text()
        note = next(line for line in purpose.splitlines()
                    if "2026-11-03_decisions_ledger_sync.md" in line)
        self.assertIn("](../../audits/2026-11-03_decisions_ledger_sync.md)", note)
        for phrase in ("문서 정합성 finding의 완료 증거", "출시 완료 증거를 대신하지 않는다"):
            self.assertIn(phrase, note)

    def test_new_decision_navigation_and_evidence_links_resolve(self):
        paths = [DOCS / "decisions/README.md", HANDOFF,
                 DOCS / "decisions/audit4-decisions-ledger-sync.md",
                 DOCS / "blueprint/audits/2026-11-03_decisions_ledger_sync.md"]
        for path in paths:
            links = re.findall(r"\]\(([^)]+)\)", path.read_text())
            self.assertTrue(links)
            for link in links:
                if "://" in link or link.startswith("#"):
                    continue
                with self.subTest(path=path.name, link=link):
                    target = (path.parent / link.split("#", 1)[0]).resolve()
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.exists(), f"missing target: {link}")


if __name__ == "__main__":
    unittest.main()
