"""Shared helpers for the CI checkers in tools/ci (stdlib only, no repo imports).

Findings carry a stable rule id. Every checker's --selftest plants one violation per rule and
requires that exactly that rule id is reported, so a check can only pass for the intended reason.
"""
import json
import os
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = ROOT / "infra/ci/deps.json"
FLAGS_PATH = ROOT / "packages/schemas/feature_flags.json"
PRUNE_DIRS = {".git", "target", "node_modules", ".dart_tool", "__pycache__"}


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str

    def render(self):
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.rule}] {where}: {self.message}"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_rules(path=RULES_PATH):
    return load_json(path)


@lru_cache(maxsize=None)
def _glob_re(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def match(rel, patterns):
    return any(_glob_re(p).match(rel) for p in patterns)


def iter_files(root, ignore, exts=None):
    """Yield (relative posix path, Path) of files under root, skipping ignored globs."""
    root = Path(root)
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in PRUNE_DIRS)
        for name in sorted(files):
            full = Path(base) / name
            rel = full.relative_to(root).as_posix()
            if exts is not None and full.suffix not in exts and name not in exts:
                continue
            if match(rel, ignore):
                continue
            yield rel, full


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def zone_of(rel, zones):
    """Zone name whose path globs match rel, or None."""
    for name, z in zones.items():
        if match(rel, z["paths"]):
            return name
    return None


def norm_pkg(name):
    """Normalize a crate / npm / pub package name so one internal package has one key."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def report(findings, ok_message, title):
    """Print findings, return the process exit code (0 clean, 1 findings)."""
    if findings:
        print(f"{title}: {len(findings)} finding(s)")
        for f in findings:
            print("  " + f.render())
        return 1
    print(f"{title}: {ok_message}")
    return 0


def run_selftest(title, cases, runner, quiet=False):
    """cases: list of (name, files{rel: text}, expected_rule). A clean case has expected_rule None.

    runner(root: Path) -> list[Finding]. Each case is written to a temp tree and must produce the
    expected rule id (and for a clean case, nothing). A case that fails for a different reason fails
    the selftest.
    """
    import tempfile

    bad = []
    for name, files, expected in cases:
        with tempfile.TemporaryDirectory() as tmp:
            for rel, text in files.items():
                p = Path(tmp) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            got = runner(Path(tmp))
        rules = sorted({f.rule for f in got})
        if expected is None:
            if rules:
                bad.append(f"{name}: expected clean, got {rules}")
        elif expected not in rules:
            bad.append(f"{name}: expected {expected}, got {rules or 'nothing'}")
    if bad:
        print(f"{title} selftest failed: {len(bad)} case(s) not caught for the intended reason")
        for b in bad:
            print("  " + b)
        return 1
    n_bad = sum(1 for _, _, e in cases if e)
    if quiet:
        return 0
    print(f"{title} selftest ok: {n_bad} violations each caught for its intended rule, {len(cases) - n_bad} clean case(s) pass")
    return 0


def usage_error(message):
    print(message, file=sys.stderr)
    return 2
