"""Format checks shared by sample validation and source I/O boundaries."""
import re
from urllib.parse import urlsplit


def check_sha256(digest):
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        raise ValueError("sha256 must be 64 hex characters")


def https_origin(url):
    """Validate an HTTPS source URL; return its origin with the default port resolved."""
    if (not isinstance(url, str) or not url or "\\" in url
            or any(ord(c) <= 32 or ord(c) == 127 for c in url)):
        raise ValueError("invalid HTTPS source URL")
    p = urlsplit(url)
    if (p.scheme != "https" or not p.hostname
            or p.username is not None or p.password is not None):
        raise ValueError("source URL must use HTTPS without credentials")
    port = p.port if p.port is not None else 443
    if port == 0:
        raise ValueError("invalid port")
    return p.scheme, p.hostname.lower(), port
