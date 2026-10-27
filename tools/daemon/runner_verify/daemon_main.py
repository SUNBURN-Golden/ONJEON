"""One daemon operation in its own OS process (T-OP-09). The shared core (tools/daemon/core) runs over the real
adapters of adapters.py; a fault point can kill this process with SIGKILL, which is the "daemon crash" of R4, R16,
R18, R19 and R22. This is not the daemon: it has no loop and starts nothing by itself (05 §6).

    python3 -I daemon_main.py --state DIR [--die-at POINT[@SKIP]] [--delay-at POINT=SEC] [--fail POINT]
                              [--net-block] [--git-env K=V] OP [args]

Prints one line `RV_RESULT <json>` on exit. A process killed at a fault point prints nothing and has exit code -9.
"""
import argparse
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from daemon.core import DaemonCore, Rules  # noqa: E402
from daemon.core.ports import PreconditionFailed, SpecGap  # noqa: E402
from daemon.runner_verify import adapters  # noqa: E402
from daemon.runner_verify.common import Layout, append_jsonl, now_ns, read_json  # noqa: E402

OUTCOME_KEYS = ("accepted", "noop", "return_code", "transition", "written", "applied", "reason", "restart")
MSG_EVENTS = {"push_requested", "pr_update_requested"}


def outcome(out):
    return {k: out.get(k) for k in OUTCOME_KEYS if k in out}


def build_core(args):
    layout = Layout(args.state)
    cfg = read_json(layout.config)
    faults = adapters.ProcessFaults(
        die_at={p.partition("@")[0]: int(p.partition("@")[2] or 0) for p in args.die_at},
        delay={p.split("=")[0]: float(p.split("=")[1]) for p in args.delay_at},
        fail=args.fail, trace_path=layout.root / "faults.jsonl")
    git_env = dict(kv.split("=", 1) for kv in args.git_env)
    ports = adapters.build_ports(layout, faults, net_block=args.net_block, git_env=git_env)
    rules = Rules(read_json(cfg["rules"]))
    return layout, DaemonCore(rules, ports), ports


def handle_message(core, msg):
    """One message of the daemon's inbox (file queue or HTTP): an envelope or a push/PR request."""
    kind, task_id = msg["msg_type"], msg["task_id"]
    if kind in MSG_EVENTS:
        return core.handle_event({"event": kind, "task_id": task_id, "payload": msg["payload"]})
    return core.submit_envelope(task_id, kind, msg["envelope"])


def op_drain(layout, core, args):
    done = []
    for path in sorted(layout.daemon_inbox.glob("*.json")):
        try:
            msg = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        try:
            res = {"name": path.name, "ok": True, "outcome": outcome(handle_message(core, msg)),
                   "msg_type": msg["msg_type"], "task_id": msg["task_id"]}
        except (PreconditionFailed, SpecGap, KeyError, RuntimeError) as exc:
            res = {"name": path.name, "ok": False, "error": type(exc).__name__, "msg": str(exc)[:300]}
        if res["ok"] and res["outcome"].get("reason") == core.guard_wait["result"]:
            # issue_lease.on_guard_wait: the envelope was not taken (not seen); the next drain delivers it again
            done.append(res)
            continue
        core.ports.faults.check("drain:processed_unmoved")
        (layout.daemon_done / (path.name + ".out")).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        os.replace(path, layout.daemon_done / path.name)
        done.append(res)
    return done


def op_issue_credential(layout, core, args):
    """The builder host asks for its credentials after its receiver-side validation. Only the current, active lease
    gets them: a replaced lease cannot obtain a credential any more."""
    lease = core.current_lease(args.task)
    if not lease or lease.get("status") != "active" or lease.get("lease_id") != args.lease_id:
        return {"issued": False, "reason": "lease_not_current_or_not_active"}
    if args.name not in ("builder_write_credential", "builder_token"):
        return {"issued": False, "reason": "name_not_issuable_to_builder"}
    core.ports.credentials.issue(args.name, args.task, lease["lease_id"])
    return {"issued": True, "lease_id": lease["lease_id"]}


def op_serve(layout, core, args):
    """HTTP delivery of envelopes: POST /message with the same JSON as a queue file. --delay-first-response makes
    the first request answer late (after it was processed), so that a client with a short timeout retries."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    import time
    state = {"n": 0, "lock": threading.Lock()}
    log = layout.root / "http_server.jsonl"

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)))
            with state["lock"]:
                state["n"] += 1
                n = state["n"]
                try:
                    res = {"ok": True, "outcome": outcome(handle_message(core, body))}
                except (PreconditionFailed, SpecGap, KeyError, RuntimeError) as exc:
                    res = {"ok": False, "error": type(exc).__name__}
            append_jsonl(log, {"n": n, "envelope_id": (body.get("envelope") or {}).get("envelope_id"), "res": res,
                               "ns": now_ns()})
            if n == 1 and args.delay_first_response:
                time.sleep(args.delay_first_response)
            data = json.dumps(res).encode()
            try:
                self.send_response(200)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except OSError:
                pass  # the client gave up waiting

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    (layout.root / "http_port").write_text(str(srv.server_address[1]), encoding="utf-8")
    srv.timeout = 0.2
    end = time.time() + args.duration
    while time.time() < end and not (layout.root / "http_stop").exists():
        srv.handle_request()
    srv.server_close()
    return {"served": state["n"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", required=True)
    ap.add_argument("--die-at", action="append", default=[])
    ap.add_argument("--delay-at", action="append", default=[])
    ap.add_argument("--fail", action="append", default=[])
    ap.add_argument("--net-block", action="store_true")
    ap.add_argument("--git-env", action="append", default=[])
    sub = ap.add_subparsers(dest="op", required=True)
    p = sub.add_parser("init-task")
    p.add_argument("task")
    p.add_argument("--decision", action="append", default=[])
    p = sub.add_parser("event")
    p.add_argument("name")
    p.add_argument("task")
    p.add_argument("--payload", default="{}")
    p = sub.add_parser("grant")
    p.add_argument("task")
    p.add_argument("--reason", default="from_queue")
    p = sub.add_parser("submit")
    p.add_argument("task")
    p.add_argument("msg_type")
    p.add_argument("--envelope", required=True)
    p = sub.add_parser("observe")
    p.add_argument("task")
    p.add_argument("kind")
    p.add_argument("--payload", default="{}")
    sub.add_parser("drain")
    sub.add_parser("tick")
    sub.add_parser("restart")
    sub.add_parser("retry-usage")
    p = sub.add_parser("issue-credential")
    p.add_argument("task")
    p.add_argument("name")
    p.add_argument("lease_id")
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--duration", type=float, default=30)
    p.add_argument("--delay-first-response", type=float, default=0)
    args = ap.parse_args(argv)

    try:
        layout, core, ports = build_core(args)
        if args.op == "init-task":
            core.register_task(args.task, "blocked", decisions=args.decision)
            core.evaluate_prereqs(args.task)
            res = {"state": core.snapshot()["tasks"][args.task]["task_state"]["state"]}
        elif args.op == "event":
            res = outcome(core.handle_event({"event": args.name, "task_id": args.task,
                                             "payload": json.loads(args.payload)}))
        elif args.op == "grant":
            res = outcome(core.handle_event({"event": "lease_granted", "task_id": args.task,
                                             "payload": {"reason": args.reason}}))
        elif args.op == "submit":
            res = outcome(core.submit_envelope(args.task, args.msg_type, json.loads(args.envelope)))
        elif args.op == "observe":
            res = outcome(core.observe(None if args.task == "-" else args.task, args.kind, **json.loads(args.payload)) or {})
        elif args.op == "drain":
            res = op_drain(layout, core, args)
        elif args.op == "tick":
            core.tick()
            res = {"ticked": True}
        elif args.op == "restart":
            res = outcome(core.restart())
        elif args.op == "retry-usage":
            res = {"written": core.retry_usage()}
        elif args.op == "issue-credential":
            res = op_issue_credential(layout, core, args)
        else:
            res = op_serve(layout, core, args)
        payload = {"ok": True, "result": res, "instance_id": core.instance_id}
    except (PreconditionFailed, SpecGap, KeyError, RuntimeError) as exc:
        payload = {"ok": False, "error": type(exc).__name__, "msg": str(exc)[:500],
                   "trace": traceback.format_exc()[-800:]}
    sys.stdout.write("RV_RESULT " + json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    return 0 if payload["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
