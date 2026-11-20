"""Record PASS, FAIL, UNCONFIRMED and GAP checks. GAP records a difference between the specification and the
observation. A scenario is FAIL if any check failed, PASS if every check passed, UNCONFIRMED if it has no checks
or only UNCONFIRMED checks, and PARTIAL otherwise. A GAP makes the scenario PARTIAL unless a check failed."""
import copy

PASS, FAIL, UNCONFIRMED, GAP, PARTIAL = "PASS", "FAIL", "UNCONFIRMED", "GAP", "PARTIAL"


class Rep:
    def __init__(self):
        self.checks = []
        self.evidence = {}
        self.not_proven = []
        self.findings = []

    def _add(self, name, status, expected=None, actual=None, **extra):
        rec = {"name": name, "status": status, "expected": copy.deepcopy(expected), "actual": copy.deepcopy(actual)}
        rec.update(extra)
        self.checks.append(rec)
        return status == PASS

    def eq(self, name, expected, actual):
        return self._add(name, PASS if expected == actual else FAIL, expected, actual)

    def ok(self, name, cond, detail=None):
        return self._add(name, PASS if cond else FAIL, True, bool(cond), detail=detail)

    def unconfirmed(self, name, reason, expected=None, actual=None):
        return self._add(name, UNCONFIRMED, expected, actual, reason=reason)

    def gap(self, name, note, expected=None, actual=None):
        self.findings.append({"name": name, "note": note})
        return self._add(name, GAP, expected, actual, note=note)

    def evid(self, key, value):
        self.evidence[key] = copy.deepcopy(value)

    def not_proved(self, *items):
        self.not_proven.extend(items)

    def status(self):
        kinds = {c["status"] for c in self.checks}
        if FAIL in kinds:
            return FAIL
        if kinds == {PASS}:
            return PASS
        if kinds <= {UNCONFIRMED}:
            return UNCONFIRMED
        return PARTIAL
