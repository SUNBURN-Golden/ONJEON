"""Before/after evidence for audit2-spec-check-reads-prose-when.

Runs two copies of spec_check.py (the parent commit's and the working tree's) against the same rule mutations and
prints the verdict of the target check. The old copy has no (T, D) parameters, so its `load` is patched.
Usage (repo root): python3 -I tools/evidence/audit2-spec-check-reads-prose-when/mutations.py <old spec_check.py> <new spec_check.py>
"""
import copy
import importlib.util
import json
import os
import sys
import warnings

ROOT = os.getcwd()
BUNDLE = os.path.join(ROOT, "docs/blueprint/proposals/설계검토_결과")
with open(os.path.join(BUNDLE, "daemon_rules.json"), encoding="utf-8") as f:
    RULES = json.load(f)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.BUNDLE = BUNDLE
    return m


def verdict(m, D, gid):
    orig = m.load
    m.load = lambda name: copy.deepcopy(D) if name == "daemon_rules.json" else orig(name)
    m.RESULTS.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        m.run(ROOT)
    m.load = orig
    return "PASS" if [r for r in m.RESULTS if r["check"].startswith(gid + " ")][0]["ok"] else "FAIL"


def row(D, frm, event, to):
    return [t for t in D["transitions"] if (t["from"], t["event"], t["to"]) == (frm, event, to)][0]


def mutate(fn):
    D = copy.deepcopy(RULES)
    fn(D)
    return D


def drop(field):
    return lambda r: r.__setitem__("cond", [p for p in r.get("cond") or [] if p.get("field") != field])


def no_guard(r):
    r.pop("guard", None)
    drop("lease_guards")(r)


CASES = [
    ("bundle as is", None, "G22"),
    ("all `when` blanked", lambda D: [t.__setitem__("when", "") for t in D["transitions"]], "G22"),
    ("merged→done cond removed (when still says docs_only)", lambda D: row(D, "merged", "impl_counter_incremented", "done").pop("cond"), "G22"),
    ("merged→audit_queued cond removed (cond-less sibling wins)", lambda D: row(D, "merged", "impl_counter_incremented", "audit_queued").pop("cond"), "G22"),
    ("blocked→queued start cond removed", lambda D: drop("task.decision_gates.start")(row(D, "blocked", "prereqs_satisfied", "queued")), "G5b"),
    ("blocked→queued prereq cond removed", lambda D: drop("prereq_tasks_in(post_merge_states)")(row(D, "blocked", "prereqs_satisfied", "queued")), "G6b"),
    ("audit_pending→merge_wait audit_pass cond removed", lambda D: row(D, "audit_pending", "audit_pass", "merge_wait").pop("cond"), "G5c"),
    ("fence_violation lease_generation pred removed", lambda D: drop("report.lease_generation")(row(D, "building", "fence_violation", "returned")), "G33"),
    ("changes_requested→building lease_granted without guard", lambda D: no_guard(row(D, "changes_requested", "lease_granted", "building")), "G35"),
    ("building→building result_failed_tests without guard", lambda D: no_guard(row(D, "building", "result_failed_tests", "building")), "G35"),
    ("ci_failed→building without issue_lease effect",
     lambda D: row(D, "ci_failed", "lease_granted", "building").__setitem__("side_effects", []), "G42"),
    ("handoff→leased preservation_state pred removed", lambda D: drop("handoff_record.preservation_state")(row(D, "handoff", "preserved", "leased")), "G44"),
]


def main():
    old, new = module(sys.argv[1], "spec_check_old"), module(sys.argv[2], "spec_check_new")
    print(f"{'mutation':<62} check  before  after")
    for label, fn, gid in CASES:
        D = mutate(fn) if fn else copy.deepcopy(RULES)
        print(f"{label:<62} {gid:<6} {verdict(old, D, gid):<7} {verdict(new, D, gid)}")


if __name__ == "__main__":
    main()
