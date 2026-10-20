import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "services/collect/evidence"
COMMANDS = [
    ["cargo", "fmt", "-p", "onjeon-collect", "--", "--check"],
    ["cargo", "clippy", "-p", "onjeon-collect", "--all-targets", "--", "-D", "warnings"],
    ["cargo", "test", "-p", "onjeon-collect", "adapters"],
    ["cargo", "test", "--workspace"],
    ["cargo", "build", "-p", "onjeon-collect"],
    ["python3", "-m", "unittest", "discover", "-s", "services/collect/tests", "-p", "test_*.py", "-v"],
    ["python3", "-m", "unittest", "discover", "-s", "tools/tests", "-v"],
    ["python3", "-I", "tools/ci/check_deps.py"],
    ["python3", "-I", "tools/ci/check_leak.py"],
    ["python3", "-I", "tools/ci/check_leak.py", "--selftest"],
    ["python3", "-I", "tools/ci/check_skeleton.py"],
    ["python3", "-I", "tools/ci/check_skeleton.py", "--selftest"],
]


def main():
    results = []
    for index, command in enumerate(COMMANDS):
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = result.stdout.decode(errors="replace").replace(str(ROOT), "<worktree>")
        name = f"verification-{index:02d}.log"
        (EVIDENCE / name).write_text("$ " + " ".join(command) + "\n" + text + f"\nexit_code={result.returncode}\n")
        results.append({"command": command, "exit_code": result.returncode, "log": name})
        print(f"exit={result.returncode}: {' '.join(command)}", flush=True)
    files = [ROOT / "Cargo.toml", ROOT / "Cargo.lock"] + sorted((ROOT / "services/collect").rglob("*.rs")) + sorted((ROOT / "services/collect/tests").glob("*.py")) + [ROOT / "services/collect/Cargo.toml"]
    manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (EVIDENCE / "verification.json").write_text(json.dumps({"task_id": "T-DT-04", "base_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "files_sha256": manifest, "results": results}, indent=2) + "\n")
    return int(any(r["exit_code"] for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
