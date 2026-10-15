"""Static checks over the daemon sources (done_criteria of T-OP-00). Each returns a list of violations."""
import ast
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE / "core"
FORBIDDEN_IMPORTS = {"socket", "ssl", "urllib", "http", "ftplib", "smtplib", "requests", "subprocess",
                     "asyncio", "multiprocessing", "xmlrpc", "telnetlib", "pty"}
FORBIDDEN_CALLS = {"system", "popen", "execv", "execvp", "execl", "spawnl", "spawnv", "fork", "urlopen"}
# Dynamic code execution and import: the daemon runs only the code that is in its sources.
FORBIDDEN_DYNAMIC_IMPORTS = {"importlib", "runpy", "builtins", "code", "codeop", "imp", "pkgutil"}
FORBIDDEN_DYNAMIC_NAMES = {"eval", "exec", "compile", "__import__"}
_MODEL_WORDS = ["son" + "net", "op" + "us", "hai" + "ku", "fa" + "ble", "gr" + "ok", "g" + "pt", "g" + "lm",
                "dev" + "in", "swe" + "2", "cur" + "sor", "cla" + "ude", "anth" + "ropic", "mist" + "ral", "gem" + "ini"]


RUNNER_VERIFY = HERE / "runner_verify"   # T-OP-09: the real-runner verification tool; it must launch processes, so it has its own checks


def _py_files(root, include_self=False):
    """The checker itself is left out: it has to name the patterns it looks for. So is runner_verify/ (T-OP-09):
    it needs subprocess, time and signal by design, and the mock-daemon rules here do not apply to it."""
    return sorted(p for p in root.rglob("*.py") if (include_self or p.name != "static_checks.py") and RUNNER_VERIFY not in p.parents)


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


def no_network_or_cli(root=HERE):
    """No network, CLI or process launch, and no dynamic code (eval, exec, compile, __import__, importlib ...).

    A bare name is flagged wherever it appears (a call, an alias such as `f = eval`, a default argument), so
    `re.compile` is fine and `compile(...)` is not. `builtins.eval(...)` is caught by the `builtins` import ban."""
    bad = []
    for p in _py_files(root):
        for node in ast.walk(_parse(p)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top in FORBIDDEN_IMPORTS or top in FORBIDDEN_DYNAMIC_IMPORTS:
                        bad.append(f"{p.name}:{node.lineno}: import {a.name}")
            elif isinstance(node, ast.ImportFrom) and node.module and (
                    node.module.split(".")[0] in FORBIDDEN_IMPORTS or node.module.split(".")[0] in FORBIDDEN_DYNAMIC_IMPORTS):
                bad.append(f"{p.name}:{node.lineno}: from {node.module}")
            elif isinstance(node, ast.ImportFrom) and not node.module:
                for a in node.names:  # `from . import importlib` style relative imports
                    if a.name in FORBIDDEN_DYNAMIC_IMPORTS:
                        bad.append(f"{p.name}:{node.lineno}: from . import {a.name}")
            elif isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
                if name in FORBIDDEN_CALLS:
                    bad.append(f"{p.name}:{node.lineno}: call {name}")
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_DYNAMIC_NAMES:
                bad.append(f"{p.name}:{node.lineno}: dynamic code {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in ("__import__", "import_module"):
                bad.append(f"{p.name}:{node.lineno}: dynamic import {node.attr}")
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


def no_scheduler_or_runner():
    """No start-up feature: no scheduler, loop-forever or process launching in the daemon sources."""
    bad = []
    for p in _py_files(HERE):
        src = p.read_text(encoding="utf-8")
        for pat in (r"\bsched\b", r"while True", r"apscheduler", r"cron", r"signal\.signal", r"os\.fork"):
            for m in re.finditer(pat, src):
                bad.append(f"{p.name}: {pat}")
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
