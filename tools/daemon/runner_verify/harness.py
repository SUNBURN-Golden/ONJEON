"""Test harness for the real executor verification: builds a state directory with a verification remote, runs
daemon operations as separate OS processes, plays the builder-side adapter (receiver validation, worktree,
credentials, process start) and reads the evidence back from the files, the git remote and /proc.
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..core import DaemonCore, Rules
from ..core.envelope_validator import receiver_validation
from . import adapters, remote as rv_remote
from .common import (DEFAULT_BUILDERS, DEFAULT_RULES, DEFAULT_TASKS, PKG_DIR, ClockFile, Layout, append_jsonl,
                     atomic_write_json, group_members, new_id, now_ns, read_json, read_jsonl)

PY = sys.executable
DAEMON_MAIN = str(PKG_DIR / "daemon_main.py")
STANDIN = str(PKG_DIR / "standin.py")
BASIC, HANDOFF, OTHER = "T-MOCK-BASIC", "T-MOCK-HANDOFF", "T-MOCK-OTHER"


class DaemonRun:
    def __init__(self, proc):
        self.rc = proc.returncode
        self.stdout, self.stderr = proc.stdout or "", proc.stderr or ""
        self.payload = None
        for line in self.stdout.splitlines():
            if line.startswith("RV_RESULT "):
                self.payload = json.loads(line[len("RV_RESULT "):])

    @property
    def killed(self):
        return self.rc == -9

    @property
    def ok(self):
        return bool(self.payload and self.payload.get("ok"))

    @property
    def result(self):
        if not self.ok:
            raise RuntimeError(f"daemon operation failed rc={self.rc}: {self.payload or self.stderr[-600:]}")
        return self.payload["result"]


class Handle:
    """A started stand-in process."""

    def __init__(self, popen, instr, token, script):
        self.popen, self.instr, self.token, self.script = popen, instr, token, script

    @property
    def pid(self):
        return self.popen.pid

    @property
    def lease_id(self):
        return self.instr["lease_id"]

    @property
    def worktree(self):
        return self.instr["worktree"]

    def log(self, world, suffix="main"):
        return read_jsonl(world.layout.standin / self.instr["task_id"] / f"{self.lease_id}.{suffix}.jsonl")


class World:
    def __init__(self, workdir, rules=DEFAULT_RULES, tasks=DEFAULT_TASKS, remote="auto", time_scale=0.05):
        self.layout = Layout(workdir).make()
        self.rules_path, self.tasks_path = Path(rules), Path(tasks)
        self.time_scale = time_scale
        self.handles = []
        self._core = None
        raw = read_json(self.rules_path)
        self.raw = raw
        self.rules = Rules(raw)
        if remote in ("auto", "local", None):
            self.remote = rv_remote.provision(self.layout.root / "remote.git", self.layout.home)
            self.remote_kind = "provisioned_local_bare_repository"
        else:
            self.remote = rv_remote.check_accepts(remote)
            rv_remote.reset(self.remote, self.layout.home)
            self.remote_kind = "existing_marked_bare_repository"
        env = rv_remote.git_env(self.layout.home)
        rv_remote.run_git(["clone", "-q", str(self.remote), str(self.layout.clone)], env=env)
        rv_remote.run_git(["config", "gc.auto", "0"], cwd=self.layout.clone, env=env)
        builders = json.loads(DEFAULT_BUILDERS.read_text(encoding="utf-8"))["builders"]
        for b in builders:
            b["probe"] = [s.replace("{python}", PY).replace("{standin}", STANDIN) for s in b["probe"]]
        atomic_write_json(self.layout.config, {
            "remote": str(self.remote), "rules": str(self.rules_path), "tasks": str(self.tasks_path),
            "builders": builders, "time_scale": time_scale, "credential_ttl_s": 7200})
        self.builders = builders

    def use_builders(self, builders):
        """Replace the builder list of the fixture (a list of {name, runner, family, probe})."""
        cfg = read_json(self.layout.config)
        cfg["builders"] = builders
        atomic_write_json(self.layout.config, cfg)
        self.builders = builders
        self._core = None

    # ---- lifecycle
    def close(self):
        for h in self.handles:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(os.getpgid(h.pid), 9)
            with contextlib.suppress(Exception):
                h.popen.wait(timeout=5)
        self.kill_all_stragglers()
        adapters.make_writable(str(self.layout.worktrees))
        shutil.rmtree(self.layout.root, ignore_errors=True)

    def kill_all_stragglers(self):
        """Survivors started with a new session are not in any registered group: find them by their state dir."""
        for name in os.listdir("/proc"):
            if not name.isdigit() or int(name) == os.getpid():
                continue
            with contextlib.suppress(OSError):
                with open(f"/proc/{name}/environ", "rb") as f:
                    env = f.read()
                if f"RV_STATE={self.layout.root}".encode() in env:
                    os.kill(int(name), 9)

    # ---- daemon processes
    def _cmd(self, op_args, die_at=(), delay_at=(), fail=(), net_block=False, git_env=(), wrapper=None):
        cmd = [PY, "-I", DAEMON_MAIN, "--state", str(self.layout.root)]
        for flag, items in (("--die-at", die_at), ("--delay-at", delay_at), ("--fail", fail), ("--git-env", git_env)):
            for item in items:
                cmd += [flag, item]
        if net_block:
            cmd.append("--net-block")
        cmd += [str(a) for a in op_args]
        return (list(wrapper) + cmd) if wrapper else cmd

    def daemon(self, *op_args, timeout=300, **kw):
        proc = subprocess.run(self._cmd(op_args, **kw), capture_output=True, text=True, timeout=timeout,
                              env=self._env())
        return DaemonRun(proc)

    def daemon_async(self, *op_args, **kw):
        return subprocess.Popen(self._cmd(op_args, **kw), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=self._env())

    def _env(self):
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TMPDIR")}
        env["HOME"] = str(self.layout.home)
        return env

    # shorthands
    def init_task(self, task, **kw):
        return self.daemon("init-task", task, **kw)

    def grant(self, task, reason="from_queue", **kw):
        return self.daemon("grant", task, "--reason", reason, **kw)

    def event(self, name, task, payload=None, **kw):
        return self.daemon("event", name, task, "--payload", json.dumps(payload or {}), **kw)

    def submit(self, task, msg_type, envelope, **kw):
        return self.daemon("submit", task, msg_type, "--envelope", json.dumps(envelope), **kw)

    def drain(self, **kw):
        return self.daemon("drain", **kw)

    def tick(self, **kw):
        return self.daemon("tick", **kw)

    def restart(self, **kw):
        return self.daemon("restart", **kw)

    def observe(self, task, kind, payload=None, **kw):
        return self.daemon("observe", task or "-", kind, "--payload", json.dumps(payload or {}), **kw)

    def tamper(self, fn):
        """Fault injection on the persisted state: what a bad write or a bad disk would do. Same lock as the daemon."""
        from .common import file_lock
        with file_lock(self.layout.store_lock):
            data = read_json(self.layout.store)
            fn(data)
            atomic_write_json(self.layout.store, data)

    def queue_file(self, msg, name=None):
        """Put a message into the daemon's inbox the way a builder adapter does (temp file + rename)."""
        name = name or f"{time.time_ns()}-injected.json"
        tmp = self.layout.daemon_inbox / f".{name}.tmp"
        tmp.write_text(json.dumps(msg), encoding="utf-8")
        os.replace(tmp, self.layout.daemon_inbox / name)
        return name

    def done_messages(self):
        """The messages the daemon has already taken from its inbox, in arrival order."""
        out = []
        for p in sorted(self.layout.daemon_done.glob("*.json")):
            out.append((p.name, json.loads(p.read_text(encoding="utf-8"))))
        return out

    # ---- clock
    @property
    def clock(self):
        return ClockFile(self.layout.clock)

    def advance(self, seconds):
        return self.clock.add(seconds)

    def ttl(self):
        return int(self.rules.number("concurrency.lease.ttl_s"))

    def heartbeat_s(self):
        return int(self.rules.get("concurrency.lease.heartbeat_s"))

    # ---- state reads
    def snap(self):
        return read_json(self.layout.store, {"tasks": {}, "journal": []})

    def task(self, task_id):
        return self.snap()["tasks"][task_id]

    def state(self, task_id):
        return self.task(task_id)["task_state"]["state"]

    def lease(self, task_id):
        return self.task(task_id)["lease_record"]

    def journal(self):
        return self.snap()["journal"]

    def mark(self):
        return len(self.journal())

    def core(self):
        """A core over the real adapters in this (harness) process: used for read-only questions and the builder
        side validation, never to change state."""
        if self._core is None:
            ports = adapters.build_ports(self.layout)
            self._core = DaemonCore(self.rules, ports)
        return self._core

    def ports(self):
        return self.core().ports

    # ---- remote and logs
    def remote_refs(self):
        return rv_remote.refs(self.remote, self.layout.home)

    def push_log(self):
        return rv_remote.push_log(self.remote)

    def cred_log(self):
        return read_jsonl(self.layout.creds / "log.jsonl")

    def proc_log(self):
        return read_jsonl(self.layout.procs / "events.jsonl")

    def sent(self):
        return read_jsonl(self.layout.inbox / "sent.jsonl")

    def git(self, args, cwd=None, check=True, env=None):
        full = rv_remote.git_env(self.layout.home)
        full.update(env or {})
        return rv_remote.run_git(args, cwd=cwd or self.layout.clone, env=full, check=check)

    # ---- the builder side
    def instructions(self, runner):
        d = self.layout.inbox / runner
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.exists() else []

    def latest_instruction(self, task_id):
        t = self.task(task_id)
        lease = t["lease_record"]
        for runner_dir in sorted(self.layout.inbox.glob("*/")):
            for p in runner_dir.glob("*.json"):
                ins = json.loads(p.read_text(encoding="utf-8"))
                if ins["lease_id"] == lease["lease_id"] and ins["task_id"] == task_id:
                    return ins
        return None

    def validate_instruction(self, instr):
        core = self.core()
        return receiver_validation(self.rules, instr, core, core.clock)

    def prepare_worktree(self, instr):
        path = instr["worktree"]
        branch = instr["branch"]
        local = self.git(["rev-parse", "--verify", "-q", f"refs/heads/{branch}"], check=False)
        start = local.stdout.strip() if local.returncode == 0 else instr["base_sha"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.git(["worktree", "add", "-q", "--detach", path, start])
        return start

    def start_builder(self, instr, script, name="main", validate=True, with_credentials=True, extra_env=None):
        """What the builder adapter does with an instruction: validate it, prepare the worktree, ask the daemon for
        the credentials, start the process in its own session and register its process group."""
        if validate:
            ok, _checks = self.validate_instruction(instr)
            if not ok:
                return None
        start = self.prepare_worktree(instr)
        token = None
        if with_credentials:
            for cred in ("builder_write_credential", "builder_token"):
                res = self.daemon("issue-credential", instr["task_id"], cred, instr["lease_id"])
                if not res.ok or not res.result.get("issued"):
                    raise RuntimeError(f"credential {cred} was not issued: {res.payload}")
            token = self.ports().credentials.token("builder_write_credential", instr["task_id"])
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL")}
        env.update(HOME=str(self.layout.home), RV_STATE=str(self.layout.root), RV_WORKTREE=instr["worktree"],
                   RV_LEASE=json.dumps(instr), RV_PUSH_CREDENTIAL=token or "", RV_REMOTE_URL=str(self.remote),
                   RV_PUSH_CLIENT="builder", GIT_CONFIG_NOSYSTEM="1")
        env.update(extra_env or {})
        pop = subprocess.Popen([PY, "-I", STANDIN, "--script", json.dumps(script)], cwd=instr["worktree"], env=env,
                               start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        self.ports().process.register(instr["task_id"], pop.pid, os.getpgid(pop.pid), instr["lease_id"], instr["runner"])
        h = Handle(pop, instr, token, script)
        h.start_commit = start
        self.handles.append(h)
        return h

    def start_command(self, instr, argv, env, stdout_path=None):
        """Like start_builder, for a real vendor CLI: same checks, worktree and credentials, but the process is the
        command itself and its stdout goes to a file outside the worktree."""
        ok, _checks = self.validate_instruction(instr)
        if not ok:
            return None
        start = self.prepare_worktree(instr)
        for cred in ("builder_write_credential", "builder_token"):
            res = self.daemon("issue-credential", instr["task_id"], cred, instr["lease_id"])
            if not res.ok or not res.result.get("issued"):
                raise RuntimeError(f"credential {cred} was not issued: {res.payload}")
        token = self.ports().credentials.token("builder_write_credential", instr["task_id"])
        env = dict(env, RV_STATE=str(self.layout.root))
        out = open(stdout_path, "wb") if stdout_path else subprocess.DEVNULL
        pop = subprocess.Popen(argv, cwd=instr["worktree"], env=env, start_new_session=True, stdin=subprocess.DEVNULL,
                               stdout=out, stderr=subprocess.DEVNULL)
        if stdout_path:
            out.close()  # the child holds its own descriptor
        self.ports().process.register(instr["task_id"], pop.pid, os.getpgid(pop.pid), instr["lease_id"], instr["runner"])
        h = Handle(pop, instr, token, argv)
        h.start_commit = start
        h.began = time.time()
        self.handles.append(h)
        return h

    def envelope_msg(self, instr, msg_type, **fields):
        """A heartbeat / signal / result message built by the adapter for the lease of `instr`."""
        base = {"envelope_id": new_id(""), "task_id": instr["task_id"], "lease_id": instr["lease_id"],
                "lease_generation": instr["lease_generation"], "fencing_token": instr["fencing_token"], "at": self.clock.now()}
        if msg_type == "switch_signal":
            base.update(source="provider_http_response", attempt=instr["attempt"], call_id=new_id(""), runner=instr["runner"],
                        status="usage_limit", observed_at=self.clock.now())
        elif msg_type == "result":
            base.update(attempt=instr["attempt"], builder=instr["builder"], runner=instr["runner"], status="failed_tests",
                        branch=instr["branch"], head_sha="h" * 40, touched_paths=[], tests_run=[], test_log_ref="adapter://log",
                        signals_seen=[], cost_units=0, calls=0, wall_s=0)
        base.update(fields)
        if msg_type == "result" and base["status"] == "pr_opened" and "pr_body" not in fields:
            base["pr_body"] = {"task_id": instr["task_id"], "authors": [instr["builder"]],
                               "target_sha": base["head_sha"], "test_log_ref": base["test_log_ref"]}
        return {"msg_type": msg_type, "task_id": instr["task_id"], "envelope": base}

    def wait_log(self, handle, op, suffix="main", timeout=30, count=1, **match):
        """Wait until the stand-in logged `count` entries of `op` (with the given fields)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            rows = [r for r in handle.log(self, suffix) if r["op"] == op and all(r.get(k) == v for k, v in match.items())]
            if len(rows) >= count:
                return rows
            time.sleep(0.03)
        raise TimeoutError(f"stand-in did not log {op} x{count}: {handle.log(self, suffix)[-3:]}")

    def wait_gone(self, handle, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if handle.popen.poll() is not None:
                return True
            time.sleep(0.03)
        return False

    def lease_to_building(self, task_id, script, name="main", **kw):
        """init-task, grant, start the stand-in, drain its first heartbeat: the task is `building`."""
        self.init_task(task_id).result
        res = self.grant(task_id)
        if not res.ok:
            raise RuntimeError(f"grant failed: {res.payload}")
        instr = self.latest_instruction(task_id)
        h = self.start_builder(instr, [{"op": "first_heartbeat"}] + script, **kw)
        self.wait_log(h, "first_heartbeat")
        out = self.drain().result
        return instr, h, out

    def kill_handle(self, h):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(h.pid), 9)

    # ---- generic helpers for evidence
    def survivors(self, root=None):
        root = str(root or self.layout.root)
        out = []
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            with contextlib.suppress(OSError):
                with open(f"/proc/{name}/environ", "rb") as f:
                    if f"RV_STATE={root}".encode() in f.read():
                        out.append(int(name))
        return out


# ---------------------------------------------------------------- journal views over a list of records
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
        if r["kind"] == kind and all(r.get(k) == v or (r.get("args") or {}).get(k) == v for k, v in match.items()):
            return r["seq"]
    return None


@contextlib.contextmanager
def world(**kw):
    base = tempfile.mkdtemp(prefix="rv-")
    w = World(base, **kw)
    try:
        yield w
    finally:
        w.close()
