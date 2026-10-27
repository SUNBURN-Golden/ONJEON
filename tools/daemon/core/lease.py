"""issue_lease (the only place that changes lease_generation), the lease lock, lease guards, outbox send and resend."""
from . import usage
from .envelope_validator import build_instruction, validate_instruction
from .gate_evaluator import Clockview, Ctx, GuardResult
from .ports import PreconditionFailed, SpecGap


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


# ---------------------------------------------------------------- lease_lock (concurrency.lease_issue.lock, G45)
def _lock_spec(core):
    return core.rules.get("concurrency.lease_issue.lock")


def acquire_lock(core, task_id):
    """acquire: before the first lease guard is evaluated, in its own committed write. A row held by another
    instance is left alone (lock_acquired then fails and the evaluator waits)."""
    spec = _lock_spec(core)["acquire"]["writes"]
    with core.ports.store.transaction() as d:
        row = d.setdefault("lease_lock", {}).get(task_id) or {"task_id": task_id, "holder": None, "acquired_at": None}
        if row["holder"] is None:
            ctx = core.ctx(d, task_id) if task_id in d["tasks"] else None
            row = {"task_id": task_id, "holder": core.instance_id,
                   "acquired_at": ctx.value(spec["acquired_at"]) if ctx else core.clock.now()}
            d["lease_lock"][task_id] = row
        return row["holder"] == core.instance_id


def release_lock(core, task_id):
    """release: after the issue_lease transaction, on a failed guard or precondition, on error. Only our own row."""
    with core.ports.store.transaction() as d:
        row = d.setdefault("lease_lock", {}).get(task_id)
        if row and row["holder"] == core.instance_id:
            d["lease_lock"][task_id] = {"task_id": task_id, "holder": None, "acquired_at": None}


def clear_foreign_locks(core):
    """lock.restart: at restart, rows whose holder is not this (new) instance are cleared."""
    with core.ports.store.transaction() as d:
        for task_id, row in list(d.setdefault("lease_lock", {}).items()):
            if row.get("holder") not in (None, core.instance_id):
                d["lease_lock"][task_id] = {"task_id": task_id, "holder": None, "acquired_at": None}
                core.rec.diagnostic(d, task_id, "lease_lock_cleared_at_restart")


class _LockView:
    """lease_lock(task_id): the lock row of a task. lock.self.means: a holder equal to this instance's id reads
    as "self"."""

    def __init__(self, core, d):
        self.core, self.d = core, d

    def __call__(self, task_id):
        row = dict(self.d.setdefault("lease_lock", {}).get(task_id) or {"task_id": task_id, "holder": None, "acquired_at": None})
        if row["holder"] is not None and row["holder"] == self.core.instance_id:
            row["holder"] = "self"
        return row


def candidate_validation(core, d, task_id, reason):
    """envelope_validator(instruction) for the instruction the next lease would carry: (result, missing_fields)."""
    cand = _candidate_lease(core, d, task_id, reason)
    inst = build_instruction(core, d, task_id, cand, "(new)")
    return validate_instruction(core, task_id, inst, d["tasks"][task_id]["task_state"]["decisions_recorded"])


def run_guards(core, d, task_id, reason="from_queue"):
    """lease_guards[], in the order the contract lists them. kind=store and kind=core are predicates the core
    evaluates itself; kind=adapter goes to the adapter. Returns a GuardResult; `missing_fields` carries what the
    envelope validator found (lease_guards[].on_fail payload)."""
    t = d["tasks"][task_id]
    task_def = core.ports.catalog.task(task_id)
    attempt = t["task_state"]["attempt"]
    this = {"task_id": task_id, "branch": branch_name(core, task_id, attempt),
            "conflict_paths": task_def.get("conflict_paths", [])}
    # The guard predicates name their own scope (task_id != this.task_id, G29): the collection is every lease.
    leases = [dict(v["lease_record"]) for v in d["tasks"].values() if v.get("lease_record")]
    roots = {"this": this, "lease_lock": _LockView(core, d), "usage_record": usage.UsageView(core, d),
             "lease_record": t.get("lease_record") or {}}
    found = {}

    def valid(_arg):
        result, missing = candidate_validation(core, d, task_id, reason)
        found["missing_fields"] = missing
        return result

    roots["clock"] = Clockview(core.clock.now())
    items = []
    for guard in core.rules.view["lease_guards"]:
        kind = guard["kind"]
        if kind == "adapter":
            ok = bool(core.ports.guards.check(guard["id"], {"task_id": task_id, "reason": reason,
                                                            "previous": (t.get("lease_record") or {}).get("builder")}))
        else:
            ctx = Ctx(core.rules, roots, funcs={"envelope_validator": valid},
                      variables={"task_id": task_id, "next_generation": t["lease_generation"] + 1},
                      collections={"lease_record": leases, "outbox": t["outbox"]},
                      task_of=lambda row: core.ports.catalog.task(row["task_id"]),
                      relation=(guard.get("conflict_match") or {}).get("relation"))
            ok = ctx.predicate(guard["check"])[0]
        items.append((guard["id"], ok))
    gr = GuardResult(items)
    gr.missing_fields = found.get("missing_fields", [])
    return gr


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
    result, missing = validate_instruction(core, task_id, inst, t["task_state"]["decisions_recorded"])
    if result != "valid":
        raise PreconditionFailed([f"instruction invalid: {missing}"])
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


def check_mark_sent(rules):
    """At core start: resend_outbox.mark_sent.compare_and_set names exactly one of resend_outbox.checks, `set` writes
    the status, and on_conflict writes nothing (a conflicting row is never overwritten)."""
    spec = rules.get("core_contract.operations.resend_outbox")
    mark = spec.get("mark_sent") or {}
    ids = [c["id"] for c in spec["checks"]]
    conflict = mark.get("on_conflict") or {}
    if (ids.count(mark.get("compare_and_set")) != 1 or "status" not in (mark.get("set") or {})
            or conflict.get("writes") != [] or not conflict.get("diagnostic") or not conflict.get("result")):
        raise SpecGap("operations.resend_outbox.mark_sent: compare_and_set must name one of checks[].id, set must "
                      "write status, on_conflict must have writes [] and a diagnostic and a result")


def _mark_sent(core, d, task_id, row, spec, trigger):
    """resend_outbox.mark_sent: compare-and-set. The send ran outside any transaction, so an expiry, cancel or
    corruption (void) or another send (sent) may have changed the row since the checks passed. The check named by
    compare_and_set is evaluated again in this transaction; if it fails the row is left as it is."""
    mark = spec["mark_sent"]
    cas, = [c for c in spec["checks"] if c["id"] == mark["compare_and_set"]]
    ctx = core.ctx(d, task_id, row=row)
    ok, rec = ctx.predicate(cas["pred"])
    env_id = row["envelope_id"]
    if not ok:
        conflict = mark["on_conflict"]
        core.rec.diagnostic(d, task_id, conflict["diagnostic"], envelope_id=env_id, status=row["status"],
                            void_reason=row["void_reason"], trigger=trigger, check=rec)
        core.rec.result(d, task_id, "send_envelope", conflict["result"], envelope_id=env_id)
        return False
    for key, expr in mark["set"].items():
        row[key] = ctx.value(expr)
    core.rec.side_effect(d, task_id, "send_envelope", envelope_id=env_id,
                         lease_generation=row["lease_generation"], kind="instruction", trigger=trigger)
    core.rec.result(d, task_id, "send_envelope", row["status"], envelope_id=env_id)
    return True


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
                follow = list(on_fail.get("then_events") or [])  # G43
                action = (failed_key, None)
        if action[0] == "send":
            core.ports.sender.send(task_id, action[1])
            core.ports.faults.check("resend:after_send")
            with core.ports.store.transaction() as d:
                t = d["tasks"][task_id]
                row = next(r for r in t["outbox"] if r["envelope_id"] == env_id)
                if not _mark_sent(core, d, task_id, row, spec, trigger):
                    action = ("not_marked", None)
        elif follow:
            with core.ports.store.transaction() as d:
                recovery.follow_up(core, d, task_id, follow, {"detect_id": recovery.detect_id(core, d, task_id)})
        results.append((env_id, action[0]))
    return results
