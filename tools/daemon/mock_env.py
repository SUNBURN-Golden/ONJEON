"""Test bench for the dry run: builds ports, mock builders and a DaemonCore, and restarts the core."""
import json

from .core import DaemonCore, Rules
from .core.envelope_validator import receiver_validation
from .core.ports import SimulatedCrash
from .mock_adapters import MockProc, VirtualClock, build_ports


class MockBuilder:
    """Mock builder adapter. Validates every instruction with the core's receiver_validation before it
    starts, otherwise sends only a lease_invalid result."""

    def __init__(self, env, name, runner):
        self.env, self.name, self.runner = env, name, runner
        self.seen_instructions = {}
        self.executed = []
        self.invalid = []
        self.steps = {}  # task_id -> [(step id, ran)]
        self.active = {}
        self.proc_options = {}

    def _eid(self):
        return self.env.ports.ids.new_id()

    def process_inbox(self, first="first_heartbeat"):
        results = []
        inbox = self.env.ports.sender.inboxes.get(self.runner, [])
        while inbox:
            results.append(self.on_instruction(inbox.pop(0), first))
        return results

    def on_instruction(self, instr, first="first_heartbeat"):
        ok, recs = receiver_validation(self.env.rules, instr, self.env.core, self.env.clock)
        if not ok:
            self.invalid.append(instr["envelope_id"])
            return ("lease_invalid", self.send_result(instr, "lease_invalid"))
        if instr["envelope_id"] in self.seen_instructions:
            # duplicate delivery of an instruction already started: answer with the same envelope again
            return ("duplicate", self.env.submit(instr["task_id"], first, self.seen_instructions[instr["envelope_id"]]))
        self.executed.append(instr["envelope_id"])
        self.active[instr["task_id"]] = instr
        t = instr["task_id"]
        # rules_for_builder: real_data_allowed=false runs the mock/local steps only
        task_def = self.env.ports.catalog.task(t)
        self.steps[t] = [(s["id"], (not s["real_data"]) or instr.get("real_data_allowed") is True)
                         for s in task_def.get("mock_steps", [])]
        creds = self.env.ports.credentials
        creds.issue("builder_write_credential", t, instr["lease_id"])
        creds.issue("builder_token", t, instr["lease_id"])
        path = instr["worktree"]
        self.env.ports.worktree.ensure(path)
        self.env.ports.process.spawn(MockProc(t, self.env.ports.worktree, path, **self.proc_options.get(t, {})))
        hb = self.heartbeat_envelope(instr)
        self.seen_instructions[instr["envelope_id"]] = hb
        return ("started", self.env.submit(t, first, hb))

    # ---- envelope makers
    def heartbeat_envelope(self, instr, envelope_id=None):
        return {"envelope_id": envelope_id or self._eid(), "task_id": instr["task_id"], "lease_id": instr["lease_id"],
                "lease_generation": instr["lease_generation"], "fencing_token": instr["fencing_token"],
                "at": self.env.clock.now()}

    def result_envelope(self, instr, status, **over):
        env = {"envelope_id": self._eid(), "task_id": instr["task_id"], "attempt": instr["attempt"],
               "lease_id": instr["lease_id"], "lease_generation": instr["lease_generation"],
               "fencing_token": instr["fencing_token"], "builder": instr["builder"], "runner": instr["runner"],
               "status": status, "branch": instr["branch"], "head_sha": "h" * 40, "touched_paths": [],
               "tests_run": [], "test_log_ref": "mock://log", "signals_seen": [], "cost_units": 0,
               "calls": 0, "wall_s": 0}
        env.update(over)
        return env

    def signal_envelope(self, instr, status="usage_limit", **over):
        env = {"source": "provider_http_response", "task_id": instr["task_id"], "attempt": instr["attempt"],
               "call_id": self._eid(), "lease_id": instr["lease_id"], "lease_generation": instr["lease_generation"],
               "fencing_token": instr["fencing_token"], "runner": instr["runner"], "envelope_id": self._eid(),
               "status": status, "observed_at": self.env.clock.now()}
        env.update(over)
        return env

    def send_result(self, instr, status, **over):
        return self.env.submit(instr["task_id"], "result", self.result_envelope(instr, status, **over))


class MockEnv:
    def __init__(self, rules_path, tasks_path, builders=None):
        if isinstance(rules_path, dict):
            self.raw = rules_path
        else:
            with open(rules_path, encoding="utf-8") as f:
                self.raw = json.load(f)
        with open(tasks_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        if builders is not None:
            self.cfg["builders"] = builders
        self.clock = VirtualClock()
        self.rules = Rules(self.raw)
        excludes = self.rules.view["preserve_manifest"]["excludes"]
        self.ports = build_ports(self.clock, self.cfg["tasks"], self.cfg["builders"], excludes)
        self.core = DaemonCore(self.rules, self.ports)
        self.ports.git.trace_len = lambda: len(self.ports.store._data["journal"])
        self.builders = {b["name"]: MockBuilder(self, b["name"], b["runner"]) for b in self.cfg["builders"]}

    @property
    def store(self):
        return self.ports.store

    def restart(self):
        """The daemon process dies and starts again: a new core over the same store and the same world."""
        self.ports.faults.armed.clear()
        self.core = DaemonCore(self.rules, self.ports)
        return self.core.handle_event({"event": "daemon_restart"})

    def crash(self, fn):
        """Run fn; it must die at an armed fault point (the daemon process is gone afterwards)."""
        try:
            fn()
        except SimulatedCrash as e:
            return str(e)
        raise AssertionError("expected a simulated crash")

    def new_core(self):
        """A daemon process is running again but has not run restart recovery yet."""
        self.ports.faults.armed.clear()
        self.core = DaemonCore(self.rules, self.ports)
        return self.core

    def crash_restart(self, fn):
        point = self.crash(fn)
        self.restart()
        return point

    # ---- helpers
    def event(self, name, task_id, **payload):
        return self.core.handle_event({"event": name, "task_id": task_id, "payload": payload})

    def submit(self, task_id, msg_type, envelope):
        return self.core.submit_envelope(task_id, msg_type, envelope)

    def observe(self, task_id, kind, **payload):
        return self.core.observe(task_id, kind, **payload)

    def start_task(self, task_id):
        """Register the task as blocked; the core moves it to queued when its prerequisites and start gates hold."""
        self.core.register_task(task_id, "blocked")
        self.core.evaluate_prereqs(task_id)

    def grant(self, task_id, reason="from_queue"):
        return self.event("lease_granted", task_id, reason=reason)

    def run_builders(self, first="first_heartbeat"):
        out = []
        for b in self.builders.values():
            out += b.process_inbox(first)
        return out

    def snap(self):
        return self.store.snapshot()

    def task(self, task_id):
        return self.snap()["tasks"][task_id]

    def state(self, task_id):
        return self.task(task_id)["task_state"]["state"]

    def lease(self, task_id):
        return self.task(task_id)["lease_record"]

    def builder_for(self, task_id):
        return self.builders[self.lease(task_id)["builder"]]

    def instr(self, task_id):
        return self.builder_for(task_id).active[task_id]

    def journal(self):
        return self.snap()["journal"]

    def bring_to_building(self, task_id):
        self.start_task(task_id)
        self.grant(task_id)
        self.run_builders()
        assert self.state(task_id) == "building", self.state(task_id)
