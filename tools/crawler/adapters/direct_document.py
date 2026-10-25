"""A source URL that is itself a document; no empty_ok for missing document bytes.

Discovery checks a bounded signature, not full format validity. The caller must
still apply document admission validation before archival or downstream use.
"""
from urllib.parse import urlsplit

from ..adapter import DiscoveryManifest, DocumentRef
from ..config import HARD_OBJECT_CAP_BYTES
from ._html import MetadataAdapter, http_url

_SIGNATURES = {"pdf": (b"%PDF-",), "hwp": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
               "zip": (b"PK\x03\x04", b"PK\x05\x06")}


class DirectDocumentAdapter(MetadataAdapter):
    def __init__(self, source_id, *, document_kind=None):
        super().__init__(source_id)
        if document_kind is not None and document_kind not in _SIGNATURES:
            raise ValueError("document_kind must be pdf, hwp or zip")
        self.document_kind = document_kind

    def discover(self, page_bytes, base_url):
        if not isinstance(page_bytes, bytes):
            raise TypeError("page_bytes must be bytes")
        url = http_url(base_url)
        if not url:
            return DiscoveryManifest((), "structure_changed", "invalid_source_url")
        if len(page_bytes) > HARD_OBJECT_CAP_BYTES:
            return DiscoveryManifest((), "structure_changed", "document_size_limit")
        kind = self.document_kind or urlsplit(url).path.rsplit(".", 1)[-1].lower()
        if kind not in _SIGNATURES or not page_bytes.startswith(_SIGNATURES[kind]):
            return DiscoveryManifest((), "structure_changed", "unexpected_document_signature")
        return DiscoveryManifest((DocumentRef(url, kind),), "complete")
