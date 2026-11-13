"""pre-receive / post-receive hook of the verification remote (stand-in for a Git host's protected branch and its
short-lived push credentials). Runs inside `git receive-pack`; the pusher's credential arrives in RV_PUSH_CREDENTIAL.

Rules, in this order, for every ref a push updates:
  1. protected branches (main, release/*) accept no push at all           -> RV-REJECT protected_branch
  2. only refs/heads/task/T-MOCK-* are writable                           -> RV-REJECT ref_not_allowed
  3. the credential must be known, not revoked, not expired, of a name
     that may write, and issued for the task the branch belongs to        -> RV-REJECT permission_denied |
                                                                             credential_revoked | credential_expired |
                                                                             scope_mismatch
  4. builder writes require their current, active, unexpired lease        -> RV-REJECT lease_unavailable |
                                                                             lease_not_current_or_not_active |
                                                                             lease_expired
     (preserve credentials are the daemon's separate handoff authority)
Every decision is appended to rv/push_log.jsonl before the ref is touched. Standard library only.
"""
import fcntl
import hashlib
import json
import math
import os
import re
import sys
import time

GIT_DIR = os.environ.get("GIT_DIR", ".")
RV = os.path.join(GIT_DIR, "rv")
WRITERS = {"builder_write_credential", "preserve_credential"}
PROTECTED = (re.compile(r"^refs/heads/main$"), re.compile(r"^refs/heads/release/"))
WRITABLE = re.compile(r"^refs/heads/task/(T-MOCK-[A-Za-z0-9_-]+)-a\d+$")


def append(name, record):
    fd = os.open(os.path.join(RV, name), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, (json.dumps(record, sort_keys=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def credential_state(token):
    """Replay rv/tokens.jsonl: the entry of this token with its revocation, or None if it was never issued."""
    if not token:
        return None
    sha = hashlib.sha256(token.encode()).hexdigest()
    entry = None
    try:
        with open(os.path.join(RV, "tokens.jsonl"), encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("token_sha") != sha:
                    continue
                if rec["op"] == "issue":
                    entry = dict(rec, revoked_ns=None)
                elif rec["op"] == "revoke" and entry is not None:
                    entry["revoked_ns"] = rec["ts_ns"]
    except FileNotFoundError:
        return None
    return entry


def control(name):
    """Test controls placed next to the registry by the harness: a reason that rejects every push, and extra
    protected ref patterns (a remote that refuses the daemon's push)."""
    try:
        with open(os.path.join(RV, name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def lease_rejection(entry):
    """Read the atomic state snapshot using the daemon's shifted clock. No tick/revoke is needed to expire a
    builder. Missing bindings/state and malformed data fail closed. Do not take the store lock: a daemon
    preserve push can run inside its transaction, and readers see either complete snapshot after rename."""
    try:
        with open(entry["lease_store"], encoding="utf-8") as f:
            lease = json.load(f)["tasks"][entry["task_id"]]["lease_record"]
        offset = 0.0
        try:
            with open(entry["lease_clock"], encoding="utf-8") as f:
                offset = float(json.load(f).get("offset", 0.0))
        except FileNotFoundError:
            pass  # ClockFile also uses offset 0 until the first clock advance.
        if not isinstance(lease, dict) or not math.isfinite(offset):
            return "lease_unavailable"
        if lease.get("lease_id") != entry["lease_id"] or lease.get("status") != "active":
            return "lease_not_current_or_not_active"
        expires = lease["expires_at"]
        if type(expires) not in (int, float) or not math.isfinite(expires):
            return "lease_unavailable"
        if expires <= int(time.time() + offset):
            return "lease_expired"
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return "lease_unavailable"
    return None


def decide(ref, token):
    forced = control("force_reject")
    if forced:
        return "rejected", forced["reason"], None
    for pat in PROTECTED:
        if pat.search(ref):
            return "rejected", "protected_branch", None
    for pattern in control("extra_protected.json") or []:
        if re.search(pattern, ref):
            return "rejected", "protected_branch", None
    m = WRITABLE.match(ref)
    if not m:
        return "rejected", "ref_not_allowed", None
    entry = credential_state(token)
    if entry is None:
        return "rejected", "permission_denied", None
    if entry["revoked_ns"] is not None:
        return "rejected", "credential_revoked", entry
    if entry["expires_ns"] <= time.time_ns():
        return "rejected", "credential_expired", entry
    if entry["name"] not in WRITERS or entry["task_id"] != m.group(1):
        return "rejected", "scope_mismatch", entry
    if entry["name"] == "builder_write_credential":
        reason = lease_rejection(entry)
        if reason:
            return "rejected", reason, entry
    return "accepted", "ok", entry


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    token = os.environ.get("RV_PUSH_CREDENTIAL", "")
    lines = [ln.split() for ln in sys.stdin.read().splitlines() if ln.strip()]
    if mode == "post":
        for old, new, ref in lines:
            append("push_log.jsonl", {"ts_ns": time.time_ns(), "event": "applied", "ref": ref, "old": old, "new": new,
                                       "pid": os.getppid()})
        return 0
    rejected = None
    for old, new, ref in lines:
        decision, reason, entry = decide(ref, token)
        append("push_log.jsonl", {
            "ts_ns": time.time_ns(), "event": "pre_receive", "ref": ref, "old": old, "new": new,
            "decision": decision, "reason": reason, "client": os.environ.get("RV_PUSH_CLIENT", ""),
            "credential_name": (entry or {}).get("name"), "task_id": (entry or {}).get("task_id"),
            "lease_id": (entry or {}).get("lease_id")})
        if decision == "rejected" and rejected is None:
            rejected = reason
    if rejected:
        sys.stderr.write(f"RV-REJECT {rejected}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
