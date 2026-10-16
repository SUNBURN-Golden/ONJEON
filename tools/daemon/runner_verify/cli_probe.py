"""Real vendor CLI probes (05 §1b, R6, R7, R10). A CLI that has a documented way to point at another base URL is
started against the test provider proxy with a dummy key and an isolated home directory, never against a real
provider and never with the user's login. What is kept from its output is only the structured status fields: the
exit code, the HTTP status the CLI reports, the retry events, the CLI's own token and cost figures. The raw output
is not stored (it carries model identifiers and session ids).

A CLI without a confirmed way to reach the proxy is recorded as unconfirmed; this module never guesses one.
"""
import json
import os
import shutil
import subprocess
import time

from .common import PKG_DIR, read_json

TARGETS = read_json(PKG_DIR / "fixtures/cli_targets.json")["targets"]
DUMMY_KEY = "test-key-local"  # a placeholder, accepted by nothing


def target(target_id):
    return next(t for t in TARGETS if t["id"] == target_id)


def find(t):
    return shutil.which(t["command"]) if t.get("command") else None


def version(t):
    """First line of the version output, or None. Only the version is kept."""
    exe = find(t)
    if not exe:
        return None
    try:
        res = subprocess.run([exe] + t["version_args"], capture_output=True, text=True, timeout=30,
                             env={"PATH": os.environ.get("PATH", ""), "HOME": "/nonexistent"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    return (res.stdout.strip().splitlines() or [""])[0][:80] or None


def cli_env(t, base_url, home, max_retries):
    p = t["proxy"]
    env = {"PATH": os.environ.get("PATH", ""), "LANG": os.environ.get("LANG", "C.UTF-8")}
    for name in p["isolate_env"]:
        env[name] = str(home / name.lower())
        os.makedirs(env[name], exist_ok=True)
    env[p["base_url_env"]] = base_url
    env[p["dummy_key_env"]] = DUMMY_KEY
    env[p["retry_env"]] = str(max_retries)
    env.update(p["extra_env"])
    return env


def cli_args(t, prompt="hi"):
    return [find(t)] + [a.replace("{prompt}", prompt) for a in t["proxy"]["args"]]


def parse_stream(text):
    """Structured fields of a stream-json run. Unknown shapes are ignored, nothing else is kept."""
    retries, result = [], None
    for line in text.splitlines():
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") == "system" and row.get("subtype") == "api_retry":
            retries.append({"attempt": row.get("attempt"), "error_status": row.get("error_status"),
                            "error": row.get("error")})
        elif row.get("type") == "result":
            usage = row.get("usage") or {}
            result = {"is_error": row.get("is_error"), "api_error_status": row.get("api_error_status"),
                      "terminal_reason": row.get("terminal_reason"), "num_turns": row.get("num_turns"),
                      "duration_ms": row.get("duration_ms"), "cli_cost_usd": row.get("total_cost_usd"),
                      "cli_input_tokens": usage.get("input_tokens"), "cli_output_tokens": usage.get("output_tokens")}
    return {"retries": retries, "result": result}


def run_once(t, base_url, home, max_retries, timeout=90, cwd=None, extra_args=(), prompt="hi"):
    """Run the CLI to its end. Returns the exit code, the wall time and the structured summary."""
    args = cli_args(t, prompt) + list(extra_args)
    began = time.time()
    try:
        res = subprocess.run(args, env=cli_env(t, base_url, home, max_retries), capture_output=True, text=True,
                             timeout=timeout, cwd=cwd, stdin=subprocess.DEVNULL)
        rc, out = res.returncode, res.stdout
    except subprocess.TimeoutExpired as exc:
        rc, out = "timeout", (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
    summary = parse_stream(out)
    summary["rc"], summary["wall_s"] = rc, round(time.time() - began, 2)
    return summary


# ---------------------------------------------------------------- what the daemon's switch rules make of the channel
def signals_from_stream(retries, result):
    """The switch signals a status-channel adapter may emit for this CLI from its structured output
    (switch_policy.allowed_switch_signals, source provider_http_response):
      429                      -> usage_limit
      401 or 403               -> auth_failure
      >=500 three in a row     -> service_unavailable
    A status that is not one of these emits nothing."""
    out = []
    statuses = [r["error_status"] for r in retries if r.get("error_status")]
    final = (result or {}).get("api_error_status")
    if final:
        statuses = statuses + [final] if not statuses or statuses[-1] != final else statuses
    if 429 in statuses:
        out.append("usage_limit")
    if any(s in (401, 403) for s in statuses):
        out.append("auth_failure")
    run = 0
    for s in statuses:
        run = run + 1 if isinstance(s, int) and s >= 500 else 0
        if run >= 3:
            out.append("service_unavailable")
            break
    return out


def exit_code_row(runs):
    """Fold the runs of one CLI into the §1b row. A code is confirmed as a limit (or unavailable) signal only if it
    appears for that situation and for no other one, including an ordinary failure. Otherwise the profile stays
    empty and the exit code is not a switch basis."""
    by = {}
    for name, rs in runs.items():
        by[name] = sorted({r["rc"] for r in rs if isinstance(r["rc"], int)})
    other = lambda *names: {c for n in by for c in by[n] if n not in names}
    limit = [c for c in by.get("429", []) if c != 0 and c not in other("429")]
    unavailable = [c for c in by.get("503", []) if c != 0 and c not in other("503", "500", "529")]
    return {"codes_by_situation": by, "limit_exit_codes": limit, "unavailable_exit_codes": unavailable,
            "confirmed": bool(limit or unavailable)}
