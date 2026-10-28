"""Adapter interfaces. The core touches the outside world only through these.

A test bench supplies in-memory implementations (in the adapter module beside this package). A real executor would
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

    @abstractmethod
    def dispatch_guard(self):
        """Yield a committed snapshot under the same exclusive lock as transaction(), without a transaction.
        Hold through remote dispatch so lease replacement/end cannot race validation and execution.
        The snapshot is read-only to the caller; changes are never persisted. No nested mutations."""


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
    """git_write_tree_oid(worktree, includes, excludes) is the one tree-identity function. Its name is read
    from the rules. `excludes` carries the extra paths (files that matched a secret pattern) that are left out
    of the tree on top of the manifest's own excludes."""

    @abstractmethod
    def preserve_commit(self, worktree, branch, message, excludes=()): ...

    @abstractmethod
    def included_files(self, worktree, excludes=()):
        """{relative path: content} of the files the tree identity function would put into the tree."""

    @abstractmethod
    def push(self, branch, sha): ...

    @abstractmethod
    def find_commit_by_tree(self, branch, tree_oid): ...

    @abstractmethod
    def remote_ref(self, branch): ...

    @abstractmethod
    def base_sha(self, task_id): ...


class GuardChecks(ABC):
    """Lease guards whose kind is `adapter` (they need the outside world). Store and core guards never get here."""

    @abstractmethod
    def check(self, name, info): ...


class BuilderPool(ABC):
    @abstractmethod
    def select(self, task_id, reason, previous): ...

    @abstractmethod
    def available(self, which, previous): ...

    @abstractmethod
    def family(self, builder):
        """The provider family of a builder (roles.families in a real executor's configuration)."""


class ReviewerPool(ABC):
    """Reviewer candidates in the configured order: [{name, family, available}]. The core excludes the authors'
    families itself (observation layer)."""

    @abstractmethod
    def candidates(self): ...


class Catalog(ABC):
    @abstractmethod
    def task(self, task_id): ...

    @abstractmethod
    def reply_to(self): ...


class Remote(ABC):
    """A fenced write (push, pull request update). Called outside the store transaction, after the checks,
    inbox identity and intent commit, with fencing revalidated under store.dispatch_guard() held through execution.
    Credentials must belong to request.lease_id. An error leaves that identity claimed: replay must not repeat an
    ambiguous remote write. This interface does not promise exactly-once delivery or automatic recovery."""

    @abstractmethod
    def execute(self, kind, task_id, request): ...


class IdSource(ABC):
    @abstractmethod
    def new_id(self): ...


class Faults(ABC):
    @abstractmethod
    def check(self, point):
        """Raise SimulatedCrash if the process dies at this point."""

    @abstractmethod
    def fails(self, point):
        """True if a write at this point cannot be made (state store write failure). The process stays alive."""


class Ports:
    def __init__(self, clock, store, sender, process, credentials, worktree, git, guards, builders, catalog, ids, faults,
                 remote, reviewers):
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
        self.remote = remote
        self.reviewers = reviewers
