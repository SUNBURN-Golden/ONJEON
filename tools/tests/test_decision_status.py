"""Audit 8 regressions for decision records and generated status tables."""
import copy
import json
import re
import unittest
from pathlib import Path

from tools import decision_status as sync


class DecisionStatusSync(unittest.TestCase):
    def setUp(self):
        self.root = sync.ROOT
        self.registry = json.loads((self.root / sync.REGISTRY).read_text(encoding="utf-8"))
        self.index = self.registry["decision_index"]
        self.ledger = (self.root / sync.LEDGER).read_text(encoding="utf-8")
        self.purpose = (self.root / sync.PURPOSE).read_text(encoding="utf-8")
        self.record_names = {path.stem for path in (self.root / "docs/decisions").glob("DEC-*.md")}
        self.metadata = sync.ledger_metadata(self.ledger, self.record_names)

    def test_generated_outputs_match_committed_tables(self):
        for path, expected in sync.projections(self.root):
            with self.subTest(path=path):
                self.assertEqual((self.root / path).read_text(encoding="utf-8"), expected)

    def test_every_dec_record_and_actual_task_phase_has_an_index_entry(self):
        self.assertEqual(self.record_names, {
            Path(entry["record_ref"]).stem
            for entry in self.index.values() if entry["record_ref"]
        })
        for gate, entry in self.index.items():
            with self.subTest(gate=gate):
                self.assertEqual(set(entry), {"status", "decided_by", "record_ref", *sync.PHASES})
                for phase in sync.PHASES:
                    self.assertEqual(entry[phase], [
                        task["id"] for task in self.registry["tasks"]
                        if gate in task["decision_gates"][phase]
                    ])
        o19 = self.index["O19"]
        self.assertEqual((o19["status"], o19["decided_by"], o19["record_ref"]), ("open", None, None))
        self.assertEqual(o19["real_data"], ["T-DT-04"])

    def test_no_status_promotes_pending_or_provisional_records_to_owner_decisions(self):
        for gate in ("D-09", "D-10", "D-15", "O03"):
            with self.subTest(gate=gate):
                entry = self.index[gate]
                self.assertEqual(entry["status"], "scope_only" if gate == "O03" else "awaiting_audit")
                self.assertIsNone(entry["decided_by"])
                self.assertEqual(entry["record_ref"], f"docs/decisions/DEC-{gate}.md")
        for gate in ("D-02", "D-07", "D-08", "D-16", "O04", "O12"):
            with self.subTest(gate=gate):
                self.assertTrue(self.index[gate]["status"].startswith("provisional"))
                self.assertIn("Fable 5.1", self.index[gate]["decided_by"])

    def test_d12_is_scoped_to_app_and_still_has_its_release_assignments(self):
        for gate in ("D-12", "O16"):
            self.assertEqual(self.index[gate]["status"], "scope_resolved")
            self.assertEqual(self.index[gate]["decided_by"], "준태님(소유자)")
            self.assertEqual(self.index[gate]["record_ref"], "docs/decisions/DEC-D-12.md")
        self.assertEqual(self.index["D-12"]["release"], ["T-AP-02", "T-OP-07"])
        self.assertFalse(any(self.index["O16"][phase] for phase in sync.PHASES))
        summary = next(line for line in self.ledger.splitlines() if line.startswith("| [O16]("))
        self.assertIn("공개 저장소의 새 원문 발췌 추가·그 밖의 재배포 조건은 잔여", summary)

    def test_purpose_displays_task_gates_and_scope_decisions(self):
        rows = {}
        lines = self.purpose.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("| # |"):
                self.assertEqual(len(sync.table_cells(line)), len(sync.table_cells(lines[i + 1])))
            if re.match(r"^\| P\d{2} \|", line):
                cells = sync.table_cells(line)
                rows[cells[0]] = cells[-2]
        self.assertEqual(set(rows), {f"P{i:02}" for i in range(1, 21)})
        for purpose, phrases in {
            "P01": ("O19 ‒ 미정",),
            "P02": ("DEC-O02.md) ‒ 위임 결정", "DEC-D-18.md) ‒ 위임 결정"),
            "P03": ("DEC-D-14.md) ‒ 위임 결정",),
            "P04": ("DEC-O03.md) ‒ 범위만 기록·내용 미정",),
            "P14": ("[D-12](../../../decisions/DEC-D-12.md) ‒ 기록 범위 해결",
                    "[O16](../../../decisions/DEC-D-12.md) ‒ 기록 범위 해결"),
            "P19": ("DEC-D-15.md) ‒ 감리 대기·미승인", "DEC-D-16.md) ‒ 잠정 개발 기준"),
        }.items():
            for phrase in phrases:
                with self.subTest(purpose=purpose, phrase=phrase):
                    self.assertIn(phrase, rows[purpose])
        self.assertFalse(any("결정 대기" in cell for cell in rows.values()))

    def test_generating_09_replaces_only_the_status_cell(self):
        original = next(line for line in self.purpose.splitlines() if line.startswith("| P14 |"))
        cells = original.split("|")
        cells[-3] = " 결정 대기 "
        edited = self.purpose.replace(original, "|".join(cells))
        self.assertEqual(
            self.purpose, sync.render_purpose(edited, self.index, self.registry["tasks"])
        )

    def test_missing_or_misdirected_source_records_fail_generation(self):
        with self.assertRaisesRegex(ValueError, "missing DEC rows.*DEC-D-99"):
            sync.ledger_metadata(self.ledger, self.record_names | {"DEC-D-99"})
        bad_link = self.ledger.replace("[DEC-D-12](../decisions/DEC-D-12.md)",
                                       "[DEC-D-12](../decisions/DEC-D-04.md)")
        with self.assertRaisesRegex(ValueError, "invalid DEC reference"):
            sync.ledger_metadata(bad_link, self.record_names)

    def test_task_gate_changes_update_only_their_own_phase_and_require_metadata(self):
        tasks = copy.deepcopy(self.registry["tasks"])
        source = next(task for task in tasks if task["id"] == "T-DT-04")
        source["decision_gates"]["real_data"].remove("O19")
        source["decision_gates"]["merge"].append("O19")
        changed = sync.build_index(self.metadata, tasks)
        self.assertEqual(changed["O19"]["real_data"], [])
        self.assertEqual(changed["O19"]["merge"], ["T-DT-04"])
        source["decision_gates"]["release"].append("D-99")
        with self.assertRaisesRegex(ValueError, "T-DT-04 release: D-99"):
            sync.build_index(self.metadata, tasks)


if __name__ == "__main__":
    unittest.main()
