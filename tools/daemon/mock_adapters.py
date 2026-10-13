"""In-memory adapters for the dry run: virtual clock, store, builders, processes, credentials, mock git.

Nothing here touches a real process, file system, network, git remote or model. The mock git computes
tree identity from path, mode and content with a Git-like object model; it is a model, not Git.
"""
import contextlib
import copy
import fnmatch
import hashlib
import re
import threading

from .core.ports import (
    BuilderPool, Catalog, Clock, CommitFailed, Credentials, Faults, Git, GuardChecks, IdSource, Ports,
    ProcessControl, PushFailed, Remote, Sender, SimulatedCrash, SpecGap, Store, Worktree,
)


class VirtualClock(Clock):
    """clock.now() / advance(seconds) / set(ts). advance ticks one virtual second at a time so that
    mock processes write while time passes."""

    def __init__(self, start=1_000_000):
        self._now = start
        self._listeners = []

    def now(self):
        return self._now

    def set(self, ts):
        self._now = ts

    def advance(self, seconds):
        for _ in range(int(seconds)):
            self._now += 1
            for cb in list(self._listeners):
                cb(self._now)

    def sleep(self, seconds):
        self.advance(seconds)

    def on_tick(self, cb):
        self._listeners.append(cb)


class MemoryStore(Store):
    def __init__(self):
        self._data = {"tasks": {}, "journal": []}
        self._lock = threading.RLock()

    @contextlib.contextmanager
    def transaction(self):
        with self._lock:
            work = copy.deepcopy(self._data)
            yield work
            self._data = work  # reached only when the body did not raise: all or nothing

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def tamper(self, fn):
        """Fault injection: change the persisted state the way a crash or a bad write would."""
        with self.transaction() as d:
            fn(d)


class IdGen(IdSource):
    def __init__(self):
        self.n = 0

    def new_id(self):
        self.n += 1
        return f"01MOCK{self.n:020d}"


class MockFaults(Faults):
    def __init__(self):
        self.armed = {}
        self.failing = {}
        self.hits = []

    def arm(self, point, times=1):
        self.armed[point] = times

    def arm_fail(self, point, times=1):
        """The next `times` writes at this point cannot be made (None: until cleared)."""
        self.failing[point] = times

    def clear_fail(self, point):
        self.failing.pop(point, None)

    def fails(self, point):
        n = self.failing.get(point, 0)
        if n is None:
            return True
        if n > 0:
            self.failing[point] = n - 1
            return True
        return False

    def check(self, point):
        n = self.armed.get(point, 0)
        if n > 0:
            self.armed[point] = n - 1
            self.hits.append(point)
            raise SimulatedCrash(point)


class MockCredentials(Credentials):
    def __init__(self):
        self.active = set()
        self.log = []

    def issue(self, name, task_id, lease_id):
        self.active.add((name, task_id))
        self.log.append(("issue", name, task_id))

    def revoke(self, name, task_id, lease_id):
        self.active.discard((name, task_id))
        self.log.append(("revoke", name, task_id))

    def is_active(self, name, task_id):
        return (name, task_id) in self.active


# ------------------------------------------------------------------ worktrees and git
class MockWorktree(Worktree):
    def __init__(self, clock, credentials):
        self.clock = clock
        self.creds = credentials
        self.trees = {}
        self.denied_writes = []

    def path_for(self, task_id, lease_id):
        return f"/mock/worktrees/{task_id}/{lease_id}"

    def ensure(self, path):
        return self.trees.setdefault(path, {"files": {}, "readonly": False, "handles": 0})

    def set_readonly(self, path):
        self.ensure(path)["readonly"] = True

    def max_mtime(self, path):
        files = self.ensure(path)["files"]
        return max((e["mtime"] for e in files.values()), default=0)

    def open_write_handles(self, path):
        return self.ensure(path)["handles"]

    # --- file operations. writer='builder' is subject to the write ban and the revoked credential.
    def _guard(self, path, writer, task_id):
        tree = self.ensure(path)
        if writer == "builder":
            if tree["readonly"] or (task_id and not self.creds.is_active("builder_write_credential", task_id)):
                self.denied_writes.append((self.clock.now(), path))
                raise PermissionError(path)
        return tree

    def write(self, path, rel, content, mode=0o644, writer="harness", task_id=None):
        tree = self._guard(path, writer, task_id)
        parts = rel.split("/")
        for i in range(1, len(parts)):
            tree["files"].setdefault("/".join(parts[:i]), {"kind": "dir", "mode": 0o755, "content": "", "mtime": self.clock.now()})
        tree["files"][rel] = {"kind": "file", "mode": mode, "content": content, "mtime": self.clock.now()}

    def symlink(self, path, rel, target, writer="harness"):
        tree = self._guard(path, writer, None)
        tree["files"][rel] = {"kind": "symlink", "mode": 0o777, "content": target, "mtime": self.clock.now()}

    def mkdir(self, path, rel, writer="harness"):
        tree = self._guard(path, writer, None)
        tree["files"][rel] = {"kind": "dir", "mode": 0o755, "content": "", "mtime": self.clock.now()}

    def chmod(self, path, rel, mode, writer="harness"):
        tree = self._guard(path, writer, None)
        tree["files"][rel]["mode"] = mode
        tree["files"][rel]["mtime"] = self.clock.now()

    def delete(self, path, rel, writer="harness"):
        tree = self._guard(path, writer, None)
        tree["files"].pop(rel, None)

    def listing(self, path):
        return sorted(self.ensure(path)["files"])


class MockGit(Git):
    """Tree identity = SHA-1 over a Git-like tree object built from (path, mode, content)."""

    def __init__(self, worktree, excludes):
        self.wt = worktree
        pat = re.compile(r"^[\w.*/-]+$")
        self.excludes = [e for e in excludes if pat.match(e)]
        self.ignored_exclude_entries = [e for e in excludes if not pat.match(e)]
        self.commits = {}
        self.remote = {}
        self.injected = {}
        self.commit_count = 0
        self.push_count = 0
        self.before_commit = []
        self.oid_calls = 0
        self.trace = []  # (operation, journal length when it physically happened)
        self.trace_len = lambda: 0
        self.consumed = {}

    # fault injection: a list of exceptions consumed in order for one operation
    def inject(self, op, excs):
        self.injected[op] = list(excs)

    def _maybe_fail(self, op):
        q = self.injected.get(op)
        if q:
            self.consumed[op] = self.consumed.get(op, 0) + 1
            exc = q.pop(0)
            if exc is not None:
                raise exc

    # --- the one tree identity function (name read from concurrency.quiescence.manifest_function)
    def _excluded(self, rel, extra=()):
        if rel in extra:
            return True
        parts = rel.split("/")
        for pat in self.excludes:
            if pat.endswith("/"):
                if pat[:-1] in parts[:-1]:
                    return True
            elif fnmatch.fnmatch(parts[-1], pat):
                return True
        return False

    def _gitignored(self, tree, rel):
        ign = tree["files"].get(".gitignore")
        if not ign:
            return False
        for line in ign["content"].splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("/"):
                if line[:-1] in rel.split("/")[:-1]:
                    return True
            elif fnmatch.fnmatch(rel.split("/")[-1], line) or fnmatch.fnmatch(rel, line):
                return True
        return False

    def _included(self, worktree, extra=()):
        tree = self.wt.ensure(worktree)
        leaves = {}
        for rel, e in tree["files"].items():
            if e["kind"] == "dir":
                continue  # a Git tree holds no empty directories
            if self._excluded(rel, extra) or self._gitignored(tree, rel):
                continue
            leaves[rel] = e
        return leaves

    def included_files(self, worktree, excludes=()):
        return {rel: e["content"] for rel, e in self._included(worktree, tuple(excludes)).items()}

    def git_write_tree_oid(self, worktree, includes=None, excludes=()):
        self.oid_calls += 1
        self._maybe_fail("git_write_tree_oid")
        return self._hash(self._included(worktree, tuple(excludes or ())))

    @staticmethod
    def _hash(leaves):
        root = {}
        for rel, e in leaves.items():
            parts = rel.split("/")
            cur = root
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = ("leaf", e)

        def tree_sha(node):
            ents = []
            for name, val in node.items():
                if isinstance(val, tuple):
                    e = val[1]
                    if e["kind"] == "symlink":
                        mode, data = "120000", e["content"].encode()
                    else:
                        mode, data = ("100755" if e["mode"] & 0o111 else "100644"), e["content"].encode()
                    sha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
                    ents.append((name, mode, sha))
                else:
                    sub = tree_sha(val)
                    if sub is not None:
                        ents.append((name + "/", "40000", sub))
            if not ents:
                return None
            ents.sort(key=lambda x: x[0])
            body = b"".join(m.encode() + b" " + n.rstrip("/").encode() + b"\0" + bytes.fromhex(s) for n, m, s in ents)
            return hashlib.sha1(b"tree %d\0" % len(body) + body).hexdigest()

        return tree_sha(root) or hashlib.sha1(b"tree 0\0").hexdigest()

    # --- Git port
    def preserve_commit(self, worktree, branch, message, excludes=()):
        self._maybe_fail("commit")
        for hook in self.before_commit:
            hook()
        tree_oid = self.git_write_tree_oid(worktree, excludes=excludes)
        self.commit_count += 1
        self.trace.append(("commit", self.trace_len()))
        sha = hashlib.sha1(f"commit {self.commit_count} {tree_oid} {message}".encode()).hexdigest()
        self.commits[sha] = {"tree": tree_oid, "branch": branch, "message": message,
                             "paths": sorted(self._included(worktree, tuple(excludes)))}
        return {"commit_tree_oid": tree_oid, "wip_commit_sha": sha}

    def push(self, branch, sha):
        self._maybe_fail("push")
        self.push_count += 1
        self.trace.append(("push", self.trace_len()))
        self.remote[branch] = sha
        return sha

    def remote_ref(self, branch):
        self._maybe_fail("remote_ref")
        return self.remote.get(branch)

    def find_commit_by_tree(self, branch, tree_oid):
        self._maybe_fail("find_commit")
        for sha, c in self.commits.items():
            if c["branch"] == branch and c["tree"] == tree_oid:
                return sha
        return None

    def base_sha(self, task_id):
        return "b" * 40


# ------------------------------------------------------------------ processes, sender, pool, guards
class MockProc:
    def __init__(self, task_id, wt, path, writes_forever=False, term_ignored=False, survives_kill=False, ghost=False):
        self.task_id = task_id
        self.wt = wt
        self.path = path
        self.alive = True
        self.term_ignored = term_ignored
        self.survives_kill = survives_kill
        self.ghost = ghost
        self.writes_forever = writes_forever
        self.n = 0
        wt.ensure(path)["handles"] = 1

    def tick(self, now):
        if self.alive and self.writes_forever:
            self.n += 1
            with contextlib.suppress(PermissionError):
                self.wt.write(self.path, "progress.txt", f"tick {self.n}", writer="builder", task_id=self.task_id)
        elif not self.alive and self.ghost:
            with contextlib.suppress(PermissionError):
                self.wt.write(self.path, "ghost.txt", f"late {now}", writer="builder", task_id=self.task_id)

    def stop(self):
        if not self.term_ignored:
            self.alive = False
            self.wt.ensure(self.path)["handles"] = 0

    def kill(self):
        if not self.survives_kill:
            self.alive = False
            self.wt.ensure(self.path)["handles"] = 0


class MockProcessControl(ProcessControl):
    def __init__(self, clock):
        self.procs = {}
        clock.on_tick(lambda now: [p.tick(now) for p in list(self.procs.values())])

    def spawn(self, proc):
        self.procs[proc.task_id] = proc

    def alive_count(self, task_id):
        p = self.procs.get(task_id)
        return 1 if p and p.alive else 0

    def terminate_group(self, task_id):
        p = self.procs.get(task_id)
        if p:
            p.kill()

    def request_stop(self, task_id):
        p = self.procs.get(task_id)
        if p:
            p.stop()


class MockSender(Sender):
    def __init__(self, process):
        self.process = process
        self.sent = []
        self.inboxes = {}
        self.stops = []
        self.hold = False
        self.in_flight = []

    def send(self, task_id, instruction):
        self.sent.append({"envelope_id": instruction["envelope_id"], "task_id": task_id,
                          "lease_generation": instruction["lease_generation"]})
        if self.hold:
            self.in_flight.append(copy.deepcopy(instruction))
        else:
            self.inboxes.setdefault(instruction["runner"], []).append(copy.deepcopy(instruction))

    def release(self):
        for ins in self.in_flight:
            self.inboxes.setdefault(ins["runner"], []).append(ins)
        self.in_flight = []

    def request_stop(self, task_id, builder):
        self.stops.append((task_id, builder))
        self.process.request_stop(task_id)


class MockBuilderPool(BuilderPool):
    def __init__(self, builders):
        self.builders = builders
        self.unavailable = set()

    def _avail(self):
        return [b for b in self.builders if b["name"] not in self.unavailable]

    def _after(self, previous):
        names = [b["name"] for b in self.builders]
        start = names.index(previous) + 1 if previous in names else 0
        for b in self.builders[start:]:
            if b["name"] not in self.unavailable:
                return b
        return None

    def available(self, which, previous):
        if which == "next":
            return self._after(previous) is not None
        return bool(self._avail())

    def select(self, task_id, reason, previous):
        if reason == "handoff":
            return self._after(previous)
        for b in self.builders:
            if b["name"] == previous and previous not in self.unavailable:
                return b
        av = self._avail()
        return av[0] if av else None


class MockCatalog(Catalog):
    def __init__(self, tasks):
        self.tasks = {t["task_id"]: t for t in tasks}

    def task(self, task_id):
        return self.tasks[task_id]

    def reply_to(self):
        return "mock://daemon-inbox"


class MockGuards(GuardChecks):
    """The only guard that needs the outside world: is a builder runner available."""

    def __init__(self, pool):
        self.pool = pool

    def check(self, name, info):
        if name == "builder_available":
            return self.pool.available("any", None)
        raise SpecGap(f"no mock check for guard {name}")


class MockRemote(Remote):
    def __init__(self):
        self.writes = []

    def execute(self, kind, task_id, request):
        self.writes.append((kind, task_id, request.get("lease_generation"), request.get("envelope_id")))


def build_ports(clock, tasks, builders, excludes):
    creds = MockCredentials()
    wt = MockWorktree(clock, creds)
    proc = MockProcessControl(clock)
    pool = MockBuilderPool(builders)
    catalog = MockCatalog(tasks)
    return Ports(
        clock=clock, store=MemoryStore(), sender=MockSender(proc), process=proc, credentials=creds, worktree=wt,
        git=MockGit(wt, excludes), guards=MockGuards(pool), builders=pool,
        catalog=catalog, ids=IdGen(), faults=MockFaults(), remote=MockRemote(),
    )
