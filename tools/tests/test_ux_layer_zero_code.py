"""audit1-ux-layer-zero-code: the decision record must match the repo and the task graph.

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
