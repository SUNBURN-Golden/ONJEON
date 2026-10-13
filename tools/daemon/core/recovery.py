"""restart_recovery, normal expiry, state corruption (state_integrity)."""
from . import effects, lease as lease_mod, transition_engine


def expiry_candidates(core, state):
    """Events that move an expired lease out of `state`, taken from the transition table."""
    return [e for e in core.expiry_events if any(tr["event"] == e and tr["from"] == state for tr in core.rules.transitions)]


def normal_expiry_due(core, d, task_id):
    t = d["tasks"][task_id]
    lease = t.get("lease_record")
    if not lease or t["task_state"]["state"] not in ("leased", "building"):
        return False
    ctx = core.ctx(d, task_id)
    ok, _ = ctx.all(core.rules.get("state_integrity.normal_expiry.detect"))
    return ok


def expire(core, d, task_id):
    """The existing expiry transition (lease_expired / heartbeat_missed_twice). Pending outbox -> void(expired)."""
    state = d["tasks"][task_id]["task_state"]["state"]
    for ev in expiry_candidates(core, state):
        out = transition_engine.apply_event(core, d, task_id, ev, {})
        if out["applied"]:
            return out
    lease_mod.void_pending(core, d, task_id, "expired")
    return None


def corruption_reason(core, d, task_id):
    """Detections of state_integrity.corruption.detect (the contract lists them as prose; coded here).
    The 'handoff phase unreadable' item is not applied: it conflicts with transitions[27] (see gaps)."""
    t = d["tasks"][task_id]
    lease = t.get("lease_record")
    ts = t["task_state"]
    live_state = ts["state"] in ("leased", "building")
    if lease is None:
        return "state has no lease record" if live_state else None
    if lease["status"] != "active" and not live_state:
        return None
    rows = t["outbox"]
    mine = [r for r in rows if r["lease_id"] == lease["lease_id"] or r["lease_generation"] == lease["lease_generation"]]
    if not mine:
        return "lease_record without an outbox row of the same generation"
    for r in mine:
        if (r["lease_id"] == lease["lease_id"]) != (r["lease_generation"] == lease["lease_generation"]):
            return "outbox.lease_generation != lease_record.lease_generation"
    if lease["lease_generation"] != t["lease_generation"] or lease["fencing_token"] != lease["lease_generation"]:
        return "generation decreased or fencing_token != lease_generation"
    if live_state and lease["status"] != "active":
        return "leased/building without an active lease_record"
    return None


def handle_corruption(core, d, task_id, why):
    """effects of state_integrity.corruption, then returned(R-08). No new lease is issued."""
    t = d["tasks"][task_id]
    ts = t["task_state"]
    frm = ts["state"]
    lease = t.get("lease_record")
    if lease is not None and lease["status"] != "revoked":
        lease["status"] = "revoked"
    core.rec.side_effect(d, task_id, "revoke_token", lease_id=(lease or {}).get("lease_id"), via="corruption")
    for name in core.rules.always_revoke:
        core.ports.credentials.revoke(name, task_id, (lease or {}).get("lease_id"))
        core.rec.side_effect(d, task_id, "revoke_credential", credential=name, via="corruption")
    lease_mod.void_pending(core, d, task_id, "corrupt")
    code = core.rules.token("state_integrity.corruption.effects", r"R-\d\d", " ".join(core.rules.get("state_integrity.corruption.effects")))
    ts["state"] = "returned"
    ts["return_code"] = code
    core.rec.transition(d, task_id, frm, "returned", "state_integrity.corruption", [], source="state_integrity")
    core.rec.diagnostic(d, task_id, "corruption", why=why)
    core.rec.returned(d, task_id, code)


def restart_recovery(core):
    """core_contract.operations.restart_recovery.order, per task."""
    snap = core.snapshot()
    post = []
    for task_id in sorted(snap["tasks"]):
        # 1 classify
        with core.ports.store.transaction() as d:
            why = corruption_reason(core, d, task_id)
            if why:
                handle_corruption(core, d, task_id, why)
                continue
            if normal_expiry_due(core, d, task_id):
                expire(core, d, task_id)
                continue
        # 2 normal: resend pending, sent waits for a heartbeat
        lease_mod.resend_outbox(core, task_id, "daemon_restart")
        # 3 handoff in progress: resume from handoff_record.phase
        state = core.snapshot()["tasks"][task_id]["task_state"]["state"]
        if state == "handoff":
            post.append(("restart_handoff", task_id))
    return post
