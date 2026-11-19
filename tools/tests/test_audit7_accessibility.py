"""Check the minimum accessibility decision and its delivery owners."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = Path("docs/BLUEPRINT.md")
DECISIONS = Path("docs/decisions")
ADR = DECISIONS / "ADR-0021-첫-출시-최소-접근성.md"
AUDIT = DECISIONS / "audit7-accessibility-out-of-scope.md"
LEDGER = Path("docs/blueprint/DECISIONS.md")
BUNDLE = Path("docs/blueprint/proposals/설계검토_결과")
PURPOSE = BUNDLE / "09_제품목적_대응표.md"
EVIDENCE = Path("tools/evidence/audit7-accessibility-out-of-scope/README.md")
PENDING = "위임 결정·가역·사용자 확정 아님"  # Historical audit finding.
RATIFIED = "2026-11-19 소유자 확정"


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def row(text, key):
    matches = [line for line in text.splitlines() if line.startswith(f"| {key} |")]
    if len(matches) != 1:
        raise AssertionError(f"Expected one row for {key}, found {len(matches)}")
    return [cell.strip() for cell in matches[0].strip("|").split("|")]


class AccessibilityContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = read(BLUEPRINT)
        cls.adr = read(ADR)
        cls.purpose = read(PURPOSE)
        cls.tasks = {task["id"]: task for task in json.loads(read(BUNDLE / "tasks.json"))["tasks"]}

    def require(self, text, *phrases):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_blueprint_applies_the_same_minimum_as_the_adr(self):
        section = self.blueprint.split("### 7.2 ", 1)[1].split("### 7.3 ", 1)[0]
        _, decision, authority = row(section, "접근성")
        self.require(decision, "앱·공개 웹", "개발·검증 기준", RATIFIED)
        self.assertNotIn("목표 아님", decision)
        self.assertIn(ADR.name, authority)
        for content in (section, self.adr):
            self.require(content, "200%", "4.5:1", "3:1", "비텍스트", "제목",
                         "이름·역할·상태", "읽기 순서", "활성화")

    def test_historical_exclusion_and_visual_restriction_are_superseded_for_development(self):
        replacements = self.blueprint.split("### 7.3 ", 1)[1].split("## 8. ", 1)[0]
        self.require(replacements, "§51.4", "당시 사용자 결정", "화면_조작_설계서.md",
                     "시안 변경 제한", "색상·치수·줄바꿈·시맨틱", "§7.2", RATIFIED, "첫 출시 소비자 앱·공개 웹")
        self.require(read(DECISIONS / "ADR-0001-기술-스택.md"), ADR.name, "역사적 기록")
        self.require(read("docs/blueprint/SYSTEM_CONTRACT.md"), "72-방식", "200%", "비텍스트", "스크린 리더")

    def test_owner_ratification_preserves_history_and_release_gates(self):
        _, direction, authority = row(read(LEDGER), "BP-D-22")
        self.require(direction, "§51.4", "당시 제외 결정", "이 첫 출시 범위에서 대체", "09 P19")
        self.require(authority, ADR.name + "#사용자-확정", RATIFIED)
        self.require(self.adr, "2026-11-19 | 소유자 확정", "2026-10-08 결정은 당시의 이력으로 보존",
                     "첫 출시 소비자 앱·공개 웹에 한하여", "P19 실제 화면 검증 또는 출시 승인이 아니다",
                     "T-OP-08 출시 판정")
        self.require(read(AUDIT), PENDING, ADR.name + "#사용자-확정")
        self.require(read(DECISIONS / "README.md"), ADR.name + "#사용자-확정", RATIFIED, "P19", "T-OP-08")
        _, timing, authority = row(self.blueprint, "첫 출시 최소 접근성")
        self.require(timing, "T-OP-08", "소유자 답", "P19")
        self.require(authority, ADR.name + "#사용자-확정", "2026-11-19 소유자가 확정했다", "P19", "출시 판정은 별도")

    def test_p19_requires_real_mobile_and_web_evidence_and_assigns_owners(self):
        p19 = row(self.purpose, "P19")
        self.require(p19[7], "상태 카탈로그 캡처 1:1", "실제 참가자 이해 시험 결과",
                     "실제 앱·공개 웹", "200%", "대비", "시맨틱 트리", "TalkBack", "VoiceOver",
                     "웹 스크린 리더 실행 기록")
        self.require(p19[9], ADR.name, RATIFIED, "실제 화면과 보조 기술 시험은 미완료")
        for owner, test_id, platform in (
            ("T-MB-03", "mobile-screen-accessibility", "TalkBack·VoiceOver"),
            ("T-WB-01", "public-web-accessibility", "웹 스크린 리더"),
        ):
            with self.subTest(owner=owner):
                task = self.tasks[owner]
                self.assertIn(owner, p19[6].split(", "))
                self.assertIn(str(ADR), task["inputs"])
                self.assertIn(test_id, task["required_test_ids"])
                self.assertIn(f"`{test_id}`({owner})", self.purpose)
                check = next(test for test in task["tests"] if test.startswith(f"시험 {test_id}("))
                self.require(check, "200%", "4.5:1", "3:1", "시맨틱", platform)
                self.require(" ".join(task["done_criteria"]), "P19", platform, "실행 기록")

    def test_p18_tracks_the_older_participant_plan_and_u7_results(self):
        self.require(row(self.purpose, "P18")[7], "고령 참가자", "사전등록", "U7 결과")
        task = self.tasks["T-UX-01"]
        self.require(" ".join(task["done_criteria"]), "PREREG", "고령 참가자", "U7", "DEC-D-16")
        self.assertEqual(task["decision_gates"]["start"], ["D-16"])

    def test_decision_and_evidence_links_resolve(self):
        self.assertTrue((ROOT / EVIDENCE).is_file())
        for document in (ADR, AUDIT):
            for target in re.findall(r"\]\(([^)]+)\)", read(document)):
                if not target.startswith("https://"):
                    with self.subTest(document=document, target=target):
                        self.assertTrue((ROOT / document.parent / target.split("#", 1)[0]).is_file())


if __name__ == "__main__":
    unittest.main()
