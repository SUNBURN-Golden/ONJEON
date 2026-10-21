"""Static and log checks of the verification tool itself (T-OP-09 done criteria): no write to a product branch and no
merge, no secret or model identifier in sources and outputs, fixtures marked as fixtures, one place that computes a tree
identity, runner_profile limited to confirmed values. Each check returns a list of violations."""
import ast
import json
import re
import subprocess
from pathlib import Path

from .common import PKG_DIR, ROOT, read_json

SELF = Path(__file__).name
MERGE_STR = re.compile(r"merge_pull_request|enable_pr_auto_merge|enable_auto_merge|gh pr merge|/merge\b|git merge|\"merge\"|'merge'")
# the shape of a model identifier: a family word followed by a version number
MODEL_ID = re.compile(r"\b(?:claude|gpt|glm|grok|gemini|swe|sonnet|opus|haiku|fable)[-_ ]?\d", re.I)
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)


def sources():
    """Tool code. The tests hold strings that the checks look for (URLs to refuse, secret shapes) and are scanned
    separately for secrets and model identifiers only."""
    return sorted(p for p in PKG_DIR.rglob("*.py") if p.name != SELF and "__pycache__" not in p.parts and "tests" not in p.parts)


def test_sources():
    return sorted((PKG_DIR / "tests").glob("*.py"))


def fixtures():
    return sorted((PKG_DIR / "fixtures").glob("*.json"))


def no_merge_api():
    """No function named merge, no merge API string, no `gh` or hosting API call: this tool never merges and never
    talks to a hosting service."""
    bad = []
    for p in sources():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and "merge" in node.name.lower():
                bad.append(f"{p.name}:{node.lineno}: def {node.name}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if MERGE_STR.search(node.value):
                    bad.append(f"{p.name}:{node.lineno}: {node.value[:50]!r}")
                if node.value in ("gh", "hub") or re.search(r"api\.github|github\.com|https://", node.value):
                    bad.append(f"{p.name}:{node.lineno}: hosting service {node.value[:40]!r}")
    return bad


def product_repo_only_read():
    """The product repository's location (ROOT) is used only to refuse it as a remote, to read its state before and
    after the run, and to find files. No source passes it to git as a place to run push, commit, merge or checkout."""
    bad = []
    allowed = {"remote.py", "cli.py", "common.py", "reporting.py", "context.py", "__init__.py"}
    for p in sources():
        src = p.read_text(encoding="utf-8")
        if p.name in allowed or p.parent.name == "tests":
            continue
        if re.search(r"\bROOT\b", src):
            bad.append(f"{p.name}: uses ROOT")
    return bad


def push_targets():
    """Every `git push` in the sources goes to a variable (the test remote of the state directory), never to a
    literal URL, `origin` of the product repository, or a path inside it."""
    bad = []
    for p in sources():
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "push":
                for e in node.elts[1:]:
                    if isinstance(e, ast.Constant) and isinstance(e.value, str) and not e.value.startswith("-") and not e.value.startswith("refs/") \
                            and not re.match(r"^HEAD:refs/heads/task/T-MOCK-", e.value):
                        bad.append(f"{p.name}:{node.lineno}: push target literal {e.value!r}")
    return bad


def secrets_absent(rules_path, extra_texts=()):
    pats = [re.compile(x) for x in read_json(rules_path)["preserve_manifest"]["secret_patterns"]["patterns"]]
    bad = []
    texts = [(p.name, p.read_text(encoding="utf-8")) for p in sources() + test_sources() + fixtures()] + list(extra_texts)
    for name, text in texts:
        for pat in pats:
            if pat.search(text):
                bad.append(f"{name}: secret pattern {pat.pattern[:24]!r}")
    return bad


def no_model_identifiers(extra_texts=()):
    bad = []
    texts = [(p.name, p.read_text(encoding="utf-8")) for p in sources() + test_sources() + fixtures()] + list(extra_texts)
    for name, text in texts:
        m = MODEL_ID.search(text)
        if m:
            line = text[: m.start()].count("\n") + 1
            bad.append(f"{name}:{line}: {m.group(0)!r}")
    return bad


def fixtures_marked():
    bad = []
    for p in fixtures():
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("origin") != "fixture" or d.get("fixture_only") is not True:
            bad.append(f"{p.name}: not marked origin=fixture, fixture_only=true")
    return bad


def single_tree_identity():
    """The tree identity (git write-tree) is computed in one function of the Git adapter."""
    bad = []
    for p in sources():
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and node.value == "write-tree":
                bad.append(p.name)
    if bad != ["adapters.py"]:
        return [f"write-tree appears in {bad}, expected only adapters.py (RealGit._staged)"]
    return []


def no_leak_in_outputs(text):
    """Raw CLI output carries session ids and user paths; none of it may reach a result file."""
    bad = []
    if UUID.search(text):
        bad.append("uuid in output")
    for needle in ("session_id", "/home/", "modelUsage", "api_key=", "Authorization"):
        if needle in text:
            bad.append(f"{needle!r} in output")
    return bad


def runner_profile_confirmed_only(profile):
    """A CLI's exit codes are in the profile only if the table says they were confirmed."""
    bad = []
    for runner, row in profile.items():
        if (row["limit_exit_codes"] or row["unavailable_exit_codes"]) and not row.get("confirmed"):
            bad.append(f"{runner}: exit codes without confirmation")
    return bad


def product_repo_state():
    """Branches, HEAD and the remotes of the product repository (read only)."""
    def git(*a):
        return subprocess.run(["git", "-C", str(ROOT)] + list(a), capture_output=True, text=True).stdout

    return {"head": git("rev-parse", "HEAD").strip(), "refs": git("for-each-ref", "--format=%(refname) %(objectname)").strip(),
            "remotes": git("remote", "-v").strip()}


def all_static(rules_path):
    return [
        ("병합 API·호스팅 서비스 호출 없음", no_merge_api()),
        ("제품 저장소 경로(ROOT)는 거부·읽기에만 쓴다", product_repo_only_read()),
        ("git push 대상이 리터럴 주소·제품 원격이 아니다", push_targets()),
        ("비밀값 패턴 없음(소스·fixture)", secrets_absent(rules_path)),
        ("모델 식별자 모양 없음(소스·fixture)", no_model_identifiers()),
        ("fixture는 origin=fixture, fixture_only=true", fixtures_marked()),
        ("트리 해시(write-tree)는 Git 어댑터 한 곳", single_tree_identity()),
    ]
