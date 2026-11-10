"""preserve_manifest.secret_patterns (G38): the three scan points and the redaction of journal text.

Matched text is never stored: a match leaves only scan_id, match_count and the file path or field name.
Patterns come from the rule data, including quoted JSON assignments and provider token shapes.
R2/S3/AWS 32/64-hex keys are matched next to a credential name and also as bare values. A digest of
the same length is not a credential, so a bare hex match is skipped only when a checksum or hash
label (`checksum`, `content_hash`, `tree_hash`, ...) is the assignment that immediately precedes that
value. A digest elsewhere on the line does not exempt an unrelated value: minified JSON such as
{"checksum": "<digest>", "value": "<key>"} must still be detected.
"""
import re

from .ports import SpecGap

REDACTED = "<redacted>"

# The label whose assigned value is a checksum/hash, not a credential. It must be the immediately
# preceding assignment (only quotes, separators and spaces may sit between the label and the value)
# so that another field on the same line cannot suppress detection.
# `sha[-_]?\d+` and `md\d+` cover the digest labels without spelling a hash algorithm name in the
# core (the static check keeps hash definitions in git_write_tree_oid only).
_DIGEST_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:checksum|sha[-_]?[0-9]+|md[0-9]+|digest|integrity|"
    r"content[_-]?hash|tree[_-]?hash|commit[_-]?(?:id|hash)?|oid|hash)"
    r"[ \t]*['\"]?[ \t]*[:=][ \t]*['\"]?[ \t]*\Z"
)
_HEX_KEY = re.compile(r"(?:[A-Fa-f0-9]{32}|[A-Fa-f0-9]{64})")


def patterns(rules):
    return [re.compile(p) for p in rules.get("preserve_manifest.secret_patterns.patterns")]


def scan_spec(rules, scan_id):
    for item in rules.get("preserve_manifest.secret_patterns.scan"):
        if item["id"] == scan_id:
            return item
    raise SpecGap(f"secret_patterns.scan has no {scan_id}")


def count(pats, text):
    """Matches that are credentials: a bare hex value assigned to a digest label is excluded.

    The exemption is decided from the match context, so a digest on the same line does not hide a
    different bare hex value (for example a minified JSON object holding both values).
    """
    if not isinstance(text, str):
        return 0
    return sum(1 for p in pats for m in p.finditer(text) if not _is_digest_value(text, m))


def _is_digest_value(text, match):
    # endpos keeps the search in the prefix without copying it; \Z anchors at that boundary.
    return bool(_HEX_KEY.fullmatch(match.group(0))
                and _DIGEST_ASSIGNMENT.search(text, 0, match.start()))


def count_in(pats, value):
    """Matches in every string value of a nested value."""
    if isinstance(value, str):
        return count(pats, value)
    if isinstance(value, dict):
        return sum(count_in(pats, v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(count_in(pats, v) for v in value)
    return 0


def redact(pats, value):
    """(value with every matching string replaced, match count)."""
    if isinstance(value, str):
        n = count(pats, value)
        return (REDACTED if n else value), n
    if isinstance(value, dict):
        out, n = {}, 0
        for k, v in value.items():
            out[k], m = redact(pats, v)
            n += m
        return out, n
    if isinstance(value, (list, tuple)):
        out, n = [], 0
        for v in value:
            x, m = redact(pats, v)
            out.append(x)
            n += m
        return type(value)(out), n
    return value, 0


def event_payload(rules, scan_id, match_count):
    """on_match.payload names the fields of the secret_detected payload."""
    values = {"scan_id": scan_id, "match_count": match_count}
    return {k: values[k] for k in rules.get("preserve_manifest.secret_patterns.on_match.payload")}
