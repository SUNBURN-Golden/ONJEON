"""Audit 6: current implementation inventory must stay separate from gate evidence."""
import csv
import importlib.util
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = "blueprint/audits/2026-11-16_blueprint_s11_current_state.md"


def section(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


def table_rows(text):
    return {
        cells[0]: cells[1:]
        for line in text.splitlines() if line.startswith("| ")
        if (cells := [cell.strip() for cell in line.strip().strip("|").split("|")])
    }


def registry_rows(name):
    with (ROOT / "data/registry" / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class CurrentState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        cls.milestones = section(cls.text, "### 9.2 마일스톤", "### 9.3")
        cls.inventory = section(cls.text, "## 11.", "## 12.")
        cls.rows = table_rows(cls.milestones)

    def test_each_milestone_separates_criteria_from_current_verdict(self):
        self.assertEqual(self.rows["ID"][-1], "현재 구현·판정(§11 기준일)")
        for mid in ("M0", "V0", "V1", *[f"M{i}" for i in range(1, 7)]):
            with self.subTest(milestone=mid):
                self.assertEqual(len(self.rows[mid]), 4)
                current = self.rows[mid][-1]
                self.assertIn("완료" if mid in ("M0", "V0") else "관문 미통과", current)
        self.assertIn("기관", self.rows["V0"][-1])
        self.assertIn("초기 관측과 전체 분모 판정은 M3", self.rows["V0"][-1])

    def test_m1_reports_generated_contracts_and_review_schema_limits(self):
        current = self.rows["M1"][-1]
        for source in ("packages/schemas/codegen/generated/", "infra/db/"):
            self.assertTrue((ROOT / source).is_dir())
            self.assertIn(source, current)
        for term in ("Rust·Dart·TS", "검토본", "I7", "I12", "미승격"):
            self.assertIn(term, current)
        db = table_rows(self.inventory)["DB·실행 환경"][0]
        for source in ("infra/db/", "infra/compose/"):
            self.assertTrue((ROOT / source).is_dir())
            self.assertIn(source, db)
        self.assertIn("검토본", db)

    def test_m2_reports_components_without_claiming_an_end_to_end_service(self):
        current = self.rows["M2"][-1]
        for source in ("services/collect/", "services/docproc/", "packages/ontology/",
                       "packages/twin-runtime/"):
            self.assertTrue((ROOT / source).is_dir())
            self.assertIn(source, current)
        for term in ("L1~L9", "I6", "hold", "그림자 비교", "미완료"):
            self.assertIn(term, current)

    def test_v1_preserves_historical_observation_and_remaining_conditions(self):
        v1 = " ".join(self.rows["V1"])
        for term in ("2026-10-09", "8/14", "6건", "S1·S6", "이종 계열", "관문 미통과"):
            self.assertIn(term, v1)
        self.assertIn("audit2-v1-gate-closure.md", v1)

    def test_future_milestones_keep_actual_data_and_screen_gates_open(self):
        expected = {"M3": ("O19", "초기 실행", "전체 분모", "/coverage", "I17"), "M4": ("I7", "I8"),
                    "M5": ("PDF", "두 안 비교"), "M6": ("T-OP-08", "P01~P19")}
        for mid, terms in expected.items():
            for term in terms:
                with self.subTest(milestone=mid, term=term):
                    self.assertIn(term, self.rows[mid][-1])
        self.assertIn("실제 제공자 어댑터 없음", self.inventory)
        self.assertIn("서비스 API·공개 웹의 출시 구현은 없다", self.inventory)

    def test_data_row_registry_counts_match_the_committed_csvs(self):
        row = table_rows(self.inventory)["데이터"][0]
        stated = re.search(r"보험사 (\d+), 공제 등 (\d+).*?제외·과거 (\d+), 근거 (\d+)", row)
        self.assertIsNotNone(stated, "§11 데이터 행 must state the four registry counts")
        for name, count in zip(("insurers", "cooperatives_and_others",
                                "excluded_or_historical", "sources"), stated.groups()):
            with self.subTest(csv=name):
                self.assertEqual(int(count), len(registry_rows(name)),
                                 f"§11 {name} count is stale against data/registry/{name}.csv")

    def test_source_total_accounts_for_every_dated_observation(self):
        row = table_rows(self.inventory)["데이터"][0]
        self.assertIn("data/registry/sources.csv", row)
        stated = re.search(
            r"근거 (\d+)\(2026-10-09 1차 조사 (\d+)건 \+ 2026-11-10 감독당국 재조회 (\d+)건", row)
        self.assertIsNotNone(stated, "§11 must break the source total into dated observations")
        total, first, recheck = map(int, stated.groups())
        dates = Counter(r["retrieved_at"][:10] for r in registry_rows("sources"))
        self.assertEqual(total, sum(dates.values()))
        self.assertEqual(first, dates["2026-10-09"])
        self.assertEqual(recheck, dates["2026-11-10"])
        self.assertEqual(first + recheck, total,
                         "every sources.csv record must belong to a stated observation date")

    def test_documented_release_counts_match_live_checker_not_test_registrations(self):
        path = ROOT / "tools/release_readiness/check.py"
        spec = importlib.util.spec_from_file_location("blueprint_readiness", path)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        report = checker.check(checker.BUNDLE / "tasks.json", checker.PURPOSE,
                               ROOT / "docs/release-readiness/evidence")
        row = table_rows(self.inventory)["출시 증거"][0]
        counts = re.search(r"P행 open=(\d+)·closed=(\d+)·excluded=(\d+), 기능 open=(\d+)·closed=(\d+)·excluded=(\d+)", row)
        self.assertIsNotNone(counts, "§11 must report the observed readiness inventory")
        actual = tuple(report[group + "_counts"][state]
                       for group in ("rows", "features")
                       for state in ("open", "closed", "excluded"))
        self.assertEqual(tuple(map(int, counts.groups())), actual)
        for term in ("tools/release_readiness/check.py", "readiness.json", "완료 증거", "출시 승인"):
            self.assertIn(term, row)
        self.assertIn("docs/release-readiness/evidence/", self.rows["M6"][-1])

    def test_current_review_links_evidence_and_existing_source_paths(self):
        self.assertIn(AUDIT, self.milestones)
        self.assertIn(AUDIT, self.inventory)
        self.assertTrue((ROOT / "docs" / AUDIT).is_file())
        for source in re.findall(r"`((?:packages|services|apps|infra|tools)/[^` ]+)`",
                                 self.milestones + self.inventory):
            if "*" not in source:
                with self.subTest(source=source):
                    self.assertTrue((ROOT / source).exists(), source)


if __name__ == "__main__":
    unittest.main()
