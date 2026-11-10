"""Audit 5: reject tracked credential and virtual-environment paths repo-wide.

The live-tree test runs the same command as the early CI step. Synthetic
mutations stay in temporary Git repositories under this worktree's ignored
`target/` directory and contain no credential values.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/check_tracked_secrets.py"
sys.path.insert(0, str(ROOT / "tools"))
import check_tracked_secrets as gate  # noqa: E402


def git_env():
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


class ViolationRules(unittest.TestCase):
    def test_flags_each_kind_at_root_and_nested_depths(self):
        cases = [
            (".env", "environment file"),
            (".env.local", "environment file"),
            (".envrc", "environment file"),
            ("services/collect/.env.production", "environment file"),
            ("certificate.pem", "PEM file"),
            ("infra/compose/server.pem", "PEM file"),
            ("private.key", "key file"),
            ("services/app/config/private.key", "key file"),
            (".venv/pyvenv.cfg", "virtual environment"),
            ("services/app/.venv/bin/python", "virtual environment"),
        ]
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(gate.violations([path]), [(path, expected)])

    def test_accepts_ordinary_files_and_near_matches(self):
        paths = [
            "README.md",
            "services/app/env.example",
            "services/app/certificate.pem.txt",
            "services/app/private.key.example",
            "services/app/.venv-notes/README.md",
            "infra/compose/docker-compose.yml",
        ]
        self.assertEqual(gate.violations(paths), [])

    def test_only_the_checked_in_placeholder_template_is_allowed(self):
        self.assertEqual(gate.violations(["infra/compose/.env.example"]), [])
        self.assertTrue(gate.violations(["services/app/.env.example"]))
        self.assertTrue(gate.violations(["infra/compose/.env.example.bak"]))

    def test_selftest_passes(self):
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--selftest"],
            cwd=ROOT, env=git_env(), capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TrackedTreeCheck(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "target"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="tracked-secrets-", dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.env = git_env()

    def run_check(self, repo):
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--root", str(repo)],
            cwd=repo, env=self.env, capture_output=True, text=True, timeout=30,
        )

    def test_live_tree_is_clean(self):
        result = self.run_check(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ok", result.stdout)

    def test_clean_repository_exits_zero(self):
        repo = Path(self.tmp.name) / "clean"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=repo, env=self.env,
                       check=True, timeout=15)
        (repo / "README.md").write_text("ok\n", encoding="utf-8")
        subprocess.run(["git", "add", "--all"], cwd=repo, env=self.env,
                       check=True, timeout=15)
        result = self.run_check(repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tracked_sensitive_paths_exit_one(self):
        repo = Path(self.tmp.name) / "dirty"
        repo.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=repo, env=self.env,
                       check=True, timeout=15)
        paths = [".env", "services/app/certificate.pem",
                 "services/app/private.key", ".venv/pyvenv.cfg"]
        for name in paths:
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        subprocess.run(["git", "add", "--all"], cwd=repo, env=self.env,
                       check=True, timeout=15)
        result = self.run_check(repo)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for name in paths:
            self.assertIn(name, result.stdout)

    def test_ci_runs_the_gate_before_dependency_install(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("run: python3 -I tools/check_tracked_secrets.py", workflow)


if __name__ == "__main__":
    unittest.main()
