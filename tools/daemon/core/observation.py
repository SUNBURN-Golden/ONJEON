"""Observations from outside the builder channel: CI, the pull request, reviews, audits, landings, decision records.

The transition rows of this part of the life cycle (blocked -> queued and pr_open ... done) have no cond, and the
rules that pick their event are prose (04 §2.2, §4, §5; daemon_rules.json when, audit_triggers.immediate_rules,
record_separation.merge_observation_fields._rule, review_assignment.exclude_rule) or live outside
core_contract.reads (post_merge_states, audit_triggers, record_separation). This module is the narrowest reading
of those rules. It is shared by every executor (it is core, not adapter), reads the structured values it needs
only through Rules.outside(), and every rule it applies in code is listed in spec gaps G51-G54.

It never decides what a row does: it picks the event and the payload facts the rows' cond read (docs_only for
merged -> audit_queued / done), then the transition engine applies the row from the data.
"""
import json

from . import transition_engine
from .gate_evaluator import normalize_path, paths_within_scope, patterns_overlap

# ---- rules written in code (spec gaps)
# G51: merge_wait.reason after each event that enters or stays in merge_wait (states.merge_wait is prose)
REASON_AFTER = {"audit_not_required": "ready", "audit_pass": "ready", "decision_recorded": "ready",
                "decision_pending": "decision_pending", "reviewer_unavailable": "reviewer_unavailable",
                "auditor_unavailable": "auditor_unavailable"}
# G51: docs-only PR (04 §2.2 row merged -> done: 'docs/** 뿐 또는 label docs-only')
DOCS_ONLY_PATTERN, DOCS_ONLY_LABEL = "docs/**", "docs-only"
# G52: the noop each duplicated observation leaves (noop_events has the names, no noop_rules map them)
DUPLICATE_NOOP = {"ci_passed": "ci_passed_duplicate", "pr_merged_observed": "pr_merged_observed_duplicate",
                  "merged_without_valid_approval": "pr_merged_observed_duplicate",
                  "review_approved": "review_result_duplicate", "review_changes_requested": "review_result_duplicate",
                  "audit_pass": "audit_result_duplicate", "audit_changes_requested": "audit_result_duplicate",
                  "decision_recorded": "decision_recorded_duplicate"}
GENERIC_DUPLICATE, CI_PENDING, STATUS_UNCHANGED = "notification_retry", "ci_pending", "builder_status_unchanged"
# G53: return codes recorded by this layer (the rows have no record_r_code)
STALE_RESULT, INVALID_LANDING = "R-04", "R-12"


# ---------------------------------------------------------------- store
def _pr(d, task_id):
    return d.setdefault("pr", {}).get(task_id)


def _audit(d):
    return d.setdefault("audit", {"merged_impl_counter": 0, "batches": []})


def _state(d, task_id):
    return d["tasks"][task_id]["task_state"]["state"]


def active_pr_states(core):
    """The states a pull request is open in: the from-states of head_sha_changed (all lead to pr_open)."""
    return {tr["from"] for tr in core.rules.transitions if tr["event"] == "head_sha_changed"}


def _has_row(core, state, event):
    return any(tr["event"] == event and tr["from"] in (state, "*") for tr in core.rules.transitions)


def reviewer_family(core, pr, p):
    """The family of the reviewer of a review_result, read from the reviewer registry (ReviewerPool), never from
    the payload. Once a reviewer is assigned (pr.reviewer) only that reviewer may report; a result that arrives
    before the assignment (held, out of order) names its reviewer and that name must be registered.
    Returns (family, reason); family is None when the result cannot be attributed (fail closed)."""
    name = (pr or {}).get("reviewer") or p.get("reviewer")
    if (pr or {}).get("reviewer") and p.get("reviewer") != pr["reviewer"]:
        return None, "reviewer_not_assigned"
    registered = {c["name"]: c["family"] for c in core.ports.reviewers.candidates()}
    family = registered.get(name)
    if family is None:
        return None, "reviewer_not_registered"
    if not p.get("reviewer_family"):
        return None, "reviewer_family_missing"
    if p["reviewer_family"] != family:
        return None, "reviewer_family_mismatch"
    return family, None


def authors_families(core, d, task_id):
    """Families of every builder that held a lease of this task (from the issue_lease records)."""
    fams = []
    for r in d["journal"]:
        if r.get("task_id") == task_id and r["kind"] == "side_effect_record" and r["id"] == "issue_lease":
            fam = core.ports.builders.family(r["args"]["builder"])
            if fam not in fams:
                fams.append(fam)
    return fams


def _sync_decisions(d):
    for t in d["tasks"].values():
        for dec in d.get("decisions", []):
            if dec not in t["task_state"]["decisions_recorded"]:
                t["task_state"]["decisions_recorded"].append(dec)


# ---------------------------------------------------------------- results of the builder
def result_event(core, task_id, envelope):
    """Status event after accept_envelope's structured scope and PR body checks."""
    name = "result_" + str(envelope.get("status"))
    if name not in core.rules.transition_events:
        return "unmapped_condition"
    return name


def _inside(path, patterns):
    return any(patterns_overlap(path, p) and (p == path or p.endswith("/**")) for p in patterns or [])


def _clean_paths(paths):
    """The normalized form of the touched paths that the PR record keeps (docs-only and immediate-audit checks
    read it); accept_envelope has already checked every path."""
    out = []
    for raw in paths or []:
        path = normalize_path(raw)
        if path is not None and path not in out:
            out.append(path)
    return out


def out_of_scope(core, task_id, touched):
    """Compatibility helper; shared predicate semantics live in gate_evaluator."""
    return not paths_within_scope(touched, core.ports.catalog.task(task_id))


def on_pr_opened(core, d, task_id, envelope):
    """The pull request record. concurrency.pr_dedup: an open pull request of the task is reused."""
    lease = d["tasks"][task_id]["lease_record"] or {}
    pr = _pr(d, task_id)
    if pr is None:
        pr = {"pr_number": envelope.get("pr_number"), "head_sha": envelope.get("head_sha"), "base_sha": lease.get("base_sha"),
              "changed_paths": _clean_paths(envelope.get("touched_paths")), "labels": list(envelope.get("labels") or []),
              "review_results": [], "audit_results": [], "reviewer": None, "merge_wait_reason": None,
              "approved_head_sha": None, "approved_base_sha": None, "auditor_available": True}
        d["pr"][task_id] = pr
        core.rec.diagnostic(d, task_id, "pr_record_created", pr_number=pr["pr_number"])
        return
    for p in _clean_paths(envelope.get("touched_paths")):
        if p not in pr["changed_paths"]:
            pr["changed_paths"].append(p)
    if envelope.get("head_sha") and envelope["head_sha"] != pr["head_sha"]:
        _invalidate(core, d, task_id, pr)
        pr["head_sha"] = envelope["head_sha"]
    core.rec.diagnostic(d, task_id, "pr_record_reused", pr_number=pr["pr_number"],
                        claimed_pr_number=envelope.get("pr_number"))


# ---------------------------------------------------------------- applying events
def _apply(core, d, task_id, event, payload=None):
    out = transition_engine.apply_event(core, d, task_id, event, payload or {})
    pr = _pr(d, task_id)
    if out.get("applied") and pr is not None and event in REASON_AFTER and _state(d, task_id) == "merge_wait":
        pr["merge_wait_reason"] = REASON_AFTER[event]
    return out


def _invalidate(core, d, task_id, pr):
    """record_separation.review_audit_validity: results tied to the old head are marked, never deleted (R-04)."""
    stale = [r for r in pr["review_results"] + pr["audit_results"] if r.get("invalidated_at") is None]
    for r in stale:
        r["invalidated_at"] = core.clock.now()
    pr["approved_head_sha"] = pr["approved_base_sha"] = None
    pr["merge_wait_reason"] = None
    if stale:
        core.rec.returned(d, task_id, STALE_RESULT)
    return len(stale)


def _route(core, d, task_id, event, payload, sha=None):
    """Apply now, hold (out-of-order: the event has a row only from another open-PR state), or let the engine
    treat it as unmapped."""
    state = _state(d, task_id)
    if _has_row(core, state, event):
        return _apply(core, d, task_id, event, payload)
    if state in active_pr_states(core) and any(tr["event"] == event and tr["from"] in active_pr_states(core)
                                               for tr in core.rules.transitions):
        d.setdefault("held", {}).setdefault(task_id, []).append({"event": event, "payload": payload, "sha": sha})
        core.rec.diagnostic(d, task_id, "event_held", event=event, state=state, sha=sha)
        return {"applied": False, "held": True, "transition": None}
    return _apply(core, d, task_id, event, payload)


def _release_held(core, d, task_id):
    held = d.setdefault("held", {}).get(task_id) or []
    pr = _pr(d, task_id)
    for item in list(held):
        if not _has_row(core, _state(d, task_id), item["event"]):
            continue
        held.remove(item)
        if pr is not None and item["sha"] is not None and item["sha"] != pr["head_sha"]:
            core.rec.diagnostic(d, task_id, "held_event_invalid_sha", event=item["event"], sha=item["sha"])
            core.rec.returned(d, task_id, STALE_RESULT)
            continue
        _on_result_applied(core, d, task_id, item["event"], item["payload"])
        _apply(core, d, task_id, item["event"], item["payload"])
        return True
    return False


def _on_result_applied(core, d, task_id, event, payload):
    pr = _pr(d, task_id)
    if pr is None:
        return
    if event in ("review_approved", "review_changes_requested"):
        pr["review_results"].append({"sha": payload.get("sha"), "verdict": event, "reviewer": payload.get("reviewer"),
                                     "at": core.clock.now(), "invalidated_at": None})
        if event == "review_approved":
            pr["approved_head_sha"], pr["approved_base_sha"] = payload.get("sha"), pr["base_sha"]
    elif event in ("audit_pass", "audit_changes_requested", "decision_pending") and payload.get("audit"):
        pr["audit_results"].append({"sha": payload.get("sha"), "verdict": payload.get("verdict"),
                                    "at": core.clock.now(), "invalidated_at": None})


# ---------------------------------------------------------------- the steps the daemon takes by itself
def _landing_gates_recorded(core, d, task_id):
    """Picks audit_not_required / audit_pass vs decision_pending; the rows' cond (task.decision_gates.merge subset_of /
    not_subset_of task_state.decisions_recorded) checks the same gate again (audit2-spec-check-reads-prose-when)."""
    gates = (core.ports.catalog.task(task_id).get("decision_gates") or {}).get("merge") or []
    return set(gates) <= set(d["tasks"][task_id]["task_state"]["decisions_recorded"])


def immediate_audit_required(core, d, task_id):
    """audit_triggers.immediate_rules: changed paths ∩ immediate_audit_paths, or task.immediate_audit. The label
    and body rules are prose and are not applied (G51)."""
    pr = _pr(d, task_id)
    paths = core.rules.outside("audit_triggers.immediate_audit_paths")
    if any(patterns_overlap(c, p) for c in pr["changed_paths"] for p in paths):
        return True
    return bool(core.ports.catalog.task(task_id).get("immediate_audit"))


def docs_only(d, task_id):
    pr = _pr(d, task_id)
    if DOCS_ONLY_LABEL in pr["labels"]:
        return True
    return bool(pr["changed_paths"]) and all(patterns_overlap(c, DOCS_ONLY_PATTERN) for c in pr["changed_paths"])


def _eligible_reviewer(core, d, task_id):
    fams = authors_families(core, d, task_id)
    for c in core.ports.reviewers.candidates():
        if c["family"] in fams:
            continue  # review_assignment: authors' families are excluded, self review forbidden
        if c["available"]:
            return c
    return None


def _count_landing(core, d, task_id):
    """merged -> audit_queued (implementation PR, counter +1, periodic batch) or done (docs-only, no count). The
    event carries docs_only and the rows' cond on event.docs_only pick the destination; the count follows the row."""
    out = _apply(core, d, task_id, "impl_counter_incremented", {"docs_only": docs_only(d, task_id)})
    if out.get("transition") != ("merged", "audit_queued", "impl_counter_incremented"):
        return out
    audit = _audit(d)
    every = core.rules.outside("audit_triggers.periodic.every")
    if not audit["batches"] or audit["batches"][-1]["closed"]:
        audit["batches"].append({"batch_id": f"B{len(audit['batches']) + 1}", "tasks": [], "closed": False})
    batch = audit["batches"][-1]
    audit["merged_impl_counter"] += 1
    batch["tasks"].append(task_id)
    batch["closed"] = audit["merged_impl_counter"] % every == 0
    core.rec.side_effect(d, task_id, "increment_counter", field="merged_impl_counter",
                         value=audit["merged_impl_counter"], batch_id=batch["batch_id"], batch_closed=batch["closed"])
    return out


def _step(core, d, task_id):
    """One automatic step from the current state, if any. Returns True when the state changed."""
    state = _state(d, task_id)
    pr = _pr(d, task_id)
    before = state
    if pr is not None and state == "review_pending":
        c = _eligible_reviewer(core, d, task_id)
        if c is not None:
            pr["reviewer"] = c["name"]
            _apply(core, d, task_id, "reviewer_assigned", {"reviewer": c["name"]})
        else:
            _apply(core, d, task_id, "reviewer_unavailable", {})
    elif pr is not None and state == "review_approved":
        if immediate_audit_required(core, d, task_id):
            _apply(core, d, task_id, "audit_required", {})
        elif _landing_gates_recorded(core, d, task_id):
            _apply(core, d, task_id, "audit_not_required", {})
        else:
            _apply(core, d, task_id, "decision_pending", {})
    elif pr is not None and state == "audit_pending" and not pr["auditor_available"]:
        _apply(core, d, task_id, "auditor_unavailable", {})
    elif pr is not None and state == "merge_wait":
        reason = pr["merge_wait_reason"]
        if reason == "reviewer_unavailable" and _eligible_reviewer(core, d, task_id) is not None:
            _apply(core, d, task_id, "reviewer_available", {})
        elif reason == "auditor_unavailable" and pr["auditor_available"]:
            _apply(core, d, task_id, "auditor_available", {})
        elif reason == "decision_pending" and _landing_gates_recorded(core, d, task_id):
            _apply(core, d, task_id, "decision_recorded", {})
            return pr["merge_wait_reason"] != reason
    elif pr is not None and state == "merged":
        _count_landing(core, d, task_id)
    if _state(d, task_id) != before:
        return True
    return _release_held(core, d, task_id)


def settle(core, d, task_id):
    """Run automatic steps until nothing moves; when a task reaches a post-merge state, re-evaluate the blocked."""
    post = core.rules.outside("post_merge_states")
    for _ in range(64):
        if not _step(core, d, task_id):
            break
    if _state(d, task_id) in post:
        for other in sorted(d["tasks"]):
            if d["tasks"][other]["task_state"]["state"] == "blocked":
                _prereqs(core, d, other)


# ---------------------------------------------------------------- prerequisites and start gates
def prereq_tasks_in(core, d, task_id, path):
    """Every prereq_tasks entry of the task is a registered task whose state is in the rules list `path`: the
    blocked -> queued cond prereq_tasks_in(post_merge_states) (audit2-spec-check-reads-prose-when). The list is read
    through Rules.outside(), so only an OUTSIDE_READS path can be named."""
    states = core.rules.outside(path)
    for pre in core.ports.catalog.task(task_id).get("prereq_tasks") or []:
        if pre not in d["tasks"] or _state(d, pre) not in states:
            return False
    return True


def _prereqs(core, d, task_id):
    """blocked -> queued: every prerequisite task in post_merge_states and decision_gates.start recorded (04 §2.2).
    Both are the row's cond: prereq_tasks_in(post_merge_states) (audit2-spec-check-reads-prose-when) and
    task.decision_gates.start subset_of task_state.decisions_recorded, so an unrecorded or missing start list keeps
    the task blocked and leaves a cond_not_met diagnostic that names the gate (audit1-start-gates-enforcement).
    The event is raised only once the prerequisites hold (same function as the cond), so a task that still waits
    for a prerequisite leaves no diagnostic."""
    _sync_decisions(d)
    if _state(d, task_id) != "blocked":
        return None
    if not prereq_tasks_in(core, d, task_id, "post_merge_states"):
        return None
    return _apply(core, d, task_id, "prereqs_satisfied", {})


def evaluate_prereqs(core, task_id):
    return core._txn(task_id, lambda d: _prereqs(core, d, task_id))


# ---------------------------------------------------------------- entry point
def _seen(core, d, key):
    seen = d.setdefault("obs_seen", {})
    if key in seen:
        return True
    seen[key] = core.clock.now()
    return False


def _duplicate(core, d, task_id, event):
    noop = DUPLICATE_NOOP.get(event, GENERIC_DUPLICATE)
    core.rec.noop(d, task_id, noop)
    return {"applied": False, "noop": noop, "transition": None}


def _observe(core, d, task_id, kind, p):
    if kind == "decision_record":
        dec = p["decision_id"]
        if _seen(core, d, f"decision|{dec}"):
            return _duplicate(core, d, None, "decision_recorded")
        d.setdefault("decisions", []).append(dec)
        _sync_decisions(d)
        core.rec.diagnostic(d, None, "decision_recorded", decision_id=dec, source_ref=p.get("source_ref"))
        for other in sorted(d["tasks"]):
            _prereqs(core, d, other)
            settle(core, d, other)
        return {"applied": True, "transition": None}
    if kind == "batch_audit_result":
        audit = _audit(d)
        batch = next((b for b in audit["batches"] if b["batch_id"] == p["batch_id"]), None)
        if batch is None or not batch["closed"] or p.get("verdict") != "pass":
            core.rec.diagnostic(d, None, "batch_audit_not_applied", batch_id=p["batch_id"], verdict=p.get("verdict"))
            return {"applied": False, "transition": None}
        if _seen(core, d, f"batch|{p['batch_id']}"):
            return _duplicate(core, d, None, "audit_pass")
        for t in batch["tasks"]:
            if _state(d, t) == "audit_queued":
                _apply(core, d, t, "batch_audit_pass", {"batch_id": p["batch_id"]})
        return {"applied": True, "transition": None}

    pr = _pr(d, task_id)
    if kind == "ci":
        if p["conclusion"] == "pending":
            core.rec.noop(d, task_id, CI_PENDING)
            return {"applied": False, "noop": CI_PENDING, "transition": None}
        event = "ci_passed" if p["conclusion"] == "success" else "ci_failed"
        if _seen(core, d, f"{task_id}|ci|{p['sha']}|{p['conclusion']}"):
            return _duplicate(core, d, task_id, event)
        if pr is not None and p["sha"] != pr["head_sha"]:
            core.rec.diagnostic(d, task_id, "ci_for_other_sha", sha=p["sha"])
            return {"applied": False, "transition": None}
        out = _route(core, d, task_id, event, {}, sha=p["sha"])
    elif kind == "review_result":
        event = "review_approved" if p["verdict"] == "approved" else "review_changes_requested"
        family, why = reviewer_family(core, pr, p)
        if family is None:
            core.rec.diagnostic(d, task_id, "review_result_rejected", reviewer=p.get("reviewer"), reason=why)
            return {"applied": False, "transition": None}
        if family in authors_families(core, d, task_id):
            core.rec.diagnostic(d, task_id, "self_review_rejected", reviewer=p.get("reviewer"))
            return {"applied": False, "transition": None}
        if _seen(core, d, f"{task_id}|review|{p['sha']}|{p.get('reviewer')}|{p['verdict']}"):
            return _duplicate(core, d, task_id, event)
        if _has_row(core, _state(d, task_id), event) and pr is not None and p["sha"] != pr["head_sha"]:
            core.rec.diagnostic(d, task_id, "review_sha_mismatch", sha=p["sha"], head_sha=pr["head_sha"])
            core.rec.returned(d, task_id, STALE_RESULT)
            return {"applied": False, "transition": None}
        if _has_row(core, _state(d, task_id), event):
            _on_result_applied(core, d, task_id, event, p)
        out = _route(core, d, task_id, event, dict(p), sha=p["sha"])
    elif kind == "audit_result":
        if p["verdict"] == "pass":
            event = "audit_pass" if _landing_gates_recorded(core, d, task_id) else "decision_pending"
        else:
            event = "audit_changes_requested"
        if _seen(core, d, f"{task_id}|audit|{p['sha']}|{p['verdict']}"):
            return _duplicate(core, d, task_id, "audit_pass" if p["verdict"] == "pass" else event)
        if pr is not None and p["sha"] != pr["head_sha"]:
            core.rec.diagnostic(d, task_id, "audit_sha_mismatch", sha=p["sha"], head_sha=pr["head_sha"])
            core.rec.returned(d, task_id, STALE_RESULT)
            return {"applied": False, "transition": None}
        payload = dict(p, audit=True)
        if _has_row(core, _state(d, task_id), event):
            _on_result_applied(core, d, task_id, event, payload)
        out = _route(core, d, task_id, event, payload, sha=p["sha"])
    elif kind == "auditor_status":
        if pr is None or pr["auditor_available"] == p["available"]:
            core.rec.noop(d, task_id, STATUS_UNCHANGED)
            return {"applied": False, "noop": STATUS_UNCHANGED, "transition": None}
        pr["auditor_available"] = p["available"]
        out = {"applied": False, "transition": None}
    elif kind == "reviewers_changed":
        out = {"applied": False, "transition": None}
    elif kind == "head_sha":
        if pr is None or p["sha"] == pr["head_sha"]:
            return _duplicate(core, d, task_id, "head_sha_changed")
        _invalidate(core, d, task_id, pr)
        pr["head_sha"] = p["sha"]
        if _has_row(core, _state(d, task_id), "head_sha_changed"):
            out = _apply(core, d, task_id, "head_sha_changed", {"sha": p["sha"]})
        else:
            core.rec.diagnostic(d, task_id, "head_recorded_without_transition", state=_state(d, task_id))
            out = {"applied": False, "transition": None}
    elif kind == "landing":
        out = _landing(core, d, task_id, pr, p)
        if out.get("noop"):
            return out
    else:
        out = _apply(core, d, task_id, "unmapped_condition", {"original_observation": kind})
    settle(core, d, task_id)
    return out


def _landing_key(task_id, p):
    """The merge commit identifies a landing. Without one, the other observed fields do, so that landings that
    carry no merge_commit_sha are not all taken for the same one."""
    if p.get("merge_commit_sha"):
        return f"{task_id}|landing|{p['merge_commit_sha']}"
    rest = [p.get("head_sha_at_merge"), p.get("base_sha_at_merge"), p.get("integration_check")]
    return f"{task_id}|landing|no_merge_commit|" + json.dumps(rest)


def _landing(core, d, task_id, pr, p):
    """A pull request was found landed (by a person). record_separation.merge_observation_fields go to the
    completion facts either way; valid only with reason ready, head_sha_at_merge == approved_head_sha and an
    unchanged base. merge_commit_sha is recorded, never compared."""
    # a missing SHA is never a match: None == None must not make a landing valid
    shas = (p.get("head_sha_at_merge"), p.get("base_sha_at_merge"))
    approved = (pr or {}).get("approved_head_sha"), (pr or {}).get("approved_base_sha")
    valid = (pr is not None and _state(d, task_id) == "merge_wait" and pr["merge_wait_reason"] == "ready"
             and all(isinstance(x, str) and x for x in shas + approved) and shas == approved)
    event = "pr_merged_observed" if valid else "merged_without_valid_approval"
    if _seen(core, d, _landing_key(task_id, p)):
        return _duplicate(core, d, task_id, event)
    values = {"approved_head_sha": (pr or {}).get("approved_head_sha"), "base_sha": (pr or {}).get("approved_base_sha"),
              "head_sha_at_merge": p.get("head_sha_at_merge"), "merge_commit_sha": p.get("merge_commit_sha"),
              "integration_check": p.get("integration_check")}
    fields = {k: values.get(k) for k in core.rules.outside("record_separation.merge_observation_fields")}
    d.setdefault("completion_facts", []).append(dict(task_id=task_id, kind="landing_observed", valid=valid,
                                                     observed_at=core.clock.now(), **fields))
    core.rec.side_effect(d, task_id, "record_merge_observation", valid=valid, **fields)
    out = _apply(core, d, task_id, event, {})
    # R-12 only when the merged_without_valid_approval row itself applied; a state with no such row falls through
    # to unmapped_condition, which already records its own R code
    if not valid and (out.get("transition") or (None, None, None))[2] == event:
        core.rec.returned(d, task_id, INVALID_LANDING)
    return out


def observe(core, task_id, kind, payload):
    return core._txn(task_id, lambda d: _observe(core, d, task_id, kind, dict(payload)))
