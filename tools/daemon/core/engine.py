"""DaemonCore: the shared transition and validation core. Callers differ only in the `ports` they supply."""
from . import effects, envelope_validator, fencing, handoff, lease as lease_mod, recovery, transition_engine, usage
from .gate_evaluator import Clockview, Ctx, Lazy
from .ports import PreconditionFailed, SpecGap
from .records import Recorder


class DaemonCore:
    def __init__(self, rules, ports):
        self.rules = rules
        self.ports = ports
        self.clock = ports.clock
        self.rec = Recorder(rules, ports.clock)
        self.effects = effects
        if rules.unmatched_reads:
            raise SpecGap(f"core_contract.reads lists fields the file does not have: {rules.unmatched_reads}")
        self.known_events = rules.known_events
        payload_names = set(rules.get("core_contract.events_in.payloads").keys())
        if payload_names - self.known_events:
            raise SpecGap(f"events_in.payloads names events outside event_catalog: {sorted(payload_names - self.known_events)}")
        self.issue_reasons = rules.issue_reasons

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
    def ctx(self, d, task_id, row=None, event=None, envelope=None, funcs=None, reason="from_queue"):
        t = d["tasks"][task_id]
        lease = t["lease_record"] or {}
        if row is None:
            # the outbox row of the current lease (state_integrity predicates talk about "the" outbox row)
            mine = [r for r in t["outbox"] if r["lease_id"] == lease.get("lease_id")]
            row = mine[-1] if mine else {}
        ev = dict(event or {})
        ev["at"] = self.clock.now()  # events_in.schema: at is the clock time of the event
        env = envelope if envelope is not None else {}

        def instruction():
            if not lease:
                return {}
            rows = [r for r in t["outbox"] if r["lease_id"] == lease["lease_id"]]
            return envelope_validator.build_instruction(self, d, task_id, lease, rows[-1]["envelope_id"] if rows else "(none)")

        roots = {"task_state": t["task_state"], "lease_record": lease,
                 "handoff_record": t["handoff_record"] or {}, "outbox": row,
                 "clock": Clockview(self.clock.now()), "event": ev, "envelope": env, "signal": env, "report": env,
                 "request": env, "daemon": self, "instruction": Lazy(instruction),
                 "usage_record": usage.UsageView(self, d)}
        prev = lease.get("builder")
        task_def = self.ports.catalog.task(task_id)
        roots["this"] = {"task_id": task_id, "conflict_paths": task_def.get("conflict_paths", []),
                         "branch": lease_mod.branch_name(self, task_id, t["task_state"]["attempt"])}
        base = {
            "lease_guards": lambda _a: lease_mod.run_guards(self, d, task_id, reason),
            "builder_available": lambda a: self.ports.builders.available(a, prev),
            "envelope_validator": lambda a: self._validate_instruction(d, task_id, reason),
        }
        base.update(funcs or {})
        journal = []
        for rec in d["journal"]:
            if rec.get("task_id") == task_id:
                flat = dict(rec)
                flat.update(rec.get("args") or {})
                journal.append(flat)
        own = [dict(lease)] if lease else []
        return Ctx(self.rules, roots, base, {"task_id": task_id, "next_generation": t["lease_generation"] + 1},
                   collections={"lease_record": own, "outbox": t["outbox"], "journal": journal},
                   task_of=lambda r: self.ports.catalog.task(r["task_id"]))

    def _validate_instruction(self, d, task_id, reason):
        cand = lease_mod._candidate_lease(self, d, task_id, reason)
        inst = envelope_validator.build_instruction(self, d, task_id, cand, "(new)")
        return "invalid" if envelope_validator.missing_instruction_fields(self, task_id, inst) else "valid"

    # ---- entry points
    def handle_event(self, ev):
        name = ev["event"]
        if name == "daemon_restart":
            return self.restart()
        task_id, payload = ev["task_id"], dict(ev.get("payload") or {})
        if name == "fence_violation":
            return self.submit_envelope(task_id, "fence_violation", payload)
        if name in ("push_requested", "pr_update_requested"):
            kind = "push" if name == "push_requested" else "pr_update"
            with self.ports.store.transaction() as d:
                out = fencing.fenced_write(self, d, task_id, name, kind, payload)
            self._after_commit(out)
            return out
        with self.ports.store.transaction() as d:
            out = transition_engine.apply_event(self, d, task_id, name, payload)
        self._after_commit(out)
        return out

    def submit_envelope(self, task_id, msg_type, envelope):
        with self.ports.store.transaction() as d:
            out = fencing.accept(self, d, task_id, msg_type, envelope)
        self._after_commit(out)
        return out

    def issue_lease(self, task_id, reason):
        """Direct call of the one issuing function: it needs the row that leads out of the task's state."""
        with self.ports.store.transaction() as d:
            tr = transition_engine.row_for_issue(self, d, task_id, reason)
            if tr is None:
                raise PreconditionFailed([f"no transition issues a lease for {reason} from the current state"])
            lease, _row = lease_mod.issue_lease(self, d, task_id, reason, tr, [])
        self.ports.faults.check("issue_lease:committed")
        return lease

    def tick(self):
        """Clock-driven normal expiry (the clock, not an envelope, causes these transitions)."""
        for task_id in sorted(self.snapshot()["tasks"]):
            with self.ports.store.transaction() as d:
                if recovery.normal_expiry_due(self, d, task_id):
                    recovery.expire(self, d, task_id)

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
