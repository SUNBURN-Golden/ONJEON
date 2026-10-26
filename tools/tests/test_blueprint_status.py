"""§11 freshness: exercise added, edited, removed and renamed ADR/DEC records."""
import contextlib
import datetime as dt
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import blueprint_status as status

TODAY = dt.date(2026, 10, 26)
DOCUMENT = """# Blueprint
## 10. 드리프트 방지 규칙
keep rules
## 11. 현재 위치 (2026-10-09)

| 항목 | 상태 |
|---|---|
| 코드 | reviewed status |

## 12. 열린 결정
keep gates
"""


class Freshness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "docs/decisions"
        self.directory.mkdir(parents=True)
        for name in ("ADR-0001-범위.md", "DEC-D-02.md"):
            (self.directory / name).write_text("record\n", encoding="utf-8")
        self.records = status.decision_records(self.root)
        self.fresh = status.refresh(DOCUMENT, self.records, TODAY)

    def test_missing_snapshot_fails(self):
        self.assertTrue(status.check(DOCUMENT, self.records, TODAY))

    def test_refresh_checks_clean_and_stamps_both_dates(self):
        self.assertEqual(status.check(self.fresh, self.records, TODAY), [])
        self.assertIn("## 11. 현재 위치 (2026-10-26)", self.fresh)
        self.assertIn("결정 기록 대조일: 2026-10-26", self.fresh)
        self.assertIn("[ADR-0001-범위](decisions/ADR-0001-범위.md)", self.fresh)
        self.assertIn("[DEC-D-02](decisions/DEC-D-02.md)", self.fresh)

    def test_refresh_preserves_status_rows_other_sections_and_is_idempotent(self):
        self.assertIn("| 코드 | reviewed status |", self.fresh)
        self.assertEqual(self.fresh.split("## 11.")[0], DOCUMENT.split("## 11.")[0])
        self.assertEqual(self.fresh.split("## 12.")[1], DOCUMENT.split("## 12.")[1])
        self.assertEqual(status.refresh(self.fresh, self.records, TODAY), self.fresh)

    def test_each_record_mutation_requires_refresh_for_both_kinds(self):
        for name in ("ADR-0001-범위.md", "DEC-D-02.md"):
            for action in ("add", "edit", "delete", "rename"):
                with self.subTest(name=name, action=action):
                    path = self.directory / name
                    new = self.directory / name.replace(".md", "-new.md")
                    if action == "add":
                        new.write_text("new record", encoding="utf-8")
                    elif action == "edit":
                        path.write_text("changed decision", encoding="utf-8")
                    elif action == "delete":
                        # Keep one file of this kind so empty inventories fail separately.
                        new.write_text("other record", encoding="utf-8")
                        before = status.decision_records(self.root)
                        self.fresh = status.refresh(DOCUMENT, before, TODAY)
                        path.unlink()
                    else:
                        path.rename(new)
                    records = status.decision_records(self.root)
                    self.assertTrue(status.check(self.fresh, records, TODAY))
                    updated = status.refresh(self.fresh, records, TODAY)
                    self.assertEqual(status.check(updated, records, TODAY), [])
                    if new.exists():
                        new.unlink()
                    path.write_text("record\n", encoding="utf-8")
                    self.fresh = status.refresh(DOCUMENT, self.records, TODAY)

    def test_same_day_edit_is_detected_and_next_day_refresh_restamps(self):
        (self.directory / "DEC-D-02.md").write_text("edited twice today", encoding="utf-8")
        records = status.decision_records(self.root)
        self.assertTrue(status.check(self.fresh, records, TODAY))
        tomorrow = TODAY + dt.timedelta(days=1)
        updated = status.refresh(self.fresh, records, tomorrow)
        self.assertIn("## 11. 현재 위치 (2026-10-27)", updated)
        self.assertEqual(status.check(updated, records, tomorrow), [])

    def test_historical_snapshot_does_not_expire_without_record_changes(self):
        self.assertEqual(status.check(self.fresh, self.records, TODAY + dt.timedelta(days=7)), [])

    def test_invalid_future_or_mismatched_dates_fail(self):
        for text in (self.fresh.replace("2026-10-26", "2026-02-30"),
                     self.fresh.replace("2026-10-26", "2026-10-27"),
                     self.fresh.replace("위치 (2026-10-26)", "위치 (2026-10-25)")):
            with self.subTest(text=text[:60]):
                self.assertTrue(status.check(text, self.records, TODAY))

    def test_missing_duplicate_reversed_or_outside_markers_fail(self):
        for text in (self.fresh.replace(status.END, ""),
                     self.fresh.replace(status.START, status.START * 2),
                     self.fresh.replace(status.START, "TEMP").replace(status.END, status.START)
                     .replace("TEMP", status.END),
                     DOCUMENT + status.render_index(self.records, TODAY.isoformat())):
            with self.subTest(text=text[-60:]):
                self.assertTrue(status.check(text, self.records, TODAY))
                with self.assertRaises(ValueError):
                    status.refresh(text, self.records, TODAY)

    def test_missing_or_duplicate_heading_fails(self):
        for text in ("no section", self.fresh + "\n## 11. 현재 위치 (2026-10-26)\n"):
            self.assertTrue(status.check(text, self.records, TODAY))
            with self.assertRaises(ValueError):
                status.refresh(text, self.records, TODAY)

    def test_index_cannot_be_edited_independently(self):
        self.assertTrue(status.check(self.fresh.replace("DEC (1)", "DEC (99)"),
                                     self.records, TODAY))

    def test_unrelated_files_do_not_invalidate_snapshot(self):
        (self.directory / "README.md").write_text("index", encoding="utf-8")
        self.assertEqual(status.decision_records(self.root), self.records)

    def test_empty_or_missing_record_kind_fails_closed(self):
        (self.directory / "DEC-D-02.md").unlink()
        with self.assertRaisesRegex(ValueError, "no DEC"):
            status.decision_records(self.root)
        (self.directory / "ADR-0001-범위.md").unlink()
        with self.assertRaisesRegex(ValueError, "no ADR"):
            status.decision_records(self.root)

    def invoke(self, *args):
        output = io.StringIO()
        with patch.object(status, "ROOT", self.root), patch.object(sys, "argv", ["status", *args]), \
                contextlib.redirect_stdout(output):
            result = status.main()
        return result, output.getvalue()

    def test_cli_stale_check_does_not_write_and_returns_one(self):
        path = self.root / "docs/BLUEPRINT.md"
        path.write_text(DOCUMENT, encoding="utf-8")
        code, output = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn("--write", output)
        self.assertEqual(path.read_text(encoding="utf-8"), DOCUMENT)

    def test_cli_write_then_check_succeeds_without_other_file_changes(self):
        path = self.root / "docs/BLUEPRINT.md"
        path.write_text(DOCUMENT, encoding="utf-8")
        self.assertEqual(self.invoke("--write")[0], 0)
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(status.decision_records(self.root), self.records)
        self.assertIn(dt.datetime.now(dt.timezone.utc).date().isoformat(),
                      path.read_text(encoding="utf-8"))

    def test_cli_unreadable_input_returns_two(self):
        code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("BLUEPRINT-S11", output)

    def test_cli_write_refuses_malformed_input(self):
        path = self.root / "docs/BLUEPRINT.md"
        path.write_text("missing section", encoding="utf-8")
        self.assertEqual(self.invoke("--write")[0], 2)
        self.assertEqual(path.read_text(encoding="utf-8"), "missing section")


class Repository(unittest.TestCase):
    def test_live_blueprint_matches_all_decision_records(self):
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        self.assertEqual(status.check(blueprint, status.decision_records(ROOT),
                                      dt.datetime.now(dt.timezone.utc).date()), [])

    def test_current_status_mentions_new_tools_and_preserves_release_gate(self):
        _, body = status.section((ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8"))
        for text in ("tools/daemon/", "tools/r2_budget.py", "tools/registry_normalize.py",
                     "09_제품목적_대응표", "완료 증거", "D-04", "O14", "O17",
                     "개발 도구", "가동 승인"):
            with self.subTest(text=text):
                self.assertIn(text, body)


if __name__ == "__main__":
    unittest.main()
