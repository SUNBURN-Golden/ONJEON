"""issue_lease (the only place that changes lease_generation), guards, outbox send/resend, expiry helpers."""
import re

from .envelope_validator import build_instruction, missing_instruction_fields
from .gate_evaluator import GuardResult
from .ports import PreconditionFailed


def issue_reasons(rules):
    text = rules.get("core_contract.operations.issue_lease.inputs")[1]
    m = re.search(r"\{([^}]*)\}", text)
    rules.token_log.add(("core_contract.operations.issue_lease.inputs", "reason set in braces"))
    return [x.strip() for x in m.group(1).split(",")]


def _candidate_lease(core, d, task_id, reason, lease_id="(new)"):
    t = d["tasks"][task_id]
    ts = t["task_state"]
    now = core.clock.now()
    builder = core.ports.builders.select(task_id, reason, (t.get("lease_record") or {}).get("builder"))
    return {
        "lease_id": lease_id, "task_id": task_id, "lease_generation": t["lease_generation"] + 1,
        "fencing_token": t["lease_generation"] + 1,
        "builder": builder["name"] if builder else None, "runner": builder["runner"] if builder else None,
        "branch": core.ports.catalog.branch_for(task_id, ts["attempt"]),
        "base_sha": core.ports.git.base_sha(task_id), "issued_at": now,
        "expires_at": now + core.rules.number("concurrency.lease.ttl_s"),
        "last_heartbeat_at": None, "status": "active",
    }


def run_guards(core, d, task_id, reason="initial"):
    """lease_guards, in the order the contract lists them. The names come from the data; the checks
    that need the outside world are adapter calls, instruction_envelope_valid is the core's own."""
    t = d["tasks"][task_id]
    task_def = core.ports.catalog.task(task_id)
    attempt = t["task_state"]["attempt"]
    info = {"task_id": task_id, "attempt": attempt, "branch": core.ports.catalog.branch_for(task_id, attempt),
            "conflict_paths": task_def.get("conflict_paths", []), "snapshot": d}
    items = []
    for entry in core.rules.view["lease_guards"]:
        name = core.rules.token("lease_guards", r"^[A-Za-z_][A-Za-z0-9_]*", entry)
        if name == "instruction_envelope_valid":
            cand = _candidate_lease(core, d, task_id, reason)
            inst = build_instruction(core, d, task_id, cand, "(new)")
            ok = not missing_instruction_fields(core, task_id, inst)
        else:
            ok = bool(core.ports.guards.check(name, info))
        items.append((entry, ok))
    return GuardResult(items)


def issue_lease(core, d, task_id, reason):
    """The one function that issues a lease. Everything else calls this."""
    rules = core.rules
    t = d["tasks"][task_id]
    if reason not in core.issue_reasons:
        raise PreconditionFailed([f"reason not allowed: {reason}"])
    ctx = core.ctx(d, task_id)
    failures = []
    for pre in rules.get("core_contract.operations.issue_lease.preconditions"):
        if "when_reason" in pre and pre["when_reason"] != reason:
            continue
        ok, rec = ctx.predicate({k: pre[k] for k in ("field", "op", "value")})
        if not ok:
            failures.append(rec)
    if failures:
        raise PreconditionFailed(failures)
    prev = t.get("lease_record") or {}
    builder = core.ports.builders.select(task_id, reason, prev.get("builder"))
    if builder is None:
        raise PreconditionFailed(["no builder"])
    now = core.clock.now()
    new_gen = t["lease_generation"] + 1
    lease = _candidate_lease(core, d, task_id, reason, lease_id=core.ports.ids.new_id())
    row = {"envelope_id": core.ports.ids.new_id(), "task_id": task_id, "lease_id": lease["lease_id"],
           "lease_generation": new_gen, "envelope_kind": "instruction", "status": "pending",
           "created_at": now, "sent_at": None, "void_reason": None}
    inst = build_instruction(core, d, task_id, lease, row["envelope_id"])
    missing = missing_instruction_fields(core, task_id, inst)
    if missing:
        raise PreconditionFailed([f"instruction fields missing: {missing}"])
    core.ports.faults.check("issue_lease:staged")
    t["lease_generation"] = new_gen
    t["lease_record"] = lease
    t["outbox"].append(row)
    core.rec.side_effect(d, task_id, "issue_lease", reason=reason, lease_id=lease["lease_id"],
                         lease_generation=new_gen, envelope_id=row["envelope_id"], builder=lease["builder"])
    return lease, row


# ---- outbox
def void_pending(core, d, task_id, reason, only_envelope=None):
    t = d["tasks"][task_id]
    for row in t["outbox"]:
        if row["status"] == "pending" and (only_envelope is None or row["envelope_id"] == only_envelope):
            row["status"] = "void"
            row["void_reason"] = reason
            core.rec.side_effect(d, task_id, "void_outbox", envelope_id=row["envelope_id"], reason=reason)


def classify_resend_failure(recs, lease, ts):
    failed = {r["field"] for r in recs if not r["result"]}
    if "outbox.status" in failed:
        return "not_pending", None
    if failed & {"lease_record.lease_id", "lease_record.lease_generation"}:
        return "generation_or_lease_mismatch", None
    if "task_state.cancelled" in failed or ts.get("state") == "cancelled" or ts.get("cancelled"):
        return "revoked_or_cancelled", "cancelled"
    if lease.get("status") == "expired" or (lease.get("status") == "active" and "clock.now" in failed):
        return "expired", "expired"
    return "revoked_or_cancelled", "revoked"


def resend_outbox(core, task_id, trigger):
    """core_contract.operations.resend_outbox. Same envelope_id, only if every check in
    state_integrity.resend_same_envelope_id_only_if holds."""
    rules = core.rules
    checks = rules.get("state_integrity.resend_same_envelope_id_only_if")
    results = []
    pending = [r["envelope_id"] for r in core.snapshot()["tasks"][task_id]["outbox"] if r["status"] == "pending"]
    for env_id in pending:
        action = None
        with core.ports.store.transaction() as d:
            t = d["tasks"][task_id]
            row = next(r for r in t["outbox"] if r["envelope_id"] == env_id)
            if row["status"] != "pending":
                continue
            ctx = core.ctx(d, task_id, row=row)
            ok, recs = ctx.all(checks)
            if ok:
                lease = t["lease_record"]
                instruction = build_instruction(core, d, task_id, lease, row["envelope_id"])
                core.rec.intent(d, task_id, "send_envelope", envelope_id=env_id, trigger=trigger)
                action = ("send", instruction)
            else:
                kind, reason = classify_resend_failure(recs, t.get("lease_record") or {}, t["task_state"])
                if kind == "generation_or_lease_mismatch":
                    action = ("corruption", None)
                else:
                    void_pending(core, d, task_id, reason, only_envelope=env_id)
                    action = (kind, reason)
        if action[0] == "send":
            core.ports.sender.send(task_id, action[1])
            core.ports.faults.check("resend:after_send")
            with core.ports.store.transaction() as d:
                t = d["tasks"][task_id]
                row = next(r for r in t["outbox"] if r["envelope_id"] == env_id)
                row["status"] = "sent"
                row["sent_at"] = core.clock.now()
                core.rec.side_effect(d, task_id, "send_envelope", envelope_id=env_id,
                                     lease_generation=row["lease_generation"], kind="instruction", trigger=trigger)
                core.rec.result(d, task_id, "send_envelope", "sent", envelope_id=env_id)
        elif action[0] == "corruption":
            from . import recovery
            with core.ports.store.transaction() as d:
                recovery.handle_corruption(core, d, task_id, why="outbox/lease mismatch found while resending")
        elif action[0] == "expired":
            from . import recovery
            with core.ports.store.transaction() as d:
                recovery.expire(core, d, task_id)
        results.append((env_id, action[0]))
    return results
