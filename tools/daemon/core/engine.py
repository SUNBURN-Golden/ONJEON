"""DaemonCore: the shared transition and validation core. Callers differ only in the `ports` they supply."""
from . import effects, envelope_validator, fencing, handoff, lease as lease_mod, recovery, transition_engine
from .gate_evaluator import Clockview, Ctx
from .records import Recorder
import re


class DaemonCore:
    def __init__(self, rules, ports):
        self.rules = rules
        self.ports = ports
        self.clock = ports.clock
        self.rec = Recorder(rules, ports.clock)
        self.effects = effects
        payload_names = set(rules.get("core_contract.events_in.payloads").keys())
        self.known_events = set(rules.events) | {n for n in payload_names if n != "result_*"} | {"daemon_restart"}
        path = rules.get("state_integrity.normal_expiry.path")
        self.expiry_events = [e for e in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", path) if e in rules.events]
        rules.token_log.add(("state_integrity.normal_expiry.path", "event names inside the path text"))
        self.issue_reasons = lease_mod.issue_reasons(rules)

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
    def ctx(self, d, task_id, row=None, event=None, envelope=None, funcs=None):
        t = d["tasks"][task_id]
        roots = {"task_state": t["task_state"], "lease_record": t["lease_record"] or {},
                 "handoff_record": t["handoff_record"] or {}, "outbox": row or {},
                 "clock": Clockview(self.clock.now()), "event": event or {}, "envelope": envelope or {},
                 "daemon": self}
        prev = (t["lease_record"] or {}).get("builder")
        base = {
            "lease_guards": lambda _a: lease_mod.run_guards(self, d, task_id),
            "builder_available": lambda a: self.ports.builders.available(a, prev),
            "envelope_validator": lambda a: self._validate_instruction(d, task_id),
        }
        base.update(funcs or {})
        return Ctx(self.rules, roots, base, {"task_id": task_id})

    def _validate_instruction(self, d, task_id):
        cand = lease_mod._candidate_lease(self, d, task_id, "initial")
        inst = envelope_validator.build_instruction(self, d, task_id, cand, "(new)")
        return "invalid" if envelope_validator.missing_instruction_fields(self, task_id, inst) else "valid"

    # ---- entry points
    def handle_event(self, ev):
        name = ev["event"]
        if name == "daemon_restart":
            return self.restart()
        task_id, payload = ev["task_id"], dict(ev.get("payload") or {})
        if name == "fence_violation":
            # detected violation by the holder of a lease: only the current lease's counts (fencing)
            env = dict(payload)
            env.setdefault("lease_generation", env.get("fencing_token"))
            return self.submit_envelope(task_id, "fence_violation", env)
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
        with self.ports.store.transaction() as d:
            lease, _row = lease_mod.issue_lease(self, d, task_id, reason)
        self.ports.faults.check("issue_lease:committed")
        return lease

    def tick(self):
        """Clock-driven normal expiry (the clock, not an envelope, causes these transitions)."""
        for task_id in sorted(self.snapshot()["tasks"]):
            with self.ports.store.transaction() as d:
                if recovery.normal_expiry_due(self, d, task_id):
                    recovery.expire(self, d, task_id)

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
