"""Audit 5: should the owner ratify DEC-D-02, D-07, D-08, D-16, O04 and O12,
which "Fable autoloop" made? In D-16 the agent admits its 80%/90% pass
thresholds have no basis.

Finding: six decision records were made by the Fable autoloop before the
2026-10-15 14:44 KST delegation, and D-16 explicitly proposes its 80%/90%
thresholds, 3-person repeat rule and 12-person confirmation round "with no
basis elsewhere in the repo" while those numbers judge release gate 9
(09 P18). The finding asks whether the owner should ratify them.

The decision record (docs/decisions/audit5-confirm-agent-made-decisions.md)
resolves this without ratifying on the owner's behalf: ratification (사용자
확정) is an owner-only act, so the six stay provisional, reversible delegated
development baselines (audit4-dec-record-authority's 잠정 autoloop 기록(위임 전)
class), ratification is routed to the owner as a per-decision checklist, and
D-16's numbers keep working-baseline force only until docs/ux-tests/PREREG.md
records the owner's confirmation or override — a confirmation round run under
unconfirmed criteria cannot support '이해됨' or release gate 9. This test pins
both halves so a later edit cannot silently reopen the finding:

1. The record keeps the owner-only ratification boundary, the no-promotion
   guard, the per-decision checklist and the D-16 PREREG confirmation hook.
2. The cited repo state actually backs it: the six records' Fable autoloop
   headers and delegated markers, D-16's no-basis admission and §4 freeze,
   audit4's pre-delegation classification, the index/ledger/BLUEPRINT wording
   that separates delegation from owner confirmation, and the unchanged
   tasks.json gates and 09 P18 evidence condition.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
RECORD = ROOT / "docs/decisions/audit5-confirm-agent-made-decisions.md"
DECISIONS_DIR = ROOT / "docs/decisions"
AUDIT4 = DECISIONS_DIR / "audit4-dec-record-authority.md"
INDEX = DECISIONS_DIR / "README.md"
LEDGER = ROOT / "docs/blueprint/DECISIONS.md"
BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
ADR0006 = DECISIONS_DIR / "ADR-0006-AI-검수와-AI-분모-조사.md"
PURPOSE = BUNDLE / "09_제품목적_대응표.md"
PREREG = ROOT / "docs/ux-tests/PREREG.md"

SIX = ("D-02", "D-07", "D-08", "D-16", "O04", "O12")
# Recorded timestamps of the six pre-delegation records (audit4 classification).
TIMESTAMPS = {"D-02": "2026-10-14 06:31 KST", "O12": "2026-10-15 07:35 KST",
              "O04": "2026-10-15 08:06 KST", "D-08": "2026-10-15 08:22 KST",
              "D-07": "2026-10-15 10:34 KST", "D-16": "2026-10-15 10:34 KST"}
# Lenient markers for the owner-confirmation field the decision record routes
# into PREREG: any of these phrasings records the owner's confirmation or
# override of the proposed numbers. PREREG is owned by T-UX-01, not this node.
OWNER_CONFIRM_MARKERS = ("owner confirm", "owner-confirmed", "owner's confirmation",
                         "owner override", "소유자 확인", "사용자 확정", "준태님")


def read(path):
    return path.read_text(encoding="utf-8")


def ledger_row(text, dec_id):
    section = text.split("### 3.1 ", 1)[1].split("## 4.", 1)[0]
    return next(line for line in section.splitlines()
                if line.startswith(f"| [DEC-{dec_id}]("))


class RecordKeepsRatificationOwnerOnly(unittest.TestCase):
    def setUp(self):
        self.record = read(RECORD)

    def test_record_refuses_self_ratification(self):
        for phrase in ("Do not ratify on the owner's behalf",
                       "ratification (사용자 확정) is an owner-only act",
                       "the autoloop ratifying its own records would be the self-approval forbidden by ADR-0006 §5",
                       "DEC-D-08 ('autoloop-made records are never labelled as owner-approved')",
                       "audit4-dec-record-authority"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_keeps_the_six_as_provisional_baselines(self):
        for phrase in ("Keep DEC-D-02, D-07, D-08, D-16, O04, O12 as provisional, reversible delegated development baselines",
                       "audit4's 잠정 autoloop 기록(위임 전) classification",
                       "the 2026-10-15 delegation does not ratify them retroactively",
                       "ratification remains a routed owner review"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_routes_a_per_decision_checklist(self):
        for phrase in ("Route ratification to the owner as a per-decision checklist",
                       "recommend ratifying D-07/D-08/O04/O12 as written",
                       "D-02's composition principles + policy ownership",
                       "spend/accounts/keys/access verification kept as separate user actions"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_waives_no_gate_and_changes_no_canon(self):
        for phrase in ("ratification waives no remaining gate or evidence condition",
                       "change no tasks.json gate, daemon rule, DEC record or ledger row",
                       "D-02 procurement/spend/keys and D-16 number confirmation stay flagged user actions this decision does not authorize"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_keeps_d16_numbers_as_a_working_baseline_not_proof(self):
        for phrase in ("keep the proposed 80%/90% thresholds, 3-person repeat rule and 12-person confirmation round as the working baseline",
                       "minimum bar, not statistical proof",
                       "round 1 (8–12, problem discovery) may proceed with proposed values"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_requires_owner_confirmed_criteria_for_the_confirmation_round(self):
        for phrase in ("require docs/ux-tests/PREREG.md to record the owner's confirmation or override of them before the first session",
                       "a confirmation round run without owner-confirmed criteria cannot support '이해됨' or release gate 9 (09 P18)",
                       "changing the numbers still needs a new decision record per D-16 §4"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_links_resolve(self):
        for link in re.findall(r"\]\(([^)]+)\)", self.record):
            if "://" in link or link.startswith("#"):
                continue
            with self.subTest(link=link):
                target = (RECORD.parent / link.split("#", 1)[0]).resolve()
                self.assertTrue(target.is_relative_to(ROOT))
                self.assertTrue(target.exists(), f"missing target: {link}")


class SixRecordsStayDelegated(unittest.TestCase):
    def test_all_six_are_fable_autoloop_records(self):
        for dec_id in SIX:
            with self.subTest(dec=dec_id):
                header = read(DECISIONS_DIR / f"DEC-{dec_id}.md").splitlines()[2]
                self.assertIn("Decided by Fable 5.1 (ONJEON autoloop", header)
                self.assertIn(TIMESTAMPS[dec_id], header)
                self.assertIn("reversible", header)

    def test_d02_d07_d08_carry_explicit_delegation_markers(self):
        d02 = read(DECISIONS_DIR / "DEC-D-02.md")
        self.assertIn("위임 결정, 사용자 확정 아님", d02)
        self.assertIn("정책 소유자는 사용자 본인 1인이다", d02)
        self.assertIn("AI가 자기 임계값을 정하면 통제가 아님", d02)
        self.assertIn("지출·계약·계정 개설·키 발급을 하지도 승인하지도 않는다", d02)
        d07 = read(DECISIONS_DIR / "DEC-D-07.md")
        self.assertIn("This is a delegated decision, not an owner decision, and can be reversed.", d07)
        d08 = read(DECISIONS_DIR / "DEC-D-08.md")
        self.assertIn("autoloop-made records are never labelled as owner-approved", d08)
        self.assertIn("defaults_enabled=true needs a separate owner decision record", d08)

    def test_d16_admits_its_numbers_have_no_basis(self):
        d16 = read(DECISIONS_DIR / "DEC-D-16.md")
        for phrase in ("The 80%/90% thresholds, the 3-person repeat rule and the 12-person confirmation round are my proposed values, with no basis elsewhere in the repo.",
                       "The decision is made by the agent on the owner's behalf, and the owner can override it before the test starts.",
                       "the confirmation round alone supports '이해됨' and release gate 9",
                       "The thresholds are a minimum bar before launch, not statistical proof."):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, d16)

    def test_d16_freezes_prereg_and_requires_a_new_record_for_changes(self):
        d16 = read(DECISIONS_DIR / "DEC-D-16.md")
        for phrase in ("Before the first session, commit docs/ux-tests/PREREG.md",
                       "Changing any of them after the test starts voids that round.",
                       "Changing the criteria later needs a new decision record."):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, d16)

    def test_ledger_rows_keep_owner_confirmation_pending(self):
        ledger = read(LEDGER)
        for dec_id in SIX:
            with self.subTest(dec=dec_id):
                self.assertIn("사용자 확정 아님", ledger_row(ledger, dec_id))

    def test_audit4_classifies_the_six_as_pre_delegation_provisional(self):
        note = read(AUDIT4)
        row = next(line for line in note.splitlines()
                   if line.startswith("| 잠정 autoloop 기록(위임 전) |"))
        for dec_id in SIX:
            with self.subTest(dec=dec_id):
                self.assertIn(f"[DEC-{dec_id}](DEC-{dec_id}.md)", row)
        for phrase in ("사용자 확정이 아닌 잠정 개발 기준이며",
                       "게이트 정의·완료 기준·승인 상태를 바꾸지 못한다",
                       "DEC-O17의 위임은 그 이전 기록을 소급 승인하지 않으며"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, note)


class CanonWordingSeparatesDelegationFromConfirmation(unittest.TestCase):
    def test_decisions_index_forbids_promotion(self):
        self.assertIn("위임 결정은 사용자 확정으로 승격하지 않는다", read(INDEX))

    def test_blueprint_s12_1_keeps_delegation_distinct_and_d16_unrun(self):
        section = read(BLUEPRINT).split("### 12.1 ", 1)[1].split("### 12.2", 1)[0]
        self.assertIn("위임 결정은 사용자 확정과 구분하며, DEC 기록의 존재만으로 접근·가동 관문이 열리지는 않는다", section)
        d16_row = next(line for line in section.splitlines() if "소비자 이해도 시험(O07)" in line)
        for phrase in ("위임 결정·사용자 확정 아님",
                       "첫 세션 전 PREREG 고정",
                       "실제 시험·확인 회차 통과는 미완료"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, d16_row)
        owner_row = next(line for line in section.splitlines() if "정책 소유자 지정" in line)
        self.assertIn("사람의 유일한 역할", owner_row)
        self.assertIn("사용자 확정 대기", owner_row)

    def test_adr0006_reserves_policy_to_one_human_owner(self):
        self.assertIn("사람은 정책 소유자 1인이 임계값·모델 구성·사고 시 중단/재개를 정책 수준에서 정한다",
                      read(ADR0006))


class GatesAreUnchanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t["id"]: t for t in json.loads(read(BUNDLE / "tasks.json"))["tasks"]}

    def test_d02_gates_are_exactly_where_the_record_says(self):
        self.assertEqual(["D-02"], self.tasks["T-OP-03"]["decision_gates"]["start"])
        self.assertEqual([], self.tasks["T-OP-03"]["decision_gates"]["real_data"])
        self.assertEqual([], self.tasks["T-KN-06"]["decision_gates"]["start"])
        self.assertEqual(["D-02"], self.tasks["T-KN-06"]["decision_gates"]["real_data"])
        self.assertEqual(["D-02"], self.tasks["T-OP-02"]["decision_gates"]["real_data"])

    def test_d07_d08_d16_gates_are_unchanged(self):
        self.assertEqual(["D-06", "D-07"], self.tasks["T-AP-08"]["decision_gates"]["merge"])
        self.assertEqual(["D-08"], self.tasks["T-KN-14"]["decision_gates"]["release"])
        self.assertEqual(["D-16"], self.tasks["T-UX-01"]["decision_gates"]["start"])

    def test_o04_o12_release_gates_are_unchanged(self):
        self.assertEqual(["O04"], self.tasks["T-KN-09"]["decision_gates"]["release"])
        self.assertEqual(["O12"], self.tasks["T-TW-04"]["decision_gates"]["release"])
        self.assertEqual(["O12"], self.tasks["T-TW-05"]["decision_gates"]["release"])


class D16ConfirmationHook(unittest.TestCase):
    def test_09_p18_requires_the_explanation_vs_source_task(self):
        row = next(line for line in read(PURPOSE).splitlines() if line.startswith("| P18 |"))
        for phrase in ("사용자 이해 시험(T-UX-01)", "설명과 원문 대조", "과제 통과"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)

    def test_tux01_owns_prereg_and_pre_fixed_numbers(self):
        tasks = {t["id"]: t for t in json.loads(read(BUNDLE / "tasks.json"))["tasks"]}
        tux = tasks["T-UX-01"]
        self.assertEqual(["docs/ux-tests/**"], tux["allowed_paths"])
        self.assertIn("수락 수치가 시험 전에 고정되어 있다", tux["done_criteria"])
        u7 = next(item for item in tux["done_criteria"] if "U7" in item)
        self.assertIn("설명과 원문 대조", u7)
        self.assertIn("확인 회차의 U7 결과가 DEC-D-16 수락 수치로 판정된다", u7)

    def test_prereg_records_owner_confirmation_once_committed(self):
        record = read(RECORD)
        if PREREG.exists():
            text = read(PREREG)
            self.assertTrue(any(marker in text for marker in OWNER_CONFIRM_MARKERS),
                            "PREREG must record the owner's confirmation or override of the proposed numbers")
            self.assertIn("80%", text)
            self.assertIn("90%", text)
        else:
            # Not committed yet: the requirement must stay routed to PREREG,
            # and T-UX-01 (not this node) remains its sole writer.
            self.assertIn("require docs/ux-tests/PREREG.md to record the owner's confirmation or override of them before the first session",
                          record)
            self.assertIn("the PREREG owner-confirmation rule once committed", record)


if __name__ == "__main__":
    unittest.main()
