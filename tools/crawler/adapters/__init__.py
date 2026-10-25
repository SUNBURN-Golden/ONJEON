"""Versioned built-in parsers. Importing registers classes only; no collection runs.

Use a fresh builtin_registry() for isolated configuration, or register_adapters()
to explicitly add these exact versions to an existing AdapterRegistry.
"""
from ..adapter import AdapterRegistry
from .direct_document import DirectDocumentAdapter
from .link_list import LinkListAdapter, LinkListConfig
from .member_table import MemberRow, MemberTableAdapter, MemberTableConfig, MemberTableManifest

BUILTINS = (("link_list", LinkListAdapter), ("member_table", MemberTableAdapter),
            ("direct_document", DirectDocumentAdapter))


def register_adapters(registry):
    for name, adapter_class in BUILTINS:
        registry.register(name, adapter_class.VERSION, adapter_class)
    return registry


def builtin_registry():
    return register_adapters(AdapterRegistry())


registry = builtin_registry()

__all__ = ["LinkListAdapter", "LinkListConfig", "MemberTableAdapter", "MemberTableConfig",
           "MemberRow", "MemberTableManifest", "DirectDocumentAdapter", "builtin_registry",
           "register_adapters", "registry"]
