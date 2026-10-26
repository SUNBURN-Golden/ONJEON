"""audit1-ux-layer-zero-code: the decision record must match the repo and the task graph.

Checks that each P15-P19 paragraph follows the 09 product-purpose row of the same
number (evidence test IDs, implementation tasks), that P18's evidence has
owners (DEC-D-16 U7, T-MB-02 condition-labels-factual), and that no view-model
schema carries a score or rank property.
Checks the scaffold claim against apps/mobile, that T-CT-08 owns the Amount
evidence_kind/applicability contract work (with its rejection test) and gates
T-AP-02, and that the record's "optional, not yet enforced" claim about Amount
matches common.schema.json today (and flips once T-CT-08 lands).
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
DECISION = ROOT / "docs/decisions/audit1-ux-layer-zero-code.md"
COMMON = ROOT / "packages/schemas/json/common.schema.json"
VOCAB = ROOT / "packages/schemas/vocabulary.json"
AXES = ("evidence_kind", "applicability")
PENDING = "x-onjeon-pending-axis"
PURPOSE = BUNDLE / "09_제품목적_대응표.md"
SCHEMA_DIR = ROOT / "packages/schemas/json"
TASK_ID = re.compile(r"T-[A-Z]{2}-\d{2}")


def load_tasks():
    data = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
    return data, {t["id"]: t for t in data["tasks"]}


def amount_def():
    return json.loads(COMMON.read_text(encoding="utf-8"))["$defs"]["Amount"]


def vocab_values(axis):
    for a in json.loads(VOCAB.read_text(encoding="utf-8"))["axes"]:
        if a["id"] == axis:
            return {v["code"] if isinstance(v, dict) else v for v in a.get("values", [])}
    return None


def accepts_amount_fields(amount, doc):
    """Field-level check of an Amount document against the schema's required list and
    each axis property. True when the schema would let the axis fields through."""
    if any(f not in doc for f in amount.get("required", [])):
        return False
    for axis in AXES:
        if axis not in doc:
            continue
        prop = amount["properties"][axis]
        if "$ref" in prop:
            allowed = vocab_values(prop["$ref"].rsplit("/", 1)[-1])
            if allowed is None or doc[axis] not in allowed:
                return False
        elif not re.fullmatch(prop.get("pattern", ".*"), doc[axis]):
            return False
    return True


def contract_complete(amount):
    return all(PENDING not in amount["properties"][a] and a in amount.get("required", []) for a in AXES)


def table_row(text, tid):
    rows = [l for l in text.splitlines() if l.startswith(f"| {tid} | ") and "| S" in l]
    return rows[0] if rows else None


class DecisionMatchesRepo(unittest.TestCase):
    def setUp(self):
        self.text = DECISION.read_text(encoding="utf-8")
        self.data, self.tasks = load_tasks()

    def test_scaffold_claim_matches_apps_mobile(self):
        mobile = ROOT / "apps/mobile"
        self.assertTrue((mobile / "pubspec.yaml").is_file())
        self.assertIn("apps/mobile/pubspec.yaml", self.text)
        self.assertNotIn("No code for P15-P19 is expected", self.text)
        self.assertTrue((mobile / "lib/states").is_dir())
        log = (mobile / "evidence/test.log").read_text(encoding="utf-8")
        m = re.search(r"\+(\d+): All tests passed!", log)
        self.assertIsNotNone(m, "recorded flutter test run must have passed")
        self.assertIn(f"{m.group(1)} passing tests", self.text)
        # the record must still list what the scaffold lacks
        for gap in ("no API integration", "capture catalog", "docs/ux-tests/"):
            self.assertIn(gap, self.text)
        self.assertFalse((ROOT / "apps/web").exists(), "record says apps/web does not exist")
        self.assertFalse((ROOT / "docs/ux-tests").exists(), "record says there is no docs/ux-tests/")

    def test_d16_is_recorded(self):
        self.assertTrue((ROOT / "docs/decisions/DEC-D-16.md").is_file())
        self.assertEqual(["D-16"], self.tasks["T-UX-01"]["decision_gates"]["start"])

    def test_record_does_not_call_the_contract_settled(self):
        self.assertNotIn("already fixed ahead of screen work", self.text)
        self.assertIn("not complete", self.text)
        self.assertIn("T-CT-08", self.text)


def purpose_rows():
    """09 §4 rows P15-P19 as {row: (purpose, tasks, bold test IDs, evidence text)}."""
    rows = {}
    for line in PURPOSE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] in {f"P{i}" for i in range(15, 20)}:
            rows[cells[0]] = (cells[1], TASK_ID.findall(cells[6]),
                              re.findall(r"\*\*`([a-z0-9-]+)`\*\*", cells[7]), cells[7])
    return rows


def decision_paragraph(text, row):
    found = [l for l in text.splitlines() if re.match(rf"\(\d\) \*\*{row} ", l)]
    return found[0] if len(found) == 1 else None


def schema_property_names():
    names = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "properties" and isinstance(value, dict):
                    names.update(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in SCHEMA_DIR.glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return names


class PurposeRowsFollow09(unittest.TestCase):
    """Each P15-P19 paragraph must be the 09 row of that number, not the finding title's labels."""

    def setUp(self):
        self.text = DECISION.read_text(encoding="utf-8")
        self.rows = purpose_rows()
        self.data, self.tasks = load_tasks()

    def test_all_five_rows_parsed(self):
        self.assertEqual({f"P{i}" for i in range(15, 20)}, set(self.rows))
        self.assertEqual(["decisive-conditions-not-hidden"], self.rows["P16"][2])
        self.assertEqual(["no-composite-score"], self.rows["P17"][2])
        self.assertIn("설명과 원문 대조", self.rows["P18"][3])

    def test_each_paragraph_names_its_rows_evidence_and_tasks(self):
        for row, (_purpose, tasks, test_ids, _evidence) in self.rows.items():
            para = decision_paragraph(self.text, row)
            self.assertIsNotNone(para, f"{row} needs exactly one numbered paragraph")
            self.assertIn(f"Tasks: {', '.join(tasks)}.", para, row)
            self.assertIn("Outstanding:", para, row)
            for test_id in test_ids:
                self.assertIn(f"**`{test_id}`**", para, row)
                owners = [t for t in tasks if test_id in self.tasks[t].get("required_test_ids", [])]
                self.assertTrue(owners, f"{row}: {test_id} is not registered in any of {tasks}")

    def test_title_labels_are_not_used_as_rows(self):
        for wrong in ("**P16 web", "**P17 state catalog", "**P19 user comprehension"):
            self.assertNotIn(wrong, self.text)
        self.assertIn("Web is not one of the five rows", self.text)

    def test_p18_explanation_versus_source_is_owned_by_d16_and_t_ux_01(self):
        dec = (ROOT / "docs/decisions/DEC-D-16.md").read_text(encoding="utf-8")
        self.assertIn("1) Seven tasks.", dec)
        self.assertIn("The seventh is U7, check a planner's explanation against the source", dec)
        self.assertIn("U4, U6 and U7 need 90% or more", dec)
        ux = self.tasks["T-UX-01"]
        self.assertTrue(any("U7" in c and "09 P18" in c for c in ux["done_criteria"]))
        # T-UX-01 cannot add the task itself, which is why this node had to
        self.assertIn("docs/decisions/**", ux["forbidden_paths"])
        self.assertIn("U7", decision_paragraph(self.text, "P18"))

    def test_p18_factual_label_capture_is_owned_by_t_mb_02(self):
        self.assertIn("평가어 없이 사실 라벨", self.rows["P18"][3])
        mb = self.tasks["T-MB-02"]
        self.assertIn("condition-labels-factual", mb["required_test_ids"])
        self.assertTrue(any(t.startswith("시험 condition-labels-factual(09 P18)") for t in mb["tests"]))
        self.assertTrue(any("사실 라벨" in c and "09 P18" in c for c in mb["done_criteria"]))
        row = table_row((BUNDLE / "03_작업명세.md").read_text(encoding="utf-8"), "T-MB-02")
        self.assertIsNotNone(row)
        spec = (BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        self.assertIn("| decisive-conditions-not-hidden, condition-labels-factual |", spec)
        self.assertIn("**`condition-labels-factual`**", decision_paragraph(self.text, "P18"))

    def test_no_row_claims_evidence_that_does_not_exist(self):
        # "None of the five rows has its completion evidence yet": no feature screens, no study
        self.assertIn("None of the five rows has its completion evidence yet", self.text)
        self.assertFalse((ROOT / "apps/mobile/lib/features").exists())
        self.assertFalse((ROOT / "docs/ux-tests").exists())

    def test_no_composite_score_field_in_view_model_schemas(self):
        names = schema_property_names()
        self.assertGreater(len(names), 50, "schema walk found too few properties")
        bad = sorted(n for n in names if re.search(r"score|rank", n, re.I))
        self.assertEqual([], bad)
        self.assertIn("no schema under `packages/schemas/json/` defines a score or rank property",
                      decision_paragraph(self.text, "P17"))


class FollowUpTask(unittest.TestCase):
    def setUp(self):
        self.data, self.tasks = load_tasks()
        self.t = self.tasks.get("T-CT-08")
        self.assertIsNotNone(self.t, "T-CT-08 must exist in tasks.json")

    def test_owns_vocabulary_and_schema_paths(self):
        allowed = self.t["allowed_paths"]
        for path in ("packages/schemas/vocabulary.json", "docs/blueprint/VOCABULARY.md", "packages/schemas/json/**"):
            self.assertIn(path, allowed)
            self.assertNotIn(path, self.t["forbidden_paths"])

    def test_canon_change_needs_approval_like_t_ct_02(self):
        cc = self.t["canon_change"]
        self.assertTrue(cc["required"])
        self.assertEqual(self.tasks["T-CT-02"]["canon_change"]["approval"]["scope_paths"], cc["approval"]["scope_paths"])
        self.assertTrue(any("canon_change_approval" in c for c in self.t["done_criteria"]))

    def test_requires_fields_and_rejection_test(self):
        tests = " ".join(self.t["tests"])
        self.assertIn("amount-evidence-axes-required", tests)
        self.assertIn("cargo test -p onjeon-contracts", tests)
        done = " ".join(self.t["done_criteria"])
        for axis in AXES:
            self.assertIn(f"Amount.{axis}", done)
        self.assertIn("required", done)
        self.assertIn("거부", done)

    def test_prereqs_are_the_contract_baseline(self):
        self.assertEqual(["T-CT-01", "T-CT-02", "T-CT-03"], self.t["prereq_tasks"])

    def test_t_ap_02_waits_for_t_ct_08_and_cannot_do_it_itself(self):
        ap = self.tasks["T-AP-02"]
        self.assertIn("T-CT-08", ap["prereq_tasks"])
        self.assertIn("packages/schemas/vocabulary.json", ap["forbidden_paths"])
        self.assertFalse(any(p.startswith("packages/schemas") for p in ap["allowed_paths"]))
        self.assertTrue(any("evidence_kind" in c and "applicability" in c for c in ap["done_criteria"]))
        # T-MB-02 reaches T-CT-08 through T-AP-02
        self.assertIn("T-AP-02", self.tasks["T-MB-02"]["prereq_tasks"])

    def test_feature_registry_lists_t_ct_08(self):
        for f in self.data["feature_registry"]:
            if f["id"] in ("coverage-detail", "evidence-view"):
                self.assertIn("T-CT-08", f["tasks"], f["id"])
                self.assertIn(f["id"], self.t["features"])

    def test_work_spec_tables_match_tasks_json(self):
        spec = (BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        for tid in ("T-CT-08", "T-AP-02"):
            row = table_row(spec, tid)
            self.assertIsNotNone(row, tid)
            self.assertIn(f"| {', '.join(self.tasks[tid]['prereq_tasks'])} |", row)
        self.assertIn("| T-CT-08 | schema:Amount.evidence_kind", spec)
        n = len(self.data["tasks"])
        self.assertIn(f"과제 {n}개", (BUNDLE / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"과제는 {n}개다", spec)


class AmountContractState(unittest.TestCase):
    """The record says the two axes are optional and accept invented values until T-CT-08."""

    def setUp(self):
        self.amount = amount_def()
        self.base = {"krw": 1, "source": "x"}

    def test_state_matches_record(self):
        missing = dict(self.base)
        invented = dict(self.base, evidence_kind="invented", applicability="invented")
        if contract_complete(self.amount):
            self.assertFalse(accepts_amount_fields(self.amount, missing))
            self.assertFalse(accepts_amount_fields(self.amount, invented))
        else:
            # read-only evidence of the gap the record documents; T-CT-08 must flip this
            self.assertTrue(accepts_amount_fields(self.amount, missing))
            self.assertTrue(accepts_amount_fields(self.amount, invented))
            for axis in AXES:
                self.assertEqual(axis, self.amount["properties"][axis].get(PENDING))
            text = DECISION.read_text(encoding="utf-8")
            self.assertIn("optional `x-onjeon-pending-axis` strings", text)
            self.assertIn("`invented`", text)

    def test_helper_rejects_against_a_completed_contract(self):
        # self-test: a schema shaped like T-CT-08's target rejects both documents
        done = {"required": ["krw", "source", *AXES],
                "properties": {a: {"$ref": f"vocabulary.schema.json#/$defs/{a}"} for a in AXES}}
        self.assertTrue(contract_complete(done))
        self.assertFalse(accepts_amount_fields(done, dict(self.base)))
        self.assertFalse(accepts_amount_fields(done, dict(self.base, evidence_kind="invented", applicability="invented")))


if __name__ == "__main__":
    unittest.main()
