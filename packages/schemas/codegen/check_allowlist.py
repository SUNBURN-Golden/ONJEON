#!/usr/bin/env python3
"""Analytics event allow list check (02_구현계약 §3.2, C-17): packages/schemas/analytics-events.json.

  python3 -I packages/schemas/codegen/check_allowlist.py                 # the committed allow list and its examples
  python3 -I packages/schemas/codegen/check_allowlist.py --selftest      # prove the check fails on a leaked field
  python3 -I packages/schemas/codegen/check_allowlist.py EVENTS.json ... # also check the events in those files
                                                                         # (one JSON object, or an array of objects)

Python twin of src/allowlist.rs: the Rust services use that one, Python tools (the CI leak scanner of
T-CT-06, fixture loaders) import this module. Both read the same file and must agree; the `examples`
in analytics-events.json pin them together, because every `valid` example must pass and every
`rejected` example must fail in both languages (tests/test_allowlist.py and the Rust `allowlist_*`
tests).

Rules, in both implementations: a field may be sent only if its event lists it (`required` or
`optional`), and only with the listed value shape - a lowercase token, a vocabulary value of the
listed axes (`state_code`, and `error_class` as the wire ErrorResponse carries it), an integer at
or above the minimum, `rel:<yyyymmdd>-<n>`, or `x.y.z`. Anything else - another field, free text, a nested object, an
event that is not listed - is rejected, and the message names the forbidden category the field
looks like (계약 금액, 담보 명, ...).

Exit: 0 passed, 1 failed, 2 usage or setup error (a file that does not exist or is not JSON).
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMAS_DIR = HERE.parent
ALLOWLIST_PATH = SCHEMAS_DIR / "analytics-events.json"
VOCAB_PATH = SCHEMAS_DIR / "vocabulary.json"
CARGO_TOML = SCHEMAS_DIR / "Cargo.toml"

KINDS = ("token", "vocabulary", "integer", "release_id", "semver")
# same shapes as src/allowlist.rs: is_token / is_release_id / is_semver (fullmatch: `$` would accept a trailing newline)
TOKEN_RE = re.compile(r"[a-z][a-z0-9_.\-]*")
RELEASE_RE = re.compile(r"rel:[0-9]{8}-[0-9]+")
SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
I64_MIN, I64_MAX = -(2**63), 2**63 - 1
CARGO_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.M)


class CheckError(Exception):
    """Setup problem (missing or unreadable input), never a verdict."""


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CheckError(f"missing {path.name}") from None
    except (OSError, ValueError) as e:
        raise CheckError(f"{path.name}: {e}") from None


def crate_version(cargo_toml: Path = CARGO_TOML) -> str:
    """`version` of the contracts crate; analytics-events.json must carry the same value (C-23)."""
    m = CARGO_VERSION_RE.search(cargo_toml.read_text(encoding="utf-8"))
    if not m:
        raise CheckError(f"{cargo_toml.name}: no version")
    return m.group(1)


def axis_codes(axis: str, vocabulary: dict) -> list:
    """Codes of one vocabulary axis (never deprecated aliases). Empty when the axis does not exist."""
    return [
        v["code"]
        for a in vocabulary.get("axes", [])
        if a.get("id") == axis
        for v in a.get("values", [])
        if isinstance(v.get("code"), str)
    ]


class AllowList:
    """The allow list plus the canon it refers to (vocabulary axes) and the crate version."""

    def __init__(self, data: dict, vocabulary: dict, package_version: str):
        self.data = data
        self.vocabulary = vocabulary
        self.package_version = package_version
        self.event_key = data.get("event_key", "event")
        self.allowed_fields = data.get("allowed_fields", {})
        self.forbidden_categories = data.get("forbidden_categories", [])
        self.events = data.get("events", {})
        self.examples = data.get("examples", {})

    @classmethod
    def load(cls, path: Path = ALLOWLIST_PATH) -> "AllowList":
        """The committed allow list; the vocabulary and the crate version come from its siblings."""
        return cls(load_json(path), load_json(VOCAB_PATH), crate_version())

    # ---- one event -------------------------------------------------------------------------------

    def is_allowed_field(self, name: str) -> bool:
        """Whether any event may carry a field with this name (what the leak scanner asks)."""
        return name in self.allowed_fields

    def forbidden_category(self, name: str):
        """The forbidden category a field name looks like, for the failure message; None otherwise."""
        lower = name.lower()
        for cat in self.forbidden_categories:
            if any(h in lower for h in cat.get("name_hints", [])):
                return cat.get("category_ko")
        return None

    def check_event(self, event) -> list:
        """Everything wrong with one event; empty when it may be sent.

        An event is a flat JSON object: `event` names it and the other keys are its fields.
        """
        if not isinstance(event, dict):
            return ["an event must be a JSON object"]
        name = event.get(self.event_key)
        if not isinstance(name, str):
            return [f"missing event name `{self.event_key}`"]
        rule = self.events.get(name)
        if rule is None:
            return [f"event `{name}` is not on the allow list"]
        out = []
        for field, value in event.items():
            if field == self.event_key:
                continue
            if field not in rule.get("required", []) and field not in rule.get("optional", []):
                if self.is_allowed_field(field):
                    why = "allowed only on other events"
                elif (cat := self.forbidden_category(field)) is not None:
                    why = f"forbidden category: {cat}"
                else:
                    why = "not on the allow list"
                out.append(f"{name}: field `{field}` {why}")
                continue
            problem = self.check_value(field, value)
            if problem is not None:
                out.append(f"{name}: field `{field}` {problem}")
        for field in rule.get("required", []):
            if field not in event:
                out.append(f"{name}: required field `{field}` is missing")
        return out

    def check_value(self, field: str, value):
        rule = self.allowed_fields.get(field)
        if rule is None:
            return None
        kind = rule.get("kind")
        text = value if isinstance(value, str) else None
        if kind == "token":
            ok = text is not None and len(text) <= rule.get("max_len", 64) and TOKEN_RE.fullmatch(text)
            return None if ok else "must be a lowercase token (a-z 0-9 _ . -), not free text"
        if kind == "vocabulary":
            axes = rule.get("axes", [])
            ok = text is not None and any(text in axis_codes(a, self.vocabulary) for a in axes)
            return None if ok else f"must be a vocabulary value of {', '.join(axes)}"
        if kind == "integer":
            ok = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and I64_MIN <= value <= I64_MAX
                and value >= rule.get("minimum", I64_MIN)
            )
            return None if ok else "must be an integer within the minimum"
        if kind == "release_id":
            return None if text is not None and RELEASE_RE.fullmatch(text) else "must be rel:<yyyymmdd>-<n>"
        if kind == "semver":
            return None if text is not None and SEMVER_RE.fullmatch(text) else "must be x.y.z"
        return f"has unknown kind `{kind}` in the allow list"

    # ---- the file itself -------------------------------------------------------------------------

    def problems(self) -> list:
        """Everything wrong with the allow list itself (not with an event)."""
        out = []
        if self.data.get("contracts_version") != self.package_version:
            out.append(
                f"contracts_version {self.data.get('contracts_version')!r} differs from the package "
                f"version {self.package_version!r} (C-23)"
            )
        for name, rule in self.events.items():
            for f in list(rule.get("required", [])) + list(rule.get("optional", [])):
                fr = self.allowed_fields.get(f)
                if fr is None:
                    out.append(f"{name}: `{f}` is not an allowed field")
                    continue
                only = fr.get("only_events", [])
                if only and name not in only:
                    out.append(f"{name}: `{f}` is restricted to {only}")
        for f, fr in self.allowed_fields.items():
            for e in fr.get("only_events", []):
                if e not in self.events:
                    out.append(f"{f}: only_events names unknown event {e}")
            if self.forbidden_category(f) is not None:
                out.append(f"{f}: an allowed field looks like a forbidden category")
            for a in fr.get("axes", []):
                if not axis_codes(a, self.vocabulary):
                    out.append(f"{f}: vocabulary axis {a} does not exist")
            if fr.get("kind") not in KINDS:
                out.append(f"{f}: unknown kind {fr.get('kind')!r}")
        return out

    def check_examples(self) -> list:
        """The listed examples must pass and fail as declared; both lists must be non-empty."""
        out = []
        valid = self.examples.get("valid", [])
        rejected = self.examples.get("rejected", [])
        if not valid:
            out.append("examples.valid is empty")
        if not rejected:
            out.append("examples.rejected is empty")
        for i, ex in enumerate(valid):
            bad = self.check_event(ex)
            if bad:
                out.append(f"valid example {i} was rejected: {'; '.join(bad)}")
        for i, item in enumerate(rejected):
            ex = item.get("example") if isinstance(item, dict) else None
            if not self.check_event(ex):
                out.append(f"rejected example {i} ({item.get('reason_ko', '?')}) was accepted")
        return out

    def summary(self) -> str:
        return (
            f"allow list: {len(self.events)} events, {len(self.allowed_fields)} allowed fields, "
            f"{len(self.examples.get('valid', []))} valid and {len(self.examples.get('rejected', []))} "
            f"rejected examples"
        )


def check_event_file(allow: AllowList, path: Path) -> list:
    """Problems of the events in `path` (one object or an array of objects), prefixed with their index."""
    doc = load_json(path)
    events = doc if isinstance(doc, list) else [doc]
    return [f"{path.name}[{i}]: {p}" for i, ev in enumerate(events) for p in allow.check_event(ev)]


def run(allowlist_path: Path = ALLOWLIST_PATH, event_files: list | None = None) -> list:
    """All problems of the allow list, its examples and the given event files; empty means PASSED."""
    allow = AllowList.load(allowlist_path)
    problems = allow.problems() + allow.check_examples()
    for f in event_files or []:
        problems += check_event_file(allow, Path(f))
    return problems


def selftest(allowlist_path: Path = ALLOWLIST_PATH) -> list:
    """Each planted defect must fail for its intended reason. Returns the defects that did not."""
    base = AllowList.load(allowlist_path)
    failures = []

    def expect(label: str, problems: list, needle: str):
        if not any(needle in p for p in problems):
            failures.append(f"{label}: expected a failure mentioning {needle!r}, got {problems}")

    def mutated(edit) -> AllowList:
        data = copy.deepcopy(base.data)
        edit(data)
        return AllowList(data, base.vocabulary, base.package_version)

    # 1. an event carrying a contract amount
    expect(
        "amount field",
        base.check_event({"event": "screen_view", "screen_id": "home", "monthly_premium_krw": 53000}),
        "forbidden category: 계약 금액",
    )
    # 2. an event carrying a user identifier
    expect(
        "user identifier",
        base.check_event({"event": "state_shown", "screen_id": "home", "state_code": "hold", "user_id": "u"}),
        "`user_id`",
    )
    # 3. free text where a token is expected
    expect(
        "free text screen_id",
        base.check_event({"event": "screen_view", "screen_id": "내 설계"}),
        "not free text",
    )
    # 4. an event name that is not listed
    expect("unlisted event", base.check_event({"event": "page_hit", "screen_id": "home"}), "not on the allow list")

    # 5. the file itself lists a coverage-name field
    def list_coverage_name(d):
        d["allowed_fields"]["coverage_name"] = {"kind": "token", "max_len": 64}
        d["events"]["screen_view"]["optional"].append("coverage_name")

    expect("listed coverage_name", mutated(list_coverage_name).problems(), "forbidden category")

    # 6. a rejected example moved into the valid list
    def promote_rejected(d):
        d["examples"]["valid"].append(d["examples"]["rejected"][0]["example"])

    expect("promoted rejected example", mutated(promote_rejected).check_examples(), "was rejected")

    # 7. a valid example that the checker would accept listed as rejected
    def demote_valid(d):
        d["examples"]["rejected"].append({"example": d["examples"]["valid"][0], "reason_ko": "planted"})

    expect("demoted valid example", mutated(demote_valid).check_examples(), "was accepted")

    # 8. version drift (C-23)
    def bump(d):
        d["contracts_version"] = "99.0.0"

    expect("version drift", mutated(bump).problems(), "contracts_version")
    return failures


def main(argv: list) -> int:
    args = list(argv)
    allowlist_path = ALLOWLIST_PATH
    if "--allowlist" in args:
        i = args.index("--allowlist")
        if i + 1 >= len(args):
            print("usage: check_allowlist.py [--allowlist FILE] [--selftest] [EVENTS.json ...]")
            return 2
        allowlist_path = Path(args[i + 1])
        del args[i : i + 2]
    do_selftest = "--selftest" in args
    files = [a for a in args if a != "--selftest"]
    if any(a.startswith("-") for a in files):
        print("usage: check_allowlist.py [--allowlist FILE] [--selftest] [EVENTS.json ...]")
        return 2
    try:
        if do_selftest:
            failed = selftest(allowlist_path)
            for f in failed:
                print(f"FAIL: self-test {f}")
            if failed:
                print("RESULT: FAILED")
                return 1
            print("self-test ok: 8 planted defects fail for their intended reasons")
            return 0
        problems = run(allowlist_path, files)
        for p in problems:
            print(f"FAIL: {p}")
        if problems:
            print("RESULT: FAILED")
            return 1
        allow = AllowList.load(allowlist_path)
        extra = f", {len(files)} event file(s)" if files else ""
        print(f"{allow.summary()}{extra}, PASSED")
        return 0
    except CheckError as e:
        print(f"Error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
