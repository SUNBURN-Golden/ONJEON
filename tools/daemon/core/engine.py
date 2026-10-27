"""DaemonCore: the shared transition and validation core. Callers differ only in the `ports` they supply."""
from . import effects, fencing, handoff, lease as lease_mod, observation, recovery, transition_engine, usage
from .envelope_validator import build_instruction
from .gate_evaluator import Clockview, Ctx, Lazy
from .ports import PreconditionFailed, SimulatedCrash, SpecGap
from .records import Recorder

# core_contract.operations.handle_event.routes: the operations an event may be routed to
_ROUTES = ("restart_recovery", "accept_envelope", "fenced_write")


def _reads_clock(cond):
    for p in cond or []:
        if p.get("field") == "clock.now":
            return True
        if isinstance(p.get("value"), list) and _reads_clock([x for x in p["value"] if isinstance(x, dict)]):
            return True
    return False


class _GuardWait(Exception):
    """Raised inside a store transaction to discard it (operations.issue_lease.on_guard_wait)."""

    def __init__(self, out, kept):
        super().__init__("guard_wait")
        self.out, self.kept = out, kept


class DaemonCore:
    def __init__(self, rules, ports):
        self.rules = rules
        self.ports = ports
        self.clock = ports.clock
        self.rec = Recorder(rules, ports.clock)
        self.effects = effects
        # core_contract.daemon_instance: generated at process start, never reused (lease_lock.holder)
        self.instance_id = ports.ids.new_id()
        if rules.unmatched_reads:
            raise SpecGap(f"core_contract.reads lists fields the file does not have: {rules.unmatched_reads}")
        self.known_events = rules.known_events
        payload_names = set(rules.get("core_contract.events_in.payloads").keys())
        if payload_names - self.known_events:
            raise SpecGap(f"events_in.payloads names events outside event_catalog: {sorted(payload_names - self.known_events)}")
        self.issue_reasons = rules.issue_reasons
        self.entry = rules.get("core_contract.operations.handle_event")
        routed, bare = set(self.entry["routes"]), set(self.entry["without_envelope"])
        if (routed | bare) - self.known_events or routed & bare or set(self.entry["routes"].values()) - set(_ROUTES):
            raise SpecGap("operations.handle_event: routes and without_envelope must be disjoint catalog events "
                          f"and routes must name {sorted(_ROUTES)}")
        lease_mod.check_mark_sent(rules)
        self.guard_wait = lease_mod.check_guard_wait(rules)

    # ---- state access
    def snapshot(self):
        return self.ports.store.snapshot()

    def register_task(self, task_id, state="blocked", decisions=()):
        with self.ports.store.transaction() as d:
            d["tasks"][task_id] = {
                "task_state": {"task_id": task_id, "state": state, "attempt": 1, "consecutive_failed_tests": 0,
                               "stop_requested_at": None, "cancelled": False, "return_code": None,
                               "decisions_recorded": list(decisions)},
                "lease_generation": 0, "lease_record": None, "outbox": [], "inbox_seen": {}, "handoff_record": None,
            }

    def current_lease(self, task_id):
        """daemon.current_lease(task_id): what a builder adapter checks an instruction against."""
        t = self.snapshot()["tasks"].get(task_id)
        return dict((t or {}).get("lease_record") or {})

    # ---- evaluation context
    def issuing_reason(self, state):
        """The issue_lease reason of the row that issues a lease out of `state` (None if no row does)."""
        for tr in self.rules.transitions:
            if tr["from"] == state:
                r = transition_engine._issue_reason(tr)
                if r is not None:
                    return r
        return None

    def ctx(self, d, task_id, row=None, event=None, envelope=None, funcs=None, reason=None, extra_vars=None):
        t = d["tasks"][task_id]
        lease = t["lease_record"] or {}
        if reason is None:
            reason = self.issuing_reason(t["task_state"]["state"]) or "from_queue"
        if row is None:
            # state_integrity.corruption.bindings.outbox.in_field_path: the latest row of the current lease
            mine = [r for r in t["outbox"] if r["lease_id"] == lease.get("lease_id")]
            row = mine[-1] if mine else {}
        ev = dict(event or {})
        ev["at"] = self.clock.now()  # events_in.schema: at is the clock time of the event
        env = envelope if envelope is not None else {}

        def instruction():
            if not lease:
                return {}
            rows = [r for r in t["outbox"] if r["lease_id"] == lease["lease_id"]]
            return build_instruction(self, d, task_id, lease, rows[-1]["envelope_id"] if rows else "(none)")

        task_def = self.ports.catalog.task(task_id)
        roots = {"task_state": t["task_state"], "lease_record": lease,
                 "handoff_record": t["handoff_record"] or {}, "outbox": row,
                 "clock": Clockview(self.clock.now()), "event": ev, "envelope": env, "signal": env, "report": env,
                 "request": env, "daemon": self, "instruction": Lazy(instruction), "task": task_def,
                 "usage_record": usage.UsageView(self, d)}
        prev = lease.get("builder")
        roots["this"] = {"task_id": task_id, "conflict_paths": task_def.get("conflict_paths", []),
                         "branch": lease_mod.branch_name(self, task_id, t["task_state"]["attempt"])}
        base = {
            "lease_guards": lambda _a: lease_mod.run_guards(self, d, task_id, reason),
            "builder_available": lambda a: self.ports.builders.available(a, prev),
            "envelope_validator": lambda a: lease_mod.candidate_validation(self, d, task_id, reason)[0],
            "prereq_tasks_in": lambda a: observation.prereq_tasks_in(self, d, task_id, a),
        }
        base.update(funcs or {})
        journal = []
        for rec in d["journal"]:
            if rec.get("task_id") == task_id:
                flat = dict(rec)
                flat.update(rec.get("args") or {})
                journal.append(flat)
        own = [dict(lease)] if lease else []
        variables = {"task_id": task_id, "next_generation": t["lease_generation"] + 1}
        variables.update(extra_vars or {})
        return Ctx(self.rules, roots, base, variables,
                   collections={"lease_record": own, "outbox": t["outbox"], "journal": journal},
                   task_of=lambda r: self.ports.catalog.task(r["task_id"]))

    # ---- transactions
    def _txn(self, task_id, fn):
        """One store transaction; journal_text secret hits become secret_detected before it commits.

        A lease guard that only waits (outcome `guard_wait`) discards the whole transaction
        (operations.issue_lease.on_guard_wait): the before_cond counter, inbox_seen, the usage slot the guard prepared
        and the result's usage are not kept, so a redelivery of the same envelope is processed as new. Only the
        keep_diagnostics records of that transaction are written again, in a transaction of their own."""
        spec = self.guard_wait
        try:
            with self.ports.store.transaction() as d:
                start = len(d["journal"])
                out = fn(d)
                if out and out.get("guard_wait"):
                    kept = [r for r in d["journal"][start:]
                            if r["kind"] == "diagnostic_record" and r["what"] in spec["keep_diagnostics"]]
                    raise _GuardWait(out, kept)
                transition_engine.settle_secrets(self, d)
            return out
        except _GuardWait as wait:
            out, kept = wait.out, wait.kept
        with self.ports.store.transaction() as d:
            for r in kept:
                self.rec.diagnostic(d, r["task_id"], r["what"],
                                    **{k: v for k, v in r.items() if k not in ("seq", "kind", "task_id", "what", "at")})
            self.rec.diagnostic(d, task_id, spec["diagnostic"], event=out["guard_wait"]["event"],
                                failed=out["guard_wait"]["failed"], envelope_id=out["guard_wait"].get("envelope_id"))
            transition_engine.settle_secrets(self, d)
        out = dict(out, accepted=False, applied=False, transition=None, post=[], emitted=[], reason=spec["result"])
        return out

    def _issues_lease(self, task_id, name):
        t = self.snapshot()["tasks"].get(task_id)
        if t is None:
            return False
        state = t["task_state"]["state"]
        return any(tr["event"] == name and tr["from"] in (state, "*") and tr.get("guard")
                   for tr in self.rules.transitions)

    def _locked(self, task_id, fn):
        """concurrency.lease_issue.lock around a lease-issuing operation: acquired before the guards, released
        after the transaction, on failure and on error. A crashed process releases nothing."""
        lease_mod.acquire_lock(self, task_id)
        self.ports.faults.check("lease_lock:acquired")
        crashed = False
        try:
            return fn()
        except SimulatedCrash:
            crashed = True
            raise
        finally:
            if not crashed:
                lease_mod.release_lock(self, task_id)

    # ---- entry points
    def handle_event(self, ev):
        """core_contract.operations.handle_event: a routed event goes to its checked operation; an event on
        without_envelope reaches the transition table; any other name is rejected (on_reject), state unchanged."""
        name = ev["event"]
        route = self.entry["routes"].get(name)
        if route == "restart_recovery":
            return self.restart()
        task_id, payload = ev["task_id"], dict(ev.get("payload") or {})
        if route == "accept_envelope":
            return self.submit_envelope(task_id, name, payload)
        if route == "fenced_write":
            kind = "push" if name == "push_requested" else "pr_update"
            out = self._txn(task_id, lambda d: fencing.fenced_write(self, d, task_id, name, kind, payload))
            self._after_commit(out)
            return out
        if name not in self.entry["without_envelope"]:
            return self._txn(task_id, lambda d: fencing.reject_without_envelope(self, d, task_id, name, self.entry["on_reject"]))

        def run():
            return self._txn(task_id, lambda d: transition_engine.apply_event(self, d, task_id, name, payload))

        out = self._locked(task_id, run) if self._issues_lease(task_id, name) else run()
        self._after_commit(out)
        return out

    def submit_envelope(self, task_id, msg_type, envelope):
        def run():
            return self._txn(task_id, lambda d: fencing.accept(self, d, task_id, msg_type, envelope))

        lease_event = msg_type == "result" and self._issues_lease(task_id, fencing.event_for(self, msg_type, envelope, task_id))
        out = self._locked(task_id, run) if lease_event else run()
        self._after_commit(out)
        return out

    def issue_lease(self, task_id, reason):
        """Direct call of the one issuing function: it needs the row that leads out of the task's state."""
        def run():
            with self.ports.store.transaction() as d:
                tr = transition_engine.row_for_issue(self, d, task_id, reason)
                if tr is None:
                    raise PreconditionFailed([f"no transition issues a lease for {reason} from the current state"])
                lease, _row = lease_mod.issue_lease(self, d, task_id, reason, tr, [])
            return lease

        lease = self._locked(task_id, run)
        self.ports.faults.check("issue_lease:committed")
        return lease

    def observe(self, task_id, kind, **payload):
        """An observation from outside the builder channel (CI, pull request, review, audit, decision record).
        Observations never issue a lease: lease_granted stays a separate event."""
        return observation.observe(self, task_id, kind, payload)

    def evaluate_prereqs(self, task_id):
        return observation.evaluate_prereqs(self, task_id)

    def tick(self):
        """Clock-driven events. Normal expiry (state_integrity.normal_expiry), then the hard stop events
        (core_contract.operations.hard_stop.trigger_events) whose row from the current state compares clock.now."""
        triggers = self.rules.get("core_contract.operations.hard_stop.trigger_events").values()
        for task_id in sorted(self.snapshot()["tasks"]):
            with self.ports.store.transaction() as d:
                if recovery.normal_expiry_due(self, d, task_id):
                    recovery.expire(self, d, task_id)
                    transition_engine.settle_secrets(self, d)
                    continue
                state = d["tasks"][task_id]["task_state"]["state"]
                names = []
                for trig in triggers:
                    if state not in trig["states"]:
                        continue
                    for name in (trig["event"], trig.get("then")):
                        if name and name not in names:
                            names.append(name)
                for name in names:
                    rows = [tr for tr in self.rules.transitions if tr["event"] == name and tr["from"] == state]
                    if rows and all(_reads_clock(tr.get("cond")) for tr in rows):
                        if transition_engine.try_event(self, d, task_id, name, {}):
                            break
                transition_engine.settle_secrets(self, d)

    def retry_usage(self):
        return usage.retry_pending(self)

    def restart(self):
        post = recovery.restart_recovery(self)
        for kind, task_id in post:
            if kind == "restart_handoff":
                handoff.resume(self, task_id)
        return {"applied": False, "restart": True}

    def _after_commit(self, out):
        for kind, task_id in out.get("post", []):
            if kind == "issued":
                self.ports.faults.check("issue_lease:committed")
                lease_mod.resend_outbox(self, task_id, "send")
            elif kind == "handoff":
                handoff.run(self, task_id)
        for emitted in out.get("emitted", []):
            self._after_commit(emitted)
