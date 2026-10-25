"""Pure source-adapter contracts for L0/L1 discovery; no fetching or side effects.

Only complete and explicitly verified empty_ok manifests count as successful discovery.
Partial links from blocked/structure_changed listings may be retained as evidence, but never
turn those listings into successes. Concrete site adapters belong in later nodes.
"""
import abc
import inspect
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple, Type

from . import __version__
from .transport import Response

Completeness = Literal["complete", "blocked", "structure_changed", "empty_ok"]


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


@dataclass(frozen=True)
class DocumentRef:
    url: str
    kind: str
    title: Optional[str] = None

    def __post_init__(self):
        _nonempty(self.url, "url")
        _nonempty(self.kind, "kind")
        if self.title is not None and not isinstance(self.title, str):
            raise ValueError("title must be a string or None")


@dataclass(frozen=True)
class DiscoveryManifest:
    """Snapshot of a document list; input lists are copied to an immutable tuple.

An empty complete manifest is invalid: adapters must explicitly establish empty_ok.
reason is optional diagnostic evidence, especially for incomplete listings.
"""

    documents: Tuple[DocumentRef, ...]
    completeness: Completeness
    reason: Optional[str] = None

    def __post_init__(self):
        if self.completeness not in ("complete", "blocked", "structure_changed", "empty_ok"):
            raise ValueError("unknown discovery completeness")
        documents = tuple(self.documents)
        if not all(isinstance(doc, DocumentRef) for doc in documents):
            raise ValueError("documents must contain DocumentRef instances")
        if self.completeness == "empty_ok" and documents:
            raise ValueError("empty_ok cannot contain documents")
        if self.completeness == "complete" and not documents:
            raise ValueError("an empty listing requires explicit empty_ok")
        if self.reason is not None:
            _nonempty(self.reason, "reason")
        object.__setattr__(self, "documents", documents)

    @property
    def is_success(self) -> bool:
        return self.completeness in ("complete", "empty_ok")


@dataclass(frozen=True)
class Classification:
    """An adapter decision; every gap carries a reason for the caller's gap record."""

    kind: Literal["ok", "gap"]
    reason: Optional[str] = None

    def __post_init__(self):
        if self.kind == "gap":
            _nonempty(self.reason, "gap reason")
        elif self.kind != "ok" or self.reason is not None:
            raise ValueError("classification must be ok or gap(reason)")


class SourceAdapter(abc.ABC):
    """Versioned parser contract. No I/O, clocks, sleeping or randomness are needed.

    discover receives already capped listing bytes and resolves links against base_url.
    classify inspects response metadata without consuming the one-shot body. An ok
    classification still requires validate_document before a document can be accepted.
    A gap means stop and record the reason; callers must not try alternative identities.
    """

    def __init__(self, source_id: str, version: str):
        _nonempty(source_id, "source_id")
        _nonempty(version, "adapter version")
        self.source_id = source_id
        self.version = version

    @abc.abstractmethod
    def discover(self, page_bytes: bytes, base_url: str) -> DiscoveryManifest:
        """Distinguish verified listing termination from missing/changed/blocked structure."""

    @abc.abstractmethod
    def classify(self, response: Response) -> Classification:
        """Return ok or gap(reason), leaving the body stream for document validation."""


class DuplicateAdapterError(ValueError):
    pass


class UnknownAdapterError(LookupError):
    pass


class AdapterRegistry:
    """Explicit (name, version) lookup, with no automatic imports or latest fallback."""

    def __init__(self):
        self._classes: Dict[Tuple[str, str], Type[SourceAdapter]] = {}

    def register(self, name: str, version: str, adapter_class: Type[SourceAdapter]) -> None:
        _nonempty(name, "adapter name")
        _nonempty(version, "adapter version")
        if (not isinstance(adapter_class, type) or not issubclass(adapter_class, SourceAdapter)
                or inspect.isabstract(adapter_class)):
            raise TypeError("adapter_class must be a concrete SourceAdapter subclass")
        key = (name, version)
        if key in self._classes:
            raise DuplicateAdapterError(f"adapter already registered: {name}@{version}")
        self._classes[key] = adapter_class

    def resolve(self, name: str, version: str) -> Type[SourceAdapter]:
        _nonempty(name, "adapter name")
        _nonempty(version, "adapter version")
        try:
            return self._classes[(name, version)]
        except KeyError:
            raise UnknownAdapterError(f"unknown adapter: {name}@{version}") from None


def observation_metadata(adapter: SourceAdapter, user_agent_version: str = __version__) -> Dict[str, str]:
    """Version evidence only; the observation owner supplies timestamps and response data.

    Pass the version used to build the fixed User-Agent when overriding its package default.
    This helper neither builds nor changes request headers.
    """
    if not isinstance(adapter, SourceAdapter):
        raise TypeError("adapter must be a SourceAdapter")
    _nonempty(user_agent_version, "user_agent_version")
    return {"source_id": adapter.source_id, "adapter_version": adapter.version,
            "user_agent_version": user_agent_version}
