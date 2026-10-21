#!/usr/bin/env python3
"""bootstrap-sample prune engine: rebuild "main minus non-prerequisite task outputs" in a clone.

tasks.json is the source of truth for which task produced what. A task's outputs are the files its
pull-request merge added, plus the edits it made to files that existed before. This script finds the
first-parent PR merges on a ref, maps each merge subject `.../onjeon-T-XX-NN...` to a tasks.json task
id, and peels every merge that belongs to a task outside the keep set. The keep set is the
declared-dependency closure: the sample task, its transitive `prereq_tasks`, and —
transitively — the producers of every artifact those tasks declare in `consumes` (a consumed
crate means every task that produced a path inside its member directory, since a crate is the
sum of its files). Peeling is newest-first:

  A (added)    -> delete the file
  D (deleted)  -> restore the M^1 copy
  M/T (edited) -> unmerge the merge's edit on top of the current file (git merge-file), so later
                  edits survive; warn and leave the file when the 3-way merge conflicts

Merges whose branch is not a tasks.json task (decision docs, audits, crawler chores) are base: their
changes stay. Afterwards the workspace `members` list is rewritten to the members that still have a
directory, and empty directories are removed. The build that follows is run.sh's job, not this
script's.

Usage:
  python3 -I prune.py crate --task T-TW-01 [--tasks FILE]     print the task's produced crate name
  python3 -I prune.py keep  --task T-TW-01 [--repo DIR --ref SHA]   print the keep set, one id per
                             line (with --repo/--ref the declared consumes edges are resolved)
  python3 -I prune.py pick  --task T-TW-01 --repo DIR --ref SHA   print one non-prerequisite task id
  python3 -I prune.py prune --task T-TW-01 --repo DIR --ref SHA [--only T-XX-NN] [--except T-XX-NN]...
  python3 -I prune.py diagnose --task T-TW-01 --repo DIR --ref SHA --workdir DIR [--max-trials N]
  python3 -I prune.py --selftest
Exit: 0 clean, 1 task/graph problem or residual output that could not be peeled, 2 usage.
"""
import argparse
import fnmatch
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TASKS = ROOT / "docs/blueprint/proposals/설계검토_결과/tasks.json"
MERGE_TASK = re.compile(r"onjeon-(T-[A-Z]{2}-\d{2})[a-z]?(?:[^A-Za-z0-9]|$)")
MEMBERS_RE = re.compile(r"(?ms)^(\s*members\s*=\s*)\[(.*?)\]")
ENTRY_RE = re.compile(r'"([^"]+)"')


class GraphError(Exception):
    pass


def load_tasks(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise GraphError(f"cannot read tasks {path}: {e}")
    return {t["id"]: t for t in data["tasks"]}


def keep_set(tasks, tid):
    if tid not in tasks:
        raise GraphError(f"task {tid} is not in tasks.json")
    out, visiting = set(), set()

    def visit(t):
        if t in visiting:
            raise GraphError(f"{tid}: prerequisite cycle through {t}")
        if t in out:
            return
        if t not in tasks:
            raise GraphError(f"{tid}: prerequisite {t} is not in tasks.json")
        visiting.add(t)
        for parent in tasks[t].get("prereq_tasks", []):
            visit(parent)
        visiting.remove(t)
        out.add(t)

    visit(tid)
    return out


def target_crate(tasks, tid):
    keep_set(tasks, tid)
    crates = [p.split(":", 1)[1] for p in tasks[tid].get("produces", []) if p.startswith("crate:")]
    if len(crates) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]+", crates[0]):
        raise GraphError(f"{tid} must produce exactly one valid crate")
    return crates[0]


def _sample(pattern):
    return pattern.replace("**", "s/t").replace("*", "x").replace("?", "q")


def paths_overlap(a, b):
    """Can two globs point at the same file (same approximation as check_bootstrap.overlap)."""
    if fnmatch.fnmatch(_sample(a), b) or fnmatch.fnmatch(_sample(b), a):
        return True
    pa, pb = a.split("*")[0], b.split("*")[0]
    return (a.endswith("**") and pb.startswith(pa)) or (b.endswith("**") and pa.startswith(pb))


def producer_index(tasks):
    """(crate producers {name: {task,...}}, path producers [(glob, task)]) over all produces."""
    crates, paths = {}, []
    for tid, t in tasks.items():
        for p in t.get("produces", []):
            kind, _, val = p.partition(":")
            if kind == "crate":
                crates.setdefault(val, set()).add(tid)
            elif kind == "path":
                paths.append((val, tid))
    return crates, paths


def member_crates_at(repo, ref):
    """{package name: member dir} resolved from git objects at `ref`, not the working tree."""
    try:
        root = tomllib.loads(git(repo, "show", f"{ref}:Cargo.toml").stdout)
    except (GraphError, tomllib.TOMLDecodeError):
        return {}
    members = (root.get("workspace") or {}).get("members") or []
    out = {}
    for rel in git(repo, "ls-tree", "-r", "--name-only", ref).stdout.splitlines():
        if not rel.endswith("/Cargo.toml"):
            continue
        d = rel.rsplit("/", 1)[0]
        if not any(fnmatch.fnmatch(d, pat) for pat in members):
            continue
        try:
            name = (tomllib.loads(git(repo, "show", f"{ref}:{rel}").stdout)
                    .get("package") or {}).get("name")
        except tomllib.TOMLDecodeError:
            continue
        if name:
            out[name] = d
    return out


def expanded_keep(tasks, tid, crate_dirs, landed=None):
    """Declared-dependency keep set: `tid` plus, transitively, its prereq_tasks and the
    producers of every artifact those tasks declare in `consumes`. A consumed crate is the
    sum of its workspace member directory, so tasks producing paths inside it count as the
    crate's producers; a consumed path is produced by any task with an overlapping glob.
    `landed` restricts producer candidates to tasks whose merge is on the ref — an unlanded
    task cannot have contributed to the artifact's current state (None = no restriction,
    for callers without merge history)."""
    keep_set(tasks, tid)  # fail early on unknown tasks, missing prereqs and prereq cycles
    crates, paths = producer_index(tasks)

    def landed_only(ids):
        return [t for t in ids if landed is None or t in landed]

    keep, queue = set(), [tid]
    while queue:
        t = queue.pop()
        if t in keep:
            continue
        if t not in tasks:
            raise GraphError(f"{tid}: prerequisite {t} is not in tasks.json")
        keep.add(t)
        queue.extend(tasks[t].get("prereq_tasks", []))
        for ref in tasks[t].get("consumes", []):
            kind, _, val = ref.partition(":")
            if kind == "crate":
                queue.extend(landed_only(crates.get(val, ())))
                d = crate_dirs.get(val)
                if d:
                    queue.extend(landed_only(p for g, p in paths if paths_overlap(g, d + "/**")))
            elif kind == "path":
                queue.extend(landed_only(p for g, p in paths if paths_overlap(g, val)))
    return keep


def landed_tasks(merges):
    """Task ids with a first-parent merge in a mainline_merges() listing."""
    return {tag for _, tag, _ in merges if tag}


def git(repo, *args, inp=None, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, input=inp)
    if check and r.returncode:
        raise GraphError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r


def mainline_merges(repo, ref):
    """First-parent merges on ref, newest first: [(sha, task_id or None, subject)]."""
    shas = git(repo, "rev-list", "--first-parent", "--merges", ref).stdout.split()
    out = []
    for sha in shas:
        subject = git(repo, "show", "-s", "--format=%s", sha).stdout.strip()
        m = MERGE_TASK.search(subject)
        out.append((sha, m.group(1) if m else None, subject))
    return out


def blob(repo, spec):
    """Blob id of spec (rev:path), or None when the path is absent at that rev."""
    r = git(repo, "rev-parse", "--verify", "--quiet", spec, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def merge_diff(repo, merge):
    """name-status pairs of merge^1..merge with renames split into D+A."""
    out = []
    for line in git(repo, "diff", "--name-status", "--no-renames", f"{merge}^1", merge).stdout.splitlines():
        st, _, path = line.partition("\t")
        if path:
            out.append((st, path))
    return out


def peel(repo, merge, ref, log):
    """Undo one merge's file-level effect in the clone's working tree."""
    removed = restored = 0
    for st, rel in merge_diff(repo, merge):
        path = Path(repo) / rel
        if st == "A":
            if path.exists() or path.is_symlink():
                path.unlink()
                removed += 1
            continue
        if st == "D":
            if path.exists():
                log.append(f"    WARN {rel}: re-added after {merge[:8]}, left in place")
                continue
            write_rev(repo, f"{merge}^1", rel, path)
            restored += 1
            continue
        # modified / type-changed: undo merge^1->merge on top of the current file (3-way merge),
        # so later edits survive and only this merge's contribution is removed.
        if not path.exists():
            if blob(repo, f"{ref}:{rel}") is None:
                continue  # a later merge already removed it; nothing to restore
            write_rev(repo, f"{merge}^1", rel, path)
            restored += 1
            continue
        if unmerge(repo, path, rel, merge):
            restored += 1
            continue
        log.append(f"    WARN {rel}: edited by {merge[:8]} but later work conflicts; non-prerequisite lines may remain")
    return removed, restored


def unmerge(repo, path, rel, merge):
    """Apply the inverse of merge^1->merge to `path` via git merge-file. False on conflicts."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        theirs = Path(tmp) / "theirs"
        current = Path(tmp) / "current"
        texts = [path.read_text(encoding="utf-8"),
                 git(repo, "show", f"{merge}:{rel}").stdout,
                 git(repo, "show", f"{merge}^1:{rel}").stdout]
        members = None
        if rel == "Cargo.toml" and all(MEMBERS_RE.search(text) for text in texts):
            current_members, after, before = [ENTRY_RE.findall(MEMBERS_RE.search(text).group(2))
                                              for text in texts]
            added = set(after) - set(before)
            deleted = set(before) - set(after)
            members = [entry for entry in current_members if entry not in added]
            members.extend(entry for entry in before if entry in deleted and entry not in members)
            texts = [MEMBERS_RE.sub('members = []', text, count=1) for text in texts]
        for dest, text in zip((current, base, theirs), texts):
            dest.write_text(text, encoding="utf-8")
        r = subprocess.run(["git", "merge-file", "-p", str(current), str(base), str(theirs)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False
        result = r.stdout
        if members is not None:
            block = 'members = [\n' + ''.join(f'    "{entry}",\n' for entry in members) + ']'
            result = MEMBERS_RE.sub(lambda m: block, result, count=1)
        Path(path).write_text(result, encoding="utf-8")
        return True


def write_rev(repo, rev, rel, path):
    text = git(repo, "show", f"{rev}:{rel}").stdout
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def original_members(repo):
    text = Path(repo, "Cargo.toml").read_text(encoding="utf-8") if Path(repo, "Cargo.toml").exists() else ""
    m = MEMBERS_RE.search(text)
    return ENTRY_RE.findall(m.group(2)) if m else []


def repair_members(repo, members, log):
    toml = Path(repo) / "Cargo.toml"
    if not toml.exists():
        return
    text = toml.read_text(encoding="utf-8")
    keep = [m for m in members if (repo / m / "Cargo.toml").exists()]
    dropped = [m for m in members if m not in keep]
    block = "members = [\n" + "".join(f'    "{m}",\n' for m in keep) + "]"
    new, n = MEMBERS_RE.subn(lambda m: block, text, count=1)
    if n:
        toml.write_text(new, encoding="utf-8")
    for m in dropped:
        log.append(f"  workspace member removed: {m}")


def drop_empty_dirs(repo):
    for base, dirs, files in os.walk(repo, topdown=False):
        p = Path(base)
        if p == Path(repo) or ".git" in p.parts:
            continue
        try:
            p.rmdir()
        except OSError:
            pass


def prune(repo, ref, tasks, tid, only=None, except_ids=frozenset()):
    merges = mainline_merges(repo, ref)
    keep = expanded_keep(tasks, tid, member_crates_at(repo, ref), landed_tasks(merges))
    log, removed, restored = [], 0, 0
    peeled = []
    for sha, tag, subject in merges:
        if tag is None or tag not in tasks:
            continue  # base branch (decisions, audits, chores): stays
        if tag in keep or tag in except_ids:
            continue  # the sample task or one of its prerequisites: stays
        if only and tag != only:
            continue
        rm, rs = peel(repo, sha, ref, log)
        removed += rm
        restored += rs
        peeled.append(tag)
        log.append(f"  peel {tag} {sha[:8]}: {rm} file(s) removed, {rs} restored/reverted")
    repair_members(repo, original_members(repo), log)
    drop_empty_dirs(repo)
    conflicts = [line for line in log if "WARN" in line]
    if conflicts:
        raise GraphError("residual non-prerequisite output:\n" + "\n".join(conflicts))
    return log, sorted(set(peeled)), removed, restored


def pick(tasks, tid, repo, ref):
    """One non-prerequisite task that left outputs on this ref: prefer a crate producer with files."""
    merges = mainline_merges(repo, ref)
    keep = expanded_keep(tasks, tid, member_crates_at(repo, ref), landed_tasks(merges))
    first = {}
    for sha, tag, _ in merges:
        if tag and tag in tasks and tag not in keep and tag not in first:
            first[tag] = sha
    for tag, sha in first.items():
        has_crate = any(p.startswith("crate:") for p in tasks[tag].get("produces", []))
        if has_crate and merge_diff(repo, sha):
            return tag
    for tag, sha in first.items():
        if any(st == "A" for st, _ in merge_diff(repo, sha)):
            return tag
    raise GraphError("no landed non-prerequisite task produced files on this ref")


# ---------- undeclared-dependency diagnosis ----------
def member_crates(repo):
    """{package name: member dir} resolved from the root workspace members list."""
    try:
        members = (tomllib.loads((Path(repo) / "Cargo.toml").read_text(encoding="utf-8"))
                   .get("workspace") or {}).get("members") or []
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out = {}
    for pattern in members:
        for m in sorted(glob.glob(str(Path(repo) / pattern))) or []:
            cargo = Path(m) / "Cargo.toml"
            try:
                name = (tomllib.loads(cargo.read_text(encoding="utf-8")).get("package") or {}).get("name")
            except (OSError, tomllib.TOMLDecodeError):
                continue
            if name:
                out[name] = cargo.parent.relative_to(repo).as_posix()
    return out


def dep_dirs(repo, crate):
    """Member dirs of `crate` plus the workspace path dependencies it transitively needs."""
    crates = member_crates(repo)
    out, queue, seen = set(), [crate], set()
    while queue:
        name = queue.pop()
        if name in seen or name not in crates:
            continue
        seen.add(name)
        out.add(crates[name])
        try:
            data = tomllib.loads((Path(repo) / crates[name] / "Cargo.toml").read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for sect in ("dependencies", "dev-dependencies", "build-dependencies"):
            for dep, spec in (data.get(sect) or {}).items():
                if isinstance(spec, dict) and "path" in spec:
                    queue.append(dep)
    return out


def suspect_merges(repo, ref, tasks, tid, dirs):
    """Peeled task merges that touched a file inside the dependency-closure dirs."""
    merges = mainline_merges(repo, ref)
    keep = expanded_keep(tasks, tid, member_crates_at(repo, ref), landed_tasks(merges))
    out = []
    for sha, tag, _ in merges:
        if not tag or tag not in tasks or tag in keep or tag in out:
            continue
        paths = [p for _, p in merge_diff(repo, sha)]
        if any(p == d or p.startswith(d + "/") for p in paths for d in dirs):
            out.append(tag)
    return out


def artifact_consumers(repo, tasks, keep, dirs):
    """For each dependency-closure dir, the keep tasks that declare a consume on its artifact."""
    crates = member_crates(repo)
    by_dir = {}
    for k in keep:
        for ref in tasks[k].get("consumes", []):
            kind, _, val = ref.partition(":")
            for d in dirs:
                if kind == "crate" and crates.get(val) == d:
                    by_dir.setdefault(d, set()).add(k)
                elif kind == "path" and (val == d or val.startswith(d + "/") or d.startswith(val + "/")):
                    by_dir.setdefault(d, set()).add(k)
    return by_dir


def diagnose(repo, ref, tasks, tid, crate, workdir, emit, max_trials=12):
    """Identify peeled task merges whose outputs the sample build actually needs.

    A failing phase only says the pruned tree does not build; it does not say which
    non-prerequisite merge the keep set silently relied on. This routine restores
    peeled merges inside the crate's dependency closure, one trial build at a time,
    and returns the minimal set that makes `cargo build`/`cargo test -p crate` pass
    (a greedy minimal, not a proven minimum). Each trial resets one clone to `ref`,
    prunes with that set exempted and compiles. Returns the task ids, [] when the
    failure needs no task merge back (a base/keep-side problem), or None when even
    every suspect restored still fails. Trial count is capped by max_trials; on a
    cap hit the last verified-sufficient superset is returned.
    """
    dirs = sorted(dep_dirs(repo, crate))
    suspects = suspect_merges(repo, ref, tasks, tid, dirs)
    shas = {tag: sha for sha, tag, _ in mainline_merges(repo, ref) if tag}
    emit(f"dependency closure of {crate}: {', '.join(dirs) or '(none)'}")
    emit(f"peeled merges that touched it: {', '.join(suspects) or 'none'}")
    if not suspects:
        emit("diagnosis: no peeled merge touched the dependency crates; the failure is not "
             "explained by a single task merge (base content or a keep-side defect)")
        return []
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    clone = workdir / "clone"
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(repo), str(clone)],
                   check=True, capture_output=True, text=True)
    target = workdir / "target"
    trials = [0]

    def trial(exceptions):
        trials[0] += 1
        git(clone, "reset", "--hard", "--quiet", ref)
        git(clone, "clean", "-fdq")
        try:
            prune(clone, ref, tasks, tid, except_ids=exceptions)
        except GraphError:
            return False
        env = {**os.environ, "CARGO_TARGET_DIR": str(target)}
        for cmd in (["cargo", "build", "-p", crate], ["cargo", "test", "-p", crate]):
            if subprocess.run(cmd, cwd=clone, env=env, capture_output=True).returncode:
                return False
        return True

    needed = set(suspects)
    if not trial(needed):
        emit("diagnosis: build still fails with every suspect restored; the gap is not a "
             "simple set of peeled task merges")
        return None
    for tag in suspects:
        if len(needed) <= 1 or trials[0] >= max_trials:
            break
        if trial(needed - {tag}):
            needed.discard(tag)
    keep = expanded_keep(tasks, tid, member_crates_at(repo, ref),
                         landed_tasks(mainline_merges(repo, ref)))
    consumers = artifact_consumers(repo, tasks, keep, dirs)
    emit(f"diagnosis: keep set needs output from {len(needed)} non-prerequisite task(s) "
         f"({trials[0]} trial build(s)):")
    for tag in sorted(needed):
        touched = sorted({d for d in dirs for _, p in merge_diff(repo, shas[tag])
                          if p == d or p.startswith(d + "/")})
        who = sorted({k for d in touched for k in consumers.get(d, ())})
        emit(f"  {tag}: required; tasks.json declares no prerequisite or consumes edge to it"
             + (f" (touched {', '.join(touched)}; consumed by {', '.join(who)})" if who else ""))
    if trials[0] >= max_trials:
        emit("diagnosis: trial budget reached; the reported set is sufficient but may not be minimal")
    return needed


# ---------- selftest ----------
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "selftest",
    "GIT_AUTHOR_EMAIL": "selftest@example.invalid",
    "GIT_COMMITTER_NAME": "selftest",
    "GIT_COMMITTER_EMAIL": "selftest@example.invalid",
}


def sgit(root, *args, inp=None):
    r = subprocess.run(["git", "-C", str(root), *args], env=GIT_ENV, capture_output=True, text=True, input=inp)
    if r.returncode:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def put(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def merge_branch(root, tid, edits):
    """Commit `edits` on a grokbot/onjeon-<tid> branch and PR-merge it back into main."""
    sgit(root, "checkout", "-q", "-b", f"grokbot/onjeon-{tid}")
    for rel, text in edits.items():
        put(root, rel, text)
    sgit(root, "add", "-A")
    sgit(root, "commit", "-q", "-m", f"{tid}: change")
    sgit(root, "checkout", "-q", "main")
    sgit(root, "merge", "--no-ff", "-q", "-m", f"Merge pull request #1 from x/grokbot/onjeon-{tid}", f"grokbot/onjeon-{tid}")


def selftest_repo(root):
    sgit(root, "init", "-q", "-b", "main")
    put(root, "Cargo.toml", '[workspace]\nmembers = ["pkg/a", "pkg/c"]\n')
    put(root, "pkg/a/Cargo.toml", '[package]\nname = "onjeon-aa"\n')
    put(root, "pkg/c/Cargo.toml", '[package]\nname = "onjeon-cc"\n')
    put(root, "shared.txt", "line1\nline2\nline3\n")
    sgit(root, "add", "-A")
    sgit(root, "commit", "-q", "-m", "base")
    tasks = {"tasks": [
        {"id": "T-AA-01", "prereq_tasks": [], "produces": ["crate:onjeon-aa"]},
        {"id": "T-AA-02", "prereq_tasks": ["T-AA-01"], "produces": ["crate:onjeon-bb", "path:extra/**"]},
        {"id": "T-BB-01", "prereq_tasks": ["T-AA-01"], "produces": ["crate:onjeon-cc"]},
    ]}
    put(root, "tasks.json", json.dumps(tasks))
    sgit(root, "add", "tasks.json")
    sgit(root, "commit", "-q", "-m", "tasks")
    merge_branch(root, "T-AA-01", {"pkg/a/src.rs": "// aa\n"})
    merge_branch(root, "T-AA-02", {
        "Cargo.toml": '[workspace]\nmembers = ["pkg/a", "pkg/b", "pkg/c"]\n',
        "pkg/b/Cargo.toml": '[package]\nname = "onjeon-bb"\n',
        "pkg/b/src.rs": "// bb\n",
        "extra/note.txt": "note\n",
        "shared.txt": "line1\nline-bb\nline3\n",
    })
    sgit(root, "checkout", "-q", "main")
    put(root, "shared.txt", "line0\nline1\nline-bb\nline3\nline4\n")
    sgit(root, "commit", "-qam", "later base edit")
    merge_branch(root, "T-BB-01", {"pkg/c/src.rs": "// cc\n"})
    return tasks


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        tasks = selftest_repo(repo)
        tasks = {t["id"]: t for t in tasks["tasks"]}
        ref = sgit(repo, "rev-parse", "HEAD").stdout.strip()

        assert keep_set(tasks, "T-BB-01") == {"T-BB-01", "T-AA-01"}
        assert pick(tasks, "T-BB-01", repo, ref) == "T-AA-02"

        log, peeled, removed, restored = prune(repo, ref, tasks, "T-BB-01")
        assert peeled == ["T-AA-02"], peeled
        assert not (repo / "pkg/b/src.rs").exists(), "T-AA-02 output survived"
        assert not (repo / "extra").exists(), "T-AA-02 path output survived"
        assert (repo / "pkg/a/src.rs").exists() and (repo / "pkg/c/src.rs").exists(), "keep output lost"
        # T-AA-02's shared.txt hunk was peeled (line-bb -> line2) while the later base edit stayed.
        assert (repo / "shared.txt").read_text() == "line0\nline1\nline2\nline3\nline4\n", log
        assert original_members(repo) == ["pkg/a", "pkg/c"], original_members(repo)
        text = (repo / "Cargo.toml").read_text()
        assert '"pkg/b"' not in text and '"pkg/a"' in text and '"pkg/c"' in text, text
        assert not any("WARN" in line for line in log), log

        # --only peels a single task, leaving other non-prerequisite outputs in place.
        repo2 = Path(tmp) / "repo2"
        repo2.mkdir()
        tasks = selftest_repo(repo2)
        tasks = {t["id"]: t for t in tasks["tasks"]}
        ref2 = sgit(repo2, "rev-parse", "HEAD").stdout.strip()
        prune(repo2, ref2, tasks, "T-BB-01", only="T-AA-02")
        assert not (repo2 / "pkg/b/src.rs").exists()

        # --except exempts a non-prerequisite task from peeling (diagnosis building block).
        repo3 = Path(tmp) / "repo3"
        repo3.mkdir()
        tasks = selftest_repo(repo3)
        tasks = {t["id"]: t for t in tasks["tasks"]}
        ref3 = sgit(repo3, "rev-parse", "HEAD").stdout.strip()
        _, peeled3, _, _ = prune(repo3, ref3, tasks, "T-BB-01", except_ids={"T-AA-02"})
        assert peeled3 == [], peeled3
        assert (repo3 / "pkg/b/src.rs").exists() and (repo3 / "extra/note.txt").exists()

        # dep_dirs resolves the crate's own dir; suspects are peeled merges inside it.
        assert dep_dirs(repo3, "onjeon-cc") == {"pkg/c"}
        assert suspect_merges(repo3, ref3, tasks, "T-BB-01", ["pkg/b", "extra"]) == ["T-AA-02"]
        assert suspect_merges(repo3, ref3, tasks, "T-BB-01", ["pkg/c"]) == []

        for name, fn in [("unknown task", lambda: keep_set(tasks, "T-ZZ-99")),
                         ("crate-less task", lambda: target_crate({"T-AA-01": {"produces": []}}, "T-AA-01")),
                         ("missing prereq", lambda: keep_set({"T-AA-01": {"prereq_tasks": ["T-ZZ-99"]}}, "T-AA-01"))]:
            try:
                fn()
            except GraphError:
                pass
            else:
                raise AssertionError(f"{name}: expected GraphError")
    print("prune selftest ok: peel, single-drop, except, suspects, members repair and graph errors all exercised")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="prune.py", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("crate", "keep", "pick", "prune", "diagnose"):
        p = sub.add_parser(name)
        p.add_argument("--task", required=True)
        p.add_argument("--tasks", default=str(DEFAULT_TASKS))
        if name in ("pick", "prune", "diagnose"):
            p.add_argument("--repo", required=True)
            p.add_argument("--ref", required=True)
        if name == "keep":
            p.add_argument("--repo")
            p.add_argument("--ref")
        if name == "prune":
            p.add_argument("--only", default=None)
            p.add_argument("--except", dest="except_ids", action="append", default=[])
        if name == "diagnose":
            p.add_argument("--workdir", required=True)
            p.add_argument("--max-trials", type=int, default=12)
    args = ap.parse_args(argv[1:])
    if args.selftest:
        return selftest()
    if not args.cmd:
        return 2
    try:
        tasks = load_tasks(args.tasks)
        if args.cmd == "crate":
            print(target_crate(tasks, args.task))
        elif args.cmd == "keep":
            if args.repo and args.ref:
                keep = expanded_keep(tasks, args.task, member_crates_at(Path(args.repo), args.ref),
                                     landed_tasks(mainline_merges(Path(args.repo), args.ref)))
            else:
                keep = keep_set(tasks, args.task)
            print("\n".join(sorted(keep)))
        elif args.cmd == "pick":
            print(pick(tasks, args.task, Path(args.repo), args.ref))
        elif args.cmd == "diagnose":
            crate = target_crate(tasks, args.task)
            needed = diagnose(Path(args.repo), args.ref, tasks, args.task, crate,
                              Path(args.workdir), print, args.max_trials)
            return 0 if needed is not None else 1
        else:
            log, peeled, removed, restored = prune(Path(args.repo), args.ref, tasks, args.task, args.only,
                                                   frozenset(args.except_ids))
            for line in log:
                print(line)
            print(f"prune: {len(peeled)} merge task(s) peeled ({', '.join(peeled)}), {removed} file(s) removed, {restored} restored/reverted")
    except GraphError as e:
        print(f"prune: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
