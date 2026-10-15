"""issue_lease (the only place that changes lease_generation), lease guards, outbox send and resend."""
import re

from . import usage
from .envelope_validator import build_instruction, missing_instruction_fields
from .gate_evaluator import Clockview, Ctx, GuardResult
from .ports import PreconditionFailed


def branch_name(core, task_id, attempt):
    """concurrency.branch_naming: 'task/<task_id>-a<attempt>'."""
    return core.rules.get("concurrency.branch_naming").replace("<task_id>", task_id).replace("<attempt>", str(attempt))


def _candidate_lease(core, d, task_id, reason, lease_id="(new)"):
    t = d["tasks"][task_id]
    ts = t["task_state"]
    now = core.clock.now()
    builder = core.ports.builders.select(task_id, reason, (t.get("lease_record") or {}).get("builder"))
    return {
        "lease_id": lease_id, "task_id": task_id, "lease_generation": t["lease_generation"] + 1,
        "fencing_token": t["lease_generation"] + 1,
        "builder": builder["name"] if builder else None, "runner": builder["runner"] if builder else None,
        "branch": branch_name(core, task_id, ts["attempt"]),
        "base_sha": core.ports.git.base_sha(task_id), "issued_at": now,
        "expires_at": now + core.rules.number("concurrency.lease.ttl_s"),
        "last_heartbeat_at": None, "status": "active",
    }


class _LockView:
    """lease_lock(task_id): the lock row of a task ({} when nobody holds it)."""

    def __init__(self, d):
        self.d = d

    def __call__(self, task_id):
        return self.d.setdefault("lease_lock", {}).get(task_id) or {"task_id": task_id, "holder": None, "acquired_at": None}


def run_guards(core, d, task_id, reason="from_queue"):
    """lease_guards[], in the order the contract lists them. kind=store and kind=core are predicates the core
    evaluates itself; kind=adapter goes to the adapter. Returns a GuardResult."""
    t = d["tasks"][task_id]
    task_def = core.ports.catalog.task(task_id)
    attempt = t["task_state"]["attempt"]
    this = {"task_id": task_id, "branch": branch_name(core, task_id, attempt),
            "conflict_paths": task_def.get("conflict_paths", [])}
    # Count over the leases of the other tasks: this task's own lease is the one being replaced (G29).
    others = [dict(v["lease_record"]) for k, v in d["tasks"].items() if k != task_id and v.get("lease_record")]
    roots = {"this": this, "lease_lock": _LockView(d), "usage_record": usage.UsageView(core, d),
             "lease_record": t.get("lease_record") or {}}

    def valid(_arg):
        cand = _candidate_lease(core, d, task_id, reason)
        inst = build_instruction(core, d, task_id, cand, "(new)")
        return "invalid" if missing_instruction_fields(core, task_id, inst) else "valid"

    roots["clock"] = Clockview(core.clock.now())
    ctx = Ctx(core.rules, roots, funcs={"envelope_validator": valid},
              variables={"task_id": task_id, "next_generation": t["lease_generation"] + 1},
              collections={"lease_record": others, "outbox": t["outbox"]},
              task_of=lambda row: core.ports.catalog.task(row["task_id"]))
    items = []
    for guard in core.rules.view["lease_guards"]:
        kind = guard["kind"]
        if kind == "adapter":
            ok = bool(core.ports.guards.check(guard["id"], {"task_id": task_id, "reason": reason}))
        else:
            ok = ctx.predicate(guard["check"])[0]
        items.append((guard["id"], ok))
    return GuardResult(items)


def issue_lease(core, d, task_id, reason, tr, recs):
    """The one function that issues a lease. Everything else calls this. `tr` is the transition row that issues
    it (its `to` is the state set by the atomic record and its event goes into the transition record)."""
    rules = core.rules
    t = d["tasks"][task_id]
    if reason not in rules.issue_reasons:
        raise PreconditionFailed([f"reason not allowed: {reason}"])
    if tr is None:
        raise PreconditionFailed(["issue_lease needs the transition that issues it"])
    ctx = core.ctx(d, task_id, reason=reason)
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
    if core.ports.builders.select(task_id, reason, prev.get("builder")) is None:
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
    # effects_atomic, in the order the contract lists them. All of them are written in this one transaction.
    for eff in rules.get("core_contract.operations.issue_lease.effects_atomic"):
        sid = eff["id"]
        if sid == "increment_counter":
            if eff["args"]["field"] != "lease_generation":
                raise PreconditionFailed([f"issue_lease increments only lease_generation, not {eff['args']['field']}"])
            t["lease_generation"] = new_gen
        elif sid == "create_lease_record":
            lease["expires_at"] = ctx.value(eff["args"]["expires_at"])
            lease["status"] = ctx.value(eff["args"]["status"])
            t["lease_record"] = lease
        elif sid == "create_outbox":
            t["outbox"].append(row)
        elif sid == "set_task_state":
            t["task_state"]["state"] = tr["to"]
        elif sid == "record_transition":
            core.rec.transition(d, task_id, tr["from"], tr["to"], tr["event"], recs or [])
        else:
            raise PreconditionFailed([f"issue_lease effect not understood: {sid}"])
    usage.attach_envelope(core, d, task_id, new_gen, row["envelope_id"])
    core.rec.side_effect(d, task_id, "issue_lease", reason=reason, lease_id=lease["lease_id"],
                         lease_generation=new_gen, envelope_id=row["envelope_id"], builder=lease["builder"])
    return lease, row


def prune_inbox_seen(t, keep_generation):
    """Drop the idempotency keys of generations older than keep_generation. lease_matches runs before not_seen, so
    an envelope of an older generation is late whatever inbox_seen holds: those keys can never be read again."""
    seen = t["inbox_seen"]
    for key in [k for k, v in seen.items() if v["lease_generation"] < keep_generation]:
        del seen[key]
    return len(seen)


# ---- outbox
def void_pending(core, d, task_id, reason, only_envelope=None):
    t = d["tasks"][task_id]
    for row in t["outbox"]:
        if row["status"] == "pending" and (only_envelope is None or row["envelope_id"] == only_envelope):
            row["status"] = "void"
            row["void_reason"] = reason
            core.rec.side_effect(d, task_id, "void_outbox", envelope_id=row["envelope_id"], reason=reason)


def then_events(core, where, text):
    """on_fail.<key>.then is a sentence; the event names that stand in it are the follow-up events."""
    known = core.rules.known_events
    names = [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text or "") if w in known]
    for n in names:
        core.rules.token_log.add((where, "event name inside a sentence: " + n))
    return names


def resend_outbox(core, task_id, trigger):
    """core_contract.operations.resend_outbox. Same envelope_id, only if every check passes."""
    from . import effects, recovery
    spec = core.rules.get("core_contract.operations.resend_outbox")
    results = []
    pending = [r["envelope_id"] for r in core.snapshot()["tasks"][task_id]["outbox"] if r["status"] == "pending"]
    for env_id in pending:
        action = None
        follow = []
        with core.ports.store.transaction() as d:
            t = d["tasks"][task_id]
            row = next(r for r in t["outbox"] if r["envelope_id"] == env_id)
            if row["status"] != "pending":
                continue
            ctx = core.ctx(d, task_id, row=row)
            failed_key, recs = None, []
            for chk in spec["checks"]:
                ok, rec = ctx.predicate(chk["pred"])
                recs.append(rec)
                if not ok:
                    failed_key = chk["fail_key"]
                    break
            if failed_key is None:
                lease = t["lease_record"]
                instruction = build_instruction(core, d, task_id, lease, row["envelope_id"])
                core.rec.intent(d, task_id, "send_envelope", envelope_id=env_id, trigger=trigger)
                action = ("send", instruction)
            else:
                on_fail = spec["on_fail"][failed_key]
                effects.run_effects(core, d, task_id, on_fail.get("effects"), effects.Env(only_envelope=env_id))
                follow = then_events(core, f"core_contract.operations.resend_outbox.on_fail.{failed_key}.then", on_fail.get("then"))
                action = (failed_key, None)
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
        elif follow:
            with core.ports.store.transaction() as d:
                recovery.follow_up(core, d, task_id, follow, {"detect_id": recovery.detect_id(core, d, task_id)})
        results.append((env_id, action[0]))
    return results
