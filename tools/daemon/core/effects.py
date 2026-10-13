"""Side effects: every entry of transitions[].side_effects, noop_rules[].side_effects, on_fail.effects and
state_integrity.corruption.effects is {id, args}. The ids are core_contract.expected_outputs.side_effect_ids.

A handler turns one id into a state change and a side_effect_record. Which ids a transition runs, with which
args and in which order, is data. How an id acts on the store and on the adapters is the code below.
"""
import re

from . import lease as lease_mod
from . import usage
from .ports import PreconditionFailed, SpecGap


class Env:
    """What an effect may look at besides the store: the transition row, the event payload, the envelope."""

    def __init__(self, tr=None, payload=None, envelope=None, only_envelope=None, out=None, recs=None):
        self.tr, self.payload, self.envelope = tr, payload or {}, envelope
        self.only_envelope, self.out, self.recs = only_envelope, out, recs or []


def credential_name(core, suffix):
    """The always_revoke entry a side-effect id (revoke_token, revoke_write_credential,
    revoke_preserve_credential) stands for: the one whose name ends with the id's last words."""
    hits = [n for n in core.rules.always_revoke if n.endswith(suffix)]
    core.rules.token_log.add(("side_effect_ids -> handoff_failure_policy.always_revoke", "name suffix: " + suffix))
    if len(hits) != 1:
        raise SpecGap(f"cannot tell which always_revoke entry '{suffix}' is: {hits}")
    return hits[0]


def new_handoff_record(core, task_id, lease, phase, preservation_state):
    keys = []
    for tr in core.rules.transitions:
        for eff in tr.get("side_effects", []):
            m = re.fullmatch(r"handoff_record\.attempts\.([A-Za-z_]\w*)", (eff.get("args") or {}).get("field", ""))
            if eff["id"] == "increment_counter" and m and m.group(1) not in keys:
                keys.append(m.group(1))
    return {"task_id": task_id, "lease_id": lease["lease_id"], "phase": phase,
            "preservation_state": preservation_state, "quiescent_tree_oid": None, "wip_commit_sha": None,
            "attempts": {k: 0 for k in keys}, "restart_count": 0, "token_revoked": False,
            "credentials_revoked": [], "worktree_readonly": False, "failure_log": []}


# ---------------------------------------------------------------- locating counter fields
def _locate(t, field):
    """('task_state.consecutive_failed_tests') -> (container, key)."""
    parts = field.split(".")
    root = parts[0]
    cur = t.get(root)
    if cur is None and root != "lease_generation":
        raise SpecGap(f"counter field has no record to live in: {field}")
    if root == "lease_generation":
        return t, "lease_generation"
    for seg in parts[1:-1]:
        cur = cur[seg]
    return cur, parts[-1]


# ---------------------------------------------------------------- handlers
def h_increment_counter(core, d, task_id, args, ctx, env):
    field = args["field"]
    if field == "lease_generation":
        raise SpecGap("lease_generation changes only inside issue_lease")
    t = d["tasks"][task_id]
    box, key = _locate(t, field)
    if "set" in args:
        box[key] = args["set"]
    else:
        box[key] = (box.get(key) or 0) + 1
    core.rec.side_effect(d, task_id, "increment_counter", field=field, value=box[key])


def h_end_lease(core, d, task_id, args, ctx, env):
    t = d["tasks"][task_id]
    lease = t.get("lease_record")
    if not lease:
        core.rec.diagnostic(d, task_id, "end_lease_without_lease", status=ctx.value(args.get("status")))
        return
    status = ctx.value(args["status"])
    lease["status"] = status
    core.rec.side_effect(d, task_id, "end_lease", lease_id=lease["lease_id"], lease_generation=lease["lease_generation"],
                         status=status)
    listed = {e["id"] for e in (env.tr or {}).get("side_effects", [])}
    for sid in core.rules.get("concurrency.fencing.on_lease_end"):
        if sid in listed:
            continue  # the transition lists it itself; it runs there, once
        run_effect(core, d, task_id, {"id": sid}, Env(tr=env.tr, payload=env.payload, envelope=env.envelope, out=env.out))


def h_terminate_process(core, d, task_id, args, ctx, env):
    t = d["tasks"][task_id]
    lease = t.get("lease_record") or {}
    alive = core.ports.process.alive_count(task_id) > 0
    if alive:
        core.ports.process.terminate_group(task_id)
    core.rec.side_effect(d, task_id, "terminate_process", lease_id=lease.get("lease_id"), terminated=alive)


def _revoke_one(core, d, task_id, sid, suffix):
    t = d["tasks"][task_id]
    hr = t.get("handoff_record")
    lease = t.get("lease_record") or {}
    name = credential_name(core, suffix)
    core.ports.credentials.revoke(name, task_id, lease.get("lease_id"))
    first = hr is None or name not in hr["credentials_revoked"]
    if hr is not None and name not in hr["credentials_revoked"]:
        hr["credentials_revoked"].append(name)
    if first:
        core.rec.side_effect(d, task_id, sid, credential=name, lease_id=lease.get("lease_id"))
    return name


def h_revoke_write_credential(core, d, task_id, args, ctx, env):
    _revoke_one(core, d, task_id, "revoke_write_credential", "write_credential")


def h_revoke_preserve_credential(core, d, task_id, args, ctx, env):
    _revoke_one(core, d, task_id, "revoke_preserve_credential", "preserve_credential")


def h_revoke_token(core, d, task_id, args, ctx, env):
    lease = d["tasks"][task_id].get("lease_record")
    _revoke_one(core, d, task_id, "revoke_token", "token")
    if lease and lease["status"] == "active":
        lease["status"] = "revoked"


def h_revoke_all(core, d, task_id, args, ctx, env):
    t = d["tasks"][task_id]
    hr = t["handoff_record"]
    lease_id = (t.get("lease_record") or {}).get("lease_id")
    names = list(ctx.value(args["which"]))
    fresh = []
    for name in names:
        core.ports.credentials.revoke(name, task_id, lease_id)
        if name not in hr["credentials_revoked"]:
            hr["credentials_revoked"].append(name)
            fresh.append(name)
    core.rec.side_effect(d, task_id, "revoke_all", which=names, newly_revoked=fresh)


def h_worktree_readonly(core, d, task_id, args, ctx, env):
    t = d["tasks"][task_id]
    hr = t.get("handoff_record")
    lease_id = hr["lease_id"] if hr else (t.get("lease_record") or {})["lease_id"]
    path = core.ports.worktree.path_for(task_id, lease_id)
    core.ports.worktree.set_readonly(path)
    if hr is not None:
        hr["worktree_readonly"] = bool(ctx.value(args.get("value", True)))
    core.rec.side_effect(d, task_id, "worktree_readonly", path=path)


def h_record_handoff(core, d, task_id, args, ctx, env):
    t = d["tasks"][task_id]
    hr = t.get("handoff_record") or {}
    lease = t.get("lease_record") or {}
    core.rec.side_effect(d, task_id, "record_handoff", lease_id=lease.get("lease_id"),
                         preservation_state=hr.get("preservation_state"), wip_commit_sha=hr.get("wip_commit_sha"),
                         quiescent_tree_oid=hr.get("quiescent_tree_oid"))


def h_renew_lease(core, d, task_id, args, ctx, env):
    lease = d["tasks"][task_id].get("lease_record")
    if not lease:
        return
    at = ctx.value(args["last_heartbeat_at"])
    lease["last_heartbeat_at"] = at
    lease["expires_at"] = at + core.rules.number("concurrency.lease.ttl_s")
    core.rec.side_effect(d, task_id, "renew_lease", last_heartbeat_at=at, expires_at=lease["expires_at"])


def h_void_outbox(core, d, task_id, args, ctx, env):
    lease_mod.void_pending(core, d, task_id, ctx.value(args["reason"]), only_envelope=env.only_envelope)


def h_record_r_code(core, d, task_id, args, ctx, env):
    code = ctx.value(args["code"])
    d["tasks"][task_id]["task_state"]["return_code"] = code
    core.rec.returned(d, task_id, code)


def h_set_cancelled(core, d, task_id, args, ctx, env):
    d["tasks"][task_id]["task_state"]["cancelled"] = True
    core.rec.side_effect(d, task_id, "set_cancelled")


def h_increment_attempt(core, d, task_id, args, ctx, env):
    ts = d["tasks"][task_id]["task_state"]
    ts["attempt"] += 1
    ts["return_code"] = None
    core.rec.side_effect(d, task_id, "increment_attempt", attempt=ts["attempt"])


def h_create_handoff_record(core, d, task_id, args, ctx, env):
    t = d["tasks"][task_id]
    t["handoff_record"] = new_handoff_record(core, task_id, t["lease_record"], ctx.value(args["phase"]),
                                             ctx.value(args["preservation_state"]))
    core.rec.side_effect(d, task_id, "create_handoff_record", phase=t["handoff_record"]["phase"],
                         preservation_state=t["handoff_record"]["preservation_state"])


def h_request_stop(core, d, task_id, args, ctx, env):
    ts = d["tasks"][task_id]["task_state"]
    if ts["stop_requested_at"] is None:
        ts["stop_requested_at"] = core.clock.now()
    core.rec.side_effect(d, task_id, "request_stop", deadline=ctx.value(args.get("deadline")))


def h_append_failure_log(core, d, task_id, args, ctx, env):
    hr = d["tasks"][task_id]["handoff_record"]
    event = ctx.value(args["event"])
    hr["failure_log"].append({"event": event, "at": core.clock.now(), "reason": env.payload.get("reason")})
    core.rec.side_effect(d, task_id, "append_failure_log", event=event, reason=env.payload.get("reason"))


def h_reset_attempts(core, d, task_id, args, ctx, env):
    hr = d["tasks"][task_id]["handoff_record"]
    for k in hr["attempts"]:
        hr["attempts"][k] = 0
    core.rec.side_effect(d, task_id, "reset_attempts")


def h_set_preservation_state(core, d, task_id, args, ctx, env):
    hr = d["tasks"][task_id]["handoff_record"]
    hr["preservation_state"] = ctx.value(args["value"])
    core.rec.side_effect(d, task_id, "set_preservation_state", value=hr["preservation_state"])


def _stage_from_prose(core, hr, text):
    """transitions[recovery_decision].set_handoff_field(phase) carries a sentence with two stage ids and a
    condition ('isolate 또는 preserve_remote(로컬 커밋 있음)'). Narrowest reading: the stage ids named in the
    sentence, the last one when a local commit exists, the first otherwise. Logged; reported as a gap."""
    stages = core.rules.stages
    named = []
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        if tok in stages and tok not in named:
            named.append(tok)
    if not named:
        raise SpecGap(f"no stage id in {text!r}")
    core.rules.token_log.add(("transitions[].side_effects[set_handoff_field].args.value", "stage ids inside a sentence"))
    return named[-1] if hr["preservation_state"] == "local_committed" else named[0]


def h_set_handoff_field(core, d, task_id, args, ctx, env):
    hr = d["tasks"][task_id]["handoff_record"]
    field = args["field"]
    value = ctx.value(args["value"])
    if field == "phase" and isinstance(value, str) and value not in core.rules.stages:
        value = _stage_from_prose(core, hr, value)
    hr[field] = value
    core.rec.side_effect(d, task_id, "set_handoff_field", field=field, value=value)


def h_resume_from_phase(core, d, task_id, args, ctx, env):
    hr = d["tasks"][task_id]["handoff_record"]
    spec = ctx.value(args["stage"])
    if isinstance(spec, str) and spec in core.rules.stages:
        hr["phase"] = spec
        kept = False
    else:
        # restart_resume[...] holds a procedure sentence for four phases: the phase is kept and the step
        # itself checks what already exists (commit by tree OID, remote ref). Reported as a gap.
        core.rules.token_log.add(("handoff_failure_policy.restart_resume", "procedure sentence: phase kept"))
        kept = True
    core.rec.side_effect(d, task_id, "resume_from_phase", stage=spec if not kept else None, phase=hr["phase"], kept=kept)


def h_issue_lease(core, d, task_id, args, ctx, env):
    reason = ctx.value(args["reason"])
    lease_mod.issue_lease(core, d, task_id, reason, env.tr, env.recs)
    if env.out is not None:
        env.out["post"].append(("issued", task_id))


def h_execute_write(core, d, task_id, args, ctx, env):
    kind = ctx.value(args["kind"])
    core.ports.remote.execute(kind, task_id, dict(env.payload))
    core.rec.side_effect(d, task_id, "execute_write", kind=kind)


def h_record_transition(core, d, task_id, args, ctx, env):
    state = d["tasks"][task_id]["task_state"]["state"]
    core.rec.transition(d, task_id, state, state, env.tr["event"], env.recs)


def h_record_usage(core, d, task_id, args, ctx, env):
    usage.record_result(core, d, task_id, env.envelope or {})


HANDLERS = {
    "increment_counter": h_increment_counter, "end_lease": h_end_lease, "terminate_process": h_terminate_process,
    "revoke_write_credential": h_revoke_write_credential, "revoke_preserve_credential": h_revoke_preserve_credential,
    "revoke_token": h_revoke_token, "revoke_all": h_revoke_all, "worktree_readonly": h_worktree_readonly,
    "record_handoff": h_record_handoff, "renew_lease": h_renew_lease, "void_outbox": h_void_outbox,
    "record_r_code": h_record_r_code, "set_cancelled": h_set_cancelled, "increment_attempt": h_increment_attempt,
    "create_handoff_record": h_create_handoff_record, "request_stop": h_request_stop,
    "append_failure_log": h_append_failure_log, "reset_attempts": h_reset_attempts,
    "set_preservation_state": h_set_preservation_state, "set_handoff_field": h_set_handoff_field,
    "resume_from_phase": h_resume_from_phase, "issue_lease": h_issue_lease, "execute_write": h_execute_write,
    "record_transition": h_record_transition, "record_usage": h_record_usage,
}


def _ctx_for(core, d, task_id, env):
    return core.ctx(d, task_id, event=env.payload, envelope=env.envelope)


def run_effect(core, d, task_id, eff, env):
    sid = eff["id"]
    if sid not in core.rules.get("core_contract.expected_outputs.side_effect_ids"):
        raise SpecGap(f"side effect id not in side_effect_ids: {sid}")
    handler = HANDLERS.get(sid)
    if handler is None:
        raise SpecGap(f"no handler for side effect {sid}")
    handler(core, d, task_id, dict(eff.get("args") or {}), _ctx_for(core, d, task_id, env), env)


def is_before_cond(eff):
    return (eff.get("args") or {}).get("order") == "before_cond"


def run_effects(core, d, task_id, effects, env, skip_before_cond=False):
    for eff in effects or []:
        if skip_before_cond and is_before_cond(eff):
            continue
        run_effect(core, d, task_id, eff, env)
