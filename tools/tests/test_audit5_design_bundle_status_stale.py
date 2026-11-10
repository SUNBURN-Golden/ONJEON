"""Audit 5: the design bundle must describe T-OP-00/T-OP-09 and DEC records honestly.

Finding: the bundle README, implementation contract, VM preparation guide and
handoff README still said T-OP-00 was missing or had only 16 of 33 required
test IDs, and the 09 purpose table still read as if D-06, D-07, D-08, D-12,
D-14, D-16, D-18 and O04 were pending although each has a DEC record.

This test pins the current wording: the mock core and the release-executor
validation are recorded as merged with their remaining PARTIAL/gap follow-ups,
and every settled decision is marked as recorded while its residual execution
gate stays separate. It does not claim actual daemon operation or release
completion.
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
BUNDLE_README = BUNDLE / "README.md"
CONTRACT = BUNDLE / "02_구현계약.md"
VM_PREP = BUNDLE / "05_VM실행준비.md"
HANDOFF = BUNDLE / "그록봇_인계/README.md"
PURPOSE = BUNDLE / "09_제품목적_대응표.md"
AUDIT = ROOT / "docs/blueprint/audits/2026-11-10_design_bundle_status_stale.md"
EVIDENCE = ROOT / "tools/evidence/audit5-design-bundle-status-stale/README.md"
DRY_RUN = ROOT / "tools/daemon/dry_run.py"
RULES = BUNDLE / "daemon_rules.json"
MOCK_TASKS = ROOT / "tools/daemon/mock_tasks.json"

GATE = "가격 열 대외 공개 표시는 D-18(O10) 외부 검토 담당 지정 뒤"
O04_RESOLVED = "O04는 DEC-O04로 해결"


def read(path):
    return path.read_text(encoding="utf-8")


def one_row(text, prefix):
    rows = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise AssertionError(f"expected one {prefix!r}, got {len(rows)}")
    return rows[0]


def cells(row):
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


class DesignBundleStatusClaims(unittest.TestCase):
    def setUp(self):
        self.bundle = read(BUNDLE_README)
        self.contract = read(CONTRACT)
        self.vm = read(VM_PREP)
        self.handoff = read(HANDOFF)

    def test_bundle_readme_reports_seventh_revision_and_merged_daemon_work(self):
        self.assertNotIn("수정판 6차 제출", self.bundle)
        for phrase in ("수정판 7차 제출", "1f70cdc", "T-OP-00", "T-OP-09",
                       "필수 시험 ID 33개 전부 실행", "PASS 17", "PARTIAL 5",
                       "FAIL 0", "남은 후속"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.bundle)
        for stale in ("둘 다 아직 없다", "T-OP-00·T-OP-09 없음"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.bundle)
        self.assertIn("tools/daemon/README.md", self.bundle)
        self.assertIn("vm_check/2026-10-16/RESULTS.md", self.bundle)
        self.assertIn("2026-11-10_design_bundle_status_stale.md", self.bundle)

    def test_contract_no_longer_says_only_rule_files_exist(self):
        row = one_row(self.contract, "| 데몬 상태 기계·펜싱·전환 신호 |")
        for phrase in ("T-OP-00 모의 코어", "필수 시험 ID 33개 전부 실행",
                       "T-OP-09 실제 실행기 검증", "PASS 17", "PARTIAL 5",
                       "FAIL 0", "남은 후속", "실제 가동·출시 완료 증거가 아니다",
                       "tools/daemon/README.md", "vm_check/2026-10-16/RESULTS.md"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)
        for stale in ("규칙 파일만 있음", "둘 다 가동이 아니다"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, row)

    def test_vm_prep_records_the_existing_dry_run_tool(self):
        for phrase in ("T-OP-00(#21·#97)", "필수 시험 ID 33개",
                       "--require-all", "tools/daemon/README.md",
                       "vm_check/2026-10-16/RESULTS.md",
                       "모의 규칙 검증이며 실제 실행기·가동 증거가 아니다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.vm)
        self.assertNotIn("이 도구는 아직 없다(T-OP-00)", self.vm)

    def test_handoff_marks_old_16_of_33_state_as_historical(self):
        for phrase in ("완료(2026-10-15, #21·T-OP-00b #97)",
                       "T-OP-00(#21·#97)", "33개 전부",
                       "PASS 17·PARTIAL 5·FAIL 0", "2026-10-13 당시"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.handoff)
        for stale in ("필수 시험 ID 33개 중 16개만 구현됐다",
                      "나머지 시나리오(필수 시험 ID 33개 중 구현하지 않은 17개",
                      "실제 실행기(T-OP-09)는 없다",
                      "7차 계약(07 §1e) 반영을 마친 뒤 나머지 M 시나리오를 구현한다"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.handoff)

    def test_handoff_does_not_overclaim_the_mock_and_executor_limits(self):
        # The "not proven" list must not be followed by "all confirmed".
        for stale in ("모두 단계 2·3", "구현하지 않은 시나리오"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.handoff)
        for phrase in ("R1~R22", "PASS 17·PARTIAL 5·FAIL 0",
                       "실제 제공자 청구와 사용량 기록의 대조",
                       "실제 CI·리뷰 서비스", "벤더 CLI 전체",
                       "아직 확인하지 않았다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.handoff)


class PurposeTableDecisionRecorded(unittest.TestCase):
    DECISIONS = {
        "P02": ("DEC-D-18", "DEC-O04"),
        "P03": ("DEC-D-14",),
        "P09": ("DEC-D-18", "DEC-O04"),
        "P11": ("DEC-D-06", "DEC-D-07"),
        "P14": ("DEC-D-12",),
        "P17": ("DEC-D-08",),
        "P19": ("DEC-D-16",),
    }

    def setUp(self):
        self.text = read(PURPOSE)
        self.rows = {}
        for line in self.text.splitlines():
            if re.match(r"^\| P\d{2} \|", line):
                row = cells(line)
                self.assertEqual(10, len(row))
                self.rows[row[0]] = row
        self.assertEqual({f"P{i:02}" for i in range(1, 20)}, self.rows.keys())

    def test_each_settled_gate_is_marked_recorded_and_keeps_its_residual_condition(self):
        for row, decisions in self.DECISIONS.items():
            scope = self.rows[row][-1]
            with self.subTest(row=row):
                self.assertIn("결정 기록됨", scope)
                self.assertIn("남은 조건", scope)
                self.assertNotIn("결정 대기", scope)
                self.assertNotIn("초안만", scope)
            for decision in decisions:
                with self.subTest(row=row, decision=decision):
                    self.assertIn(decision, scope)
                    target = ROOT / "docs/decisions" / f"{decision}.md"
                    self.assertTrue(target.is_file(), f"missing {target}")
                    self.assertIn(
                        f"[{decision}](../../../decisions/{decision}.md)", scope)

    def test_price_display_rows_keep_the_scope_contract_and_the_open_reviewer(self):
        for row in ("P02", "P09"):
            scope = self.rows[row][-1]
            with self.subTest(row=row):
                self.assertIn(GATE, scope)
                self.assertIn(O04_RESOLVED, scope)
                self.assertIn("외부 검토 담당", scope)
                self.assertIn("미지정", scope)
                self.assertIn("축소 아님", scope)

    def test_residual_conditions_are_not_reported_as_completed(self):
        expected = {
            "P03": ("게이트 등록", "별도"),
            "P11": ("게이트 등록", "구현 검증", "별도"),
            "P14": ("게이트 등록", "플래그 적용", "별도"),
            "P17": ("O05 미해결", "게이트 등록", "구현 검증", "별도"),
            "P19": ("게이트 등록", "별도", "실제 시험·확인 회차 통과는 미완료"),
        }
        for row, phrases in expected.items():
            for phrase in phrases:
                with self.subTest(row=row, phrase=phrase):
                    self.assertIn(phrase, self.rows[row][-1])

    def test_audit_note_points_at_the_sync_record_and_its_limit(self):
        for phrase in ("2026-11-10_design_bundle_status_stale.md",
                       "T-OP-00", "T-OP-09", "PARTIAL",
                       "문서 정합성", "출시 완료 증거를 대신하지 않는다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)


class AuditEvidenceRecords(unittest.TestCase):
    def test_audit_and_evidence_exist_with_logs(self):
        self.assertTrue(AUDIT.is_file(), "audit record must exist")
        self.assertTrue(EVIDENCE.is_file(), "evidence README must exist")
        evidence_dir = EVIDENCE.parent
        for name in ("before.log", "focused.log", "python-tests.log",
                     "dry-run.log", "status.log"):
            with self.subTest(name=name):
                self.assertTrue((evidence_dir / name).is_file())

    def test_links_in_new_records_resolve_inside_the_repository(self):
        for path in (AUDIT, EVIDENCE):
            for link in re.findall(r"\]\(([^)]+)\)", read(path)):
                if "://" in link or link.startswith("#"):
                    continue
                with self.subTest(path=path.name, link=link):
                    target = (path.parent / link.split("#", 1)[0]).resolve()
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.exists(), f"missing target: {link}")


class DaemonRequiredCoverage(unittest.TestCase):
    def test_dry_run_executes_all_33_required_ids(self):
        result = subprocess.run(
            [sys.executable, "-I", str(DRY_RUN), "--rules", str(RULES),
             "--tasks", str(MOCK_TASKS), "--scenario", "all",
             "--require-all", "--quiet"],
            cwd=ROOT, capture_output=True, text=True, timeout=180)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"검사 \d+건, 실패 0건")
        self.assertIn(
            "필수 시험 ID 33개 중 이번에 실행한 것 33개, 실행하지 않은 것 0개",
            result.stdout)
        self.assertIn("필수 목록에 없는 시험 ID 0개", result.stdout)
        self.assertIn("두 번 이상 나온 시험 ID 0개", result.stdout)


if __name__ == "__main__":
    unittest.main()
