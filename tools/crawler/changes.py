"""Conditional GET and streaming byte comparison, with no network or file writes.

decide consumes a 200 body once, holding only its current chunk and hash state.
The caller owns/closes the response and supplies already admitted document bytes.
Only a new/changed decision needs a body spool entry. Its SHA-256 identifies an
immutable version; a URL must never be used as an overwritable body storage key.
Unchanged checks still need an archive observation for exact state recovery.
"""
import hashlib
import math
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .config import DEFAULT_VERIFY_EVERY_S, HARD_OBJECT_CAP_BYTES
from .state import CrawlState, _validator
from .transport import BodyTooLargeError, Response


def full_verification_due(state: Optional[CrawlState], *, clock: Callable[[], float] = time.time,
                          verify_every_s: float = DEFAULT_VERIFY_EVERY_S) -> bool:
    if (isinstance(verify_every_s, bool) or not isinstance(verify_every_s, (int, float))
            or not math.isfinite(verify_every_s) or verify_every_s < 0):
        raise ValueError("verify_every_s must be finite and nonnegative")
    now = clock()
    if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
        raise ValueError("clock must return finite nonnegative epoch seconds")
    return (state is None or state.last_sha256 is None or not state.original_retained
            or state.last_verified is None or now - state.last_verified >= verify_every_s)


def conditional_headers(state: Optional[CrawlState], *, clock: Callable[[], float] = time.time,
                        verify_every_s: float = DEFAULT_VERIFY_EVERY_S) -> dict:
    """Empty headers force a full byte check, even if the origin repeats a bad ETag."""
    if full_verification_due(state, clock=clock, verify_every_s=verify_every_s):
        return {}
    headers = {}
    if state.etag:
        headers["If-None-Match"] = _validator(state.etag, "etag")
    if state.last_modified:
        headers["If-Modified-Since"] = _validator(state.last_modified, "last_modified")
    return headers


@dataclass(frozen=True)
class ChangeDecision:
    kind: str
    status: int
    sha256: str
    size_bytes: int
    etag: Optional[str]
    last_modified: Optional[str]

    @property
    def needs_spool(self) -> bool:
        return self.kind in ("new", "changed")

    @property
    def version_key(self) -> str:
        return f"objects/sha256/{self.sha256[:2]}/{self.sha256[2:4]}/{self.sha256}"

    def observation_extra(self, *, next_due: float, original_retained: bool) -> dict:
        """Pass as put_observation(extra=...); supply its digest/size from this decision.

        Retention must describe the current hash AFTER archiving, never a queued
        upload. No writes occur here. The state DB validates scheduling metadata.
        """
        return {"change": self.kind, "status": self.status, "etag": self.etag,
                "last_modified": self.last_modified, "next_due": next_due,
                "original_retained": original_retained}


def decide(response: Response, state: Optional[CrawlState], *,
           object_cap_bytes: int = HARD_OBJECT_CAP_BYTES) -> ChangeDecision:
    """Return new/changed/unchanged_same_hash/unchanged; errors never count as success.

    A 304 without an existing retained object is invalid. Unsupported statuses,
    invalid chunks, oversized/truncated streams raise; the caller records a failure
    observation with its reason rather than archiving a partial new version.
    """
    if type(object_cap_bytes) is not int or not 1 <= object_cap_bytes <= HARD_OBJECT_CAP_BYTES:
        raise ValueError("object_cap_bytes must be within the 64 MiB hard cap")
    if response.status not in (200, 304):
        raise ValueError("change detection requires a 200 or 304 response")
    headers = {k.lower(): v for k, v in response.headers.items()}
    etag = _validator(headers.get("etag"), "etag")
    modified = _validator(headers.get("last-modified"), "last_modified")
    if response.status == 304:
        if state is None or state.last_sha256 is None or not state.original_retained:
            raise ValueError("304 requires an existing retained object")
        return ChangeDecision("unchanged", 304, state.last_sha256, 0,
                              etag or state.etag, modified or state.last_modified)
    hasher = hashlib.sha256()
    total = 0
    declared = headers.get("content-length")
    length = None
    if declared is not None:
        if not (declared.isascii() and declared.isdigit()) or len(declared) > 18:
            raise ValueError("invalid Content-Length")
        length = int(declared)
        if length > object_cap_bytes:
            raise BodyTooLargeError("declared body exceeds object cap")
    for chunk in response.body_iter:
        if not isinstance(chunk, bytes):
            raise ValueError("body must yield byte chunks")
        total += len(chunk)
        if total > object_cap_bytes:
            raise BodyTooLargeError("body exceeds object cap")
        hasher.update(chunk)
    if length is not None and length != total:
        raise ValueError("body length does not match Content-Length")
    digest = hasher.hexdigest()
    kind = ("new" if state is None or state.last_sha256 is None else
            "unchanged_same_hash" if state.last_sha256 == digest else "changed")
    return ChangeDecision(kind, 200, digest, total, etag, modified)
