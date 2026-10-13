"""accept_envelope: ordered checks, then noop kinds (duplicate, late) or the event transition."""
from . import envelope_validator as ev, transition_engine

FAIL_KEY_BY_FIELD = {
    "envelope.required": "required_missing",
    "inbox_seen[key]": "inbox_seen_hit",
    "envelope.lease_id": "lease_or_generation_or_token_mismatch",
    "envelope.lease_generation": "lease_or_generation_or_token_mismatch",
    "envelope.fencing_token": "lease_or_generation_or_token_mismatch",
    "lease_record.status": "lease_or_generation_or_token_mismatch",
    "clock.now": "expired",
}


def event_for(core, msg_type, envelope):
    if msg_type == "result":
        name = "result_" + str(envelope.get("status"))
        return name if name in core.rules.events else "unmapped_condition"
    return msg_type


def _on_fail(core, key):
    text = core.rules.get("core_contract.operations.accept_envelope.on_fail")[key]
    noop = core.rules.token("accept_envelope.on_fail." + key, r"^[A-Za-z_][A-Za-z0-9_]*", text)
    code = core.rules.token("accept_envelope.on_fail." + key, r"R-\d\d", text)
    return (noop if noop in core.rules.noop_events else None), code


def accept(core, d, task_id, msg_type, envelope):
    """Run inside a transaction. Returns an outcome dict."""
    rules = core.rules
    t = d["tasks"][task_id]
    key = ev.dedup_key(rules, task_id, msg_type, envelope)
    missing = ev.missing_fields(rules, msg_type, envelope)
    funcs = {
        "envelope.required": lambda _a: missing,
        "inbox_seen[key]": lambda _a: t["inbox_seen"].get(key),
    }
    ctx = core.ctx(d, task_id, envelope=envelope, funcs=funcs)
    out = {"accepted": False, "noop": None, "return_code": None, "transition": None, "post": []}
    for check in rules.get("core_contract.operations.accept_envelope.checks_in_order"):
        ok, rec = ctx.predicate(check)
        if ok:
            continue
        fkey = FAIL_KEY_BY_FIELD.get(check["field"])
        noop, code = _on_fail(core, fkey)
        core.rec.noop(d, task_id, noop, envelope_id=envelope.get("envelope_id"), return_code=code,
                      failed_check=check["field"], reason=fkey)
        out.update(noop=noop or fkey, return_code=code, reason=fkey)
        return out
    t["inbox_seen"][key] = {"first_seen_at": core.clock.now()}
    out["accepted"] = True
    name = event_for(core, msg_type, envelope)
    res = transition_engine.apply_event(core, d, task_id, name, {}, envelope=envelope)
    out["transition"] = res["transition"]
    out["post"] = res["post"]
    out["noop"] = res.get("noop")
    return out
