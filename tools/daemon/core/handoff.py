"""handoff_sequence driver: stop, isolate, confirm_quiescent, preserve, revoke_token, issue_next_lease.

The order of steps comes from handoff_sequence. Failures are fed back as events so that the
transitions[] rows and handoff_failure_policy.max_attempts decide retry or handoff_blocked.
"""
import re

from . import effects, lease as lease_mod
from .ports import (CommitFailed, DiskFullError, IndexLockError, PushFailed, QueryUnavailable, SimulatedCrash, SpecGap)

PRESERVE_CREDENTIAL = "preserve_credential"
WAIT = "wait"


def _info(core, task_id):
    t = core.snapshot()["tasks"][task_id]
    hr = t["handoff_record"]
    lease = t["lease_record"]
    return t, hr, lease, core.ports.worktree.path_for(task_id, hr["lease_id"])


def _retry_from(core, event, current):
    node = core.rules.view["handoff_failure_policy"]["max_attempts"].get(event, {})
    text = node.get("retry_from") if isinstance(node, dict) else None
    if text:
        name = core.rules.token(f"handoff_failure_policy.max_attempts.{event}.retry_from", r"^[A-Za-z_][A-Za-z0-9_]*", text)
        if name in core.rules.sequence:
            return name
    return current


# ---------------------------------------------------------------- steps
def step_stop(core, task_id):
    t, hr, lease, path = _info(core, task_id)
    with core.ports.store.transaction() as d:
        ts = d["tasks"][task_id]["task_state"]
        if ts["stop_requested_at"] is None:
            ts["stop_requested_at"] = core.clock.now()
        core.rec.intent(d, task_id, "stop", lease_id=hr["lease_id"])
    core.ports.sender.request_stop(task_id, lease["builder"])
    grace = int(core.rules.number("hard_stop.grace_s"))
    waited = 0
    while core.ports.process.alive_count(task_id) > 0 and waited < grace:
        core.clock.sleep(1)
        waited += 1
    stopped = core.ports.process.alive_count(task_id) == 0
    with core.ports.store.transaction() as d:
        core.rec.result(d, task_id, "stop", "stopped" if stopped else "grace_expired", waited_s=waited)
    return None


def apply_isolation(core, d, task_id):
    t = d["tasks"][task_id]
    hr = t["handoff_record"]
    path = core.ports.worktree.path_for(task_id, hr["lease_id"])
    if core.ports.process.alive_count(task_id) > 0:
        core.ports.process.terminate_group(task_id)
        core.rec.side_effect(d, task_id, "terminate_process_group", lease_id=hr["lease_id"])
    core.ports.worktree.set_readonly(path)
    core.rec.side_effect(d, task_id, "worktree_readonly", path=path)
    hr["worktree_readonly"] = True
    for name in core.rules.always_revoke:
        if name != PRESERVE_CREDENTIAL:
            effects.revoke_credential(core, d, task_id, name)


def step_isolate(core, task_id):
    with core.ports.store.transaction() as d:
        core.rec.intent(d, task_id, "isolate")
        apply_isolation(core, d, task_id)
        core.rec.result(d, task_id, "isolate", "isolated")
    return None


def step_confirm_quiescent(core, task_id):
    t, hr, lease, path = _info(core, task_id)
    window = core.rules.number("concurrency.quiescence.window_s")
    oid_fn = getattr(core.ports.git, core.rules.get("concurrency.quiescence.manifest_function"))
    with core.ports.store.transaction() as d:
        core.rec.intent(d, task_id, "confirm_quiescent", window_s=window)
    reasons = []
    try:
        if core.ports.process.alive_count(task_id) > 0:
            reasons.append("process_alive")
        m1, o1 = core.ports.worktree.max_mtime(path), oid_fn(path)
        core.clock.sleep(window)
        m2, o2 = core.ports.worktree.max_mtime(path), oid_fn(path)
        if core.ports.process.alive_count(task_id) > 0 and "process_alive" not in reasons:
            reasons.append("process_alive")
        if core.ports.worktree.open_write_handles(path) > 0:
            reasons.append("open_write_handle")
        if m1 != m2:
            reasons.append("mtime_changed")
        if o1 != o2:
            reasons.append("tree_oid_changed")
    except IndexLockError as e:
        return ("index_lock", {"owner_pid_alive": e.owner_pid_alive})
    except DiskFullError:
        return ("disk_full", {})
    if reasons:
        with core.ports.store.transaction() as d:
            core.rec.result(d, task_id, "confirm_quiescent", "not_quiescent", reasons=reasons)
        return ("quiescence_failed", {"reason": ",".join(reasons)})
    with core.ports.store.transaction() as d:
        d["tasks"][task_id]["handoff_record"]["quiescent_tree_oid"] = o2
        core.rec.result(d, task_id, "confirm_quiescent", "quiescent", quiescent_tree_oid=o2)
    return None


def step_preserve(core, task_id):
    t, hr, lease, path = _info(core, task_id)
    branch = lease["branch"]
    faults = core.ports.faults
    failure = None
    try:
        # restart-safe reconciliation: adopt what is already there instead of redoing it
        if hr["preservation_state"] == "none" and hr["quiescent_tree_oid"]:
            found = core.ports.git.find_commit_by_tree(branch, hr["quiescent_tree_oid"])
            if found:
                core.handle_event({"event": "preserve_commit_ok", "task_id": task_id,
                                   "payload": {"commit_tree_oid": hr["quiescent_tree_oid"], "wip_commit_sha": found}})
                with core.ports.store.transaction() as d:
                    core.rec.result(d, task_id, "preserve_commit", "adopted_existing", wip_commit_sha=found)
        t, hr, lease, path = _info(core, task_id)
        if hr["preservation_state"] == "local_committed":
            ref = core.ports.git.remote_ref(branch)
            if ref is not None and ref == hr["wip_commit_sha"]:
                core.handle_event({"event": "preserve_push_ok", "task_id": task_id, "payload": {"remote_ref_sha": ref}})
                with core.ports.store.transaction() as d:
                    core.rec.result(d, task_id, "preserve_push", "adopted_existing", remote_ref_sha=ref)
    except QueryUnavailable:
        return ("preserve_commit_failed", {"reason": "cannot_verify_existing_preservation"})
    t, hr, lease, path = _info(core, task_id)
    core.ports.credentials.issue(PRESERVE_CREDENTIAL, task_id, hr["lease_id"])
    crashed = False
    try:
        if hr["preservation_state"] == "none":
            msg = f"WIP lease_id={hr['lease_id']} lease_generation={lease['lease_generation']} tree={hr['quiescent_tree_oid']}"
            with core.ports.store.transaction() as d:
                core.rec.intent(d, task_id, "preserve_commit", quiescent_tree_oid=hr["quiescent_tree_oid"])
            try:
                res = core.ports.git.preserve_commit(path, branch, msg)
            except IndexLockError as e:
                failure = ("index_lock", {"owner_pid_alive": e.owner_pid_alive})
            except DiskFullError:
                failure = ("disk_full", {})
            except CommitFailed as e:
                failure = ("preserve_commit_failed", {"reason": e.reason})
            if failure is None:
                faults.check("handoff:preserve:after_local_commit_unrecorded")
                out = core.handle_event({"event": "preserve_commit_ok", "task_id": task_id,
                                         "payload": {"commit_tree_oid": res["commit_tree_oid"],
                                                     "wip_commit_sha": res["wip_commit_sha"]}})
                if not out["applied"]:
                    failure = ("preserve_commit_failed", {"reason": "tree_oid_mismatch"})
                else:
                    with core.ports.store.transaction() as d:
                        core.rec.result(d, task_id, "preserve_commit", "committed", wip_commit_sha=res["wip_commit_sha"])
        t, hr, lease, path = _info(core, task_id)
        if failure is None and hr["preservation_state"] == "local_committed":
            faults.check("handoff:preserve:after_local_commit_recorded")
            with core.ports.store.transaction() as d:
                core.rec.intent(d, task_id, "preserve_push", wip_commit_sha=hr["wip_commit_sha"])
            try:
                ref = core.ports.git.push(branch, hr["wip_commit_sha"])
            except PushFailed as e:
                failure = ("preserve_push_failed", {"reason": e.reason})
            if failure is None:
                faults.check("handoff:preserve:after_push_unrecorded")
                out = core.handle_event({"event": "preserve_push_ok", "task_id": task_id, "payload": {"remote_ref_sha": ref}})
                if out["applied"]:
                    with core.ports.store.transaction() as d:
                        core.rec.result(d, task_id, "preserve_push", "pushed", remote_ref_sha=ref)
                else:
                    failure = ("preserve_push_failed", {"reason": "remote_ref_mismatch"})
    except SimulatedCrash:
        crashed = True  # a dead process runs no finally
        raise
    finally:
        if not crashed:
            with core.ports.store.transaction() as d:
                effects.revoke_credential(core, d, task_id, PRESERVE_CREDENTIAL)
    return failure


def step_revoke_token(core, task_id):
    with core.ports.store.transaction() as d:
        t = d["tasks"][task_id]
        hr = t["handoff_record"]
        lease = t["lease_record"]
        lease["status"] = "handed_off"
        hr["token_revoked"] = True
        lease_mod.void_pending(core, d, task_id, "revoked")
        core.rec.side_effect(d, task_id, "revoke_token", lease_id=lease["lease_id"],
                             lease_generation=lease["lease_generation"])
        for name in core.rules.always_revoke:
            if name not in hr["credentials_revoked"]:
                effects.revoke_credential(core, d, task_id, name)
        core.rec.side_effect(d, task_id, "record_handoff", lease_id=lease["lease_id"],
                             preservation_state=hr["preservation_state"], wip_commit_sha=hr["wip_commit_sha"],
                             quiescent_tree_oid=hr["quiescent_tree_oid"])
    return None


def step_issue_next_lease(core, task_id):
    out = core.handle_event({"event": "preserved", "task_id": task_id, "payload": {}})
    if not out["applied"]:
        out = core.handle_event({"event": "no_builder", "task_id": task_id, "payload": {}})
    return None if out["applied"] else WAIT


STEPS = {"stop": step_stop, "isolate": step_isolate, "confirm_quiescent": step_confirm_quiescent,
         "preserve": step_preserve, "revoke_token": step_revoke_token, "issue_next_lease": step_issue_next_lease}


# ---------------------------------------------------------------- driver
def run(core, task_id):
    seq = core.rules.sequence
    for _ in range(500):
        t = core.snapshot()["tasks"][task_id]
        if t["task_state"]["state"] != "handoff":
            return
        step = t["handoff_record"]["phase"]
        if step is None:
            return
        core.ports.faults.check(f"handoff:{step}:start")
        result = STEPS[step](core, task_id)
        if result == WAIT:
            return
        if result is None:
            nxt = seq[seq.index(step) + 1] if seq.index(step) + 1 < len(seq) else step
            snap = core.snapshot()["tasks"][task_id]
            if snap["task_state"]["state"] == "handoff":
                with core.ports.store.transaction() as d:
                    d["tasks"][task_id]["handoff_record"]["phase"] = nxt
            if step == seq[-1]:
                return
            continue
        event, payload = result
        core.handle_event({"event": event, "task_id": task_id, "payload": payload})
        snap = core.snapshot()["tasks"][task_id]
        if snap["task_state"]["state"] != "handoff":
            return
        with core.ports.store.transaction() as d:
            d["tasks"][task_id]["handoff_record"]["phase"] = _retry_from(core, event, step)
    raise SpecGap("handoff did not settle within 500 steps")


def resume(core, task_id):
    """daemon_restart_during_handoff: the transitions decide resume or handoff_blocked; on resume the
    write ban and credential revocation are re-applied, then the sequence continues from the phase."""
    out = core.handle_event({"event": "daemon_restart_during_handoff", "task_id": task_id, "payload": {}})
    t = core.snapshot()["tasks"][task_id]
    if not out["applied"] or t["task_state"]["state"] != "handoff":
        return out
    hr = t["handoff_record"]
    seq = core.rules.sequence
    if hr["phase"] in seq and seq.index(hr["phase"]) >= seq.index("isolate") or hr["worktree_readonly"]:
        with core.ports.store.transaction() as d:
            core.rec.intent(d, task_id, "reapply_isolation", phase=hr["phase"])
            apply_isolation(core, d, task_id)
            effects.revoke_credential(core, d, task_id, PRESERVE_CREDENTIAL)
    run(core, task_id)
    return out
