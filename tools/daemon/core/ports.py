"""Adapter interfaces. The core touches the outside world only through these.

A test bench supplies in-memory implementations (in the adapters module beside this package). A real executor would
supply real ones (clock, state file with a lock, process control, git, sender). No real adapter exists here.
"""
from abc import ABC, abstractmethod


class SimulatedCrash(Exception):
    """Raised by a fault-injection point to model a daemon process dying at that point."""


class PreconditionFailed(Exception):
    def __init__(self, failures):
        super().__init__(f"precondition_failed: {failures}")
        self.failures = failures


class SpecGap(Exception):
    """The contract lacks a structured field the core needs. The core stops instead of guessing."""


class IndexLockError(Exception):
    def __init__(self, owner_pid_alive=False):
        super().__init__("index.lock")
        self.owner_pid_alive = owner_pid_alive


class DiskFullError(Exception):
    pass


class CommitFailed(Exception):
    def __init__(self, reason="other"):
        super().__init__(f"commit failed: {reason}")
        self.reason = reason


class PushFailed(Exception):
    """reason in {network, permission_denied, protected_branch, other}"""

    def __init__(self, reason="other"):
        super().__init__(f"push failed: {reason}")
        self.reason = reason


class QueryUnavailable(Exception):
    pass


class Clock(ABC):
    @abstractmethod
    def now(self): ...

    @abstractmethod
    def sleep(self, seconds): ...


class Store(ABC):
    @abstractmethod
    def transaction(self):
        """Context manager yielding a mutable dict. Commit on normal exit, discard on exception, all or nothing."""

    @abstractmethod
    def snapshot(self):
        """A deep copy of the committed data."""


class Sender(ABC):
    @abstractmethod
    def send(self, task_id, instruction): ...

    @abstractmethod
    def request_stop(self, task_id, builder): ...


class ProcessControl(ABC):
    @abstractmethod
    def alive_count(self, task_id): ...

    @abstractmethod
    def terminate_group(self, task_id): ...


class Credentials(ABC):
    @abstractmethod
    def issue(self, name, task_id, lease_id): ...

    @abstractmethod
    def revoke(self, name, task_id, lease_id): ...


class Worktree(ABC):
    @abstractmethod
    def path_for(self, task_id, lease_id): ...

    @abstractmethod
    def set_readonly(self, path): ...

    @abstractmethod
    def max_mtime(self, path): ...

    @abstractmethod
    def open_write_handles(self, path): ...


class Git(ABC):
    """git_write_tree_oid(worktree) is the one tree-identity function. Its name is read from the rules."""

    @abstractmethod
    def preserve_commit(self, worktree, branch, message): ...

    @abstractmethod
    def push(self, branch, sha): ...

    @abstractmethod
    def find_commit_by_tree(self, branch, tree_oid): ...

    @abstractmethod
    def remote_ref(self, branch): ...

    @abstractmethod
    def base_sha(self, task_id): ...


class GuardChecks(ABC):
    @abstractmethod
    def check(self, name, info): ...


class BuilderPool(ABC):
    @abstractmethod
    def select(self, task_id, reason, previous): ...

    @abstractmethod
    def available(self, which, previous): ...


class Catalog(ABC):
    @abstractmethod
    def task(self, task_id): ...

    @abstractmethod
    def branch_for(self, task_id, attempt): ...

    @abstractmethod
    def reply_to(self): ...


class IdSource(ABC):
    @abstractmethod
    def new_id(self): ...


class Faults(ABC):
    @abstractmethod
    def check(self, point): ...


class Ports:
    def __init__(self, clock, store, sender, process, credentials, worktree, git, guards, builders, catalog, ids, faults):
        self.clock = clock
        self.store = store
        self.sender = sender
        self.process = process
        self.credentials = credentials
        self.worktree = worktree
        self.git = git
        self.guards = guards
        self.builders = builders
        self.catalog = catalog
        self.ids = ids
        self.faults = faults
