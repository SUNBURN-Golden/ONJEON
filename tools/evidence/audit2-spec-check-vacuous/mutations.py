"""Before/after evidence for audit2-spec-check-vacuous.

Runs two copies of spec_check.py (the parent commit's and the working tree's) on the same emptied inputs and prints
the verdict of the target check. Both copies take (T, D) in run(); document inputs are swapped by patching the
module's `read`, `integration_rows` or `open`. A crash counts as an error, not as a verdict.
Usage (repo root): python3 -I tools/evidence/audit2-spec-check-vacuous/mutations.py <old spec_check.py> <new spec_check.py>
"""
import copy
import importlib.util
import io
import json
import os
import sys
import warnings
from unittest import mock

ROOT = os.getcwd()
BUNDLE = os.path.join(ROOT, "docs/blueprint/proposals/설계검토_결과")
TBOX = os.path.join(ROOT, "docs/blueprint/proposals/온톨로지/tbox.json")
with open(os.path.join(BUNDLE, "daemon_rules.json"), encoding="utf-8") as f:
    RULES = json.load(f)
with open(os.path.join(BUNDLE, "tasks.json"), encoding="utf-8") as f:
    TASKS = json.load(f)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.BUNDLE = BUNDLE
    return m


def verdict(m, case, gid):
    D, T = copy.deepcopy(RULES), copy.deepcopy(TASKS)
    patches = []
    if case:
        out = case(m, D, T)
        D, T, patches = out if out else (D, T, [])
    m.RESULTS.clear()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            for p in patches:
                p.start()
            m.run(ROOT, T, D)
    except Exception as e:  # noqa: BLE001 — reported, not judged
        return f"ERROR({type(e).__name__})"
    finally:
        for p in patches:
            p.stop()
    return "PASS" if [r for r in m.RESULTS if r["check"].startswith(gid + " ")][0]["ok"] else "FAIL"


def set_(path, value):
    def case(m, D, T):
        node = D
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
    return case


def no_detect(m, D, T):
    for sig in D["switch_policy"]["allowed_switch_signals"]:
        sig["detect"] = []


def one_signal_no_detect(m, D, T):
    D["switch_policy"]["allowed_switch_signals"][0].pop("detect")


def no_states_no_transitions(m, D, T):
    D["states"], D["transitions"] = {}, []


def rows(value):
    return lambda m, D, T: (D, T, [mock.patch.object(m, "integration_rows", lambda repo: value)])


def heading_renamed(m, D, T):
    orig = m.integration_rows

    def renamed(repo):
        with open(os.path.join(repo, "docs/blueprint/proposals/설계통합안_검토본.md"), encoding="utf-8") as f:
            text = f.read().replace("\n### 2.", "\n### 2-")
        with mock.patch.object(m, "open", lambda *a, **k: io.StringIO(text), create=True):
            return orig(repo)
    return D, T, [mock.patch.object(m, "integration_rows", renamed)]


def range_in_words(m, D, T):
    orig = m.read
    T = json.loads(json.dumps(T, ensure_ascii=False).replace("K1~K16", "T-box 제약 전부"))
    return D, T, [mock.patch.object(m, "read", lambda n: orig(n).replace("K1~K16", "T-box 제약 전부"))]


def stale_en_dash(m, D, T):
    orig = m.read
    return D, T, [mock.patch.object(m, "read", lambda n: orig(n).replace("K1~K16", "K1–K15") if n == "02_구현계약.md" else orig(n))]


def stale_tilde(m, D, T):
    return D, json.loads(json.dumps(T, ensure_ascii=False).replace("K1~K16", "K1~K12")), []


def empty_tbox(m, D, T):
    with open(TBOX, encoding="utf-8") as f:
        data = json.load(f)
    data["constraints"] = []

    def fake_open(path, *a, **k):
        if os.path.abspath(path) == TBOX:
            return io.StringIO(json.dumps(data, ensure_ascii=False))
        return open(path, *a, **k)
    return D, T, [mock.patch.object(m, "open", fake_open, create=True)]


CASES = [
    ("bundle as is", None, "G4c"),
    ("§2 headings '### 2.x' → '### 2-x' (regex finds 0 rows)", heading_renamed, "G4c"),
    ("integration rows = []", rows([]), "G4c"),
    ("one unmapped row (control)", lambda m, D, T: rows(m.integration_rows(ROOT) + ["2.1 없는 기능"])(m, D, T), "G4c"),
    ("bundle as is", None, "G7b"),
    ("states = {}", set_(["states"], {}), "G7b"),
    ("states = {} and transitions = []", no_states_no_transitions, "G7b"),
    ("bundle as is", None, "G9"),
    ("allowed_switch_signals = []", set_(["switch_policy", "allowed_switch_signals"], []), "G9"),
    ("every signal's detect = []", no_detect, "G9"),
    ("first signal without detect", one_signal_no_detect, "G9"),
    ("bundle as is", None, "G26"),
    ("every 'K1~K16' written in words (regex finds 0)", range_in_words, "G26"),
    ("02 says 'K1–K15' (en dash, stale)", stale_en_dash, "G26"),
    ("tasks.json says 'K1~K12' (control)", stale_tilde, "G26"),
    ("tbox constraints = []", empty_tbox, "G26"),
]


def main():
    old, new = module(sys.argv[1], "spec_check_old"), module(sys.argv[2], "spec_check_new")
    print(f"{'mutation':<56} check  before             after")
    for label, case, gid in CASES:
        print(f"{label:<56} {gid:<6} {verdict(old, case, gid):<18} {verdict(new, case, gid)}")


if __name__ == "__main__":
    main()
