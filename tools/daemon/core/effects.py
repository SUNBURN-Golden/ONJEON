"""State effects of events that transitions[] carries no structured side_effects for.

The contract describes these only in prose or not at all; each function says which behavior it
implements. They are reported as specification gaps in the run report.
"""
import re

from . import lease as lease_mod


def new_handoff_record(core, task_id, lease):
    keys = []
    for tr in core.rules.transitions:
        for p in tr.get("cond", []):
            m = re.fullmatch(r"handoff_record\.attempts\.([A-Za-z_]\w*)", p.get("field", ""))
            if m and m.group(1) not in keys:
                keys.append(m.group(1))
    return {"task_id": task_id, "lease_id": lease["lease_id"], "phase": core.rules.sequence[0],
            "preservation_state": "none", "quiescent_tree_oid": None, "wip_commit_sha": None,
            "attempts": {k: 0 for k in keys}, "restart_count": 0, "token_revoked": False,
            "credentials_revoked": [], "worktree_readonly": False, "failure_log": []}


def renew(core, d, task_id):
    lease = d["tasks"][task_id]["lease_record"]
    now = core.clock.now()
    lease["last_heartbeat_at"] = now
    lease["expires_at"] = now + core.rules.number("concurrency.lease.ttl_s")


def revoke_credential(core, d, task_id, name):
    t = d["tasks"][task_id]
    hr = t["handoff_record"]
    lease = t.get("lease_record") or {}
    core.ports.credentials.revoke(name, task_id, lease.get("lease_id"))
    core.rec.side_effect(d, task_id, "revoke_credential", credential=name)
    if name not in hr["credentials_revoked"]:
        hr["credentials_revoked"].append(name)


def block_effects(core, d, task_id):
    """handoff_blocked entry: always_revoke all revoked, worktree read-only (operations.handoff_failure)."""
    t = d["tasks"][task_id]
    hr = t["handoff_record"]
    for name in core.rules.always_revoke:
        if name not in hr["credentials_revoked"]:
            revoke_credential(core, d, task_id, name)
    if not hr["worktree_readonly"]:
        path = core.ports.worktree.path_for(task_id, hr["lease_id"])
        core.ports.worktree.set_readonly(path)
        core.rec.side_effect(d, task_id, "worktree_readonly", path=path)
        hr["worktree_readonly"] = True


def mark_expired(core, d, task_id):
    """Normal expiry: the lease is expired and its pending instruction is void(expired)."""
    d["tasks"][task_id]["lease_record"]["status"] = "expired"
    lease_mod.void_pending(core, d, task_id, "expired")


def after_noop(core, d, task_id, name, payload, envelope):
    if name == "heartbeat" and d["tasks"][task_id].get("lease_record"):
        renew(core, d, task_id)


def on_transition(core, d, task_id, tr, payload, envelope, out):
    rules = core.rules
    t = d["tasks"][task_id]
    ts = t["task_state"]
    ev, frm, to = tr["event"], tr["from"], tr["to"]
    hr = t.get("handoff_record")
    if ev == "first_heartbeat":
        renew(core, d, task_id)
    if ev == "switch_signal" and to == "handoff":
        t["handoff_record"] = new_handoff_record(core, task_id, t["lease_record"])
    if ev == "preserve_commit_ok":
        hr["preservation_state"] = "local_committed"
        hr["wip_commit_sha"] = payload.get("wip_commit_sha")
        core.rec.side_effect(d, task_id, "preserve_commit", tree_oid=payload.get("commit_tree_oid"),
                             wip_commit_sha=payload.get("wip_commit_sha"))
    if ev == "preserve_push_ok":
        hr["preservation_state"] = "remote_pushed"
        core.rec.side_effect(d, task_id, "preserve_push", remote_ref_sha=payload.get("remote_ref_sha"))
    if ev == "recovery_decision" and to == "handoff":
        for k in hr["attempts"]:
            hr["attempts"][k] = 0
        hr["phase"] = rules.sequence[1] if hr["preservation_state"] == "none" else "preserve"
    if ev == "owner_resolved" and frm == "returned":
        ts["attempt"] += 1
        ts["return_code"] = None
    if to == "cancelled":
        ts["cancelled"] = True
    if to == "handoff_blocked":
        block_effects(core, d, task_id)
    if ev == "unmapped_condition":
        # R-03 for a condition the table does not map. transitions[] has no return_code field (gap).
        ts["return_code"] = "R-03"
        core.rec.returned(d, task_id, "R-03")


# on_lease_end items (concurrency.fencing.on_lease_end) -> side_effect_ids of expected_outputs.
# The two lists use different names for two items; this alias table is the only link (reported as a gap).
LEASE_END_ALIASES = {"terminate_process": "terminate_process_group", "revoke_write_credential": "revoke_credential"}


def end_lease(core, d, task_id, why):
    """The current lease ends: process group, write credential, token, handoff record (on_lease_end).
    The contract does not say which transitions end a lease; the core ends it when the task leaves the
    lease-holding states and before issuing a new lease."""
    t = d["tasks"][task_id]
    lease = t["lease_record"]
    for item in core.rules.get("concurrency.fencing.on_lease_end"):
        sid = LEASE_END_ALIASES.get(item, item)
        if sid == "terminate_process_group":
            if core.ports.process.alive_count(task_id) > 0:
                core.ports.process.terminate_group(task_id)
            core.rec.side_effect(d, task_id, sid, lease_id=lease["lease_id"], why=why)
        elif sid == "revoke_credential":
            core.ports.credentials.revoke("builder_write_credential", task_id, lease["lease_id"])
            core.rec.side_effect(d, task_id, sid, credential="builder_write_credential", why=why)
        elif sid == "revoke_token":
            lease["status"] = "revoked"
            core.rec.side_effect(d, task_id, sid, lease_id=lease["lease_id"], lease_generation=lease["lease_generation"], why=why)
        else:
            core.rec.side_effect(d, task_id, sid, lease_id=lease["lease_id"], why=why)
