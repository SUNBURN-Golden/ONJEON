"""Real adapters for the shared daemon core (core/ports.py): a file store with a cross-process lock and atomic
rename, a shifted wall clock, process groups, a credential store backed by the verification remote, real git
worktrees and pushes, a file queue sender, and a fault injector that kills the real process.

The core is the same code the mock bench runs (execution_core in daemon_rules.json); only these adapters differ.
"""
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from ..core import Rules
from ..core.ports import (BuilderPool, Clock, CommitFailed, Credentials, DiskFullError, Faults, Git, GuardChecks, IdSource,
                          IndexLockError, Ports, ProcessControl, PushFailed, QueryUnavailable, Remote, Sender, SpecGap,
                          Store, Worktree)
from ..mock_adapters import MockCatalog, MockReviewers
from . import remote as rv_remote
from .common import (ClockFile, append_jsonl, atomic_write_json, atomic_write_text, file_lock, fsync_dir, group_members,
                     new_id, now_ns, open_handles, pid_alive, read_json, read_jsonl)


# ---------------------------------------------------------------- clock and ids
class ShiftedClock(Clock):
    """Wall clock plus the harness offset. sleep() waits `scale` times the asked time for real and books the rest
    as offset, so a 120 s grace loop does not take two minutes unless scale is 1."""

    def __init__(self, layout, scale):
        self.file = ClockFile(layout.clock)
        self.scale = float(scale)

    def now(self):
        return self.file.now()

    def sleep(self, seconds):
        time.sleep(seconds * self.scale)
        if self.scale < 1:
            self.file.add(seconds * (1 - self.scale), kind="scaled_sleep")


class UniqueIds(IdSource):
    def new_id(self):
        return new_id()


# ---------------------------------------------------------------- store
class FileStore(Store):
    """One JSON file. A transaction holds an exclusive flock for its whole length, works on a copy and replaces the
    file by rename only when the body finished; a process that dies earlier leaves the old file untouched."""

    def __init__(self, layout, faults=None):
        self.layout = layout
        self.faults = faults
        self._local = threading.local()
        for stale in layout.store_dir.glob(".state.json.*.tmp"):
            try:
                pid = int(stale.name.split(".")[2])
            except (IndexError, ValueError):
                pid = 0
            if not pid_alive(pid):
                with contextlib.suppress(OSError):
                    stale.unlink()

    def _check(self, point):
        if self.faults is not None:
            self.faults.check(point)

    def _read(self):
        data = read_json(self.layout.store)
        return data if data is not None else {"tasks": {}, "journal": []}

    @contextlib.contextmanager
    def _exclusive(self):
        if getattr(self._local, "held", False):
            raise RuntimeError("nested store transaction or dispatch")
        with file_lock(self.layout.store_lock):
            self._local.held = True
            try:
                yield
            finally:
                self._local.held = False

    @contextlib.contextmanager
    def transaction(self):
        with self._exclusive():
            work = self._read()
            yield work
            self._write(work)  # reached only when the body did not raise: all or nothing

    @contextlib.contextmanager
    def dispatch_guard(self):
        with self._exclusive():
            yield self._read()  # committed state, no write/rename on exit

    def _write(self, data):
        text = json.dumps(data, ensure_ascii=False, sort_keys=True)
        tmp = self.layout.store_dir / f".state.json.{os.getpid()}.{new_id('')[:8]}.tmp"
        half = len(text) // 2
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text[:half])
            f.flush()
            self._check("store:torn_write")  # the process dies with half of the new file on disk
            f.write(text[half:])
            f.flush()
            os.fsync(f.fileno())
        self._check("store:before_rename")
        os.replace(tmp, self.layout.store)
        self._check("store:after_rename")
        fsync_dir(self.layout.store_dir)

    def snapshot(self):
        return self._read()  # the file is replaced atomically, a reader sees the old or the new one


# ---------------------------------------------------------------- faults
class ProcessFaults(Faults):
    """check(point) kills THIS process with SIGKILL when the point is armed: no finally block, no atexit, no flush.
    delay[point] makes the process wait there (to hold a lock while another process contends)."""

    def __init__(self, die_at=None, delay=None, fail=None, trace_path=None):
        self.die_at = dict(die_at or {})  # point -> remaining hits to skip
        self.delay = dict(delay or {})
        self.fail = set(fail or ())
        self.trace_path = trace_path

    def check(self, point):
        if point in self.delay:
            time.sleep(self.delay[point])
        if point in self.die_at:
            if self.die_at[point] > 0:
                self.die_at[point] -= 1
                return
            if self.trace_path:
                append_jsonl(self.trace_path, {"event": "dying", "point": point, "pid": os.getpid(), "ns": now_ns()})
            os.kill(os.getpid(), signal.SIGKILL)

    def fails(self, point):
        return point in self.fail


# ---------------------------------------------------------------- credentials
def token_sha(token):
    return hashlib.sha256(token.encode()).hexdigest()


class RemoteCredentials(Credentials):
    """Short-lived push credentials. issue() makes a random token, stores it where the builder host reads it and
    registers it at the verification remote; revoke() marks it revoked at the remote and in the store. Every call
    is appended to creds/log.jsonl with the real time (issue/revoke intervals are read from this log)."""

    def __init__(self, layout, remote_path, ttl_s):
        self.layout, self.remote, self.ttl_s = layout, remote_path, ttl_s
        self.path = layout.creds / "tokens.json"
        self.lock = layout.creds / "tokens.lock"
        self.log = layout.creds / "log.jsonl"

    def _mutate(self, fn):
        with file_lock(self.lock):
            data = read_json(self.path, {}) or {}
            out = fn(data)
            atomic_write_json(self.path, data)
            return out

    @staticmethod
    def key(name, task_id):
        return f"{name}|{task_id}"

    def issue(self, name, task_id, lease_id):
        token = os.urandom(24).hex()

        def put(data):
            old = data.get(self.key(name, task_id))
            if old and not old.get("revoked_ns"):
                # a second issue for the same slot supersedes the first one: the old token is revoked first
                rv_remote.revoke_token(self.remote, token_sha(old["token"]))
                old["revoked_ns"] = now_ns()
            data[self.key(name, task_id)] = {"token": token, "lease_id": lease_id, "name": name, "task_id": task_id,
                                             "issued_ns": now_ns(), "revoked_ns": None}

        self._mutate(put)
        rv_remote.register_token(self.remote, token_sha(token), name, task_id, lease_id, self.ttl_s)
        append_jsonl(self.log, {"op": "issue", "name": name, "task_id": task_id, "lease_id": lease_id,
                                "token_sha": token_sha(token)[:12], "ns": now_ns(), "pid": os.getpid()})

    def revoke(self, name, task_id, lease_id):
        def mark(data):
            cur = data.get(self.key(name, task_id))
            if cur and not cur.get("revoked_ns"):
                cur["revoked_ns"] = now_ns()
                rv_remote.revoke_token(self.remote, token_sha(cur["token"]))
                return cur
            return None

        cur = self._mutate(mark)
        append_jsonl(self.log, {"op": "revoke", "name": name, "task_id": task_id, "lease_id": lease_id,
                                "token_sha": token_sha(cur["token"])[:12] if cur else None, "was_active": bool(cur),
                                "ns": now_ns(), "pid": os.getpid()})

    # ---- reads (the builder host and the checks)
    def entry(self, name, task_id):
        return (read_json(self.path, {}) or {}).get(self.key(name, task_id))

    def is_active(self, name, task_id):
        e = self.entry(name, task_id)
        return bool(e and not e.get("revoked_ns"))

    def token(self, name, task_id):
        e = self.entry(name, task_id)
        return e["token"] if e and not e.get("revoked_ns") else None

    def history(self):
        return read_jsonl(self.log)


# ---------------------------------------------------------------- processes
class GroupProcessControl(ProcessControl):
    """The builder's process group. procs/<task>.json holds {pid, pgid, lease_id} written by whoever started it."""

    def __init__(self, layout):
        self.layout = layout
        self.log = layout.procs / "events.jsonl"

    def _rec(self, task_id):
        return read_json(self.layout.procs / f"{task_id}.json")

    def register(self, task_id, pid, pgid, lease_id, runner):
        atomic_write_json(self.layout.procs / f"{task_id}.json",
                          {"pid": pid, "pgid": pgid, "lease_id": lease_id, "runner": runner, "started_ns": now_ns()})
        append_jsonl(self.log, {"event": "spawn", "task_id": task_id, "pid": pid, "pgid": pgid, "lease_id": lease_id,
                                "ns": now_ns()})

    def alive_count(self, task_id):
        rec = self._rec(task_id)
        return len(group_members(rec["pgid"])) if rec else 0

    def terminate_group(self, task_id):
        rec = self._rec(task_id)
        if not rec:
            return
        members = [pid for pid, _ in group_members(rec["pgid"])]
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(rec["pgid"], signal.SIGKILL)
        deadline = time.time() + 5
        while group_members(rec["pgid"]) and time.time() < deadline:
            time.sleep(0.02)
        append_jsonl(self.log, {"event": "terminate_group", "task_id": task_id, "pgid": rec["pgid"],
                                "lease_id": rec["lease_id"], "members": members, "left": len(group_members(rec["pgid"])),
                                "ns": now_ns()})

    def request_stop(self, task_id):
        rec = self._rec(task_id)
        if not rec:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(rec["pgid"], signal.SIGTERM)
        append_jsonl(self.log, {"event": "stop_requested", "task_id": task_id, "pgid": rec["pgid"], "ns": now_ns()})


# ---------------------------------------------------------------- worktrees
def _walk_entries(root):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if os.path.realpath(dirpath) == os.path.realpath(root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in dirnames + filenames:
            yield os.path.join(dirpath, name)


def make_writable(path):
    """Undo set_readonly (cleanup of the verification run only)."""
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        for name in dirnames + filenames + [""]:
            full = os.path.join(dirpath, name) if name else dirpath
            with contextlib.suppress(OSError):
                if not os.path.islink(full):
                    os.chmod(full, os.stat(full).st_mode | 0o200 | (0o100 if os.path.isdir(full) else 0))


class FsWorktree(Worktree):
    def __init__(self, layout):
        self.layout = layout

    def path_for(self, task_id, lease_id):
        return str(self.layout.worktrees / task_id / lease_id)

    def set_readonly(self, path):
        """Write ban: every file and directory loses its write bits. A process that still holds a writable file
        descriptor is not stopped by this; terminate_group and the open-handle check are what deal with it."""
        if not os.path.isdir(path):
            return
        for full in list(_walk_entries(path)):
            if not os.path.islink(full):
                os.chmod(full, os.stat(full).st_mode & ~0o222)
        os.chmod(path, os.stat(path).st_mode & ~0o222)

    def max_mtime(self, path):
        newest = 0
        for full in _walk_entries(path):
            with contextlib.suppress(OSError):
                newest = max(newest, os.lstat(full).st_mtime_ns)
        return newest

    def open_write_handles(self, path):
        return len(open_handles(path, writable_only=True, exclude_pids=(os.getpid(),)))


# ---------------------------------------------------------------- git
_LOCK_RE = re.compile(r"index\.lock|\.lock': File exists|Unable to create '.*\.lock'")
_FULL_RE = re.compile(r"No space left on device|disk quota exceeded", re.I)


def exclude_pathspecs(patterns):
    """preserve_manifest.excludes -> git pathspecs. `x/` is a directory at any depth, `*.k` a file name glob."""
    out = []
    for pat in patterns:
        if pat == ".git/":
            continue  # git never adds its own directory
        if pat.endswith("/"):
            out.append(f":(exclude,glob)**/{pat[:-1]}/**")
        else:
            out.append(f":(exclude,glob)**/{pat}")
    return out


class RealGit(Git):
    """git_write_tree_oid is the one tree identity function: a temporary index, `git add -A` with the manifest's
    excludes, `git write-tree`. The stop check and the preserve commit both go through it."""

    def __init__(self, layout, remote_path, excludes, credentials, extra_env=None, remote_url=None):
        self.layout, self.remote, self.excludes = layout, str(remote_path), list(excludes)
        self.credentials = credentials
        self.url = remote_url or self.remote  # network-block tests point the URL at a closed port
        self.clone = layout.clone
        self.env = rv_remote.git_env(layout.home)
        self.env.update(extra_env or {})

    # ---- plumbing
    def _git(self, args, cwd=None, env=None, check=True, timeout=120):
        full = dict(self.env)
        full.update(env or {})
        res = subprocess.run(["git"] + list(args), cwd=cwd or self.clone, env=full, capture_output=True, text=True,
                             timeout=timeout)
        if check and res.returncode != 0:
            self._raise(res)
        return res

    def _raise(self, res):
        text = (res.stderr or "") + (res.stdout or "")
        if _FULL_RE.search(text):
            raise DiskFullError(text.strip())
        if _LOCK_RE.search(text):
            m = re.search(r"'([^']*index\.lock)'", text)
            raise IndexLockError(owner_pid_alive=self._lock_owner_alive(m.group(1) if m else None))
        raise CommitFailed(text.strip()[-300:] or "git failed")

    @staticmethod
    def _lock_owner_alive(lock_path):
        """The lock file has no owner field; a live process holding it open is the owner."""
        if not lock_path:
            return False
        for name in os.listdir("/proc"):
            if not name.isdigit() or int(name) == os.getpid():
                continue
            fd_dir = f"/proc/{name}/fd"
            with contextlib.suppress(OSError):
                for fd in os.listdir(fd_dir):
                    with contextlib.suppress(OSError):
                        if os.readlink(f"{fd_dir}/{fd}") == lock_path:
                            return True
        return False

    def _tmp_index(self):
        return str(self.layout.tmp / f"index.{os.getpid()}.{new_id('')[:8]}")

    def _staged(self, worktree, excludes):
        """(tree oid, {path: (mode, blob)}) of what the manifest puts into the tree, via a temporary index."""
        idx = self._tmp_index()
        env = {"GIT_INDEX_FILE": idx}
        try:
            spec = exclude_pathspecs(self.excludes) + [f":(exclude,literal){e}" for e in excludes]
            self._git(["add", "-A", "--", "."] + spec, cwd=worktree, env=env)
            oid = self._git(["write-tree"], cwd=worktree, env=env).stdout.strip()
            listing = self._git(["ls-files", "-s", "-z"], cwd=worktree, env=env).stdout
        finally:
            for suffix in ("", ".lock"):
                with contextlib.suppress(OSError):
                    os.unlink(idx + suffix)
        files = {}
        for ent in filter(None, listing.split("\0")):
            meta, path = ent.split("\t", 1)
            mode, blob, _stage = meta.split()
            files[path] = (mode, blob)
        return oid, files

    # ---- the one tree identity function
    def git_write_tree_oid(self, worktree, includes=None, excludes=()):
        return self._staged(worktree, tuple(excludes or ()))[0]

    def included_files(self, worktree, excludes=()):
        _oid, files = self._staged(worktree, tuple(excludes))
        out = {}
        for path, (mode, _blob) in files.items():
            full = os.path.join(worktree, path)
            try:
                if mode == "120000":
                    out[path] = os.readlink(full)
                else:
                    with open(full, "rb") as f:
                        out[path] = f.read(2_000_000).decode("utf-8", errors="replace")
            except OSError:
                out[path] = ""
        return out

    # ---- Git port
    def preserve_commit(self, worktree, branch, message, excludes=()):
        tree = self.git_write_tree_oid(worktree, excludes=excludes)
        head = self._git(["rev-parse", "HEAD"], cwd=worktree).stdout.strip()
        # bring the worktree's own index in line with the preserved tree: this is the step that meets index.lock
        self._git(["read-tree", tree], cwd=worktree)
        commit = self._git(["commit-tree", tree, "-p", head, "-m", message], cwd=worktree).stdout.strip()
        self._git(["update-ref", f"refs/heads/{branch}", commit], cwd=worktree)
        self._git(["update-ref", "--no-deref", "HEAD", commit], cwd=worktree)
        actual = self._git(["rev-parse", f"{commit}^{{tree}}"], cwd=worktree).stdout.strip()
        return {"commit_tree_oid": actual, "wip_commit_sha": commit}

    def _branch_task(self, branch):
        m = re.match(r"^task/(.+)-a\d+$", branch)
        return m.group(1) if m else None

    def push(self, branch, sha):
        task_id = self._branch_task(branch)
        token = self.credentials.token("preserve_credential", task_id) if task_id else None
        res = self._git(["push", self.url, f"{sha}:refs/heads/{branch}"],
                        env={"RV_PUSH_CREDENTIAL": token or "", "RV_PUSH_CLIENT": "daemon-preserve"}, check=False,
                        timeout=60)
        if res.returncode != 0:
            raise PushFailed(classify_push_failure(res))
        return self.remote_ref(branch)

    def remote_ref(self, branch):
        res = self._git(["ls-remote", self.url, f"refs/heads/{branch}"], check=False, timeout=30)
        if res.returncode != 0:
            raise QueryUnavailable(res.stderr.strip()[-200:])
        line = res.stdout.strip()
        return line.split()[0] if line else None

    def find_commit_by_tree(self, branch, tree_oid):
        ref = self._git(["rev-parse", "--verify", "-q", f"refs/heads/{branch}"], check=False)
        if ref.returncode != 0:
            return None
        base = self.base_sha(None)
        log = self._git(["rev-list", "--no-commit-header", "--format=%H %T", ref.stdout.strip(), f"^{base}"], check=False)
        if log.returncode != 0:
            raise QueryUnavailable(log.stderr.strip()[-200:])
        for line in log.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == tree_oid:
                return parts[0]
        return None

    def base_sha(self, task_id):
        return self._git(["rev-parse", "refs/remotes/origin/main"]).stdout.strip()


def classify_push_failure(res):
    text = (res.stderr or "") + (res.stdout or "")
    m = re.search(r"RV-REJECT (\w+)", text)
    if m:
        reason = m.group(1)
        if reason in ("protected_branch", "ref_not_allowed"):
            return "protected_branch"
        return "permission_denied"
    if re.search(r"Connection refused|unable to connect|Could not resolve|does not appear to be a git repository|"
                 r"Could not read from remote|timed out|Network is unreachable", text, re.I):
        return "network"
    return "other"


# ---------------------------------------------------------------- sender and remote writes
class FileSender(Sender):
    """Instruction envelopes go to inbox/<runner>/<envelope_id>.json (temp file + rename). The same file name for the
    same envelope id: a resend overwrites, it never makes a second file."""

    def __init__(self, layout, process):
        self.layout, self.process = layout, process

    def send(self, task_id, instruction):
        d = self.layout.inbox / instruction["runner"]
        d.mkdir(parents=True, exist_ok=True)
        atomic_write_json(d / f"{instruction['envelope_id']}.json", instruction)
        append_jsonl(self.layout.inbox / "sent.jsonl", {"task_id": task_id, "envelope_id": instruction["envelope_id"],
                                                        "lease_generation": instruction["lease_generation"],
                                                        "runner": instruction["runner"], "ns": now_ns(), "pid": os.getpid()})

    def request_stop(self, task_id, builder):
        append_jsonl(self.layout.inbox / "stops.jsonl", {"task_id": task_id, "builder": builder, "ns": now_ns()})
        self.process.request_stop(task_id)


class PushRemote(Remote):
    """The fenced write after the core's checks passed: the daemon pushes with the lease's builder write credential.
    pr_update has no target at a bare repository and is recorded as such."""

    def __init__(self, layout, git, credentials):
        self.layout, self.git, self.credentials = layout, git, credentials

    def execute(self, kind, task_id, request):
        if kind != "push":
            append_jsonl(self.layout.root / "remote_writes.jsonl", {"kind": kind, "task_id": task_id, "executed": False,
                                                                    "reason": "no pull request API at the test remote",
                                                                    "ns": now_ns()})
            return
        credential = self.credentials.entry("builder_write_credential", task_id)
        if (not credential or credential.get("revoked_ns")
                or credential.get("lease_id") != request.get("lease_id")):
            raise PushFailed("permission_denied")
        token = credential["token"]
        res = self.git._git(["push", self.git.url, f"{request['sha']}:refs/heads/{request['branch']}"],
                            env={"RV_PUSH_CREDENTIAL": token or "", "RV_PUSH_CLIENT": "daemon-fenced"}, check=False,
                            timeout=60)
        append_jsonl(self.layout.root / "remote_writes.jsonl", {
            "kind": kind, "task_id": task_id, "executed": res.returncode == 0, "branch": request["branch"],
            "lease_generation": request.get("lease_generation"), "envelope_id": request.get("envelope_id"),
            "ns": now_ns()})
        if res.returncode != 0:
            raise PushFailed(classify_push_failure(res))


# ---------------------------------------------------------------- builders and guards
def probe_runner(command):
    """runner_version_probe: the runner command answers `--version` with exit code 0 within 20 s."""
    try:
        res = subprocess.run(list(command) + ["--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return res.returncode == 0


class ProbedBuilderPool(BuilderPool):
    """The builders of the fixture in their configured order. A builder is available when its runner answers the
    version probe and it is not on the harness's `unavailable` list (a file, so that separate processes agree)."""

    def __init__(self, layout, builders):
        self.layout, self.builders = layout, builders

    def _unavailable(self):
        return set((read_json(self.layout.root / "unavailable.json", []) or []))

    def _ok(self, b):
        return b["name"] not in self._unavailable() and probe_runner(b["probe"])

    def _avail(self):
        return [b for b in self.builders if self._ok(b)]

    def _after(self, previous):
        names = [b["name"] for b in self.builders]
        start = names.index(previous) + 1 if previous in names else 0
        for b in self.builders[start:]:
            if self._ok(b):
                return b
        return None

    def available(self, which, previous):
        return (self._after(previous) if which == "next" else (self._avail() or [None])[0]) is not None

    def family(self, builder):
        return next((b["family"] for b in self.builders if b["name"] == builder), None)

    def select(self, task_id, reason, previous):
        if reason == "handoff":
            return self._after(previous)
        for b in self.builders:
            if b["name"] == previous and self._ok(b):
                return b
        av = self._avail()
        return av[0] if av else None


class PoolGuards(GuardChecks):
    def __init__(self, pool):
        self.pool = pool

    def check(self, name, info):
        if name == "builder_available":
            if info.get("reason") == "handoff":
                return self.pool.available("next", info.get("previous"))
            return self.pool.available("any", None)
        raise SpecGap(f"no real check for guard {name}")


# ---------------------------------------------------------------- assembly
class RealPorts(Ports):
    """Ports plus the concrete adapters, so that the harness can use their extra read methods."""


def load_config(layout):
    return read_json(layout.config)


def build_ports(layout, faults=None, net_block=False, git_env=None):
    cfg = load_config(layout)
    faults = faults or ProcessFaults()
    clock = ShiftedClock(layout, cfg["time_scale"])
    process = GroupProcessControl(layout)
    credentials = RemoteCredentials(layout, cfg["remote"], cfg["credential_ttl_s"])
    url = "git://127.0.0.1:9/blocked.git" if net_block else cfg["remote"]
    excludes = Rules(read_json(cfg["rules"])).view["preserve_manifest"]["excludes"]
    git = RealGit(layout, cfg["remote"], excludes, credentials, extra_env=git_env, remote_url=url)
    pool = ProbedBuilderPool(layout, cfg["builders"])
    tasks = read_json(cfg["tasks"])["tasks"]
    ports = RealPorts(
        clock=clock, store=FileStore(layout, faults), sender=FileSender(layout, process), process=process,
        credentials=credentials, worktree=FsWorktree(layout), git=git, guards=PoolGuards(pool), builders=pool,
        catalog=_Catalog(tasks, f"file://{layout.daemon_inbox}"), ids=UniqueIds(), faults=faults,
        remote=PushRemote(layout, git, credentials), reviewers=MockReviewers(cfg["builders"]))
    return ports


class _Catalog(MockCatalog):
    def __init__(self, tasks, reply_to):
        super().__init__(tasks)
        self._reply_to = reply_to

    def reply_to(self):
        return self._reply_to
