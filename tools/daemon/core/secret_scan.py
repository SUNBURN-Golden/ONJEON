"""preserve_manifest.secret_patterns (G38): the three scan points and the redaction of journal text.

Matched text is never stored: a match leaves only scan_id, match_count and the file path or field name.
"""
import re

from .ports import SpecGap

REDACTED = "<redacted>"


def patterns(rules):
    return [re.compile(p) for p in rules.get("preserve_manifest.secret_patterns.patterns")]


def scan_spec(rules, scan_id):
    for item in rules.get("preserve_manifest.secret_patterns.scan"):
        if item["id"] == scan_id:
            return item
    raise SpecGap(f"secret_patterns.scan has no {scan_id}")


def count(pats, text):
    return sum(len(p.findall(text)) for p in pats) if isinstance(text, str) else 0


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
    if isinstance(value, list):
        out, n = [], 0
        for v in value:
            x, m = redact(pats, v)
            out.append(x)
            n += m
        return out, n
    return value, 0


def event_payload(rules, scan_id, match_count):
    """on_match.payload names the fields of the secret_detected payload."""
    values = {"scan_id": scan_id, "match_count": match_count}
    return {k: values[k] for k in rules.get("preserve_manifest.secret_patterns.on_match.payload")}
