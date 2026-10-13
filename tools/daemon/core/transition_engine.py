"""Event dispatch over transitions[]: pick the row by from/event, evaluate cond and guard, apply side_effects.

Everything a row does comes from its own fields: cond, guard, side_effects (in order; order=before_cond
effects run before any cond of the event is looked at, once), return_code, on_cond_fail. noop_rules decide
which events are noops. Events that no row maps are unmapped_condition (returned, R-03).
"""
import json

from . import effects, lease as lease_mod
from .ports import PreconditionFailed, SpecGap


def _issue_reason(tr):
    for e in tr.get("side_effects", []):
        if e["id"] == "issue_lease":
            return (e.get("args") or {}).get("reason")
    return None


def row_for_issue(core, d, task_id, reason):
    """The row that issues a lease for `reason` out of the task's current state (for a direct issue_lease call)."""
    state = d["tasks"][task_id]["task_state"]["state"]
    for tr in core.rules.transitions:
        if tr["from"] == state and _issue_reason(tr) == reason:
            return tr
    return None


def _noop_rule(core, d, task_id, name, payload, envelope):
    for rule in core.rules.noop_rules:
        if rule["event"] != name:
            continue
        ctx = core.ctx(d, task_id, event=payload, envelope=envelope)
        ok, _ = ctx.all(rule.get("cond"))
        if ok:
            return rule
    return None


def apply_event(core, d, task_id, name, payload=None, envelope=None):
    rules = core.rules
    t = d["tasks"][task_id]
    ts = t["task_state"]
    payload = dict(payload or {})
    out = {"applied": False, "transition": None, "post": [], "rejected": None, "emitted": []}
    if name not in core.known_events:
        payload["original_event"] = name
        name = "unmapped_condition"
    rule_events = {r["event"] for r in rules.noop_rules}
    rule = _noop_rule(core, d, task_id, name, payload, envelope)
    if rule is not None:
        core.rec.noop(d, task_id, rule["noop_event"], envelope_id=(envelope or payload).get("envelope_id"))
        effects.run_effects(core, d, task_id, rule.get("side_effects"), effects.Env(payload=payload, envelope=envelope))
        out["noop"] = rule["noop_event"]
        return out
    if name in rules.noop_events and name not in rule_events:
        core.rec.noop(d, task_id, name, envelope_id=(envelope or payload).get("envelope_id"))
        out["noop"] = name
        return out
    cands = [tr for tr in rules.transitions if tr["event"] == name and tr["from"] in (ts["state"], "*")]
    cands.sort(key=lambda tr: tr["from"] == "*")
    if name in rules.noop_events or not cands:
        core.rec.diagnostic(d, task_id, "no_row_for_state", event=name, state=ts["state"])
        if name == "unmapped_condition":
            raise SpecGap("unmapped_condition has no row")
        return apply_event(core, d, task_id, "unmapped_condition", {"original_event": name}, envelope)
    # order=before_cond effects: once per distinct effect, before any cond of this event is evaluated
    pre, seen = [], set()
    for tr in cands:
        for eff in tr.get("side_effects", []):
            if effects.is_before_cond(eff):
                key = json.dumps(eff, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    pre.append(eff)
    effects.run_effects(core, d, task_id, pre, effects.Env(payload=payload, envelope=envelope))
    first_fail = None
    for tr in cands:
        reason = _issue_reason(tr)
        if reason is not None and payload.get("reason") not in (None, reason):
            continue  # lease_granted asked for another reason
        ctx = core.ctx(d, task_id, event=payload, envelope=envelope, reason=reason or "from_queue")
        ok, recs = ctx.all(tr.get("cond"))
        if ok and tr.get("guard"):
            gr = lease_mod.run_guards(core, d, task_id, reason or "from_queue")
            if not gr.all_pass:
                core.rec.diagnostic(d, task_id, "guard_failed", event=name, guard=tr["guard"], failed=gr.failed)
                out["rejected"] = ("guard", gr.failed)
                return out
        if not ok:
            if first_fail is None:
                first_fail = (tr, recs)
            continue
        _apply(core, d, task_id, tr, recs, payload, envelope, out)
        return out
    tr, recs = first_fail if first_fail else (None, [])
    core.rec.diagnostic(d, task_id, "cond_not_met", event=name, state=ts["state"], cond=recs)
    out["rejected"] = ("cond", recs)
    if tr is not None and tr.get("on_cond_fail"):
        emit = tr["on_cond_fail"]
        ctx = core.ctx(d, task_id, event=payload, envelope=envelope)
        args = {k: ctx.value(v) for k, v in (emit.get("args") or {}).items()}
        out["emitted"].append(apply_event(core, d, task_id, emit["emit"], args, envelope))
    return out


def _apply(core, d, task_id, tr, recs, payload, envelope, out):
    t = d["tasks"][task_id]
    ts = t["task_state"]
    frm, to, name = ts["state"], tr["to"], tr["event"]
    effs = tr.get("side_effects", [])
    issues = any(e["id"] == "issue_lease" for e in effs)
    out["applied"] = True
    out["transition"] = (frm, to, name)
    if not issues:
        # a row that issues a lease gets its transition record and its new state from issue_lease (effects_atomic)
        core.rec.transition(d, task_id, frm, to, name, recs)
        ts["state"] = to
    env = effects.Env(tr=tr, payload=payload, envelope=envelope, out=out, recs=recs)
    effects.run_effects(core, d, task_id, effs, env, skip_before_cond=True)
    code = tr.get("return_code")
    if code and not any(e["id"] == "record_r_code" for e in effs):
        raise SpecGap(f"transition {frm}->{to} {name} has return_code {code} but no record_r_code side effect")
    if to == "handoff" and frm != "handoff":
        out["post"].append(("handoff", task_id))
