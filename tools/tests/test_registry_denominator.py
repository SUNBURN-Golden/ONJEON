"""Repository registry denominators and the O19 domestic-IP gate (audit1-product-list-denominator-start).

Reads data/registry and the task bundle read-only; normalization runs on a temporary copy.
"""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import registry_normalize as rn

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "data/registry"
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
ACQUISITION = {x["code"] for x in rn.axis("acquisition_status")["values"]}


def rows(name):
    with (REG / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def codes(row):
    return row["product_list_reason_codes"].split(";") if row["product_list_reason_codes"] else []


class RegistryCounts(unittest.TestCase):
    def setUp(self):
        self.insurers = rows("insurers")

    def test_insurer_and_disclosure_entry_counts(self):
        self.assertEqual(len(self.insurers), 53)
        status = Counter(r["disclosure_status"] for r in self.insurers)
        self.assertEqual(status, Counter(failed=31, blocked=3, unqueried=19))
        reachable = [r for r in self.insurers if r["disclosure_url"].strip()
                     and r["disclosure_access"] == "reachable"]
        self.assertEqual(len(reachable), 8)
        self.assertEqual(sum(not r["disclosure_url"].strip() for r in self.insurers), 45)
        self.assertTrue(all(r["disclosure_status"] == "unqueried" for r in reachable))

    def test_no_product_list_is_enumerated_yet(self):
        self.assertEqual(Counter(r["product_list_status"] for r in self.insurers), Counter(unqueried=53))

    def test_reason_code_counts(self):
        per_code = Counter(c for r in self.insurers for c in codes(r))
        self.assertEqual(per_code, Counter({"awaiting_T-DT-04": 53, "awaiting_domestic_env": 53,
                                            "disclosure_entry_missing": 45, "foreign_sandbox_geo_blocked": 3}))


class RegistryConsistency(unittest.TestCase):
    TABLES = ("insurers", "cooperatives_and_others")

    def each(self):
        for name in self.TABLES:
            for r in rows(name):
                yield name, r

    def test_statuses_use_the_acquisition_axis(self):
        for name, r in self.each():
            with self.subTest(table=name, row=r["name_ko"]):
                self.assertIn(r["disclosure_status"], ACQUISITION)
                self.assertIn(r["product_list_status"], ACQUISITION)

    def test_unqueried_product_lists_carry_reason_and_known_codes(self):
        for name, r in self.each():
            if r["product_list_status"] != "unqueried":
                continue
            with self.subTest(table=name, row=r["name_ko"]):
                self.assertTrue(r["product_list_reason"].strip())
                got = codes(r)
                self.assertTrue(set(got) <= set(rn.PRODUCT_LIST_REASON_CODES), got)
                self.assertEqual(got[:2], ["awaiting_T-DT-04", "awaiting_domestic_env"])
                reachable = bool(r["disclosure_url"].strip()) and r["disclosure_access"] == "reachable"
                self.assertEqual("disclosure_entry_missing" in got, not reachable)
                geo = "geo_blocked" in (r["home_access"], r["disclosure_access"])
                self.assertEqual("foreign_sandbox_geo_blocked" in got, geo)

    def test_missing_entry_points_have_a_reason_and_are_never_not_disclosed(self):
        for name, r in self.each():
            with self.subTest(table=name, row=r["name_ko"]):
                self.assertNotEqual(r["disclosure_status"], "not_disclosed")
                self.assertNotEqual(r["disclosure_status"], "archived")
                self.assertTrue(r["disclosure_gap_reason"].strip())
                if r["disclosure_url"].strip() and r["disclosure_access"] == "reachable":
                    self.assertEqual(r["disclosure_status"], "unqueried")
                    self.assertIn("불변 보관 전", r["disclosure_gap_reason"])

    def test_committed_csvs_are_a_fixed_point_of_the_normalizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in self.TABLES:
                with self.subTest(table=name):
                    copy = Path(tmp) / f"{name}.csv"
                    shutil.copyfile(REG / f"{name}.csv", copy)
                    rn.normalize(copy)
                    self.assertEqual(copy.read_bytes(), (REG / f"{name}.csv").read_bytes())

    def test_repairs_exactly_eight_legacy_archived_rows_without_changing_evidence(self):
        # Recreate the audit finding on the actual 53-row registry, in isolation.
        affected_ids = {
            "life-aia", "life-bnpcardif", "life-chubb", "life-kyobo-lifeplanet",
            "nonlife-heungkuk", "nonlife-db", "nonlife-ace-chubb", "nonlife-mitsuisumitomo-kr",
        }
        legacy = rows("insurers")
        self.assertEqual(len(legacy), 53)
        reachable_ids = {r["insurer_id"] for r in legacy if rn.disclosure_entry_reachable(r)}
        self.assertEqual(reachable_ids, affected_ids)
        for r in legacy:
            if r["insurer_id"] in affected_ids:
                r["disclosure_status"] = "archived"
                r["disclosure_gap_reason"] = ""

        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "insurers.csv"
            with copy.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(legacy[0]))
                writer.writeheader()
                writer.writerows(legacy)
            self.assertEqual(rn.normalize(copy), 53)
            with copy.open(encoding="utf-8", newline="") as f:
                repaired = list(csv.DictReader(f))
            self.assertEqual(len(repaired), len(legacy))
            changed = {}
            for before, after in zip(legacy, repaired):
                fields = {key for key in before if before[key] != after[key]}
                if fields:
                    changed[before["insurer_id"]] = fields
                if before["insurer_id"] in affected_ids:
                    self.assertEqual(after["disclosure_status"], "unqueried")
                    self.assertIn("불변 보관 전", after["disclosure_gap_reason"])
            self.assertEqual(changed, {key: {"disclosure_status", "disclosure_gap_reason"}
                                       for key in affected_ids})
            canonical = (REG / "insurers.csv").read_bytes()
            self.assertEqual(copy.read_bytes(), canonical)
            rn.normalize(copy)
            self.assertEqual(copy.read_bytes(), canonical)


class ReasonCodeRule(unittest.TestCase):
    def test_codes_follow_disclosure_and_geo_state(self):
        base = dict(product_list_status="unqueried", home_access="reachable", disclosure_access="reachable")
        cases = [
            (dict(disclosure_status="unqueried", disclosure_url="https://example.invalid"),
             "awaiting_T-DT-04;awaiting_domestic_env"),
            (dict(disclosure_status="archived", disclosure_url=""),
             "awaiting_T-DT-04;awaiting_domestic_env;disclosure_entry_missing"),
            (dict(disclosure_status="unqueried", disclosure_url="  "),
             "awaiting_T-DT-04;awaiting_domestic_env;disclosure_entry_missing"),
            (dict(disclosure_status="blocked", disclosure_url="https://example.invalid",
                  disclosure_access="origin_denied"),
             "awaiting_T-DT-04;awaiting_domestic_env;disclosure_entry_missing"),
            (dict(disclosure_status="failed"), "awaiting_T-DT-04;awaiting_domestic_env;disclosure_entry_missing"),
            (dict(disclosure_status="blocked", home_access="geo_blocked"),
             "awaiting_T-DT-04;awaiting_domestic_env;disclosure_entry_missing;foreign_sandbox_geo_blocked"),
            (dict(disclosure_status="blocked", home_access="not_checked", disclosure_access="geo_blocked"),
             "awaiting_T-DT-04;awaiting_domestic_env;disclosure_entry_missing;foreign_sandbox_geo_blocked"),
        ]
        for extra, expected in cases:
            with self.subTest(extra=extra):
                self.assertEqual(rn.product_list_codes(dict(base, **extra)), expected)

    def test_enumerated_lists_keep_existing_codes(self):
        row = dict(product_list_status="archived", disclosure_status="failed", product_list_reason_codes="")
        self.assertEqual(rn.product_list_codes(row), "")
        self.assertEqual(rn.product_list_codes(dict(row, product_list_reason_codes="x")), "x")


class DomesticEnvironmentGate(unittest.TestCase):
    def setUp(self):
        tasks = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))["tasks"]
        self.task = next(t for t in tasks if t["id"] == "T-DT-04")
        self.tasks = tasks

    def test_t_dt_04_real_data_waits_for_d04_and_o19(self):
        self.assertEqual(self.task["decision_gates"]["real_data"], ["D-04", "O19"])
        self.assertEqual(self.task["decision_gates"]["start"], [])
        self.assertIn("O19", self.task["blocked_by"])
        self.assertIn("국내 IP", self.task["blocked_by"])
        self.assertIn("P01·P02", self.task["notes"])

    def test_o19_is_gated_only_on_t_dt_04_real_data(self):
        users = {(t["id"], k) for t in self.tasks for k, v in t["decision_gates"].items() if "O19" in (v or [])}
        self.assertEqual(users, {("T-DT-04", "real_data")})

    def test_o19_is_an_open_ledger_item_without_a_decision_record(self):
        ledger = (ROOT / "docs/blueprint/DECISIONS.md").read_text(encoding="utf-8")
        section = ledger.split("## 3. ", 1)[1].split("### 3.1 ", 1)[0]
        rows = [line for line in section.splitlines() if line.startswith("| O19 |")]
        self.assertEqual(len(rows), 1)
        self.assertIn("국내 IP", rows[0])
        self.assertIn("T-DT-04", rows[0])
        self.assertFalse((ROOT / "docs/decisions/DEC-O19.md").exists(), "O19 must stay open until the operator acts")
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        open_decisions = blueprint.split("## 12. ", 1)[1].split("## 13. ", 1)[0]
        self.assertIn("국내 IP 수집 실행 환경(O19)", open_decisions)

    def test_dec_o17_requires_a_domestic_designated_environment(self):
        text = (ROOT / "docs/decisions/DEC-O17.md").read_text(encoding="utf-8")
        addendum = text.split("**Addendum (2026-10-26", 1)[1].split("**Revisit if:**", 1)[0]
        for phrase in ("domestic-IP environment", "O19", "45 of the 53", "T-DT-04", "P01/P02"):
            self.assertIn(phrase, addendum)

    def test_blocking_tables_list_t_dt_04_under_o19(self):
        for doc in ("README.md", "03_작업명세.md"):
            with self.subTest(doc=doc):
                text = (BUNDLE / doc).read_text(encoding="utf-8")
                rows = [line for line in text.splitlines() if line.startswith("| O19 ")]
                self.assertEqual(len(rows), 1)
                cells = [c.strip() for c in rows[0].strip("|").split("|")]
                self.assertEqual(cells[1:5], ["—", "T-DT-04", "—", "—"])
        spec = (BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        self.assertIn("| T-DT-04 | 분모 열거 어댑터", spec)
        self.assertIn("| T-DT-01 | — / D-04, O19 / — / — |", spec)

    def test_registry_readme_states_counts_and_codes(self):
        text = (REG / "README.md").read_text(encoding="utf-8")
        self.assertIn("`archived` 0, `failed` 31, `blocked` 3, `unqueried` 19", text)
        self.assertIn("`reachable` 8", text)
        for code in rn.PRODUCT_LIST_REASON_CODES:
            self.assertIn(f"`{code}`", text)


if __name__ == "__main__":
    unittest.main()
