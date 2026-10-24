"""Bounded, streaming document admission checks (stdlib only, no I/O).

This is signature/MIME validation, not a full PDF/Office parser or malware scanner.
Supported expectations are PDF, legacy Word DOC, and Word DOCX (ZIP container signature).
Unknown formats fail closed. A caller owns/closes the stream, including on early rejection;
validation consumes it and does not retain or return the document. Archive callers must tee
chunks to their bounded spool rather than collecting them in memory.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from .config import HARD_OBJECT_CAP_BYTES
from .transport import BodyTooLargeError, TransportError

PREFIX_BYTES = 8192


class RejectionReason(str, Enum):
    EMPTY = "empty"
    TOO_LARGE = "too_large"
    MIME_MISMATCH = "mime_mismatch"
    MAGIC_MISMATCH = "magic_mismatch"
    LOGIN_HTML = "login_html"
    ERROR_HTML = "error_html"
    CHALLENGE_HTML = "challenge_html"
    UNEXPECTED_HTML = "unexpected_html"
    UNSUPPORTED_TYPE = "unsupported_type"
    LENGTH_MISMATCH = "length_mismatch"
    STREAM_ERROR = "stream_error"
    INVALID_STREAM = "invalid_stream"


@dataclass(frozen=True)
class BodyStreamInfo:
    """One-shot byte chunks plus HTTP metadata; lengths are hints, never trusted totals.

    body_iter should yield bounded chunks (the existing transport uses 64 KiB).
    content_type is the response MIME; declared_type in validate_document is the expected
    document kind or MIME. Missing/generic MIME is permitted only with matching magic.
    """

    body_iter: Iterable[bytes]
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    object_cap_bytes: int = HARD_OBJECT_CAP_BYTES

    def __post_init__(self):
        if (type(self.object_cap_bytes) is not int
                or not 1 <= self.object_cap_bytes <= HARD_OBJECT_CAP_BYTES):
            raise ValueError("object_cap_bytes must be between 1 and the 64 MiB hard cap")
        if self.content_length is not None and (
                type(self.content_length) is not int or self.content_length < 0):
            raise ValueError("content_length must be a nonnegative integer or None")
        if self.content_type is not None and not isinstance(self.content_type, str):
            raise ValueError("content_type must be a string or None")


@dataclass(frozen=True)
class ValidationResult:
    """size_bytes counts consumed bytes; on early rejection it may be a partial count."""

    reason: Optional[RejectionReason]
    size_bytes: int

    @property
    def ok(self) -> bool:
        return self.reason is None


_MIMES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MAGIC = {"pdf": b"%PDF-", "doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "docx": b"PK\x03\x04"}
_GENERIC_MIMES = ("", "application/octet-stream", "binary/octet-stream")
_HTML_MARKERS = ("<!doctype html", "<html", "<head", "<body", "<form", "<title", "<script")
# Deliberately small and bounded; binary documents containing these words are not HTML.
_LOGIN_MARKERS = ("login required", "please log in", "sign in to continue", "type=\"password\"",
                  "type='password'", "로그인이 필요", "로그인 후")
_ERROR_MARKERS = ("access denied", "not found", "internal server error", "service unavailable",
                  "서비스 점검", "오류가 발생", "접근이 차단")
_CHALLENGE_MARKERS = ("captcha", "verify you are human", "unusual traffic")


def _mime(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _prefix_rejection(prefix: bytearray, kind: str, mime: str) -> Optional[RejectionReason]:
    magic_ok = prefix.startswith(_MAGIC[kind])
    # A valid binary signature takes precedence over words in document text/metadata.
    # A response explicitly labelled HTML still fails the MIME check below.
    text = prefix.decode("utf-8", errors="replace").lower() if not magic_ok else ""
    if not magic_ok and (mime in ("text/html", "application/xhtml+xml")
                         or any(marker in text for marker in _HTML_MARKERS)):
        for markers, reason in (
            (_CHALLENGE_MARKERS, RejectionReason.CHALLENGE_HTML),
            (_LOGIN_MARKERS, RejectionReason.LOGIN_HTML),
            (_ERROR_MARKERS, RejectionReason.ERROR_HTML),
        ):
            if any(marker in text for marker in markers):
                return reason
        return RejectionReason.UNEXPECTED_HTML
    if mime not in (_MIMES[kind], *_GENERIC_MIMES):
        return RejectionReason.MIME_MISMATCH
    if not magic_ok:
        return RejectionReason.MAGIC_MISMATCH
    return None


def validate_document(body_stream_info: BodyStreamInfo, declared_type: str) -> ValidationResult:
    """Consume a bounded stream; return typed rejection evidence, or reason=None on success.

    Length checks use both the declared size and actual bytes. Only PREFIX_BYTES are retained
    across chunks. Transport truncation/errors never become successful document validation.
    The hard cap cannot be raised, but a source's configured object cap can lower it.
    """
    info = body_stream_info
    if not isinstance(info, BodyStreamInfo):
        raise TypeError("body_stream_info must be BodyStreamInfo")
    expected = _mime(declared_type) if isinstance(declared_type, str) else ""
    kind = next((key for key, mime in _MIMES.items() if expected in (key, mime)), None)
    if kind is None:
        return ValidationResult(RejectionReason.UNSUPPORTED_TYPE, 0)
    if info.content_length is not None and info.content_length > info.object_cap_bytes:
        return ValidationResult(RejectionReason.TOO_LARGE, 0)
    prefix = bytearray()
    total = 0
    try:
        for chunk in info.body_iter:
            if not isinstance(chunk, bytes):
                return ValidationResult(RejectionReason.INVALID_STREAM, total)
            total += len(chunk)
            if total > info.object_cap_bytes:
                return ValidationResult(RejectionReason.TOO_LARGE, total)
            if len(prefix) < PREFIX_BYTES:
                prefix.extend(chunk[:PREFIX_BYTES - len(prefix)])
    except BodyTooLargeError:
        return ValidationResult(RejectionReason.TOO_LARGE, total)
    except (TransportError, OSError):
        return ValidationResult(RejectionReason.STREAM_ERROR, total)
    if total == 0:
        return ValidationResult(RejectionReason.EMPTY, 0)
    if info.content_length is not None and total != info.content_length:
        return ValidationResult(RejectionReason.LENGTH_MISMATCH, total)
    return ValidationResult(_prefix_rejection(prefix, kind, _mime(info.content_type or "")), total)
