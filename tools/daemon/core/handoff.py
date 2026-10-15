"""handoff_sequence driver: stop, isolate, confirm_quiescent, preserve (commit, push), revoke_token,
issue_next_lease.

The order of the steps comes from handoff_sequence. What a failure does comes from transitions[]: the failure
event is fed back, the row counts the attempt, compares it with handoff_failure_policy.max_attempts and either
sets the next phase (resume_from_phase) or goes to handoff_blocked. After a push is recorded the preserve_push_ok
row itself revokes the token, ends the lease and moves the phase on to issue_next_lease.

After a daemon restart the transitions decide where to resume (daemon_restart_during_handoff, restart_resume
{check, then, else}: an existing local commit is found by its tree OID and an existing remote ref is compared with
wip_commit_sha there, G31). The step functions below only do their own step.
"""
from . import effects, lease as lease_mod, secret_scan
from .ports import CommitFailed, DiskFullError, IndexLockError, PushFailed, SimulatedCrash, SpecGap

WAIT = "wait"
HANDLED = "handled"  # the failure was already turned into transitions by the engine


def _info(core, task_id):
    t = core.snapshot()["tasks"][task_id]
    hr = t["handoff_record"]
    lease = t["lease_record"]
    return t, hr, lease, core.ports.worktree.path_for(task_id, hr["lease_id"])


def _effect(core, d, task_id, sid, **args):
    effects.run_effect(core, d, task_id, {"id": sid, "args": args}, effects.Env())


# ---------------------------------------------------------------- secret patterns and the tree identity function
def secret_files(core, path):
    """secret_patterns.scan[preserve_files]: (files that match, match count). Matching files are excluded from
    the tree (on_match.exclude_from_preserve) and the handoff stops with secret_detected."""
    pats = secret_scan.patterns(core.rules)
    flagged, n = [], 0
    for rel, content in sorted(core.ports.git.included_files(path).items()):
        k = secret_scan.count(pats, content)
        if k:
            flagged.append(rel)
            n += k
    return flagged, n


def tree_oid(core, path, flagged):
    fn = getattr(core.ports.git, core.rules.get("preserve_manifest.function"))
    return fn(path, excludes=tuple(flagged))


# ---------------------------------------------------------------- steps
def step_stop(core, task_id):
    t, hr, lease, path = _info(core, task_id)
    with core.ports.store.transaction() as d:
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
    """isolate: process group ended, worktree read-only, the builder's write credential revoked."""
    for sid, args in (("terminate_process", {}), ("worktree_readonly", {"value": True}), ("revoke_write_credential", {})):
        effects.run_effect(core, d, task_id, {"id": sid, "args": args}, effects.Env())


def step_isolate(core, task_id):
    with core.ports.store.transaction() as d:
        core.rec.intent(d, task_id, "isolate")
        apply_isolation(core, d, task_id)
        core.rec.result(d, task_id, "isolate", "isolated")
    return None


def step_confirm_quiescent(core, task_id):
    t, hr, lease, path = _info(core, task_id)
    window = core.rules.number("concurrency.quiescence.window_s")
    with core.ports.store.transaction() as d:
        core.rec.intent(d, task_id, "confirm_quiescent", window_s=window)
    reasons = []
    try:
        if core.ports.process.alive_count(task_id) > 0:
            reasons.append("process_alive")
        m1, o1 = core.ports.worktree.max_mtime(path), tree_oid(core, path, secret_files(core, path)[0])
        core.clock.sleep(window)
        flagged, matches = secret_files(core, path)
        m2, o2 = core.ports.worktree.max_mtime(path), tree_oid(core, path, flagged)
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
    spec = secret_scan.scan_spec(core.rules, "preserve_files")
    if flagged and core.snapshot()["tasks"][task_id]["task_state"]["state"] in spec["states"]:
        with core.ports.store.transaction() as d:
            core.rec.result(d, task_id, "confirm_quiescent", "secret_detected", files=flagged, match_count=matches)
        event = core.rules.get("preserve_manifest.secret_patterns.on_match.event")
        return (event, secret_scan.event_payload(core.rules, "preserve_files", matches))
    with core.ports.store.transaction() as d:
        d["tasks"][task_id]["handoff_record"]["quiescent_tree_oid"] = o2
        core.rec.result(d, task_id, "confirm_quiescent", "quiescent", quiescent_tree_oid=o2)
    return None


def _commit_part(core, task_id):
    t, hr, lease, path = _info(core, task_id)
    if hr["preservation_state"] != "none":
        return None
    msg = f"WIP lease_id={hr['lease_id']} lease_generation={lease['lease_generation']} tree={hr['quiescent_tree_oid']}"
    with core.ports.store.transaction() as d:
        core.rec.intent(d, task_id, "preserve_commit", quiescent_tree_oid=hr["quiescent_tree_oid"])
    try:
        res = core.ports.git.preserve_commit(path, lease["branch"], msg, excludes=tuple(secret_files(core, path)[0]))
    except IndexLockError as e:
        return ("index_lock", {"owner_pid_alive": e.owner_pid_alive})
    except DiskFullError:
        return ("disk_full", {})
    except CommitFailed as e:
        return ("preserve_commit_failed", {"reason": e.reason})
    core.ports.faults.check("handoff:preserve:after_local_commit_unrecorded")
    out = core.handle_event({"event": "preserve_commit_ok", "task_id": task_id,
                             "payload": {"commit_tree_oid": res["commit_tree_oid"], "wip_commit_sha": res["wip_commit_sha"]}})
    if not out["applied"]:
        return HANDLED if out.get("emitted") else ("preserve_commit_failed", {"reason": "tree_oid_mismatch"})
    with core.ports.store.transaction() as d:
        core.rec.result(d, task_id, "preserve_commit", "committed", wip_commit_sha=res["wip_commit_sha"])
    return None


def _push_part(core, task_id):
    t, hr, lease, path = _info(core, task_id)
    if hr["preservation_state"] != "local_committed":
        return None
    core.ports.faults.check("handoff:preserve:after_local_commit_recorded")
    with core.ports.store.transaction() as d:
        core.rec.intent(d, task_id, "preserve_push", wip_commit_sha=hr["wip_commit_sha"])
    try:
        ref = core.ports.git.push(lease["branch"], hr["wip_commit_sha"])
    except PushFailed as e:
        return ("preserve_push_failed", {"reason": e.reason})
    core.ports.faults.check("handoff:preserve:after_push_unrecorded")
    out = core.handle_event({"event": "preserve_push_ok", "task_id": task_id, "payload": {"remote_ref_sha": ref}})
    if not out["applied"]:
        return ("preserve_push_failed", {"reason": "remote_ref_mismatch"})
    with core.ports.store.transaction() as d:
        core.rec.result(d, task_id, "preserve_push", "pushed", remote_ref_sha=ref)
    return None


def _with_preserve_credential(core, task_id, fn):
    t, hr, lease, path = _info(core, task_id)
    name = effects.credential_name(core, "revoke_preserve_credential")
    core.ports.credentials.issue(name, task_id, hr["lease_id"])
    with core.ports.store.transaction() as d:
        rec = d["tasks"][task_id]["handoff_record"]
        if name in rec["credentials_revoked"]:
            rec["credentials_revoked"].remove(name)  # issued again for this attempt
    crashed = False
    try:
        return fn()
    except SimulatedCrash:
        crashed = True  # a dead process runs no finally
        raise
    finally:
        if not crashed:
            with core.ports.store.transaction() as d:
                _effect(core, d, task_id, "revoke_preserve_credential")


def step_preserve(core, task_id):
    def work():
        res = _commit_part(core, task_id)
        if res is not None:
            return res
        return _push_part(core, task_id)

    return _with_preserve_credential(core, task_id, work)


def step_preserve_remote(core, task_id):
    return _with_preserve_credential(core, task_id, lambda: _push_part(core, task_id))


def step_revoke_token(core, task_id):
    """Reached only when the phase says revoke_token (a restart in that phase): end the lease as handed off, which
    runs on_lease_end (revoke_token, record_handoff, ...), then mark the token revoked."""
    with core.ports.store.transaction() as d:
        lease = d["tasks"][task_id]["lease_record"]
        if lease["status"] not in ("handed_off",):
            _effect(core, d, task_id, "end_lease", status="handed_off")
        hr = d["tasks"][task_id]["handoff_record"]
        hr["token_revoked"] = True
        lease_mod.void_pending(core, d, task_id, "revoked")
        core.rec.side_effect(d, task_id, "set_handoff_field", field="token_revoked", value=True)
    return None


def step_issue_next_lease(core, task_id):
    out = core.handle_event({"event": "preserved", "task_id": task_id, "payload": {}})
    if not out["applied"] and core.snapshot()["tasks"][task_id]["task_state"]["state"] == "handoff":
        out = core.handle_event({"event": "no_builder", "task_id": task_id, "payload": {}})
    return None if out["applied"] or out.get("emitted") else WAIT


STEPS = {"stop": step_stop, "isolate": step_isolate, "confirm_quiescent": step_confirm_quiescent,
         "preserve": step_preserve, "preserve_remote": step_preserve_remote, "revoke_token": step_revoke_token,
         "issue_next_lease": step_issue_next_lease}


def _next_phase(core, phase):
    """The phase after `phase`: handoff_sequence order. A stage the sequence does not list (preserve_remote)
    follows the sequence stage that precedes it among restart_resume's stage ids."""
    seq, stages = core.rules.sequence, core.rules.stages
    base = phase
    if base not in seq:
        before = [s for s in stages[:stages.index(base)] if s in seq]
        base = before[-1]
    i = seq.index(base)
    return seq[i + 1] if i + 1 < len(seq) else base


# ---------------------------------------------------------------- driver
def run(core, task_id):
    for _ in range(500):
        t = core.snapshot()["tasks"][task_id]
        if t["task_state"]["state"] != "handoff":
            return
        phase = t["handoff_record"]["phase"]
        if phase is None:
            return
        core.ports.faults.check(f"handoff:{phase}:start")
        if phase not in STEPS:
            raise SpecGap(f"no step for phase {phase}")
        result = STEPS[phase](core, task_id)
        if result == WAIT:
            return
        if result == HANDLED:
            continue
        if result is None:
            snap = core.snapshot()["tasks"][task_id]
            if snap["task_state"]["state"] == "handoff" and snap["handoff_record"]["phase"] == phase:
                nxt = _next_phase(core, phase)
                if nxt == phase:
                    return
                with core.ports.store.transaction() as d:
                    d["tasks"][task_id]["handoff_record"]["phase"] = nxt
            continue
        event, payload = result
        core.handle_event({"event": event, "task_id": task_id, "payload": payload})
    raise SpecGap("handoff did not settle within 500 steps")


def resume(core, task_id):
    """daemon_restart_during_handoff: the transitions decide resume or handoff_blocked (and re-apply the write
    ban and the credential revocation); on resume the sequence continues from the phase they set."""
    out = core.handle_event({"event": "daemon_restart_during_handoff", "task_id": task_id, "payload": {}})
    t = core.snapshot()["tasks"][task_id]
    if not out["applied"] or t["task_state"]["state"] != "handoff":
        return out
    run(core, task_id)
    return out
