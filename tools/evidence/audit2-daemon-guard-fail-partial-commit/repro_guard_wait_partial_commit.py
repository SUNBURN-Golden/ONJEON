"""Run from the repo root with python3 -I. T-MOCK-BASIC is building; another task holds an active lease on the same
conflict_paths, so no_conflict_lease fails on the retry row (building -> building, result_failed_tests). The builder
reports failed_tests; the conflicting lease then ends and the builder delivers the same envelope again. Prints what
the store holds after each step."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tools"))
from daemon import scenarios as sc  # noqa: E402
from daemon.mock_env import MockEnv  # noqa: E402

R, T = "docs/blueprint/proposals/설계검토_결과/daemon_rules.json", "tools/daemon/mock_tasks.json"


def show(label, env, out):
    t = env.task(sc.BASIC)
    slots = [(u["lease_generation"], u["envelope_id"], u["calls"]) for u in env.snap().get("usage_record", [])
             if u["task_id"] == sc.BASIC]
    print(f"{label:<12} accepted={out.get('accepted')!s:<5} noop={out.get('noop')!s:<27} state={t['task_state']['state']:<8} "
          f"consecutive_failed_tests={t['task_state']['consecutive_failed_tests']} seen={len(t['inbox_seen'])} "
          f"generation={t['lease_generation']} lease={t['lease_record']['status']} usage={slots}")


env = MockEnv(R, T)
env.bring_to_building(sc.BASIC)
sc.inject(env, "conflict", sc.BASIC)
b = env.builder_for(sc.BASIC)
res = b.result_envelope(env.instr(sc.BASIC), "failed_tests", calls=3, wall_s=4, cost_units=5)
show("rejected", env, env.submit(sc.BASIC, "result", dict(res)))
sc.release(env, "conflict", sc.BASIC)
show("redelivered", env, env.submit(sc.BASIC, "result", dict(res)))
