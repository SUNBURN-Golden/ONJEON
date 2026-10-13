"""Event dispatch over transitions[]: pick the row by from/event, evaluate cond and guard, apply."""
import re

from . import lease as lease_mod
from .ports import PreconditionFailed, SpecGap

# Which lease reason a lease-issuing transition passes to issue_lease. The transition rows only say
# "issue_lease(task_id)" and carry no reason (reported as a specification gap), so it is derived from
# the state the transition leaves.
REASON_BY_FROM_STATE = {
    "queued": "initial", "handoff": "handoff", "paused_no_builder": "resume_paused",
    "ci_failed": "retry_ci", "changes_requested": "retry_review", "building": "retry_failed_tests",
}


def _bump_failure_counter(core, d, task_id, name, payload):
    t = d["tasks"][task_id]
    hr = t.get("handoff_record")
    if hr is None:
        return
    if name in hr["attempts"]:
        hr["attempts"][name] += 1
    elif name == "daemon_restart_during_handoff":
        hr["restart_count"] += 1
    hr["failure_log"].append({"event": name, "at": core.clock.now(), "reason": payload.get("reason")})


def _parse_side_effect(core, text):
    op = core.rules.token("transitions[].side_effects", r"^\s*([A-Za-z_][A-Za-z0-9_]*)\(", text, 1)
    if op is None:
        raise SpecGap(f"side effect is not a call: {text[:40]}")
    return op


def apply_event(core, d, task_id, name, payload=None, envelope=None):
    rules = core.rules
    t = d["tasks"][task_id]
    ts = t["task_state"]
    payload = dict(payload or {})
    out = {"applied": False, "transition": None, "post": [], "rejected": None}
    if name not in core.known_events:
        payload["original_event"] = name
        name = "unmapped_condition"
    if name in rules.noop_events:
        core.rec.noop(d, task_id, name, envelope_id=(envelope or payload).get("envelope_id"))
        core.effects.after_noop(core, d, task_id, name, payload, envelope)
        out["noop"] = name
        return out
    if name in rules.max_attempt_events or name == "daemon_restart_during_handoff":
        _bump_failure_counter(core, d, task_id, name, payload)
    cands = [tr for tr in rules.transitions if tr["event"] == name and tr["from"] in (ts["state"], "*")]
    cands.sort(key=lambda tr: tr["from"] == "*")
    if not cands:
        core.rec.diagnostic(d, task_id, "no_row_for_state", event=name, state=ts["state"])
        return apply_event(core, d, task_id, "unmapped_condition", {"original_event": name}, envelope)
    rejected = []
    for tr in cands:
        ctx = core.ctx(d, task_id, event=payload, envelope=envelope)
        ok, recs = ctx.all(tr.get("cond"))
        if not ok:
            rejected.append(recs)
            continue
        if tr.get("guard"):
            gr = lease_mod.run_guards(core, d, task_id, REASON_BY_FROM_STATE.get(tr["from"], "initial"))
            if not gr.all_pass:
                core.rec.diagnostic(d, task_id, "guard_failed", event=name, guard=tr["guard"], failed=gr.failed)
                out["rejected"] = ("guard", gr.failed)
                return out
        _apply(core, d, task_id, tr, recs, payload, envelope, out)
        return out
    core.rec.diagnostic(d, task_id, "cond_not_met", event=name, state=ts["state"], cond=rejected)
    out["rejected"] = ("cond", rejected)
    return out


def _apply(core, d, task_id, tr, recs, payload, envelope, out):
    t = d["tasks"][task_id]
    ts = t["task_state"]
    frm, to, name = ts["state"], tr["to"], tr["event"]
    calls = [_parse_side_effect(core, s) for s in tr.get("side_effects", [])]
    core.rec.transition(d, task_id, frm, to, name, recs)
    ts["state"] = to
    out["applied"] = True
    out["transition"] = (frm, to, name)
    if name in core.expiry_events and t.get("lease_record"):
        core.effects.mark_expired(core, d, task_id)
    holding = ("leased", "building")
    lease_now = t.get("lease_record")
    if frm in holding and to not in holding + ("handoff",) and lease_now and lease_now["status"] == "active":
        core.effects.end_lease(core, d, task_id, why=f"{frm}->{to}")
    for op in calls:
        if op == "issue_lease":
            lease_now = t.get("lease_record")
            if lease_now and lease_now["status"] == "active":
                core.effects.end_lease(core, d, task_id, why="superseded by the next lease")
            reason = payload.get("reason") if name == "lease_granted" and payload.get("reason") else REASON_BY_FROM_STATE.get(frm, "initial")
            lease_mod.issue_lease(core, d, task_id, reason)
            out["post"].append(("issued", task_id))
        else:
            raise SpecGap(f"unknown side effect op {op}")
    core.effects.on_transition(core, d, task_id, tr, payload, envelope, out)
    if to == "handoff" and frm != "handoff":
        out["post"].append(("handoff", task_id))
