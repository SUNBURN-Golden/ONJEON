"""§12 summarizes the recorded decisions and preserves their remaining conditions."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
AUDIT = ROOT / "docs/blueprint/audits/2026-11-10_blueprint_s12_sync_decisions.md"

SECTION12 = re.compile(r"^## 12\. 결정 상태와 남은 조건$(.*?)^## 13\. ", re.MULTILINE | re.DOTALL)
DEC_LINK = re.compile(r"\[(DEC-[^]]+)\]\((?:\.\./)?decisions/(DEC-[^)]+)\.md\)")

# (row label, record, conditions that must still be stated in the settled row)
SETTLED = (
    ("AI 제공자 구성(서로 다른 모델 계열 2개 이상)", "DEC-D-02",
     ("구성 결정됨", "접근 확인", "월 한도", "게이트 등록")),
    ("정책 소유자 지정(AI 승인 임계값·사고 시 중단)", "DEC-D-02",
     ("소유자 결정됨", "정책 소유자=사용자 본인 1인", "O06", "D-19")),
    ("서비스 실행 클라우드", "DEC-D-03",
     ("Docker Compose", "S2 실측", "공급자·지역·DB·비용은 미정")),
    ("DSL 의미론(O12)", "DEC-O12",
     ("의미론 결정은 해결", "S6", "capability-blocked")),
    ('"필요한 돈" 기본값 출처', "DEC-D-08",
     ("defaults_enabled=false", "user_assumption", "O05")),
    ("사건 입력·청구 안내", "DEC-D-06",
     ("PDF만·사진 없음", "진단서 입력은 별도 ADR", "게이트 등록")),
    ("소비자 앱 원문 이미지·발췌 표시(D-12·O16)", "DEC-D-12",
     ("원문 이미지·발췌 표시 허용", "공개 저장소의 새 원문 발췌 추가는 승인하지 않음", "O16 잔여")),
    ("정보 공백 외부 문의", "DEC-D-14",
     ("첫 출시에 공백 관리·초안 생성·회신 보존·주장별 평가 포함", "사용자 승인 뒤 사람이 수동 발송")),
    ("개인자료 외부 AI·삭제 정책(O08·O09)", "DEC-D-17",
     ("별도 동의", "기간 값은 미완료", "그 전 합성 자료만")),
    ("외부 검토 담당 지정 요건(D-18·O10)", "DEC-D-18",
     ("대외 출시 판정 전에 외부 검토 담당을 지정", "외부 검토 담당은 아직 지정되지 않았다")),
    ("대량 자동 수집 관문(O17)", "DEC-O17",
     ("대량 자동 수집 차단 유지", "지정 환경 하나", "동시 1개")),
    ("R2 버킷 잠금", "DEC-O14",
     ("조건부 쓰기", "승인 전 적용 금지", "무기한 잠금 금지")),
)

OPEN_ONLY = (
    "색 토큰",
    "공개 웹 도메인",
    "국내 IP 수집 실행 환경(O19)",
    "레포 분리 전 통합 계약(O15)",
)


def read(path):
    return path.read_text(encoding="utf-8")


def rows(text):
    return [line for line in text.splitlines() if line.startswith("| ")]


class BlueprintS12SyncDecisions(unittest.TestCase):
    def setUp(self):
        self.text = read(BLUEPRINT)
        match = SECTION12.search(self.text)
        self.assertIsNotNone(match, "§12 must identify decision status and remaining conditions")
        self.section = match.group(1)
        parts = self.section.split("### 12.1 ", 1)
        self.assertEqual(len(parts), 2, "§12 must have a 12.1 settled subsection")
        settled_text, rest = parts[1].split("### 12.2 ", 1)
        self.settled = settled_text
        self.open_items = rest

    def settled_row(self, label):
        found = [line for line in self.settled.splitlines() if line.startswith(f"| {label}")]
        self.assertEqual(len(found), 1, f"§12.1 must have exactly one {label!r} row")
        return found[0]

    def test_section_separates_settled_from_open(self):
        self.assertIn('<a id="12-열린-결정"></a>', self.text)
        self.assertIn("결정 기록에 반영된 사항", self.settled)
        self.assertIn("아직 결정되지 않은 사항", self.open_items)
        self.assertIn("담당과 관문만 기록한 O03", self.open_items)

    def test_finding_items_are_settled_with_their_record_and_conditions(self):
        for label, record, conditions in SETTLED:
            with self.subTest(label=label):
                row = self.settled_row(label)
                self.assertIn(f"[{record}](decisions/{record}.md)", row)
                for phrase in conditions:
                    self.assertIn(phrase, row)

    def test_settled_items_are_not_listed_as_open(self):
        for label, _, _ in SETTLED:
            with self.subTest(label=label):
                stale = [line for line in self.open_items.splitlines()
                         if line.startswith(f"| {label}")]
                self.assertEqual(stale, [], f"{label!r} must not remain in 12.2")

    def test_open_items_include_pending_questions_and_exclude_settled_records(self):
        labels = [cell.strip() for line in rows(self.open_items)
                  for cell in [line.strip("|").split("|")[0]]]
        for label in OPEN_ONLY:
            with self.subTest(label=label):
                self.assertTrue(any(item.startswith(label) for item in labels),
                                f"{label!r} must remain in 12.2")
        for record in sorted({record for _, record, _ in SETTLED}):
            with self.subTest(record=record):
                self.assertNotIn(record, self.open_items)

    def test_every_linked_decision_record_exists(self):
        links = DEC_LINK.findall(self.section)
        self.assertTrue(links)
        for name, target in links:
            with self.subTest(record=name):
                self.assertEqual(name, target)
                self.assertTrue((ROOT / "docs/decisions" / f"{name}.md").is_file())

    def test_audit_evidence_document_is_linked_and_present(self):
        self.assertTrue(AUDIT.is_file())
        self.assertIn("blueprint/audits/2026-11-10_blueprint_s12_sync_decisions.md",
                      self.section)


if __name__ == "__main__":
    unittest.main()
