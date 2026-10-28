"""accept_envelope and fenced_write: ordered checks, then the noop kinds (late, duplicate, invalid) or the
event transition. The checks, their fail keys and the on_fail table are all read from core_contract.operations."""
from . import effects, envelope_validator as ev, observation, secret_scan, transition_engine, usage

_SCANNED = ("result", "signal", "heartbeat")  # secret_patterns.scan[result_envelope].target


def event_for(core, msg_type, envelope, task_id=None):
    if msg_type == "result":
        return observation.result_event(core, task_id or envelope.get("task_id"), envelope)
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


def _secret_check(core, d, task_id, msg_type, envelope):
    """scan[result_envelope]: at accept_envelope.before_inbox_seen, in the states it names. A match is
    secret_detected (R-10); the envelope is not marked seen and not processed further."""
    spec = secret_scan.scan_spec(core.rules, "result_envelope")
    if ev.envelope_type(core.rules, msg_type) not in _SCANNED or d["tasks"][task_id]["task_state"]["state"] not in spec["states"]:
        return None
    n = secret_scan.count_in(secret_scan.patterns(core.rules), envelope)
    if not n:
        return None
    event = core.rules.get("preserve_manifest.secret_patterns.on_match.event")
    res = transition_engine.apply_event(core, d, task_id, event, secret_scan.event_payload(core.rules, "result_envelope", n))
    return {"accepted": False, "noop": None, "return_code": None, "transition": res["transition"], "post": res["post"],
            "secret_detected": n}


def accept(core, d, task_id, msg_type, envelope):
    """Run inside a transaction. Returns an outcome dict."""
    rules = core.rules
    t = d["tasks"][task_id]
    key = ev.dedup_key(rules, task_id, msg_type, envelope)
    missing = ev.missing_fields(rules, msg_type, envelope)
    view = ev.check_view(rules, msg_type, envelope)
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
    found = _secret_check(core, d, task_id, msg_type, envelope)
    if found is not None:
        return found
    t["inbox_seen"][key] = {"first_seen_at": core.clock.now(), "lease_generation": envelope.get("lease_generation")}
    out = {"accepted": True, "noop": None, "return_code": None, "transition": None, "post": []}
    if msg_type == "result":
        usage.record_result(core, d, task_id, envelope)  # record_after_result: never stops anything
    name = event_for(core, msg_type, envelope, task_id)
    res = transition_engine.apply_event(core, d, task_id, name, {}, envelope=envelope)
    if res["transition"] and res["transition"][1] == "pr_open":
        observation.on_pr_opened(core, d, task_id, envelope)
    out["transition"] = res["transition"]
    out["post"] = res["post"]
    out["noop"] = res.get("noop")
    out["emitted"] = res.get("emitted", [])
    if res.get("guard_wait"):
        # engine._txn discards this transaction: inbox_seen, the usage writes and the counter are not kept
        out["guard_wait"] = dict(res["guard_wait"], envelope_id=envelope.get("envelope_id"))
    return out


def reject_without_envelope(core, d, task_id, event, on_reject):
    """core_contract.operations.handle_event.on_reject: an event that arrived without an envelope and is not on
    without_envelope. Recorded only (like an envelope with every required field missing); no transition."""
    core.rec.noop(d, task_id, on_reject["noop_event"], return_code=on_reject.get("return_code"),
                  reason=on_reject["reason"], event=event)
    return {"applied": False, "accepted": False, "noop": on_reject["noop_event"],
            "return_code": on_reject.get("return_code"), "transition": None, "post": [],
            "rejected": (on_reject["reason"], event)}


def check_write(core, d, task_id, event, request, claimed=False):
    """Return the first failed check. Dispatch rechecks fencing, skipping only its already-claimed identity."""
    spec = core.rules.get("core_contract.operations.fenced_write")
    t = d["tasks"][task_id]
    key = ev.dedup_key(core.rules, task_id, event, request)
    funcs = {
        "request.required": lambda _a: [f for f in spec["required_fields"] if request.get(f) is None],
        "inbox_seen[key]": lambda _a: t["inbox_seen"].get(key),
    }
    ctx = core.ctx(d, task_id, envelope=request, funcs=funcs)
    for check in spec["checks"]:
        if claimed and check["id"] == "not_seen":
            continue
        ok, rec = ctx.predicate(check["pred"])
        if not ok:
            return check
    return None


def reject_write(core, d, task_id, request, check):
    spec = core.rules.get("core_contract.operations.fenced_write")
    out = _report(core, d, task_id, spec["on_fail"][check["fail_key"]], request, check["id"], check["fail_key"])
    out["written"] = False
    return out


def fenced_write(core, d, task_id, event, kind, request):
    """Check and claim the request atomically; stage remote writes for after the store commit."""
    spec = core.rules.get("core_contract.operations.fenced_write")
    request = dict(request)
    request["kind"] = kind  # request.kind: push or pr_update (the event says which)
    failed = check_write(core, d, task_id, event, request)
    if failed:
        return reject_write(core, d, task_id, request, failed)
    t = d["tasks"][task_id]
    key = ev.dedup_key(core.rules, task_id, event, request)
    t["inbox_seen"][key] = {"first_seen_at": core.clock.now(), "lease_generation": request["lease_generation"]}
    state = t["task_state"]["state"]
    out = {"accepted": True, "noop": None, "return_code": None, "transition": None, "post": [],
           "writes": [], "written": False}
    env = effects.Env(tr={"event": event, "from": state, "to": state}, payload=request, envelope=request, out=out)
    effects.run_effects(core, d, task_id, spec["on_pass"], env)
    return out
