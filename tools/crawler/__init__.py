"""ONJEON source-archive crawler core (stdlib only; HTTP only; network OFF by default).

Modules: config (validated settings), useragent (the one honest UA), robots (robots.txt policy),
transport (the only code that may open a socket). Real collection needs config.network_enabled
AND the env flag ONJEON_CRAWLER_ALLOW_NETWORK=1; see transport.py.
"""

__version__ = "0.1.0"
