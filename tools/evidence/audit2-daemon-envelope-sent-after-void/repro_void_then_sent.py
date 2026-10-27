"""Run from the repo root with python3 -I. A lease is issued for T-MOCK-BASIC; between the send and the marking
transaction the lease expires (tick), is cancelled and taken over by a restarted daemon, or a second send marks the
row first. Prints the outbox row afterwards."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tools"))
from daemon import scenarios as sc  # noqa: E402
from daemon.core import lease as lease_mod  # noqa: E402
from daemon.mock_env import MockEnv  # noqa: E402

R, T = "docs/blueprint/proposals/설계검토_결과/daemon_rules.json", "tools/daemon/mock_tasks.json"


def expire(env, task_id):
    env.clock.advance(sc.TTL + 1)
    env.core.tick()


def cancel_and_restart(env, task_id):
    env.event("owner_cancelled", task_id)
    env.restart()


def second_send(env, task_id):
    env.clock.advance(1)
    lease_mod.resend_outbox(env.core, task_id, "sender_retry")
    env.clock.advance(1)


for label, during in (("expired", expire), ("cancel+restart", cancel_and_restart), ("second send", second_send)):
    env = MockEnv(R, T)
    env.start_task(sc.BASIC)
    start = env.clock.now()
    env.ports.sender.during_send = lambda task_id, during=during, env=env: during(env, task_id)
    env.grant(sc.BASIC)
    t = env.task(sc.BASIC)
    row = t["outbox"][0]
    sent_at = None if row["sent_at"] is None else f"start+{row['sent_at'] - start}"
    print(f"{label:15} state={t['task_state']['state']:9} lease={t['lease_record']['status']:8} "
          f"outbox.status={row['status']:5} void_reason={row['void_reason']} sent_at={sent_at} sends={len(env.ports.sender.sent)}")
