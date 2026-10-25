"""Assert live D-04 documentation and mock access gates; no credentials or R2."""
import copy
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
REPORT = ROOT / "docs/blueprint/audits/2026-10-26_o13_d04_ruling.md"
MOCK_TASK = "T-MOCK-BASIC"

TARGETS = {
    "docs/blueprint/DECISIONS.md": ("| O13 |", "../decisions/DEC-D-04.md", 5),
    "docs/BLUEPRINT.md": ("| R2 접근 자격", "decisions/DEC-D-04.md", 3),
    "docs/blueprint/proposals/설계검토_결과/05_VM실행준비.md": (
        "| 대화에 노출된 R2", "../../../decisions/DEC-D-04.md", 2),
    "docs/blueprint/proposals/설계검토_결과/03_작업명세.md": (
        "| D-04 ", "../../../decisions/DEC-D-04.md", 6),
    "docs/blueprint/proposals/설계검토_결과/README.md": (
        "| D-04 ", "../../../decisions/DEC-D-04.md", 6),
}

# The four audited pre-fix rows: they must never be accepted as resolved.
LEGACY_ROWS = {
    "docs/blueprint/DECISIONS.md": "| O13 | ~~수집 원본의 불변 보관소~~ → D14·D16으로 결정. 2026-10-09 R2에 원본 58키·파생 v2 61키 보존, 다시 받아 전부 바이트 일치(`source_checks/2026-10-09_r2_*`). 공개 주소는 세 버킷 모두 꺼짐(검토자 API 확인). 남은 일: 대화로 받은 토큰 폐기와 범위 제한 토큰 재발급, 버킷 잠금(O14) | 데이터 운영 책임 | V1 관문 판정 전 | 보존·대조 기록 있음 / 토큰 폐기 전 추가 수집 금지 |",
    "docs/BLUEPRINT.md": "| 대화로 받은 R2 토큰 폐기와 범위 제한 토큰 재발급 | 다음 R2 작업 | 토큰 폐기 전 추가 수집 금지 |",
    "docs/blueprint/proposals/설계검토_결과/05_VM실행준비.md": "| 대화에 노출된 R2·`cfut_` 토큰 | 사용자가 폐기. 재사용·출력 금지. 폐기 전까지 T-OP-04는 시작 불가(start 관문 D-04) |",
    "docs/blueprint/proposals/설계검토_결과/03_작업명세.md": "| D-04 대화 노출 R2 토큰 폐기·범위 제한 토큰 재발급 | T-OP-04 | T-DT-01, T-OP-02, T-DT-04 | — | — | 로컬 객체 저장소 경로(T-DT-01), 모든 설계·시험·코드 작성 |",
}


def target_row(text, path):
    rows = [line for line in text.splitlines() if line.startswith(TARGETS[path][0])]
    if len(rows) != 1:
        raise AssertionError(f"{path}: expected one audited row, got {len(rows)}")
    return rows[0]


class RulingDocumentation(unittest.TestCase):
    def setUp(self):
        source = (ROOT / "docs/decisions/DEC-D-04.md").read_text(encoding="utf-8")
        self.owner = re.search(r"\| decided_by \| ([^ (]+)", source).group(1)
        self.decided_at = re.search(
            r"\| time \(`decided_at`\) \| ([^|]+) \|", source).group(1).strip()
        self.assertIn("R2 토큰 폐기만 수행하지 않는다", source)

    def assert_corrected(self, text, path):
        row = target_row(text, path)
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertEqual(TARGETS[path][2], len(cells), path)
        link = f"[DEC-D-04]({TARGETS[path][1]})"
        self.assertIn(link, row, path)
        self.assertTrue((ROOT / path).parent.joinpath(TARGETS[path][1]).is_file())
        context = row
        if TARGETS[path][2] == 6:
            notes = re.findall(r"^D-04 기록: .*?(?=^## |\Z)", text, re.M | re.S)
            self.assertEqual(1, len(notes), path)
            context += "\n" + notes[0]
            self.assertEqual("D-04 R2 접근 관문(" + link + ")", cells[0])
            self.assertEqual(["T-OP-04", "T-DT-01, T-OP-02, T-DT-04", "—", "—"], cells[1:5])
            self.assertIn("real_data_allowed = false", cells[5])
            self.assertIn("기존 D-04 관문은 유지", context)
        for required in (self.owner, self.decided_at, "폐기하지 않는다", "재사용·출력 금지", "관문"):
            self.assertIn(required, context, path)
        self.assertNotIn("폐기 전", row, path)
        self.assertNotIn("폐기·범위 제한 토큰 재발급", row, path)
        if path.endswith("DECISIONS.md"):
            for preserved in ("58키", "61키", "바이트 일치", "버킷 잠금(O14)", "실제 R2 접근은 계속 차단"):
                self.assertIn(preserved, row)
            self.assertIn(self.owner, cells[2])
            self.assertIn(self.decided_at, cells[3])
        elif path == "docs/BLUEPRINT.md":
            self.assertEqual("다음 R2 작업", cells[1])
            self.assertIn("실제 R2 접근 차단 유지", row)
            self.assertIn("O14·O17은 별도 관문", row)
        elif path.endswith("05_VM실행준비.md"):
            self.assertIn("T-OP-04 시작 불가", row)
            cfut_rows = [line for line in text.splitlines()
                         if line.startswith("| 대화에 노출된 `cfut_` 토큰 |")]
            self.assertEqual(1, len(cfut_rows))
            for required in ("사용자가 폐기", "재사용·출력 금지", "폐기 전까지 T-OP-04는 시작 불가", "D-04"):
                self.assertIn(required, cfut_rows[0])
            self.assertNotIn("폐기하지 않는다", cfut_rows[0])

    def test_live_rows_record_ruling_owner_date_and_preserve_gates(self):
        # Only live files and the owner record determine acceptance.
        for path in TARGETS:
            with self.subTest(path=path):
                self.assert_corrected((ROOT / path).read_text(encoding="utf-8"), path)

    def test_original_rows_are_rejected_in_live_documents(self):
        for path, old in LEGACY_ROWS.items():
            text = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(path=path), self.assertRaises(AssertionError):
                self.assert_corrected(text.replace(target_row(text, path), old, 1), path)

    def test_missing_ruling_metadata_duplicates_and_reuse_permission_fail(self):
        for path in TARGETS:
            text = (ROOT / path).read_text(encoding="utf-8")
            mutations = [
                text + target_row(text, path) + "\n",
                text.replace(self.owner, "미지정"),
                text.replace(self.decided_at, "날짜 미지정"),
                text.replace("폐기하지 않는다", "폐기한다"),
                text.replace("재사용·출력 금지", "재사용 허용"),
                text.replace("[DEC-D-04]", "[다른 결정]"),
            ]
            if path.endswith("05_VM실행준비.md"):
                mutations.append("\n".join(line for line in text.splitlines() if "`cfut_`" not in line))
            for n, mutation in enumerate(mutations):
                with self.subTest(path=path, mutation=n), self.assertRaises(AssertionError):
                    self.assert_corrected(mutation, path)

    def test_bundle_table_and_notes_stay_in_sync(self):
        spec = (BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
        paths = list(TARGETS)
        self.assertEqual(target_row(spec, paths[3]), target_row(readme, paths[4]))
        for text in (spec, readme):
            self.assertNotIn("D-04 대화 노출 R2 토큰 폐기·범위 제한 토큰 재발급", text)

    def test_task_descriptions_reference_ruling_without_revocation_prerequisite(self):
        tasks = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))["tasks"]
        for task in tasks:
            if task["id"] in ("T-DT-01", "T-OP-04"):
                with self.subTest(task=task["id"]):
                    self.assertIn("DEC-D-04", task["blocked_by"])
                    self.assertIn("재사용·출력 금지", task["blocked_by"])
                    self.assertNotIn("폐기·재발급", task["blocked_by"])

    def test_readme_links_current_correction_evidence(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"]({REPORT.relative_to(ROOT).as_posix()})", readme)
        self.assertTrue(REPORT.is_file())
        self.assertIn("](docs/decisions/DEC-D-04.md)", readme)
        self.assertIn("작업명세에 반영했다", readme)
        self.assertNotIn("정본 네 행은 미반영", readme)
        self.assertNotIn("docs/review/2026-10-23_audit1_o13_d04_ruling.md", readme)

    def test_correction_report_links_resolve_with_evidence_in_allowed_paths(self):
        links = re.findall(r"\]\(([^)]+)\)", REPORT.read_text(encoding="utf-8"))
        self.assertTrue(links, "correction report must link its sources and evidence")
        evidence = []
        for link in links:
            target = (REPORT.parent / link.split("#", 1)[0]).resolve()
            with self.subTest(link=link):
                self.assertTrue(target.is_relative_to(ROOT), "report link leaves repository")
                self.assertTrue(target.exists(), f"missing report target: {link}")
                self.assertFalse(target.is_relative_to(ROOT / "docs/review"),
                                 "this node must keep its evidence in allowed paths")
            if target.is_relative_to(ROOT / "tools/evidence/audit1-o13"):
                evidence.append(target)
        self.assertTrue(evidence, "correction report must link executable test evidence")


class RulingAccessGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t["id"]: t for t in json.loads(
            (BUNDLE / "tasks.json").read_text(encoding="utf-8"))["tasks"]}

    def env(self, task_id):
        env = MockEnv(BUNDLE / "daemon_rules.json", ROOT / "tools/daemon/mock_tasks.json")
        env.ports.catalog.tasks[MOCK_TASK]["decision_gates"] = copy.deepcopy(
            self.tasks[task_id]["decision_gates"])
        return env

    def test_record_file_alone_does_not_release_op04_start(self):
        self.assertTrue((ROOT / "docs/decisions/DEC-D-04.md").is_file())
        env = self.env("T-OP-04")
        env.start_task(MOCK_TASK)
        self.assertEqual("blocked", env.state(MOCK_TASK))
        self.assertNotIn("D-04", env.task(MOCK_TASK)["task_state"]["decisions_recorded"])
        self.assertEqual([], env.ports.sender.sent)

    def test_local_paths_queue_but_r2_access_stays_disabled(self):
        for task_id in ("T-DT-01", "T-DT-04", "T-OP-02"):
            with self.subTest(task=task_id):
                env = self.env(task_id)
                env.start_task(MOCK_TASK)
                self.assertEqual("queued", env.state(MOCK_TASK))
                self.assertFalse(derive(env.core, MOCK_TASK, [])["expected.real_data_allowed"])
                # The document reference is not a registered decision ID.
                self.assertFalse(derive(env.core, MOCK_TASK, ["DEC-D-04"])["expected.real_data_allowed"])

    def test_op02_requires_both_registered_decisions(self):
        env = self.env("T-OP-02")
        for decisions in ([], ["D-02"], ["D-04"]):
            with self.subTest(decisions=decisions):
                self.assertFalse(derive(env.core, MOCK_TASK, decisions)["expected.real_data_allowed"])
        # Positive control in memory only: confirms that the gate is evaluated,
        # rather than testing an unconditional denial.
        self.assertTrue(derive(env.core, MOCK_TASK, ["D-02", "D-04"])["expected.real_data_allowed"])

    def test_independent_lock_and_bulk_collection_gates_remain(self):
        self.assertEqual(["D-04"], self.tasks["T-OP-04"]["decision_gates"]["start"])
        self.assertEqual(["O14"], self.tasks["T-OP-04"]["decision_gates"]["merge"])
        self.assertEqual(["O17"], self.tasks["T-DT-05"]["decision_gates"]["release"])


if __name__ == "__main__":
    unittest.main()
