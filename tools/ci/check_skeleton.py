#!/usr/bin/env python3
"""Skeleton flag and non-exposure check (Part 3 section 58). Flags: packages/schemas/feature_flags.json.

Static checks (always):
  SKEL-FLAGS-FILE      the flags file is malformed, a required skeleton flag is missing, or ids repeat
  SKEL-FLAG-ON         a skeleton flag defaults to anything but false
  SKEL-GATE            a skeleton flag names no enable gate
  SKEL-ENABLED-CONFIG  a config file (compose, yaml, toml, env, shell) switches a skeleton flag on
  SKEL-EXPOSED-UI      app code references a skeleton flag or an inactive skeleton route (dead UI)
Runtime check (only with --base-url, against a running server):
  SKEL-ROUTE-LIVE      an inactive skeleton route answers with a status outside inactive_response.statuses

The runtime check is what the template tools/ci/templates/test_skeleton_unexposed.py.tmpl wires
into a task's own test suite. Running this script without --base-url proves the static part only;
it does not prove that any server is actually quiet.

Usage:
  python3 -I tools/ci/check_skeleton.py [--root DIR] [--rules FILE] [--flags FILE] [--base-url URL]
  python3 -I tools/ci/check_skeleton.py --selftest
Exit: 0 clean, 1 findings, 2 usage or unreadable input.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_common as C  # noqa: E402

FLAG_ID = re.compile(r"^[a-z][a-z0-9_]*_enabled$")
UI_EXT = {".ts", ".tsx", ".js", ".jsx", ".dart", ".json", ".yaml", ".yml", ".html"}


def check_flags(flags, required):
    out, seen = [], set()
    where = "packages/schemas/feature_flags.json"
    if not isinstance(flags.get("flags"), list) or not isinstance(flags.get("inactive_response", {}).get("statuses"), list):
        return [C.Finding("SKEL-FLAGS-FILE", where, 0, "needs a 'flags' list and inactive_response.statuses")]
    for f in flags["flags"]:
        fid = f.get("id", "")
        if not FLAG_ID.match(fid) or fid in seen:
            out.append(C.Finding("SKEL-FLAGS-FILE", where, 0, f"flag id '{fid}' is malformed or repeated"))
        seen.add(fid)
        if f.get("skeleton") is not True or "default" not in f:
            out.append(C.Finding("SKEL-FLAGS-FILE", where, 0, f"'{fid}' must declare skeleton:true and a default"))
        elif f["default"] is not False:
            out.append(C.Finding("SKEL-FLAG-ON", where, 0, f"skeleton flag '{fid}' defaults to {f['default']!r}; it must be false (58.1)"))
        if not str(f.get("enable_gate", "")).strip():
            out.append(C.Finding("SKEL-GATE", where, 0, f"skeleton flag '{fid}' names no enable gate"))
        for r in f.get("inactive_routes", []):
            if not str(r.get("path", "")).startswith("/") or not r.get("method"):
                out.append(C.Finding("SKEL-FLAGS-FILE", where, 0, f"'{fid}' has a route without method or absolute path: {r}"))
    for fid in required:
        if fid not in seen:
            out.append(C.Finding("SKEL-FLAGS-FILE", where, 0, f"required skeleton flag '{fid}' is missing"))
    return out


def check_tree(root, rules, flags):
    S = rules["skeleton"]
    out = []
    ids = [f["id"] for f in flags["flags"] if "id" in f]
    paths = sorted({r["path"] for f in flags["flags"] for r in f.get("inactive_routes", [])})
    id_re = re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, ids)) + r")(?![A-Za-z0-9_])") if ids else None
    on_re = (re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(map(re.escape, ids)) + r")[\"']?\s*[:=]\s*[\"']?(?:true|1|on|yes)\b", re.I)) if ids else None
    route_re = re.compile(r"""["'`](?:%s)(?:["'`/?$]|\{)""" % "|".join(map(re.escape, paths))) if paths else None
    cfg_ext = set(S["config_extensions"])
    for rel, full in C.iter_files(root, rules["scan"]["ignore"] + S["config_ignore"], None):
        text = C.read_text(full)
        if text is None:
            continue
        if (full.suffix in cfg_ext or full.name.startswith(".env")) and on_re:
            for n, line in enumerate(text.splitlines(), 1):
                m = on_re.search(line)
                if m:
                    out.append(C.Finding("SKEL-ENABLED-CONFIG", rel, n, f"switches skeleton flag '{m.group(1)}' on; turning one on is a separate decision (58.1)"))
        if C.match(rel, S["ui_globs"]) and full.suffix in UI_EXT:
            for n, line in enumerate(text.splitlines(), 1):
                hit = (id_re.search(line) if id_re else None) or (route_re.search(line) if route_re else None)
                if hit:
                    out.append(C.Finding("SKEL-EXPOSED-UI", rel, n, f"app code references skeleton '{hit.group(0).strip(chr(34) + chr(39) + chr(96))}'; screens, navigation and web pages must not expose skeletons (58.1)"))
    return out


def http_status(method, url, timeout=5):
    req = urllib.request.Request(url, method=method, data=b"{}" if method in ("POST", "PUT", "PATCH") else None, headers={"Content-Type": "application/json"})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError) as e:
        return f"unreachable: {e}"


def probe_routes(base_url, flags, fetch=http_status):
    """Hit every inactive skeleton route. An unreachable server is a finding, not a pass."""
    allowed = set(flags["inactive_response"]["statuses"])
    out = []
    for f in flags["flags"]:
        for r in f.get("inactive_routes", []):
            status = fetch(r["method"], base_url.rstrip("/") + r["path"])
            if status not in allowed:
                out.append(C.Finding("SKEL-ROUTE-LIVE", f"{r['method']} {r['path']}", 0, f"answered {status}; flag '{f['id']}' is off so it must answer one of {sorted(allowed)}"))
    return out


def probe_ui_routes(ui_routes, flags):
    """ui_routes: paths the app or web build registers (navigation, router, sitemap)."""
    paths = [r["path"] for f in flags["flags"] for r in f.get("inactive_routes", [])]
    out = []
    for route in ui_routes:
        for p in paths:
            if route == p or route.startswith(p.rstrip("/") + "/"):
                out.append(C.Finding("SKEL-EXPOSED-UI", route, 0, f"UI route exposes skeleton path '{p}'"))
    return out


def check(root, rules, flags, base_url=None, fetch=http_status):
    findings = check_flags(flags, rules["skeleton"]["required_flags"])
    if not any(f.rule == "SKEL-FLAGS-FILE" for f in findings):
        findings += check_tree(root, rules, flags)
        if base_url:
            findings += probe_routes(base_url, flags, fetch)
    return findings


# ---------- selftest ----------
def selftest():
    import copy

    rules = C.load_rules()
    good = C.load_json(C.FLAGS_PATH)

    def mutate(fn):
        f = copy.deepcopy(good)
        fn(f)
        return f

    def runner_for(flags, base_url=None, fetch=None):
        return lambda root: check(root, rules, flags, base_url, fetch or http_status)

    cases = []  # (name, flags, files, expected, base_url, fetch)
    ok_fetch = lambda m, u: 404  # noqa: E731
    live_fetch = lambda m, u: 200  # noqa: E731
    cases.append(("shipped flags file is clean", good, {"apps/web/src/a.ts": "const x = 1;\n"}, None, None, None))
    cases.append(("a flag defaulting to true", mutate(lambda f: f["flags"][0].update(default=True)), {}, "SKEL-FLAG-ON", None, None))
    cases.append(("a flag with a string default", mutate(lambda f: f["flags"][0].update(default="false")), {}, "SKEL-FLAG-ON", None, None))
    cases.append(("a required flag removed", mutate(lambda f: f["flags"].pop()), {}, "SKEL-FLAGS-FILE", None, None))
    cases.append(("a flag without an enable gate", mutate(lambda f: f["flags"][1].update(enable_gate=" ")), {}, "SKEL-GATE", None, None))
    cases.append(("a flag that is not marked skeleton", mutate(lambda f: f["flags"][1].update(skeleton=False)), {}, "SKEL-FLAGS-FILE", None, None))
    cases.append(("compose file switches a flag on", good, {"infra/compose/env.yaml": "consultation_enabled: true\n"}, "SKEL-ENABLED-CONFIG", None, None))
    cases.append(("env file switches a flag on", good, {"deploy/.env": "quotes_enabled=1\n"}, "SKEL-ENABLED-CONFIG", None, None))
    cases.append(("a flag set to false in config passes", good, {"infra/compose/env.yaml": "consultation_enabled: false\n"}, None, None, None))
    cases.append(("web page links a skeleton route", good, {"apps/web/src/nav.tsx": "<Link href=\"/agent\">Agents</Link>\n"}, "SKEL-EXPOSED-UI", None, None))
    cases.append(("app code calls the consultation route", good, {"apps/mobile/lib/c.dart": "post('/consultation-requests', body);\n"}, "SKEL-EXPOSED-UI", None, None))
    cases.append(("app code reads a skeleton flag", good, {"apps/web/src/f.ts": "if (flags.agent_portal_enabled) show();\n"}, "SKEL-EXPOSED-UI", None, None))
    cases.append(("an unrelated '/agents-guide' string is not the skeleton route", good, {"apps/web/src/a.ts": "const p = '/agents-guide';\n"}, None, None, None))
    cases.append(("inactive route answers 404", good, {}, None, "http://x", ok_fetch))
    cases.append(("inactive route answers 200", good, {}, "SKEL-ROUTE-LIVE", "http://x", live_fetch))
    cases.append(("inactive route answers 401 (exists behind auth)", good, {}, "SKEL-ROUTE-LIVE", "http://x", lambda m, u: 401))
    cases.append(("server unreachable is not a pass", good, {}, "SKEL-ROUTE-LIVE", "http://x", lambda m, u: "unreachable: refused"))

    bad = []
    for name, flags, files, expected, base_url, fetch in cases:
        runner = runner_for(flags, base_url, fetch)
        code = C.run_selftest("skeleton-case", [(name, files, expected)], runner, quiet=True)
        if code:
            bad.append(name)
    # UI route table template helper
    if not probe_ui_routes(["/agent/home"], good) or probe_ui_routes(["/coverage", "/legal"], good):
        bad.append("probe_ui_routes")
    if bad:
        print(f"check_skeleton selftest failed: {bad}")
        return 1
    print(f"check_skeleton selftest ok: {sum(1 for c in cases if c[3])} violations each caught for its intended rule, {sum(1 for c in cases if not c[3])} clean case(s) pass")
    return 0


def main(argv):
    args = argv[1:]
    if args == ["--selftest"]:
        return selftest()
    root, rules_path, flags_path, base_url = C.ROOT, C.RULES_PATH, C.FLAGS_PATH, None
    while args:
        flag = args.pop(0)
        if flag == "--root" and args:
            root = Path(args.pop(0))
        elif flag == "--rules" and args:
            rules_path = Path(args.pop(0))
        elif flag == "--flags" and args:
            flags_path = Path(args.pop(0))
        elif flag == "--base-url" and args:
            base_url = args.pop(0)
        else:
            return C.usage_error(__doc__.split("Usage:")[1].strip())
    try:
        rules, flags = C.load_rules(rules_path), C.load_json(flags_path)
    except (OSError, ValueError) as e:
        return C.usage_error(f"cannot read input: {e}")
    ok = "skeleton flags off, no exposure (static)" + (" and inactive routes answer as required" if base_url else "; runtime routes not probed")
    return C.report(check(root, rules, flags, base_url), ok, "check_skeleton")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
