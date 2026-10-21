#!/usr/bin/env python3
"""bootstrap-clean-main: static check that every task can finish from a clean main plus its prerequisites.

Input is tasks.json only (plus the repo, to see which crates and paths already exist). Nothing is
built or run; the real sample build is the separate integration task. The rules are the same as
spec_check G1, G2 and G31 of the design bundle:

  BOOT-GRAPH     a prerequisite does not exist, or the prerequisite graph has a cycle (G1)
  BOOT-CONSUMES  a task's consumes entry, or a crate named by `cargo test -p`, is neither in the repo
                 nor produced by the task itself or one of its prerequisites (G2)
  BOOT-PATH      a repo path named in a test command is not in the repo, not inside the task's own
                 allowed_paths, and not produced by a prerequisite. Stricter than spec_check G2/G31
                 (which look at crates and consumes only), so it is advisory unless --strict-paths
  BOOT-MENTION   done_criteria or tests name a task ID or an onjeon-* crate that only a task outside
                 the task's own prerequisites provides (G31)

A pass says the task graph is self-consistent. It does not say any task builds.

Usage:
  python3 -I tools/ci/check_bootstrap.py [--root DIR] [--tasks FILE] [--strict-paths]
  python3 -I tools/ci/check_bootstrap.py --selftest
Exit: 0 clean, 1 findings, 2 usage or unreadable input.
"""
import fnmatch
import glob
import json
import os
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_common as C  # noqa: E402

DEFAULT_TASKS = "docs/blueprint/proposals/설계검토_결과/tasks.json"
PATH_TOKEN = re.compile(r"(?<![A-Za-z0-9_./-])((?:tools|packages|services|apps|infra|data)/[A-Za-z0-9_./*-]+)")
TASK_ID = re.compile(r"T-[A-Z]{2}-\d{2}")


def sample(pattern):
    return pattern.replace("**", "s/t").replace("*", "x").replace("?", "q")


def overlap(a, b):
    """Can two globs point at the same file (same approximation as spec_check)."""
    if fnmatch.fnmatch(sample(a), b) or fnmatch.fnmatch(sample(b), a):
        return True
    pa, pb = a.split("*")[0], b.split("*")[0]
    return (a.endswith("**") and pb.startswith(pa)) or (b.endswith("**") and pa.startswith(pb))


def ancestors(tasks, tid, memo):
    if tid in memo:
        return memo[tid]
    memo[tid] = set()
    out = set()
    for p in tasks[tid].get("prereq_tasks", []):
        if p in tasks:
            out |= {p} | ancestors(tasks, p, memo)
    memo[tid] = out
    return out


def repo_crates(root):
    out = set()
    for cargo in glob.glob(os.path.join(str(root), "**", "Cargo.toml"), recursive=True):
        rel = os.path.relpath(cargo, str(root)).replace(os.sep, "/")
        if "/target/" in "/" + rel or rel.startswith("docs/") or "/docs/" in rel:
            continue
        try:
            name = (tomllib.loads(Path(cargo).read_text(encoding="utf-8")).get("package") or {}).get("name")
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if name:
            out.add(name)
    return out


def produced_by(tasks, ref):
    kind, _, val = ref.partition(":")
    hits = set()
    for tid, t in tasks.items():
        for p in t.get("produces", []):
            pk, _, pv = p.partition(":")
            if pk == kind and ((kind == "path" and overlap(pv, val)) or pv == val):
                hits.add(tid)
    return hits


def text_of(t):
    crit = [c if isinstance(c, str) else c.get("text", "") for c in t.get("done_criteria", [])]
    return " ".join(t.get("tests", []) + crit)


def check(root, tasks_path, strict_paths=True, advisory=None):
    data = json.loads(Path(tasks_path).read_text(encoding="utf-8"))
    tasks = {t["id"]: t for t in data["tasks"]}
    rel = Path(tasks_path).name
    out = []

    for tid, t in tasks.items():
        for p in t.get("prereq_tasks", []):
            if p not in tasks:
                out.append(C.Finding("BOOT-GRAPH", rel, 0, f"{tid}: prerequisite {p} does not exist"))
    if out:
        return out
    memo = {}
    for tid in tasks:
        if tid in ancestors(tasks, tid, memo):
            out.append(C.Finding("BOOT-GRAPH", rel, 0, f"{tid}: prerequisite graph has a cycle through this task"))
    if out:
        return out

    crates = repo_crates(root)
    for tid, t in tasks.items():
        anc = ancestors(tasks, tid, memo)
        provided = anc | {tid}
        refs = set(t.get("consumes", []))
        for cmd in t.get("tests", []):
            for c in re.findall(r"cargo test[^&;|]*?-p\s+([A-Za-z0-9_-]+)", cmd):
                refs.add("crate:" + c)
        for ref in sorted(refs):
            kind, _, val = ref.partition(":")
            if kind == "crate" and val in crates:
                continue
            if kind == "path" and glob.glob(os.path.join(str(root), val), recursive=True):
                continue
            owners = produced_by(tasks, ref)
            if not owners:
                out.append(C.Finding("BOOT-CONSUMES", rel, 0, f"{tid}: {ref} is not in the repo and no task produces it"))
            elif not (owners & provided):
                out.append(C.Finding("BOOT-CONSUMES", rel, 0, f"{tid}: {ref} is produced by {sorted(owners)}, which are not prerequisites"))

        for cmd in t.get("tests", []):
            for tok in PATH_TOKEN.findall(cmd):
                tok = tok.rstrip(".,;)")
                if glob.glob(os.path.join(str(root), tok), recursive=True):
                    continue
                owners = produced_by(tasks, "path:" + tok)
                # a task may write the script its own test runs, anywhere inside its allowed paths
                in_scope = any(overlap(a, tok) or overlap(a, tok.rstrip("/") + "/**") for a in t.get("allowed_paths", []))
                if not (owners & provided) and not in_scope:
                    (out if strict_paths or advisory is None else advisory).append(C.Finding("BOOT-PATH", rel, 0, f"{tid}: test command names {tok}, which is not in the repo, not under the task's allowed_paths, and no prerequisite produces it"))

        text = text_of(t)
        for ref in sorted(set(TASK_ID.findall(text))):
            if ref in tasks and ref not in provided:
                out.append(C.Finding("BOOT-MENTION", rel, 0, f"{tid}: done criteria or tests mention {ref}, which is not a prerequisite"))
        for c in sorted(set(re.findall(r"onjeon-[a-z0-9-]+", text))):
            if c in crates:
                continue
            owners = produced_by(tasks, "crate:" + c)
            if owners and not (owners & provided):
                out.append(C.Finding("BOOT-MENTION", rel, 0, f"{tid}: done criteria or tests rely on {c} (made by {sorted(owners)}), which is not a prerequisite"))
    return out


# ---------- selftest ----------
def task(tid, prereq=(), produces=(), consumes=(), tests=(), done=(), allowed=()):
    return {"id": tid, "allowed_paths": list(allowed), "prereq_tasks": list(prereq), "produces": list(produces), "consumes": list(consumes), "tests": list(tests), "done_criteria": list(done)}


def selftest():
    def tree(*tasks):
        return {"tasks.json": json.dumps({"tasks": list(tasks)}), "Cargo.toml": '[package]\nname = "onjeon-have"\n', "tools/have.py": ""}

    base = [task("T-AA-01", produces=["crate:onjeon-a", "path:tools/a/**"]), task("T-AA-02", prereq=["T-AA-01"])]
    cases = [
        ("self-consistent graph passes", tree(*base, task("T-AA-03", prereq=["T-AA-02"], consumes=["crate:onjeon-a"], tests=["cargo test -p onjeon-a", "python3 tools/a/run.py", "python3 tools/have.py"], done=["uses onjeon-a after T-AA-01"])), None),
        ("a repo crate needs no producer", tree(task("T-AA-01", tests=["cargo test -p onjeon-have"])), None),
        ("a prerequisite that does not exist", tree(task("T-AA-01", prereq=["T-ZZ-99"])), "BOOT-GRAPH"),
        ("a prerequisite cycle", tree(task("T-AA-01", prereq=["T-AA-02"]), task("T-AA-02", prereq=["T-AA-01"])), "BOOT-GRAPH"),
        ("cargo test of a crate nobody produces", tree(task("T-AA-01", tests=["cargo test -p onjeon-ghost"])), "BOOT-CONSUMES"),
        ("cargo test of a crate a later task produces", tree(task("T-AA-01", tests=["cargo test -p onjeon-b"]), task("T-AA-02", prereq=["T-AA-01"], produces=["crate:onjeon-b"])), "BOOT-CONSUMES"),
        ("consumes of a path only a non-prerequisite produces", tree(task("T-AA-01", consumes=["path:tools/b/**"]), task("T-AA-02", produces=["path:tools/b/**"])), "BOOT-CONSUMES"),
        ("test command path nobody produces", tree(task("T-AA-01", tests=["python3 tools/missing/run.py"])), "BOOT-PATH"),
        ("test command path inside the task's own allowed paths", tree(task("T-AA-01", tests=["bash tools/mine/run.sh"], allowed=["tools/mine/**"])), None),
        ("test command path inside only another task's allowed paths", tree(task("T-AA-01", tests=["bash tools/other/run.sh"]), task("T-AA-02", allowed=["tools/other/**"])), "BOOT-PATH"),
        ("done criteria mention a non-prerequisite task", tree(task("T-AA-01", done=["builds on T-AA-02"]), task("T-AA-02")), "BOOT-MENTION"),
        ("done criteria rely on a crate a non-prerequisite makes", tree(task("T-AA-01", done=["onjeon-b round trip"]), task("T-AA-02", produces=["crate:onjeon-b"])), "BOOT-MENTION"),
    ]
    return C.run_selftest("check_bootstrap", cases, lambda root: check(root, root / "tasks.json"))


def main(argv):
    args = argv[1:]
    if args == ["--selftest"]:
        return selftest()
    root, tasks, strict = C.ROOT, None, False
    while args:
        flag = args.pop(0)
        if flag == "--strict-paths":
            strict = True
        elif flag == "--root" and args:
            root = Path(args.pop(0))
        elif flag == "--tasks" and args:
            tasks = Path(args.pop(0))
        else:
            return C.usage_error(__doc__.split("Usage:")[1].strip())
    tasks = tasks or root / DEFAULT_TASKS
    try:
        advisory = []
        findings = check(root, tasks, strict, advisory)
    except (OSError, ValueError, KeyError) as e:
        return C.usage_error(f"cannot read tasks {tasks}: {e}")
    if advisory:
        print(f"advisory: {len(advisory)} test-command path(s) are neither in the repo nor under the task's allowed_paths (run with --strict-paths to fail on them):")
        for f in advisory:
            print("  " + f.render())
    ok = "no G1/G2/G31 violations (static only; nothing was built)" + (f"; {len(advisory)} advisory path note(s) above" if advisory else "")
    return C.report(findings, ok, "bootstrap-clean-main")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
