"""Shared bench for the scenarios: constants, the report object, journal views and handoff helpers."""
from .mock_env import MockEnv

PASS, FAIL, GAP = "PASS", "FAIL", "GAP"
BASIC, HANDOFF, OTHER = "T-MOCK-BASIC", "T-MOCK-HANDOFF", "T-MOCK-OTHER"
TTL = 3600
ALWAYS_REVOKE = ["builder_write_credential", "builder_token", "preserve_credential"]


class Report:
    def __init__(self):
        self.checks = []

    def eq(self, name, expected, actual):
        ok = expected == actual
        self.checks.append({"name": name, "expected": expected, "actual": actual, "status": PASS if ok else FAIL})

    def gap(self, name, note, expected=None, actual=None):
        self.checks.append({"name": name, "expected": expected, "actual": actual, "status": GAP, "note": note})


# ---- journal views
def jr(env, mark=0):
    return env.journal()[mark:]


def mark(env):
    return len(env.journal())


def tr(js):
    return [(r["from"], r["to"], r["event"]) for r in js if r["kind"] == "transition_record"]


def se(js, *ids):
    return [r["id"] for r in js if r["kind"] == "side_effect_record" and (not ids or r["id"] in ids)]


def noops(js):
    return [(r["noop_event"], r["return_code"]) for r in js if r["kind"] == "noop_record"]


def rets(js):
    return [r["return_code"] for r in js if r["kind"] == "return_record"]


def first_seq(js, kind, **match):
    for r in js:
        if r["kind"] == kind and all(r.get(k) == v or r.get("args", {}).get(k) == v for k, v in match.items()):
            return r["seq"]
    return None


def sent_ids(env):
    return [s["envelope_id"] for s in env.ports.sender.sent]


def crash_after_issue(env, t):
    """The daemon dies right after issue_lease committed and before the instruction is sent."""
    env.ports.faults.arm("issue_lease:committed")
    return env.crash(lambda: env.grant(t))


# =============================================================== handoff helpers
def handoff_bench(R, T, task=HANDOFF, proc=None):
    env = MockEnv(R, T)
    if proc is not None:
        env.builders["mock-builder-1"].proc_options[task] = proc
    env.bring_to_building(task)
    path = env.instr(task)["worktree"]
    env.ports.worktree.write(path, "src/work.py", "print('work')\n")
    env.ports.worktree.write(path, "notes.txt", "n\n")
    return env, path


def switch(env, task=HANDOFF):
    b = env.builder_for(task)
    return env.submit(task, "switch_signal", b.signal_envelope(env.instr(task)))


def fake_secret(name):
    """The shape of a secret (preserve_manifest.secret_patterns), built at run time; not a real value."""
    return name + " = '" + "x" * 20 + "'\n"


def failed_guard_ids(js):
    out = set()
    for r in js:
        if r["kind"] == "diagnostic_record":
            if r["what"] == "guard_failed":
                out |= set(r["failed"])
            for c in r.get("cond") or []:
                if c.get("field") == "lease_guards":
                    out |= {n for n, ok in c["left"]["guards"] if not ok}
    return sorted(out)
