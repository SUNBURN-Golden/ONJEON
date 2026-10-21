"""Stand-in builder process for the verification (T-MOCK-* tasks only). A real OS process in its own session that
plays a scripted builder: writes files in its worktree, ignores SIGTERM, sends heartbeats and envelopes into the
daemon's file queue, commits, and pushes with the credential it was given. It is not a vendor CLI: results that
rest on it are labelled `standin_process` in the report and "real CLI" stays unconfirmed for them.

    python3 -I standin.py --version
    python3 -I standin.py --script '<json list of actions>'      (environment: RV_STATE, RV_WORKTREE, RV_LEASE, ...)
"""
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from daemon.runner_verify.common import ClockFile, Layout, append_jsonl, atomic_write_json  # noqa: E402

LAYOUT = Layout(os.environ["RV_STATE"]) if "RV_STATE" in os.environ else None
LEASE = json.loads(os.environ.get("RV_LEASE", "{}"))
WORKTREE = os.environ.get("RV_WORKTREE", ".")
LOG = None


def log(op, **fields):
    if LOG:
        append_jsonl(LOG, dict(fields, op=op, pid=os.getpid(), ts_ns=time.time_ns()))


def envelope_base():
    return {"envelope_id": uuid.uuid4().hex.upper()[:26], "task_id": LEASE["task_id"], "lease_id": LEASE["lease_id"],
            "lease_generation": LEASE["lease_generation"], "fencing_token": LEASE["fencing_token"],
            "at": ClockFile(LAYOUT.clock).now()}


def queue(msg):
    name = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}.json"
    tmp = LAYOUT.daemon_inbox / f".{name}.tmp"
    tmp.write_text(json.dumps(msg), encoding="utf-8")
    os.replace(tmp, LAYOUT.daemon_inbox / name)
    return name


def result_envelope(status, fields):
    env = dict(envelope_base(), attempt=LEASE["attempt"], builder=LEASE["builder"], runner=LEASE["runner"],
               status=status, branch=LEASE["branch"], head_sha="h" * 40, touched_paths=[], tests_run=[],
               test_log_ref="standin://log", signals_seen=[], cost_units=0, calls=0, wall_s=0)
    env.update(fields or {})
    return env


def git(args, check=False):
    env = dict(os.environ)
    env.update(GIT_AUTHOR_NAME="standin", GIT_AUTHOR_EMAIL="standin@invalid", GIT_COMMITTER_NAME="standin",
               GIT_COMMITTER_EMAIL="standin@invalid", GIT_TERMINAL_PROMPT="0", GIT_CONFIG_GLOBAL="/dev/null")
    return subprocess.run(["git"] + args, cwd=WORKTREE, env=env, capture_output=True, text=True, timeout=60)


def reject_reason(res):
    for line in (res.stderr or "").splitlines():
        if "RV-REJECT" in line:
            return line.split("RV-REJECT", 1)[1].strip()
    return None


def run(script):
    for act in script:
        op = act["op"]
        if op == "ignore_term":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            log(op)
        elif op == "write":
            path = os.path.join(WORKTREE, act["path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(act.get("content", ""))
                if "mode" in act:
                    os.chmod(path, act["mode"])
                log(op, path=act["path"], ok=True)
            except OSError as exc:
                log(op, path=act["path"], ok=False, error=type(exc).__name__)
        elif op == "symlink":
            os.symlink(act["target"], os.path.join(WORKTREE, act["path"]))
            log(op, path=act["path"])
        elif op == "mkdir":
            os.makedirs(os.path.join(WORKTREE, act["path"]), exist_ok=True)
            log(op, path=act["path"])
        elif op == "delete":
            os.unlink(os.path.join(WORKTREE, act["path"]))
            log(op, path=act["path"])
        elif op == "loop_write":
            n = 0
            path = os.path.join(WORKTREE, act["path"])
            while act.get("count") is None or n < act["count"]:
                n += 1
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(f"tick {n}\n")
                    if n == 1 or n % 50 == 0:
                        log(op, n=n, ok=True)
                except OSError as exc:
                    log(op, n=n, ok=False, error=type(exc).__name__)
                    if act.get("stop_on_error"):
                        break
                time.sleep(act.get("interval", 0.01))
        elif op == "hold_open":
            fh = open(os.path.join(WORKTREE, act["path"]), "a", encoding="utf-8")
            log(op, path=act["path"], fd=fh.fileno())
            time.sleep(act.get("seconds", 3600))
        elif op == "sleep":
            time.sleep(act["s"])
        elif op == "wait_file":
            deadline = time.time() + act.get("timeout", 120)
            while not os.path.exists(act["path"]) and time.time() < deadline:
                time.sleep(0.02)
            log(op, path=os.path.basename(act["path"]), found=os.path.exists(act["path"]))
        elif op == "touch":
            Path(act["path"]).write_text("", encoding="utf-8")
        elif op == "git_commit":
            git(["add", "-A"])
            res = git(["commit", "-q", "-m", act.get("message", "standin work")] + (["--allow-empty"] if act.get("allow_empty") else []))
            sha = git(["rev-parse", "HEAD"]).stdout.strip()
            log(op, rc=res.returncode, sha=sha)
            if act.get("sha_file"):
                Path(act["sha_file"]).write_text(sha, encoding="utf-8")
        elif op == "push":
            sha = act.get("sha") or git(["rev-parse", "HEAD"]).stdout.strip()
            ref = act.get("ref") or f"refs/heads/{LEASE['branch']}"
            res = git(["push", os.environ["RV_REMOTE_URL"], f"{sha}:{ref}"] + (["--force"] if act.get("force") else []))
            reject = reject_reason(res) or ("non_fast_forward" if "non-fast-forward" in (res.stderr or "") else None)
            log(op, ref=ref, sha=sha, rc=res.returncode, reject=reject, force=bool(act.get("force")))
        elif op in ("heartbeat", "first_heartbeat"):
            for i in range(act.get("count", 1)):
                queue({"msg_type": op, "task_id": LEASE["task_id"], "envelope": envelope_base()})
                log(op, i=i)
                if i + 1 < act.get("count", 1):
                    time.sleep(act.get("every", 0.2))
        elif op == "heartbeat_forever":
            while True:
                queue({"msg_type": "heartbeat", "task_id": LEASE["task_id"], "envelope": envelope_base()})
                time.sleep(act.get("every", 0.2))
        elif op == "result":
            env = result_envelope(act["status"], act.get("fields"))
            name = queue({"msg_type": "result", "task_id": LEASE["task_id"], "envelope": env})
            log(op, status=act["status"], envelope_id=env["envelope_id"], queue_file=name)
        elif op == "switch_signal":
            env = dict(envelope_base(), source=act.get("source", "provider_http_response"), attempt=LEASE["attempt"],
                       call_id=uuid.uuid4().hex.upper()[:26], runner=LEASE["runner"], status=act.get("status", "usage_limit"),
                       observed_at=ClockFile(LAYOUT.clock).now())
            env.update(act.get("fields") or {})
            name = queue({"msg_type": "switch_signal", "task_id": LEASE["task_id"], "envelope": env})
            log(op, source=env["source"], status=env["status"], envelope_id=env["envelope_id"], queue_file=name)
        elif op == "push_request":
            sha = act.get("sha") or git(["rev-parse", "HEAD"]).stdout.strip()
            payload = dict(lease_id=LEASE["lease_id"], lease_generation=LEASE["lease_generation"],
                           fencing_token=LEASE["fencing_token"], envelope_id=uuid.uuid4().hex.upper()[:26],
                           via=act.get("via", "daemon"), branch=LEASE["branch"], sha=sha)
            name = queue({"msg_type": "push_requested", "task_id": LEASE["task_id"], "payload": payload})
            log(op, sha=sha, queue_file=name)
        elif op == "spawn_survivor":
            child = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--script", json.dumps(act["script"]),
                                      "--log-suffix", act.get("name", "survivor")],
                                     start_new_session=True, env=dict(os.environ), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log(op, child_pid=child.pid, child_pgid=os.getpgid(child.pid), own_pgid=os.getpgid(0))
        elif op == "spawn_child":
            child = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--script", json.dumps(act["script"]),
                                      "--log-suffix", act.get("name", "child")],
                                     env=dict(os.environ), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            log(op, child_pid=child.pid, child_pgid=os.getpgid(child.pid), own_pgid=os.getpgid(0))
        elif op == "loop_write_fd":
            fh = open(os.path.join(WORKTREE, act["path"]), "a", encoding="utf-8")
            n = 0
            while True:
                n += 1
                try:
                    fh.write(f"tick {n}\n")
                    fh.flush()
                except OSError as exc:
                    log(op, n=n, ok=False, error=type(exc).__name__)
                    break
                if n == 1 or n % 100 == 0:
                    log(op, n=n, ok=True)
                time.sleep(act.get("interval", 0.01))
        elif op == "exit":
            log(op, code=act.get("code", 0))
            os._exit(act.get("code", 0))
        else:
            raise SystemExit(f"unknown action {op}")


def main(argv):
    global LOG
    if "--version" in argv:
        print("standin 1")
        return 0
    script = json.loads(argv[argv.index("--script") + 1])
    suffix = argv[argv.index("--log-suffix") + 1] if "--log-suffix" in argv else "main"
    if LAYOUT is not None and LEASE:
        d = LAYOUT.standin / LEASE["task_id"]
        d.mkdir(parents=True, exist_ok=True)
        LOG = d / f"{LEASE['lease_id']}.{suffix}.jsonl"
    log("start", pgid=os.getpgid(0), sid=os.getsid(0))
    run(script)
    log("end")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
