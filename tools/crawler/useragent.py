"""The one honest User-Agent: `ONJEON-SourceArchiver/<version> (+<contact>)`.

Built from the configured contact only. An empty contact or a browser-like string is refused (raise):
we identify ourselves as a bot with a way to reach us, always. There is exactly one UA; this module has
no list of alternatives and no function that rotates, randomises or imitates another client.
"""
import re

from . import __version__

PRODUCT_NAME = "ONJEON-SourceArchiver"

_BROWSER = re.compile(
    r"mozilla|chrome|chromium|safari|firefox|gecko|webkit|msie|trident|crios|fxios|\bopera\b|\bedg(e|a|ios)?\b",
    re.IGNORECASE)
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_URL = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d+)?(/[A-Za-z0-9._~%+/?=&#:@,;-]*)?$")


class UserAgentError(ValueError):
    pass


def build_user_agent(contact_or_config, version: str = __version__) -> str:
    contact = getattr(contact_or_config, "contact", contact_or_config)
    if not isinstance(contact, str) or not contact.strip():
        raise UserAgentError("a contact (email or http(s) URL) is required to build the User-Agent")
    contact = contact.strip()
    if _BROWSER.search(contact):
        raise UserAgentError("contact looks like a browser string; refusing")
    if not (_EMAIL.match(contact) or _URL.match(contact)):
        raise UserAgentError("contact must be an email address or an http(s) URL without spaces or parentheses")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+-]{1,20}", version):
        raise UserAgentError("bad version string")
    return f"{PRODUCT_NAME}/{version} (+{contact})"
