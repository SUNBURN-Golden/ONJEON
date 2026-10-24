"""Live D-04 rows, applicable corrections, and the access gates they preserve.

Protected sources are read only. The daemon uses in-memory mock ports, and only
gate lists from real tasks are copied into a mock task; no R2 access is attempted.
"""
import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from daemon.core.envelope_validator import derive  # noqa: E402
from daemon.mock_env import MockEnv  # noqa: E402

BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
REVIEW = ROOT / "docs/review/2026-10-23_audit1_o13_d04_ruling.md"
MOCK_TASK = "T-MOCK-BASIC"


TARGETS = {
    "docs/blueprint/DECISIONS.md": ("| O13 |", "../decisions/DEC-D-04.md", 5),
    "docs/BLUEPRINT.md": ("R2", "decisions/DEC-D-04.md", 3),
    "docs/blueprint/proposals/설계검토_결과/05_VM실행준비.md": (
        "| 대화에 노출된 R2", "../../../decisions/DEC-D-04.md", 2),
    "docs/blueprint/proposals/설계검토_결과/03_작업명세.md": (
        "| D-04 ", "../../../decisions/DEC-D-04.md", 6),
}


def patch_changes():
    """Read the four single-hunk corrections, including their exact context."""
    changes = {}
    for part in REVIEW.with_suffix(".patch").read_text(encoding="utf-8").split("--- a/")[1:]:
        path, rest = part.split("\n", 1)
        lines = rest.splitlines()
        if lines[0] != "+++ b/" + path or sum(l.startswith("@@ ") for l in lines) != 1:
            raise AssertionError("Expected one hunk per target")
        body = lines[2:]
        old = "".join(l[1:] + "\n" for l in body if l[:1] in (" ", "-"))
        new = "".join(l[1:] + "\n" for l in body if l[:1] in (" ", "+"))
        removed = [l[1:] for l in body if l.startswith("-")]
        added = [l[1:] for l in body if l.startswith("+")]
        if path in changes:
            raise AssertionError("Duplicate patch target")
        changes[path] = (old, new, removed, added)
    if changes.keys() != TARGETS.keys():
        raise AssertionError("Patch must correct exactly the four audited files")
    return changes


def target_row(text, path):
    marker = TARGETS[path][0]
    rows = [line for line in text.splitlines()
            if (line.startswith(marker) if marker.startswith("|")
                else line.startswith("| ") and marker in line)]
    if path == "docs/BLUEPRINT.md":
        rows = [line for line in rows if "| 다음 R2 작업 |" in line]
    if len(rows) != 1:
        raise AssertionError(f"{path}: expected exactly one audited row, got {len(rows)}")
    return rows[0]


class RulingDocumentation(unittest.TestCase):
    def setUp(self):
        source = (ROOT / "docs/decisions/DEC-D-04.md").read_text(encoding="utf-8")
        self.owner = re.search(r"\| decided_by \| ([^ (]+)", source).group(1)
        self.decided_at = re.search(
            r"\| time \(`decided_at`\) \| ([^|]+) \|", source).group(1).strip()
        self.assertIn("R2 토큰 폐기만 수행하지 않는다", source)
        self.changes = patch_changes()

    def assert_corrected(self, text, path):
        row = target_row(text, path)
        cells = [c.strip() for c in row.strip("|").split("|")]
        self.assertEqual(TARGETS[path][2], len(cells), path)
        for required in (f"[DEC-D-04]({TARGETS[path][1]})", self.owner,
                         self.decided_at, "폐기하지 않는다", "재사용·출력 금지"):
            self.assertIn(required, row, path)
        self.assertNotIn("폐기 전", row, path)
        self.assertNotIn("폐기·범위 제한 토큰 재발급", row, path)
        self.assertIn("D-04", row, path)
        self.assertIn("관문", row, path)
        if path.endswith("DECISIONS.md"):
            for preserved in ("58키", "61키", "바이트 일치", "버킷 잠금(O14)", "실제 R2 접근은 계속 차단"):
                self.assertIn(preserved, row)
        elif path == "docs/BLUEPRINT.md":
            self.assertEqual("다음 R2 작업", cells[1])
            self.assertIn("실제 R2 접근 차단 유지", row)
            self.assertIn("O14·O17은 별도 관문", row)
        elif path.endswith("03_작업명세.md"):
            self.assertEqual(["T-OP-04", "T-DT-01, T-OP-02, T-DT-04", "—", "—"], cells[1:5])
            self.assertIn("real_data_allowed = false", cells[5])
        else:
            self.assertIn("T-OP-04 시작 불가", row)
            cfut_rows = [l for l in text.splitlines()
                         if l.startswith("| 대화에 노출된 `cfut_` 토큰 |")]
            self.assertEqual(1, len(cfut_rows))
            cfut = cfut_rows[0]
            for required in ("사용자가 폐기", "재사용·출력 금지", "폐기 전까지 T-OP-04는 시작 불가", "D-04"):
                self.assertIn(required, cfut)
            self.assertNotIn("폐기하지 않는다", cfut)

    def assert_state(self, text, path):
        old, _, removed, _ = self.changes[path]
        row = target_row(text, path)
        self.assertEqual(1, len(removed))
        if row == removed[0]:
            self.assertEqual(1, text.count(old), f"{path}: pending patch context drifted")
            return "pending"
        self.assert_corrected(text, path)
        return "corrected"

    def test_live_rows_are_exact_pending_or_corrected(self):
        # Passing pending checks prove applicability, never acceptance closure.
        for path in TARGETS:
            with self.subTest(path=path):
                self.assertIn(self.assert_state((ROOT / path).read_text(encoding="utf-8"), path),
                              ("pending", "corrected"))

    def test_patch_applies_to_copies_and_corrected_live_checks_pass(self):
        # Exercise the same checks after a real git apply, without writing sources.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp)
            for path, (old, new, _, _) in self.changes.items():
                text = (ROOT / path).read_text(encoding="utf-8")
                if self.assert_state(text, path) == "corrected":
                    self.assertEqual(1, text.count(new))
                    text = text.replace(new, old, 1)
                target = fixture / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                self.assertEqual("pending", self.assert_state(text, path))
            result = subprocess.run(["git", "apply", str(REVIEW.with_suffix(".patch"))],
                                    cwd=fixture, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for path in TARGETS:
                with self.subTest(path=path):
                    self.assertEqual("corrected", self.assert_state(
                        (fixture / path).read_text(encoding="utf-8"), path))

    def test_other_wording_duplicates_and_ruling_drift_fail(self):
        for path, (_, new, removed, _) in self.changes.items():
            with self.subTest(path=path):
                row = target_row(new, path)
                mutations = [
                    new.replace(row, removed[0] + " changed", 1),
                    new + row + "\n",
                    new.replace(self.owner, "미지정"),
                    new.replace(self.decided_at, "날짜 미지정"),
                    new.replace("폐기하지 않는다", "폐기한다"),
                    new.replace("재사용·출력 금지", "재사용 허용"),
                    new.replace("[DEC-D-04]", "[다른 결정]"),
                ]
                if path.endswith("05_VM실행준비.md"):
                    mutations.append("\n".join(l for l in new.splitlines() if "`cfut_`" not in l))
                for mutation in mutations:
                    with self.assertRaises(AssertionError):
                        self.assert_state(mutation, path)

    def test_proposal_rows_match_patch_and_link_actual_owner_record(self):
        text = REVIEW.read_text(encoding="utf-8")
        for path, (_, new, _, added) in self.changes.items():
            with self.subTest(path=path):
                self.assert_corrected(new, path)
                for row in added:
                    relative_row = row.replace(TARGETS[path][1], "../decisions/DEC-D-04.md")
                    self.assertIn(relative_row, text)
                self.assertTrue((ROOT / path).is_file())

    def test_readme_links_evidence_without_requiring_pending_status(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"]({REVIEW.relative_to(ROOT).as_posix()})", readme)
        text = REVIEW.read_text(encoding="utf-8")
        self.assertIn("실제 수집·R2 대조·제품 완료 증거가 아니며", text)
        self.assertIn(f"]({REVIEW.with_suffix('.patch').name})", text)


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
