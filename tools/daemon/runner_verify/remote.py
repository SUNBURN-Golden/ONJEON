"""The verification remote: a throwaway bare repository with a protected `main`, a hook that checks the pusher's
short-lived credential, and a push log. It is never a product repository. Only a repository that this module
provisioned (marker file + hooks) is accepted; the product repository's own location and remotes are refused.

What this stands in for, and what it does not prove, is written to the report: a real Git host's branch protection
and token issuing are set up by a person (04 §8, 05 §4) and are not exercised by a local bare repository.
"""
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import PKG_DIR, ROOT, append_jsonl, now_ns, read_jsonl

MARKER_PURPOSE = "runner_verify_test_remote"
HOOK = PKG_DIR / "hook_pre_receive.py"
SEED_FILES = {
    "tools/mock/basic/README.md": "T-MOCK fixture file. Not product content.\n",
    "tools/mock/handoff/README.md": "T-MOCK fixture file. Not product content.\n",
    "tools/mock/other/README.md": "T-MOCK fixture file. Not product content.\n",
}


class RemoteRefused(Exception):
    pass


def git_env(home):
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "TMPDIR")}
    env.update(HOME=str(home), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_TERMINAL_PROMPT="0",
               GIT_AUTHOR_NAME="runner-verify", GIT_AUTHOR_EMAIL="runner-verify@invalid",
               GIT_COMMITTER_NAME="runner-verify", GIT_COMMITTER_EMAIL="runner-verify@invalid")
    return env


def run_git(args, cwd=None, env=None, check=True, input=None, timeout=60):
    res = subprocess.run(["git"] + list(args), cwd=cwd, env=env, input=input, capture_output=True, text=True,
                         timeout=timeout)
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res


def provision(path, home):
    """Create the bare repository, its hooks, the marker and a seeded `main`. Returns the path."""
    path = Path(path).resolve()
    env = git_env(home)
    run_git(["init", "--bare", "-b", "main", str(path)], env=env)
    for key, value in (("receive.denyNonFastForwards", "true"), ("receive.denyDeletes", "true"), ("gc.auto", "0")):
        run_git(["config", key, value], cwd=path, env=env)
    (path / "rv").mkdir(exist_ok=True)
    (path / "rv" / "MARKER").write_text(json.dumps({"purpose": MARKER_PURPOSE, "origin": "fixture",
                                                    "fixture_only": True, "created_ns": now_ns()}), encoding="utf-8")
    for name, mode in (("pre-receive", "pre"), ("post-receive", "post")):
        hook = path / "hooks" / name
        hook.write_text(f"#!/bin/sh\nexec '{sys.executable}' -I '{HOOK}' {mode}\n", encoding="utf-8")
        hook.chmod(0o755)
    with tempfile.TemporaryDirectory(prefix="rv-seed-") as seed:
        run_git(["init", "-b", "main", seed], env=env)
        for rel, content in SEED_FILES.items():
            p = Path(seed) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        run_git(["add", "-A"], cwd=seed, env=env)
        run_git(["commit", "-m", "seed of the verification remote"], cwd=seed, env=env)
        run_git(["fetch", seed, "refs/heads/main:refs/heads/main"], cwd=path, env=env)
    return path


def _product_locations():
    """Paths and URLs that identify the product repository: never accepted as the verification remote."""
    out = {str(ROOT.resolve()), str((ROOT / ".git").resolve())}
    res = subprocess.run(["git", "-C", str(ROOT), "remote", "-v"], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out.add(parts[1])
            with_suffix = re.sub(r"\.git$", "", parts[1])
            out.add(with_suffix)
    res = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"], capture_output=True, text=True)
    if res.returncode == 0:
        out.add(str(Path(res.stdout.strip()).resolve()))
    return out


def check_accepts(path):
    """Refuse anything that is not a repository this tool provisioned. Returns the resolved path."""
    text = str(path)
    if "://" in text or re.match(r"^[\w.-]+@[\w.-]+:", text):
        raise RemoteRefused(f"URL remotes are not supported: {text!r}. Provision one with --remote auto or pass the "
                            "path of a repository created by this tool (credential issuing at a real host is a "
                            "person's setup and is reported as unconfirmed).")
    p = Path(text).resolve()
    if not p.is_dir() or not (p / "HEAD").exists() or not (p / "objects").is_dir():
        raise RemoteRefused(f"{p} is not a bare repository")
    marker = p / "rv" / "MARKER"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if data.get("purpose") != MARKER_PURPOSE:
        raise RemoteRefused(f"{p} has no verification-remote marker")
    for name in ("pre-receive", "post-receive"):
        if not os.access(p / "hooks" / name, os.X_OK):
            raise RemoteRefused(f"{p} lacks the {name} hook")
    product = _product_locations()
    if str(p) in product or str(p) + ".git" in product:
        raise RemoteRefused(f"{p} is the product repository")
    return p


# ---------------------------------------------------------------- queries
def push_log(remote):
    return read_jsonl(Path(remote) / "rv" / "push_log.jsonl")


def refs(remote, home):
    res = run_git(["for-each-ref", "--format=%(refname) %(objectname)"], cwd=remote, env=git_env(home))
    return dict(line.split(" ", 1) for line in res.stdout.splitlines() if line)


def register_token(remote, token_sha, name, task_id, lease_id, ttl_s):
    append_jsonl(Path(remote) / "rv" / "tokens.jsonl", {
        "op": "issue", "token_sha": token_sha, "name": name, "task_id": task_id, "lease_id": lease_id,
        "ts_ns": now_ns(), "expires_ns": now_ns() + int(ttl_s * 1e9)})


def revoke_token(remote, token_sha):
    append_jsonl(Path(remote) / "rv" / "tokens.jsonl", {"op": "revoke", "token_sha": token_sha, "ts_ns": now_ns()})


def destroy(path):
    shutil.rmtree(path, ignore_errors=True)


def reset(path, home):
    """Return an accepted remote to its seeded state before a scenario: task refs deleted, credential registry and
    push log emptied. Only a repository that passed check_accepts gets here."""
    env = git_env(home)
    for ref in refs(path, home):
        if ref.startswith("refs/heads/task/"):
            run_git(["update-ref", "-d", ref], cwd=path, env=env)
    for name in ("tokens.jsonl", "push_log.jsonl", "extra_protected.json", "force_reject"):
        with contextlib.suppress(FileNotFoundError):
            (Path(path) / "rv" / name).unlink()
