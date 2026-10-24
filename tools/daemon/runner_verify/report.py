"""Result records of the verification. A check is PASS, FAIL or UNCONFIRMED. A scenario (one R number) is FAIL if any
check failed, PASS only if every check passed, UNCONFIRMED if nothing could be checked, PARTIAL otherwise. GAP marks
a place where the specification text and what was observed differ without being one of the scenario's pass
criteria; it is listed in the summary and never hidden."""
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
        if not self.checks:
            return UNCONFIRMED
        if FAIL in kinds:
            return FAIL
        if UNCONFIRMED in kinds:
            return UNCONFIRMED if kinds <= {UNCONFIRMED, GAP} else PARTIAL
        return PASS
