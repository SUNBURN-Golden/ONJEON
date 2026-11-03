"""Static checks over the daemon sources (done_criteria of T-OP-00). Each returns a list of violations."""
import ast
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE / "core"
# Review additions here: unlisted modules/submodules and external members fail closed.
ALLOWED_IMPORTS = {
    "abc": {"ABC", "abstractmethod"},
    "argparse": {"ArgumentParser", "RawDescriptionHelpFormatter"},
    "contextlib": {"contextmanager", "suppress"},
    "copy": {"deepcopy"},
    "fnmatch": {"fnmatch"},
    "hashlib": {"sha1"},
    "json": {"dumps", "loads", "load"},
    "os": {"path"},
    "os.path": {"join"},
    "pathlib": {"Path"},
    "re": {"S", "compile", "fullmatch", "search", "split"},
    "sys": {"exit", "path"},
    "threading": {"Lock", "RLock", "Thread"},
    "traceback": {"format_exc"},
}
ALLOWED_LOCAL_MODULES = {
    "daemon", "daemon.core", "daemon.bench", "daemon.dry_run", "daemon.mock_adapters",
    "daemon.mock_env", "daemon.scenarios", "daemon.scenarios_flow", "daemon.spec_gaps", "daemon.static_checks",
    *("daemon.core." + name for name in (
        "effects", "engine", "envelope_validator", "fencing", "gate_evaluator", "handoff", "lease",
        "observation", "ports", "records", "recovery", "rules", "secret_scan", "transition_engine", "usage")),
}
FORBIDDEN_CALLS = {"system", "popen", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
                   "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
                   "posix_spawn", "posix_spawnp", "fork", "forkpty", "startfile", "urlopen"}
# Dynamic code execution and import: the daemon runs only the code that is in its sources.
FORBIDDEN_DYNAMIC_NAMES = {"eval", "exec", "compile", "__import__", "__builtins__"}
FORBIDDEN_MEMBERS = FORBIDDEN_CALLS | FORBIDDEN_DYNAMIC_NAMES | {"import_module"}
_MODEL_WORDS = ["son" + "net", "op" + "us", "hai" + "ku", "fa" + "ble", "gr" + "ok", "g" + "pt", "g" + "lm",
                "dev" + "in", "swe" + "2", "cur" + "sor", "cla" + "ude", "anth" + "ropic", "mist" + "ral", "gem" + "ini"]


RUNNER_VERIFY = HERE / "runner_verify"   # T-OP-09: the real-runner verification tool; it must launch processes, so it has its own checks


def _py_files(root, include_self=False):
    """Only this exact checker is left out: other files with the same name are checked. So is runner_verify/ (T-OP-09):
    it needs subprocess, time and signal by design, and the mock-daemon rules here do not apply to it."""
    return sorted(p for p in Path(root).rglob("*.py")
                  if (include_self or p.resolve() != Path(__file__).resolve()) and RUNNER_VERIFY not in p.resolve().parents)


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def no_natural_language_reads():
    """The core never reads `when`, `note` or `_`-prefixed keys. Only rules.py names them, to drop them."""
    bad = []
    for p in _py_files(CORE):
        for node in ast.walk(_parse(p)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                if p.name == "rules.py":
                    continue
                if v in ("when", "note") or (v.startswith("_") and not v.startswith("__") and len(v) > 1):
                    bad.append(f"{p.name}:{node.lineno}: string {v!r}")
    rules_src = (CORE / "rules.py").read_text(encoding="utf-8")
    for m in re.finditer(r"""["'](when|note)["']""", rules_src):
        line = rules_src[: m.start()].count("\n") + 1
        text = rules_src.splitlines()[line - 1]
        if "is_banned_key" not in text and "key in" not in text:
            bad.append(f"rules.py:{line}: {text.strip()}")
    return bad


def outside_reads_only_in_observation():
    """Values outside core_contract.reads are reached only through Rules.outside() and only by the observation
    layer; no core module reads the raw file."""
    bad = []
    for p in _py_files(CORE):
        src = p.read_text(encoding="utf-8")
        if p.name not in ("observation.py", "rules.py") and ".outside(" in src:
            bad.append(f"{p.name}: Rules.outside() outside the observation layer")
        if p.name != "rules.py" and re.search(r"\.raw\b", src):
            bad.append(f"{p.name}: reads the raw rules file")
    return bad


def no_dry_run_branch_in_core():
    bad = []
    for p in _py_files(CORE):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"dry[_ -]?run|mock", line, re.I):
                bad.append(f"{p.name}:{i}: {line.strip()}")
    return bad


def no_merge_api():
    bad = []
    for p in _py_files(HERE):
        tree = _parse(p)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "merge" in node.name.lower():
                bad.append(f"{p.name}:{node.lineno}: def {node.name}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(
                    r"merge_pull_request|enable_pr_auto_merge|enable_auto_merge|gh pr merge|/merge\b", node.value):
                bad.append(f"{p.name}:{node.lineno}: {node.value!r}")
    return bad


def _import_module(node, path, root):
    """Resolve relative imports within the checked daemon package, never above it."""
    if not node.level:
        return node.module or ""
    package = ["daemon", *path.relative_to(root).parent.parts]
    if node.level > len(package):
        return ""  # Outside the reviewed package.
    return ".".join(package[:len(package) - node.level + 1] + ([node.module] if node.module else []))


def _references(node, bindings):
    """Resolve import aliases and simple assignment aliases conservatively, across scopes.

    Bindings accumulate rather than trusting reassignment or execution order. This is
    deliberately not general data-flow analysis; returned objects are not module aliases.
    """
    if isinstance(node, ast.Name):
        return bindings.get(node.id, {node.id})
    if isinstance(node, ast.Attribute):
        return {base + "." + node.attr for base in _references(node.value, bindings)}
    if isinstance(node, ast.Call) and "getattr" in _references(node.func, bindings) and len(node.args) >= 2:
        member = node.args[1]
        if isinstance(member, ast.Constant) and isinstance(member.value, str):
            return {base + "." + member.value for base in _references(node.args[0], bindings)}
    return set()


def _module_bindings(tree, path, root):
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings.setdefault(alias.asname or alias.name.split(".")[0], set()).add(
                    alias.name if alias.asname else alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            module = _import_module(node, path, root)
            for alias in node.names:
                bindings.setdefault(alias.asname or alias.name, set()).add(module + "." + alias.name)
    assignments = [node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))]
    # A finite number of passes handles forward aliases without evaluating any source.
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            # Only module objects and getattr need assignment tracking. Avoid
            # expanding arbitrary data expressions or cyclic attribute chains.
            refs = {ref for ref in _references(node.value, bindings)
                    if ref in ALLOWED_IMPORTS or ref == "getattr"}
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and refs:
                    previous = bindings.setdefault(target.id, set())
                    additions = refs - previous
                    if additions:
                        previous.update(additions)
                        changed = True
        if not changed:
            break
    return bindings


def _allowed_import(module, member=None):
    if module in ALLOWED_IMPORTS:
        return member is None or member in ALLOWED_IMPORTS[module]
    if module not in ALLOWED_LOCAL_MODULES:
        return False
    if member is None:
        return True
    if member == "*":
        return False
    if module in {"daemon", "daemon.core"}:
        return module + "." + member in ALLOWED_LOCAL_MODULES or (
            module == "daemon.core" and member in {"DaemonCore", "Rules"})
    return True  # Members of reviewed local source modules are checked in their definitions.


def no_network_or_cli(root=HERE):
    """AST allowlist for imports and external module members, plus dynamic-code guards.

    No imports or calls from checked sources are executed. Unknown imports/members,
    wildcard imports and computed getattr on external modules require policy review.
    Ordinary port/data getattr and re.compile remain allowed. This is not a sandbox.
    """
    bad = []
    root = Path(root)
    for p in _py_files(root):
        tree = _parse(p)
        bindings = _module_bindings(tree, p, root)
        for node in ast.walk(tree):
            reason = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not _allowed_import(alias.name):
                        bad.append(f"{p.name}:{node.lineno}: import not allowed: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = _import_module(node, p, root)
                for alias in node.names:
                    if not _allowed_import(module, alias.name):
                        bad.append(f"{p.name}:{node.lineno}: import not allowed: from {module or '.'} import {alias.name}")
            elif isinstance(node, ast.Attribute):
                for base in _references(node.value, bindings):
                    if base in ALLOWED_IMPORTS and node.attr not in ALLOWED_IMPORTS[base]:
                        reason = f"member not allowed: {base}.{node.attr}"
            elif isinstance(node, ast.Call):
                refs = _references(node.func, bindings)
                if "getattr" in refs and len(node.args) >= 2:
                    member = node.args[1]
                    literal = member.value if isinstance(member, ast.Constant) and isinstance(member.value, str) else None
                    if literal in FORBIDDEN_MEMBERS:
                        reason = f"forbidden getattr {literal}"
                    for base in _references(node.args[0], bindings):
                        if base in ALLOWED_IMPORTS and literal not in ALLOWED_IMPORTS[base]:
                            reason = f"getattr member not allowed: {base}.{literal or '<computed>'}"
                if any(ref.rsplit(".", 1)[-1] in FORBIDDEN_CALLS for ref in refs):
                    reason = "forbidden process call"
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_DYNAMIC_NAMES:
                reason = f"dynamic code {node.id}"
            elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_MEMBERS - {"compile"}:
                reason = f"forbidden member {node.attr}"
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value == "__builtins__":
                reason = "builtins mapping access"
            if reason:
                bad.append(f"{p.name}:{node.lineno}: {reason}")
    return bad


def no_wall_clock():
    """core_contract.clock.rule: every time comparison uses clock.now(); no wall clock."""
    bad = []
    for p in _py_files(HERE):
        for node in ast.walk(_parse(p)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in ("time", "datetime", "sched"):
                        bad.append(f"{p.name}:{node.lineno}: import {a.name}")
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in ("time", "datetime", "sched"):
                bad.append(f"{p.name}:{node.lineno}: from {node.module}")
    return bad


def no_scheduler_or_runner(root=HERE):
    """No start-up feature: no scheduler, loop-forever or process launching in the daemon sources."""
    bad = []
    for p in _py_files(root):
        src = p.read_text(encoding="utf-8")
        for pat in (r"\bsched\b", r"apscheduler", r"cron", r"signal\.signal", r"os\.fork"):
            for m in re.finditer(pat, src):
                bad.append(f"{p.name}: {pat}")
        for node in ast.walk(_parse(p)):
            if isinstance(node, ast.While):
                try:
                    always_true = bool(ast.literal_eval(node.test))
                except (ValueError, TypeError):
                    always_true = False  # Input-dependent loops are permitted; no source code is executed.
                if always_true:
                    bad.append(f"{p.name}:{node.lineno}: while with truthy literal condition")
    return bad


def single_lease_generation_writer():
    """lease_generation is assigned only inside the function issue_lease (concurrency.lease_issue.sole_owner)."""
    bad = []
    for p in _py_files(HERE):
        tree = _parse(p)

        def visit(node, fn):
            for child in ast.iter_child_nodes(node):
                cur = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
                targets = []
                if isinstance(child, ast.Assign):
                    targets = child.targets
                elif isinstance(child, (ast.AugAssign, ast.AnnAssign)):
                    targets = [child.target]
                for tg in targets:
                    for sub in ast.walk(tg):
                        key = None
                        if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Constant):
                            key = sub.slice.value
                        elif isinstance(sub, ast.Attribute):
                            key = sub.attr
                        if key == "lease_generation" and cur != "issue_lease":
                            bad.append(f"{p.name}:{child.lineno}: lease_generation assigned in {cur or 'module'}")
                visit(child, cur)

        visit(tree, None)
    return bad


def _increments_generation(eff):
    return eff.get("id") == "increment_counter" and (eff.get("args") or {}).get("field") == "lease_generation"


def rules_issue_only_in_side_effects(rules_raw):
    """No transition side effect or handoff step text increments the generation by itself; the only
    increment is in issue_lease.effects_atomic."""
    bad = []
    for i, tr in enumerate(rules_raw["transitions"]):
        for eff in tr.get("side_effects", []):
            if _increments_generation(eff):
                bad.append(f"transitions[{i}] side_effects increments the generation")
    atomic = rules_raw["core_contract"]["operations"]["issue_lease"]["effects_atomic"]
    if sum(1 for eff in atomic if _increments_generation(eff)) != 1:
        bad.append("issue_lease.effects_atomic does not increment lease_generation exactly once")
    for step in rules_raw["switch_policy"]["handoff_steps"]:
        if re.search(r"lease_generation\s*(\+=|=\s*lease_generation\s*\+)", step):
            bad.append(f"handoff step increments the generation: {step[:60]}")
    return bad


def issuing_transitions_call_issue_lease(rules_raw):
    """Every transition that enters `leased`, carries lease_granted, or is the building->building re-lease
    lists issue_lease (with a reason) in side_effects."""
    bad = []
    for i, tr in enumerate(rules_raw["transitions"]):
        issues = tr["to"] == "leased" or tr["event"] == "lease_granted" or (tr["from"] == "building" and tr["to"] == "building" and tr.get("guard"))
        calls = [e for e in tr.get("side_effects", []) if e.get("id") == "issue_lease"]
        if issues and not calls:
            bad.append(f"transitions[{i}] {tr['from']}->{tr['to']} {tr['event']} has no issue_lease side effect")
        for c in calls:
            if (c.get("args") or {}).get("reason") not in rules_raw["concurrency"]["lease_issue"]["reasons"]:
                bad.append(f"transitions[{i}] issue_lease reason {(c.get('args') or {}).get('reason')!r} is not in lease_issue.reasons")
    return bad


def no_cost_cap(rules_raw=None, tasks_path=None):
    """U-05: no budget reservation or exhaustion stop. Core sources, mock files and the rule fields that decide
    behavior (events, transitions, lease_guards, instruction required list, hard_stop.trigger) name none."""
    bad = []
    for p in _py_files(CORE):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(?:budget|reserv|exhaust|cost_cap|max_cost|max_calls)", line, re.I):
                bad.append(f"core/{p.name}:{i}: {line.strip()}")
    if tasks_path is not None:
        text = Path(tasks_path).read_text(encoding="utf-8")
        for m in re.finditer(r'"(budget[a-z_]*|max_cost[a-z_]*|max_calls)"', text):
            bad.append(f"{Path(tasks_path).name}: {m.group(0)}")
    if rules_raw is not None:
        names = list(rules_raw["events"]) + [t["event"] for t in rules_raw["transitions"]] \
            + [g["id"] for g in rules_raw["lease_guards"]] + list(rules_raw["envelopes"]["instruction"]["required"]) \
            + list(rules_raw["hard_stop"]["trigger"])
        for n in names:
            if re.search(r"\b(?:budget|exhaust|reserv)", n, re.I):
                bad.append(f"rules: {n}")
        if "usage_recording" not in rules_raw:
            bad.append("rules: usage_recording is missing")
        if "limits" not in rules_raw["envelopes"]["instruction"]["required"]:
            bad.append("rules: envelopes.instruction.required has no limits")
    return bad


def single_tree_identity_function():
    """No second hash definition: no sha256 etc., and tree hashing is only called from git_write_tree_oid."""
    bad = []
    for p in _py_files(HERE):
        src = p.read_text(encoding="utf-8")
        for pat in (r"sha256", r"sha512", r"blake2", r"md5", r"crc32"):
            if re.search(pat, src):
                bad.append(f"{p.name}: {pat}")
        tree = _parse(p)

        def visit(node, fn):
            for child in ast.iter_child_nodes(node):
                cur = child.name if isinstance(child, ast.FunctionDef) else fn
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "_hash" \
                        and cur != "git_write_tree_oid":
                    bad.append(f"{p.name}:{child.lineno}: _hash called from {cur}")
                visit(child, cur)

        visit(tree, None)
    for p in _py_files(CORE):
        if "hashlib" in p.read_text(encoding="utf-8"):
            bad.append(f"core/{p.name}: hashlib in the core")
    return bad


def no_model_identifiers(extra_files=()):
    bad = []
    files = [p for p in HERE.rglob("*") if p.is_file() and p.suffix in (".py", ".json") and RUNNER_VERIFY not in p.parents] + [Path(x) for x in extra_files]
    for p in files:
        text = p.read_text(encoding="utf-8").lower()
        for w in _MODEL_WORDS:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text):
                bad.append(f"{p.name}: {w}")
    return bad


def all_static(rules_path, tasks_path=None):
    raw = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    tasks_path = tasks_path or HERE / "mock_tasks.json"
    return [
        ("코어가 when·note·_ 키를 읽지 않음", no_natural_language_reads()),
        ("읽기 목록 밖 값은 관측 계층의 Rules.outside()로만", outside_reads_only_in_observation()),
        ("코어에 dry_run·mock 분기 문자열 없음", no_dry_run_branch_in_core()),
        ("병합 API·자동 병합 호출 함수 없음", no_merge_api()),
        ("네트워크·실제 CLI·프로세스 실행·동적 코드 실행(eval·exec·compile·__import__·importlib) 없음", no_network_or_cli()),
        ("벽시계 없음(time·datetime 미사용, 시간은 clock.now()만)", no_wall_clock()),
        ("스케줄러·상주 루프 없음", no_scheduler_or_runner()),
        ("lease_generation은 issue_lease 안에서만 대입", single_lease_generation_writer()),
        ("전이 side_effects·인계 단계에 별도 세대 증가 없음", rules_issue_only_in_side_effects(raw)),
        ("임대 발급 전이는 모두 issue_lease를 부름", issuing_transitions_call_issue_lease(raw)),
        ("다른 해시 정의 없음, 트리 해시는 git_write_tree_oid만", single_tree_identity_function()),
        ("비용 상한·예산 예약·소진 정지 표현 없음(코어·모의 과제·규칙의 동작 필드)", no_cost_cap(raw, tasks_path)),
        ("모델 식별자 문자열 없음", no_model_identifiers()),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, default=HERE.parents[1] / "docs/blueprint/proposals/설계검토_결과/daemon_rules.json")
    parser.add_argument("--tasks", type=Path, default=HERE / "mock_tasks.json")
    args = parser.parse_args(argv)
    try:
        checks = all_static(args.rules, args.tasks)
    except (OSError, UnicodeError, SyntaxError, ValueError, KeyError, TypeError) as exc:
        print(f"[ERROR] static checks could not complete: {exc}", file=sys.stderr)
        return 2
    for name, violations in checks:
        print(f"[{'FAIL' if violations else 'PASS'}] {name}")
        for violation in violations:
            print(f"  {violation}")
    failed = sum(bool(violations) for _name, violations in checks)
    print(f"Checks: {len(checks)}, failed: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
