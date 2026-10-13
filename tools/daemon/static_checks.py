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
_MODEL_WORDS = ["son" + "net", "op" + "us", "hai" + "ku", "fa" + "ble", "gr" + "ok", "g" + "pt", "g" + "lm",
                "dev" + "in", "swe" + "2", "cur" + "sor", "cla" + "ude", "anth" + "ropic", "mist" + "ral", "gem" + "ini"]


def _py_files(root, include_self=False):
    """The checker itself is left out: it has to name the patterns it looks for."""
    return sorted(p for p in root.rglob("*.py") if include_self or p.name != "static_checks.py")


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


def no_network_or_cli():
    bad = []
    for p in _py_files(HERE):
        for node in ast.walk(_parse(p)):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in FORBIDDEN_IMPORTS:
                        bad.append(f"{p.name}:{node.lineno}: import {a.name}")
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                bad.append(f"{p.name}:{node.lineno}: from {node.module}")
            elif isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
                if name in FORBIDDEN_CALLS:
                    bad.append(f"{p.name}:{node.lineno}: call {name}")
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


def rules_issue_only_in_side_effects(rules_raw):
    """No transition side effect or handoff step text increments the generation by itself."""
    bad = []
    for i, tr in enumerate(rules_raw["transitions"]):
        for s in tr.get("side_effects", []):
            if re.search(r"lease_generation\s*(\+=|=\s*lease_generation\s*\+|\+\s*1)", s):
                bad.append(f"transitions[{i}] side_effects increments the generation: {s[:60]}")
            if "issue_lease(" not in s:
                bad.append(f"transitions[{i}] side_effects does not call issue_lease: {s[:60]}")
    for step in rules_raw["switch_policy"]["handoff_steps"]:
        if re.search(r"lease_generation\s*(\+=|=\s*lease_generation\s*\+)", step):
            bad.append(f"handoff step increments the generation: {step[:60]}")
    return bad


def issuing_transitions_call_issue_lease(rules_raw):
    """Every transition that enters `leased`, carries lease_granted, or is the building->building
    re-lease lists issue_lease in side_effects."""
    bad = []
    for i, tr in enumerate(rules_raw["transitions"]):
        issues = tr["to"] == "leased" or tr["event"] == "lease_granted" or (tr["from"] == "building" and tr["to"] == "building" and tr.get("guard"))
        has = any("issue_lease(" in s for s in tr.get("side_effects", []))
        if issues and not has:
            bad.append(f"transitions[{i}] {tr['from']}->{tr['to']} {tr['event']} has no issue_lease side effect")
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
    files = [p for p in HERE.rglob("*") if p.is_file() and p.suffix in (".py", ".json")] + [Path(x) for x in extra_files]
    for p in files:
        text = p.read_text(encoding="utf-8").lower()
        for w in _MODEL_WORDS:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", text):
                bad.append(f"{p.name}: {w}")
    return bad


def all_static(rules_path):
    raw = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    return [
        ("코어가 when·note·_ 키를 읽지 않음", no_natural_language_reads()),
        ("코어에 dry_run·mock 분기 문자열 없음", no_dry_run_branch_in_core()),
        ("병합 API·자동 병합 호출 함수 없음", no_merge_api()),
        ("네트워크·실제 CLI·프로세스 실행 없음", no_network_or_cli()),
        ("벽시계 없음(time·datetime 미사용, 시간은 clock.now()만)", no_wall_clock()),
        ("스케줄러·상주 루프 없음", no_scheduler_or_runner()),
        ("lease_generation은 issue_lease 안에서만 대입", single_lease_generation_writer()),
        ("전이 side_effects·인계 단계에 별도 세대 증가 없음", rules_issue_only_in_side_effects(raw)),
        ("임대 발급 전이는 모두 issue_lease를 부름", issuing_transitions_call_issue_lease(raw)),
        ("다른 해시 정의 없음, 트리 해시는 git_write_tree_oid만", single_tree_identity_function()),
        ("모델 식별자 문자열 없음", no_model_identifiers()),
    ]
