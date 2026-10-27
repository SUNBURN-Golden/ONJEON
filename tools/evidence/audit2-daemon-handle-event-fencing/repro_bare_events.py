"""Feed each envelope-born event to handle_event with no envelope, on a building task, and print what happened."""
import sys
sys.path.insert(0, "tools")
from daemon import scenarios as sc
from daemon.mock_env import MockEnv
R, T = "docs/blueprint/proposals/설계검토_결과/daemon_rules.json", "tools/daemon/mock_tasks.json"
for name in ("result_pr_opened", "result_failed_tests", "switch_signal", "heartbeat", "no_such_event"):
    env = MockEnv(R, T)
    env.bring_to_building(sc.BASIC)
    lease = env.lease(sc.BASIC)
    m = sc.mark(env)
    env.clock.advance(1)
    env.core.handle_event({"event": name, "task_id": sc.BASIC, "payload": {}})
    js = env.journal()[m:]
    print(f"{name:22} state={env.state(sc.BASIC):10} transitions={sc.tr(js)} noops={sc.noops(js)} "
          f"lease_status={env.lease(sc.BASIC).get('status')} last_heartbeat_moved={env.lease(sc.BASIC).get('last_heartbeat_at') != lease['last_heartbeat_at']}")
