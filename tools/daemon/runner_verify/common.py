"""Paths, the shifted clock and small file and process helpers shared by the daemon process, the harness and the
stand-in builder. Standard library only.

The clock is the real wall clock plus an offset kept in a file. The harness raises the offset to let a TTL or a
grace period pass without waiting for it (and `sleep` runs a scaled fraction of the real time). Processes, files,
git and the remote are real; only the daemon's reading of "now" is shifted. Every shift is written to the report.
"""
import contextlib
import fcntl
import json
import os
import time
import uuid
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2]
PKG_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
DEFAULT_RULES = ROOT / "docs/blueprint/proposals/설계검토_결과/daemon_rules.json"
DEFAULT_TASKS = TOOLS_DIR / "daemon/mock_tasks.json"
DEFAULT_BUILDERS = PKG_DIR / "fixtures/standin_builders.json"


class Layout:
    """Directory layout of one verification state directory."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = self.root / "config.json"
        self.clock = self.root / "clock.json"
        self.store_dir = self.root / "store"
        self.store = self.store_dir / "state.json"
        self.store_lock = self.store_dir / "state.lock"
        self.daemon_inbox = self.root / "daemon_inbox"
        self.daemon_done = self.root / "daemon_done"
        self.inbox = self.root / "inbox"  # <runner>/<envelope_id>.json: instructions sent to builder runners
        self.procs = self.root / "procs"
        self.creds = self.root / "creds"
        self.worktrees = self.root / "worktrees"
        self.clone = self.root / "clone"
        self.standin = self.root / "standin"
        self.tmp = self.root / "tmp"
        self.home = self.root / "home"

    def make(self):
        for p in (self.store_dir, self.daemon_inbox, self.daemon_done, self.inbox, self.procs, self.creds,
                  self.worktrees, self.standin, self.tmp, self.home):
            p.mkdir(parents=True, exist_ok=True)
        return self


# ---------------------------------------------------------------- files
def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_text(path, text):
    """Temp file in the same directory, fsync, rename, fsync of the directory."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def atomic_write_json(path, obj):
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1))


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@contextlib.contextmanager
def file_lock(path, shared=False):
    """flock on a dedicated lock file. The kernel drops it when the process dies, whatever the way."""
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def append_jsonl(path, record):
    """One line per record, appended under an exclusive lock so that concurrent writers do not interleave."""
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except FileNotFoundError:
        pass
    return out


def now_ns():
    return time.time_ns()


# ---------------------------------------------------------------- clock
class ClockFile:
    """The offset file: logical now = real now + offset."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = self.path.with_suffix(".lock")

    def offset(self):
        return float((read_json(self.path, {}) or {}).get("offset", 0.0))

    def now(self):
        return int(time.time() + self.offset())

    def add(self, delta, kind="advance"):
        with file_lock(self.lock):
            data = read_json(self.path, {}) or {}
            data["offset"] = float(data.get("offset", 0.0)) + float(delta)
            data["shifts"] = list(data.get("shifts", [])) + [{"by_s": float(delta), "kind": kind, "real_ns": now_ns()}]
            atomic_write_json(self.path, data)
        return self.now()

    def shifts(self):
        return list((read_json(self.path, {}) or {}).get("shifts", []))


# ---------------------------------------------------------------- /proc based process inspection (no lsof here)
def _stat_fields(pid):
    """(state, pgrp) from /proc/<pid>/stat, or None. The command name may hold spaces and parentheses."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except OSError:
        return None
    rest = raw[raw.rindex(")") + 2:].split()
    return rest[0], int(rest[2])


def group_members(pgid):
    """Live (non-zombie) processes of a process group: [(pid, state)]."""
    out = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        st = _stat_fields(int(name))
        if st and st[1] == pgid and st[0] != "Z":
            out.append((int(name), st[0]))
    return sorted(out)


def pid_alive(pid):
    st = _stat_fields(pid)
    return bool(st and st[0] != "Z")


def open_handles(root, writable_only=True, exclude_pids=()):
    """[(pid, path, flags)] of open file descriptors that point inside `root`; with writable_only, only those
    opened for writing. The equivalent of `lsof +D root` for the questions the quiescence check asks."""
    root = os.path.realpath(str(root))
    prefix = root + os.sep
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) in exclude_pids:
            continue
        fd_dir = f"/proc/{name}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if target != root and not target.startswith(prefix):
                continue
            flags = None
            with contextlib.suppress(OSError, ValueError, IndexError):
                with open(f"/proc/{name}/fdinfo/{fd}", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("flags:"):
                            flags = int(line.split()[1], 8)
            writable = flags is not None and (flags & os.O_ACCMODE) in (os.O_WRONLY, os.O_RDWR)
            if writable or not writable_only:
                found.append((int(name), target, flags))
    return found


def new_id(prefix="01RV"):
    return prefix + uuid.uuid4().hex.upper()[:22]
