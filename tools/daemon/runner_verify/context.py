"""Options shared by all scenarios of one run."""
import contextlib
import tempfile

from .common import DEFAULT_RULES, DEFAULT_TASKS
from .harness import World


class Ctx:
    def __init__(self, rules=DEFAULT_RULES, tasks=DEFAULT_TASKS, remote="auto", time_scale=0.05, workdir=None,
                 with_cli=True):
        self.rules, self.tasks, self.remote = rules, tasks, remote
        self.time_scale, self.workdir, self.with_cli = time_scale, workdir, with_cli
        self.worlds = 0
        self.advance_s = 0.0
        self.scaled_sleep_s = 0.0
        self.pushes = {"accepted": 0, "rejected": 0, "applied_refs_outside_task": [], "applied": 0}
        self.remote_writes = 0

    @contextlib.contextmanager
    def world(self, builders=None, **kw):
        self.worlds += 1
        base = tempfile.mkdtemp(prefix="rv-", dir=self.workdir)
        opts = dict(rules=self.rules, tasks=self.tasks, remote=self.remote,
                    time_scale=self.time_scale)
        opts.update(kw)
        w = World(base, **opts)
        if builders is not None:
            w.use_builders(builders)
        try:
            yield w
        finally:
            self.absorb(w)
            w.close()

    def absorb(self, w):
        """Totals that outlive the throwaway state directory: clock shifts and what the test remote saw."""
        for shift in w.clock.shifts():
            if shift.get("kind") == "scaled_sleep":
                self.scaled_sleep_s += shift["by_s"]
            else:
                self.advance_s += shift["by_s"]
        for e in w.push_log():
            if e["event"] == "pre_receive":
                self.pushes["accepted" if e["decision"] == "accepted" else "rejected"] += 1
            elif e["event"] == "applied":
                self.pushes["applied"] += 1
                if not e["ref"].startswith("refs/heads/task/T-MOCK-"):
                    self.pushes["applied_refs_outside_task"].append(e["ref"])
