"""The contract view of daemon_rules.json.

The core never sees the whole file. build_view() copies only the fields the contract says the core reads
(core_contract._scope), and sanitize() drops every key named `when` or `note` and every key that starts
with `_` (explanations for people) wherever it appears. Anything the core needs beyond that list is
listed in EXTENSIONS and reported as a specification gap.
"""
import re

from .ports import SpecGap

PLACEHOLDER_PREFIX = "[사용자 결정 필요]"
TRANSITION_FIELDS = ("from", "to", "event", "guard", "cond", "side_effects", "by")
CONCURRENCY_READ = ("lease", "lease_issue", "quiescence", "idempotency_key")

# Fields outside core_contract._scope that the core still needs (reported as gaps in the run report).
EXTENSIONS = (
    "events (names only)",
    "hard_stop.grace_s",
    "preserve_manifest.function / excludes",
    "concurrency.fencing.on_lease_end",
    "envelopes.*.required is read; no signal/heartbeat required list exists, so core_contract.events_in.payloads is used",
)


def is_banned_key(key):
    return key in ("when", "note") or key.startswith("_")


def sanitize(node):
    if isinstance(node, dict):
        return {k: sanitize(v) for k, v in node.items() if not is_banned_key(k)}
    if isinstance(node, list):
        return [sanitize(x) for x in node]
    return node


def build_view(raw):
    envelopes = {}
    for name, body in raw["envelopes"].items():
        if isinstance(body, dict) and "required" in body:
            envelopes[name] = {"required": list(body["required"])}
    return sanitize({
        "core_contract": raw["core_contract"],
        "transitions": [{f: t[f] for f in TRANSITION_FIELDS if f in t} for t in raw["transitions"]],
        "lease_guards": raw["lease_guards"],
        "handoff_sequence": raw["handoff_sequence"],
        "handoff_failure_policy": {k: raw["handoff_failure_policy"][k] for k in ("max_attempts", "always_revoke")},
        "concurrency": dict({k: raw["concurrency"][k] for k in CONCURRENCY_READ},
                            fencing={"on_lease_end": raw["concurrency"]["fencing"]["on_lease_end"]}),
        "envelopes": envelopes,
        "state_integrity": raw["state_integrity"],
        "noop_events": raw["noop_events"],
        "return_codes": raw["return_codes"],
        "events": raw["events"],
        "hard_stop": {"grace_s": raw["hard_stop"]["grace_s"]},
        "preserve_manifest": {k: raw["preserve_manifest"][k] for k in ("function", "excludes")},
    })


class Rules:
    """Read access to the contract view. `params` supplies numbers the contract leaves as undecided
    placeholders ("[사용자 결정 필요] 기본 N"); without an override such a value stops the core."""

    # (where, token): ids/codes pulled out of strings inside read fields. Shared by all instances so that
    # a run report can list every one of them.
    token_log = set()

    def __init__(self, raw, params=None):
        self.view = build_view(raw)
        self.params = dict(params or {})

    def get(self, path):
        for key in (path, path + ".value"):
            if key in self.params:
                return self.params[key]
        cur = self.view
        for seg in path.split("."):
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                raise SpecGap(f"contract path not found: {path}")
        if isinstance(cur, dict) and "value" in cur:
            self.token_log.add((path, "implicit .value"))
            cur = cur["value"]
        if isinstance(cur, str) and cur.startswith(PLACEHOLDER_PREFIX):
            raise SpecGap(f"undecided value without a numeric field or override: {path}")
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

    @property
    def events(self):
        return list(self.view["events"])

    @property
    def noop_events(self):
        return list(self.view["noop_events"])

    @property
    def sequence(self):
        return list(self.view["handoff_sequence"])

    @property
    def always_revoke(self):
        return list(self.view["handoff_failure_policy"]["always_revoke"])

    @property
    def max_attempt_events(self):
        return list(self.view["handoff_failure_policy"]["max_attempts"].keys())

    def return_target(self, code):
        for rc in self.view["return_codes"]:
            if rc["code"] == code:
                return rc.get("to")
        raise SpecGap(f"unknown return code {code}")

    def return_code_known(self, code):
        return any(rc["code"] == code for rc in self.view["return_codes"])
