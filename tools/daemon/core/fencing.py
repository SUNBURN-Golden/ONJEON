"""accept_envelope and fenced_write: ordered checks, then the noop kinds (late, duplicate, invalid) or the
event transition. The checks, their fail keys and the on_fail table are all read from core_contract.operations."""
from . import effects, envelope_validator as ev, transition_engine, usage


def event_for(core, msg_type, envelope):
    if msg_type == "result":
        name = "result_" + str(envelope.get("status"))
        return name if name in core.rules.transition_events else "unmapped_condition"
    return msg_type


def _report(core, d, task_id, on_fail, envelope, check_id, fkey):
    """Apply one on_fail entry: a noop record (with an R code) or a transition event."""
    out = {"accepted": False, "noop": None, "return_code": None, "transition": None, "post": [], "reason": fkey}
    if "noop_event" in on_fail:
        core.rec.noop(d, task_id, on_fail["noop_event"], envelope_id=envelope.get("envelope_id"),
                      return_code=on_fail.get("return_code"), failed_check=check_id, reason=fkey)
        out.update(noop=on_fail["noop_event"], return_code=on_fail.get("return_code"))
    else:
        res = transition_engine.apply_event(core, d, task_id, on_fail["transition_event"], {}, envelope=envelope)
        out.update(transition=res["transition"], post=res["post"], return_code=on_fail.get("return_code"),
                   applied=res["applied"])
    return out


def accept(core, d, task_id, msg_type, envelope):
    """Run inside a transaction. Returns an outcome dict."""
    rules = core.rules
    t = d["tasks"][task_id]
    key = ev.dedup_key(rules, task_id, msg_type, envelope)
    missing = ev.missing_fields(rules, msg_type, envelope)
    view = dict(envelope)
    view["kind"] = ev.envelope_name(rules, msg_type)  # envelope.kind is the kind of envelope, whatever its own fields say
    funcs = {
        "envelope.required": lambda _a: missing,
        "inbox_seen[key]": lambda _a: t["inbox_seen"].get(key),
    }
    ctx = core.ctx(d, task_id, envelope=view, funcs=funcs)
    spec = rules.get("core_contract.operations.accept_envelope")
    for check in spec["checks_in_order"]:
        ok, _rec = ctx.predicate(check["pred"])
        if ok:
            continue
        fkey = check["fail_key"]
        return _report(core, d, task_id, spec["on_fail"][fkey], envelope, check["id"], fkey)
    t["inbox_seen"][key] = {"first_seen_at": core.clock.now(), "lease_generation": envelope.get("lease_generation")}
    out = {"accepted": True, "noop": None, "return_code": None, "transition": None, "post": []}
    if msg_type == "result":
        usage.record_result(core, d, task_id, envelope)  # record_after_result: never stops anything
    name = event_for(core, msg_type, envelope)
    res = transition_engine.apply_event(core, d, task_id, name, {}, envelope=envelope)
    out["transition"] = res["transition"]
    out["post"] = res["post"]
    out["noop"] = res.get("noop")
    return out


def fenced_write(core, d, task_id, event, kind, request):
    """core_contract.operations.fenced_write: the fencing check for pushes and pull request updates."""
    spec = core.rules.get("core_contract.operations.fenced_write")
    request = dict(request)
    request["kind"] = kind  # request.kind: push or pr_update (the event says which)
    ctx = core.ctx(d, task_id, envelope=request)
    for check in spec["checks"]:
        ok, rec = ctx.predicate(check["pred"])
        if ok:
            continue
        out = _report(core, d, task_id, spec["on_fail"][check["fail_key"]], request, check["id"], check["fail_key"])
        out["written"] = False
        return out
    state = d["tasks"][task_id]["task_state"]["state"]
    env = effects.Env(tr={"event": event, "from": state, "to": state}, payload=request, envelope=request)
    effects.run_effects(core, d, task_id, spec["on_pass"], env)
    return {"accepted": True, "noop": None, "return_code": None, "transition": None, "post": [], "written": True}
