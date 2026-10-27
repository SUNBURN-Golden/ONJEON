"""audit2-spec-check-reads-prose-when: spec_check.py judges the daemon transitions by what the core reads.

G5b/G5c/G6b/G22/G33/G35/G44 searched the prose `when` text, which the daemon core never reads, so G22 passed on a
merged -> done row the core could not take (the cond-less sibling row always won). The checks now read the rows'
cond / guard / side_effects, and G35/G42 cover every lease-issuing row (issue_lease side effect, to leased, or
lease_granted), not only the rows into `leased`.

Every mutation works on an in-memory copy; the design bundle is not written.
"""
import copy
import importlib.util
import json
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
_spec = importlib.util.spec_from_file_location("spec_check", BUNDLE / "검증/spec_check.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

RULES = json.loads((BUNDLE / "daemon_rules.json").read_text(encoding="utf-8"))
TASKS = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
TARGET = ("G5b", "G5c", "G6b", "G22", "G33", "G35", "G42", "G44")


def results(D=None):
    sc.RESULTS.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)  # spec_check's other checks read files without closing them
        sc.run(str(ROOT), copy.deepcopy(TASKS), D if D is not None else copy.deepcopy(RULES))
    out = {r["check"].split(" ", 1)[0]: r for r in sc.RESULTS}
    sc.RESULTS.clear()
    return out


def rules():
    return copy.deepcopy(RULES)


def row(D, frm, event, to=None):
    rows = [t for t in D["transitions"] if t["from"] == frm and t["event"] == event and (to is None or t["to"] == to)]
    assert len(rows) == 1, (frm, event, to, len(rows))
    return rows[0]


def drop(r, field):
    r["cond"] = [p for p in r.get("cond") or [] if p.get("field") != field]


class Baseline(unittest.TestCase):
    def test_bundle_passes(self):
        res = results()
        self.assertEqual([k for k in TARGET if not res[k]["ok"]], [], {k: res[k]["detail"] for k in TARGET if not res[k]["ok"]})
        self.assertEqual([r for r in res.values() if not r["ok"]], [])

    def test_prose_is_not_read(self):
        """Blank every `when` of every transition: no target check changes (they read cond / guard / side_effects)."""
        D = rules()
        for t in D["transitions"]:
            t["when"] = ""
        res = results(D)
        self.assertEqual({k: res[k]["ok"] for k in TARGET}, {k: True for k in TARGET})

    def test_prose_alone_does_not_pass(self):
        """The when text still names every rule, but the conds are gone: each check fails."""
        D = rules()
        for t in D["transitions"]:
            if t["to"] in ("queued", "merge_wait", "done", "leased", "returned"):
                t.pop("cond", None)
        res = results(D)
        for k in ("G5b", "G5c", "G6b", "G22", "G33", "G44"):
            self.assertFalse(res[k]["ok"], k)


class StartAndPrereq(unittest.TestCase):
    def test_g5b_needs_the_start_cond(self):
        D = rules()
        drop(row(D, "blocked", "prereqs_satisfied"), "task.decision_gates.start")
        self.assertFalse(results(D)["G5b"]["ok"])

    def test_g5b_rejects_the_merge_gate_on_start(self):
        D = rules()
        row(D, "blocked", "prereqs_satisfied")["cond"].append(
            {"field": "task.decision_gates.merge", "op": "subset_of", "value": "task_state.decisions_recorded"})
        self.assertFalse(results(D)["G5b"]["ok"])

    def test_g6b_needs_the_prereq_cond(self):
        D = rules()
        drop(row(D, "blocked", "prereqs_satisfied"), "prereq_tasks_in(post_merge_states)")
        res = results(D)
        self.assertFalse(res["G6b"]["ok"])
        self.assertEqual(res["G6b"]["detail"]["post_merge_states cond 없는 전이"], ["blocked→queued (prereqs_satisfied)"])

    def test_g6b_rejects_eq_merged(self):
        D = rules()
        row(D, "blocked", "prereqs_satisfied")["cond"].append({"field": "event.prereq_state", "op": "==", "value": "merged"})
        self.assertFalse(results(D)["G6b"]["ok"])


class MergeGate(unittest.TestCase):
    def test_every_ready_and_pending_row_is_checked(self):
        for frm, event in (("review_approved", "audit_not_required"), ("review_approved", "decision_pending"),
                           ("audit_pending", "audit_pass"), ("audit_pending", "decision_pending"),
                           ("merge_wait", "decision_recorded")):
            D = rules()
            row(D, frm, event, "merge_wait").pop("cond")
            res = results(D)
            self.assertFalse(res["G5c"]["ok"], (frm, event))
            self.assertIn(f"{frm}→merge_wait ({event})", res["G5c"]["detail"]["병합 관문 cond 없는 전이"])

    def test_waiting_rows_are_not_merge_gates(self):
        """auditor_unavailable / reviewer_unavailable wait for a person, not a decision: no merge cond is asked."""
        detail = results()["G5c"]["detail"]["전이별 op"]
        self.assertNotIn("audit_pending→merge_wait (auditor_unavailable)", detail)
        self.assertEqual(len(detail), 5)

    def test_both_sides_needed(self):
        D = rules()
        for t in D["transitions"]:
            for p in t.get("cond") or []:
                if p.get("field") == "task.decision_gates.merge":
                    p["op"] = "subset_of"
        self.assertFalse(results(D)["G5c"]["ok"])


class DocsPr(unittest.TestCase):
    def test_finding_row_without_cond(self):
        """The finding: merged -> done with docs_only only in the prose, the core picks the cond-less sibling."""
        D = rules()
        done = row(D, "merged", "impl_counter_incremented", "done")
        done.pop("cond")
        self.assertIn("docs_only", done["when"])
        self.assertFalse(results(D)["G22"]["ok"])

    def test_sibling_without_cond(self):
        D = rules()
        row(D, "merged", "impl_counter_incremented", "audit_queued").pop("cond")
        res = results(D)
        self.assertFalse(res["G22"]["ok"])
        self.assertIn("merged→audit_queued (impl_counter_incremented)", res["G22"]["detail"]["코어가 고를 수 없는 이유"])

    def test_payload_must_carry_docs_only(self):
        D = rules()
        D["core_contract"]["events_in"]["payloads"]["impl_counter_incremented"] = []
        self.assertFalse(results(D)["G22"]["ok"])


class LateResult(unittest.TestCase):
    def test_g33_needs_both_lease_fields(self):
        for field in ("report.lease_id", "report.lease_generation"):
            D = rules()
            drop(row(D, "building", "fence_violation"), field)
            self.assertFalse(results(D)["G33"]["ok"], field)


class LeaseIssuingRows(unittest.TestCase):
    def test_the_set_covers_more_than_rows_into_leased(self):
        names = {sc.row_name(x) for x in sc.lease_issuing_rows(RULES["transitions"])}
        self.assertEqual(names, {"queued→leased (lease_granted)", "building→building (result_failed_tests)",
                                 "handoff→leased (preserved)", "paused_no_builder→leased (builder_available)",
                                 "ci_failed→building (lease_granted)", "changes_requested→building (lease_granted)"})

    def test_g35_rows_outside_leased(self):
        """The old check looked only at to == leased; these rows issue a lease into building."""
        for frm, event, to in (("changes_requested", "lease_granted", "building"), ("ci_failed", "lease_granted", "building"),
                               ("building", "result_failed_tests", "building")):
            D = rules()
            r = row(D, frm, event, to)
            r.pop("guard")
            drop(r, "lease_guards")
            res = results(D)
            self.assertFalse(res["G35"]["ok"], (frm, event))
            self.assertIn(f"{frm}→{r['to']} ({event})", res["G35"]["detail"]["가드 없는 전이"])

    def test_g35_guard_or_cond(self):
        """Either form makes the core run the guards (transition_engine.apply_event: tr['guard'] or the all_pass cond)."""
        D = rules()
        row(D, "building", "result_failed_tests", "building").pop("guard")
        self.assertTrue(results(D)["G35"]["ok"])

    def test_g42_issue_lease_effect(self):
        D = rules()
        r = row(D, "ci_failed", "lease_granted")
        r["side_effects"] = [e for e in r["side_effects"] if e["id"] != "issue_lease"]
        res = results(D)
        self.assertFalse(res["G42"]["ok"])
        self.assertIn("ci_failed→building (lease_granted)", res["G42"]["detail"]["issue_lease 참조 없는 전이"])

    def test_g42_reasons_one_to_one(self):
        D = rules()
        row(D, "changes_requested", "lease_granted")["side_effects"][0]["args"]["reason"] = "retry_ci"
        detail = results(D)["G42"]["detail"]["issue_lease 참조 없는 전이"]
        self.assertIn("사유 retry_ci 중복", detail)
        self.assertIn("발급 전이 없는 사유 retry_review", detail)
        D = rules()
        row(D, "ci_failed", "lease_granted")["side_effects"][0]["args"]["reason"] = "retry_other"
        self.assertFalse(results(D)["G42"]["ok"])

    def test_g42_generation_changed_outside_issue_lease(self):
        D = rules()
        row(D, "building", "result_failed_tests", "building")["side_effects"].insert(
            0, {"id": "increment_counter", "args": {"field": "lease_generation"}})
        res = results(D)
        self.assertFalse(res["G42"]["ok"])
        self.assertEqual(res["G42"]["detail"]["따로 증가"], ["building→building (result_failed_tests): increment_counter"])


class HandoffLease(unittest.TestCase):
    def test_g44_needs_preserved_cond(self):
        D = rules()
        r = row(D, "handoff", "preserved", "leased")
        drop(r, "handoff_record.preservation_state")
        self.assertIn("preserve_succeeded", r["when"])
        self.assertFalse(results(D)["G44"]["ok"])


if __name__ == "__main__":
    unittest.main()
