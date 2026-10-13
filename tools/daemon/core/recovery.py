"""restart_recovery, normal expiry and state corruption (state_integrity)."""
import re

from . import lease as lease_mod, transition_engine


def expiry_events(core):
    """The events that move an expired lease out of its state. state_integrity.normal_expiry.path names them in
    a sentence; there is no structured list (reported as a gap)."""
    path = core.rules.get("state_integrity.normal_expiry.path")
    core.rules.token_log.add(("state_integrity.normal_expiry.path", "event names inside the path text"))
    known = core.rules.transition_events
    return [e for e in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", path) if e in known]


def _expiry_rows(core, state):
    names = expiry_events(core)
    return [tr["event"] for tr in core.rules.transitions if tr["event"] in names and tr["from"] == state]


def normal_expiry_due(core, d, task_id):
    t = d["tasks"][task_id]
    state = t["task_state"]["state"]
    if not t.get("lease_record") or not _expiry_rows(core, state):
        return False
    ok, _ = core.ctx(d, task_id).all(core.rules.get("state_integrity.normal_expiry.detect"))
    return ok


def follow_up(core, d, task_id, events, payload):
    """Try the follow-up events in order; the first one that moves the task wins."""
    for ev in events:
        out = transition_engine.apply_event(core, d, task_id, ev, payload)
        if out["applied"]:
            return out
    return None


def expire(core, d, task_id):
    """The existing expiry transition (lease_expired / heartbeat_missed_twice)."""
    state = d["tasks"][task_id]["task_state"]["state"]
    out = follow_up(core, d, task_id, _expiry_rows(core, state), {})
    if out is None:
        lease_mod.void_pending(core, d, task_id, "expired")
    return out


def detect_id(core, d, task_id):
    """The id of the first state_integrity.corruption.detect item that holds, or None. The list does not say to
    which tasks it applies (reported as a gap): the core applies it to tasks whose lease is active or whose state
    holds a lease; a task that was already ended and returned is not classified again."""
    t = d["tasks"][task_id]
    holding = {tr["from"] for tr in core.rules.transitions if tr["event"] in expiry_events(core)}
    if (t.get("lease_record") or {}).get("status") != "active" and t["task_state"]["state"] not in holding \
            and t["task_state"]["state"] != "handoff":
        return None
    ctx = core.ctx(d, task_id)
    for item in core.rules.get("state_integrity.corruption.detect"):
        ok, _ = ctx.all(item["pred"])
        if ok:
            return item["id"]
    return None


def corrupt(core, d, task_id, found):
    """state_corrupted: the contract's own event; its row carries the effects and the R code."""
    return transition_engine.apply_event(core, d, task_id, core.rules.get("state_integrity.corruption.event"),
                                         {"detect_id": found})


def restart_recovery(core):
    """core_contract.operations.restart_recovery.order, per task."""
    snap = core.snapshot()
    post = []
    for task_id in sorted(snap["tasks"]):
        # 1 classify: corruption first, then normal expiry
        with core.ports.store.transaction() as d:
            found = detect_id(core, d, task_id)
            if found:
                corrupt(core, d, task_id, found)
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
