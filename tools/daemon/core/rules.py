"""The contract view of daemon_rules.json.

The core never sees the whole file. build_view() copies only the fields listed in core_contract.reads (the
canonical read list, G20) and sanitize() drops every explanation key wherever it appears: `note`, every key that
starts with `_`, and `when` when its value is prose. (noop_rules[].when is a list of structured predicates, not
prose; it is kept, see the specification gaps.) Anything the core needs beyond the read list is named in
EXTENSIONS and reported as a specification gap.
"""
import copy
import re

from .ports import SpecGap

# Fields outside core_contract.reads that the core still needs (reported as gaps in the run report).
EXTENSIONS = (
    "switch_policy.allowed_sources",
)

_MISSING = object()


def is_banned_key(key, value=None):
    if key in ("when", "note"):
        # a `when` that holds structured predicates is data (noop_rules); a prose `when` is never read
        return key in ("note",) or not _structured_predicates(value)
    return key.startswith("_")


def _structured_predicates(value):
    return isinstance(value, list) and bool(value) and all(
        isinstance(x, dict) and "field" in x and "op" in x for x in value)


def sanitize(node):
    if isinstance(node, dict):
        out = {}
        for key, v in node.items():
            if is_banned_key(key, v):
                continue
            # a structured `when` (noop_rules) is handed to the core under the name transitions use for the same thing
            out["cond" if key in ("when",) else key] = sanitize(v)
        return out
    if isinstance(node, list):
        return [sanitize(x) for x in node]
    return node


# ---------------------------------------------------------------- read list patterns
def _split_top(text, sep):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def expand_pattern(pattern):
    """'a.b[].{c,d.e}' -> [[('key','a'),('key','b'),('each',),('key','c')], [... ('key','d'),('key','e')]]"""
    seqs = [[]]
    for seg in _split_top(pattern, "."):
        if seg.startswith("{") and seg.endswith("}"):
            alts = []
            for alt in _split_top(seg[1:-1], ","):
                alts += expand_pattern(alt.strip())
            seqs = [s + a for s in seqs for a in alts]
            continue
        steps = []
        if seg.endswith("[]"):
            seg, steps = seg[:-2], [("each",)]
        head = [("all",)] if seg == "*" else [("key", seg)]
        seqs = [s + head + steps for s in seqs]
    return seqs


def _extract(node, seq):
    if not seq:
        return copy.deepcopy(node)
    head, rest = seq[0], seq[1:]
    if head[0] == "key":
        if isinstance(node, dict) and head[1] in node:
            sub = _extract(node[head[1]], rest)
            return _MISSING if sub is _MISSING else {head[1]: sub}
        return _MISSING
    if head[0] == "each":
        if not isinstance(node, list):
            return _MISSING
        out = []
        for x in node:
            sub = _extract(x, rest)
            out.append({} if sub is _MISSING else sub)
        return out
    if head[0] == "all":
        if not isinstance(node, dict):
            return _MISSING
        out = {}
        for k, v in node.items():
            sub = _extract(v, rest)
            if sub is not _MISSING:
                out[k] = sub
        return out if out else _MISSING
    raise SpecGap(f"bad read pattern step {head}")


def _combine(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _combine(out[k], v) if k in out else v
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [_combine(x, y) for x, y in zip(a, b)]
    return b


def build_view(raw):
    """Project raw onto core_contract.reads (+ EXTENSIONS) and sanitize. Returns (view, unmatched entries)."""
    reads = list(raw["core_contract"]["reads"]) + list(EXTENSIONS)
    view, unmatched = {}, []
    for entry in reads:
        hit = False
        for seq in expand_pattern(entry):
            part = _extract(raw, seq)
            if part is _MISSING:
                continue
            hit = True
            view = _combine(view, part)
        if not hit:
            unmatched.append(entry)
    return sanitize(view), unmatched


class Rules:
    """Read access to the contract view."""

    # (where, token): ids/codes pulled out of strings inside read fields. Shared by all instances so that
    # a run report can list every one of them.
    token_log = set()

    def __init__(self, raw):
        self.view, self.unmatched_reads = build_view(raw)
        if "core_contract" not in self.view:
            raise SpecGap("core_contract.reads is missing")

    def get(self, path):
        cur = self.view
        for seg in path.split("."):
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                raise SpecGap(f"contract path not found: {path}")
        return cur

    def number(self, path):
        v = self.get(path)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise SpecGap(f"not a number: {path} = {v!r}")
        return v

    def has(self, path):
        try:
            self.get(path)
            return True
        except SpecGap:
            return False

    def token(self, where, pattern, text, group=0):
        """Pull a structured token out of a string that sits inside a read field. Always logged."""
        m = re.search(pattern, text or "")
        if m:
            tok = m.group(group)
            self.token_log.add((where, tok))
            return tok
        return None

    # --- derived lists used in several places
    @property
    def transitions(self):
        return self.view["transitions"]

    def _catalog(self, key):
        v = self.get("event_catalog")[key]
        return list(self.get(v)) if isinstance(v, str) else list(v)

    @property
    def transition_events(self):
        return self._catalog("transition_events")

    @property
    def noop_events(self):
        return self._catalog("noop_events")

    @property
    def operation_events(self):
        return self._catalog("operation_events")

    @property
    def known_events(self):
        return set(self.transition_events) | set(self.noop_events) | set(self.operation_events)

    @property
    def noop_rules(self):
        return list(self.view.get("noop_rules", []))

    @property
    def sequence(self):
        return list(self.view["handoff_sequence"])

    @property
    def always_revoke(self):
        return list(self.view["handoff_failure_policy"]["always_revoke"])

    @property
    def max_attempt_events(self):
        return list(self.view["handoff_failure_policy"]["max_attempts"].keys())

    @property
    def stages(self):
        """Every stage id the contract names for resuming a handoff (the keys of restart_resume)."""
        return list(self.view["handoff_failure_policy"]["restart_resume"].keys())

    @property
    def issue_reasons(self):
        return list(self.get("concurrency.lease_issue.reasons"))

    def return_target(self, code):
        for rc in self.view["return_codes"]:
            if rc["code"] == code:
                return rc.get("to")
        raise SpecGap(f"unknown return code {code}")

    def return_code_known(self, code):
        return any(rc["code"] == code for rc in self.view["return_codes"])
