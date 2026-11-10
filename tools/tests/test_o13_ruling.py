"""D-04 owner acceptance releases only its gates; no credentials or real R2."""
import copy
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from daemon.core.envelope_validator import derive  # noqa: E402
from daemon.mock_env import MockEnv  # noqa: E402

BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
REPORT = ROOT / "docs/blueprint/audits/2026-11-10_d04_token_risk_acceptance.md"
BASELINE = ROOT / "tools/tests/fixtures/o13_unchanged_gates.json"
MOCK_TASK = "T-MOCK-BASIC"
R2_TASKS = ("T-DT-01", "T-DT-04", "T-OP-02", "T-OP-04")


def row(text, prefix):
    rows = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(rows) != 1:
        raise AssertionError(f"expected one {prefix!r}, got {len(rows)}")
    return rows[0]


class RulingDocumentation(unittest.TestCase):
    def assert_current_policy(self, text):
        for phrase in ("준태님", "2026-10-13", "2026-11-02", "2026-11-10",
                       "기존 R2 토큰", "폐기하지 않는다", "재발급 없이",
                       "ONJEON box secrets env", "값 출력·로그 금지", "D-04"):
            self.assertIn(phrase, text)
        for stale in ("접근 자격 후속 확인", "실제 R2 접근 차단 유지",
                      "실제 R2 접근은 계속 차단", "T-OP-04 시작 불가",
                      "기존 D-04 관문은 유지", "재사용·출력 금지"):
            self.assertNotIn(stale, text)

    def test_live_policy_rows_follow_latest_owner_ruling(self):
        targets = (
            (ROOT / "docs/blueprint/DECISIONS.md", "| O13 |"),
            (ROOT / "docs/BLUEPRINT.md", "| R2 기존 토큰 사용"),
            (BUNDLE / "05_VM실행준비.md", "| 대화에 노출된 R2 토큰 |"),
            (BUNDLE / "05_VM실행준비.md", "- [ ] R2 관련 과제("),
        )
        for path, prefix in targets:
            with self.subTest(path=path, prefix=prefix):
                policy = row(path.read_text(), prefix)
                self.assert_current_policy(policy)
                self.assertIn("[DEC-D-04]", policy)
                for phrase in ("O14", "O17", "ADR-0017"):
                    self.assertIn(phrase, policy)
        ledger = (ROOT / "docs/blueprint/DECISIONS.md").read_text()
        self.assertIn("58키·파생 v2 61키", row(ledger, "| O13 |"))
        self.assertIn("바이트 일치", row(ledger, "| O13 |"))
        self.assertIn("해결", row(ledger, "| [DEC-D-04]("))

    def test_missing_owner_or_env_and_stale_denial_are_rejected(self):
        policy = row((BUNDLE / "05_VM실행준비.md").read_text(),
                     "| 대화에 노출된 R2 토큰 |")
        mutations = [policy.replace(p, "누락") for p in (
            "준태님", "2026-11-10", "ONJEON box secrets env", "값 출력·로그 금지")]
        mutations += [policy + p for p in (
            "실제 R2 접근 차단 유지", "T-OP-04 시작 불가", "재사용·출력 금지")]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.assert_current_policy(mutation)

    def test_explicit_owner_risk_acceptance_and_revisit_triggers(self):
        text = REPORT.read_text()
        for phrase in ("준태님(소유자)", "2026-10-13", "2026-11-02", "2026-11-10",
                       "계정 전체 권한일 가능성", "위험을 소유자가 명시적으로 수용",
                       "계속 유효하게 유지", "폐기·재발급 없이 사용",
                       "ONJEON box secrets env", "출력·로그·봉투·증거 파일 기록을 금지",
                       "비인가 접근", "객체 생성·변경·삭제", "청구·사용량 이상",
                       "O14", "O17", "D-02", "O19", "ADR-0017"):
            self.assertIn(phrase, text)
        decision = (ROOT / "docs/decisions/DEC-D-04.md").read_text()
        current = decision.split("## 현행 결정", 1)[1].split("## 당시 기록 항목", 1)[0]
        self.assertIn("최신 소유자 결정으로 대체", current)
        self.assertIn("2026-11-10_d04_token_risk_acceptance.md", current)
        self.assertIn("기존 R2 토큰을 폐기하지 않고 재발급 없이 사용", current)

    def test_separate_cfut_rule_and_daemon_secret_boundary_remain(self):
        text = (BUNDLE / "05_VM실행준비.md").read_text()
        cfut = row(text, "| 대화에 노출된 `cfut_` 토큰 |")
        for phrase in ("기존 R2 토큰 이외", "사용자 폐기·재사용·출력 금지", "폐기 전 사용 금지"):
            self.assertIn(phrase, cfut)
        self.assertNotIn("start 관문 D-04", cfut)
        self.assertIn("데몬은 R2 토큰·DB 자격 증명·AI 검수 제공자 키를 갖지 않는다", text)
        self.assertIn("데몬 실행 계정 환경에 해당 변수 없음", text)

    def test_bundle_tables_and_handoff_do_not_reintroduce_d04(self):
        rows = []
        for name in ("03_작업명세.md", "README.md"):
            text = (BUNDLE / name).read_text()
            policy = row(text, "| D-04 해결(")
            rows.append(policy)
            self.assertEqual(["—"] * 4, [c.strip() for c in policy.split("|")[2:6]])
            note = text.split("D-04 기록: ", 1)[1].split("## ", 1)[0]
            self.assert_current_policy(note)
        self.assertEqual(rows[0], rows[1])
        handoff = (BUNDLE / "그록봇_인계/README.md").read_text()
        self.assertNotIn("start 관문 D-04", handoff)
        self.assertNotIn("실제 R2 접근 차단 유지", handoff)

    def test_report_and_readme_links_resolve(self):
        self.assertIn(f"]({REPORT.relative_to(ROOT).as_posix()})", (ROOT / "README.md").read_text())
        for path in (REPORT, BASELINE.parent.parent / "test_o13_ruling.py"):
            self.assertTrue(path.is_file())
        for link in re.findall(r"\]\(([^)]+)\)", REPORT.read_text()):
            target = (REPORT.parent / link.split("#", 1)[0]).resolve()
            with self.subTest(link=link):
                self.assertTrue(target.is_relative_to(ROOT))
                self.assertTrue(target.exists(), f"missing {link}")


class RulingAccessGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((BUNDLE / "tasks.json").read_text())
        cls.tasks = {t["id"]: t for t in cls.catalog["tasks"]}
        cls.baseline = json.loads(BASELINE.read_text())

    def env(self, task_id):
        env = MockEnv(BUNDLE / "daemon_rules.json", ROOT / "tools/daemon/mock_tasks.json")
        env.ports.catalog.tasks[MOCK_TASK]["decision_gates"] = copy.deepcopy(
            self.tasks[task_id]["decision_gates"])
        return env

    def test_resolved_d04_needs_no_runtime_registration(self):
        self.assertEqual(dict.fromkeys(("start", "real_data", "merge", "release"), []),
                         self.catalog["decision_index"]["D-04"])
        for task_id in R2_TASKS:
            with self.subTest(task=task_id):
                env = self.env(task_id)
                env.start_task(MOCK_TASK)
                self.assertEqual("queued", env.state(MOCK_TASK))
                self.assertNotIn("D-04", env.task(MOCK_TASK)["task_state"]["decisions_recorded"])
                for gates in self.tasks[task_id]["decision_gates"].values():
                    self.assertNotIn("D-04", gates)
                task = self.tasks[task_id]
                self.assertIn("ONJEON box secrets env", task["blocked_by"])
                self.assertIn("값 출력·로그 금지", task["blocked_by"])
                self.assertIn("폐기·재발급 선행 조건 없음", task["blocked_by"])

    def test_dt01_real_data_allowed_without_d04(self):
        env = self.env("T-DT-01")
        self.assertTrue(derive(env.core, MOCK_TASK, [])["expected.real_data_allowed"])

    def test_op02_still_requires_d02_but_not_d04(self):
        env = self.env("T-OP-02")
        for decisions in ([], ["D-04"], ["DEC-D-02"]):
            with self.subTest(decisions=decisions):
                self.assertFalse(derive(env.core, MOCK_TASK, decisions)["expected.real_data_allowed"])
        self.assertTrue(derive(env.core, MOCK_TASK, ["D-02"])["expected.real_data_allowed"])
        criteria = self.tasks["T-OP-02"]["done_criteria"][0]
        self.assertIn("(b) 없이 S1 관문을 통과로 적지 않는다", criteria)

    def test_dt04_still_requires_domestic_ip_gate(self):
        env = self.env("T-DT-04")
        for decisions in ([], ["D-04"]):
            with self.subTest(decisions=decisions):
                self.assertFalse(derive(env.core, MOCK_TASK, decisions)["expected.real_data_allowed"])
        self.assertTrue(derive(env.core, MOCK_TASK, ["O19"])["expected.real_data_allowed"])

    def test_independent_lock_bulk_and_all_other_gates_unchanged(self):
        self.assertEqual(["O14"], self.tasks["T-OP-04"]["decision_gates"]["merge"])
        self.assertEqual(["O17"], self.tasks["T-DT-05"]["decision_gates"]["release"])
        actual = {t["id"]: {k: v for k, v in t["decision_gates"].items() if v}
                  for t in self.catalog["tasks"] if any(t["decision_gates"].values())}
        self.assertEqual(self.baseline["task_gates"], actual)
        self.assertEqual(self.baseline["decision_index"],
                         {k: v for k, v in self.catalog["decision_index"].items() if k != "D-04"})
        ledger = (ROOT / "docs/blueprint/DECISIONS.md").read_text()
        for expected in self.baseline["ledger_rows"]:
            self.assertIn(expected, ledger.splitlines())
        for path, expected in self.baseline["unchanged_sha256"].items():
            with self.subTest(path=path):
                self.assertEqual(expected, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
