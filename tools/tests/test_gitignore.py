"""Verify the per-tree ignore policy using Git, without real credential contents.

The repository-root `.gitignore` is outside this node's allowed_paths, so the
same four rules are installed at the root of each writable code tree. These
tests read those actual files instead of a copy, and stage empty synthetic files
only in disposable repositories under this worktree's ignored `target/` directory.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TREES = (
    "apps",
    "data",
    "infra",
    "packages/schemas",
    "packages/rules-engine",
    "services",
    "tools",
)
PATTERNS = {".env*", "*.pem", "*.key", ".venv/"}


def git_env():
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


class GitignoreTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "target"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="gitignore-", dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.env = git_env()

    def git(self, cwd, *args, input=None, check=True):
        return subprocess.run(
            ["git", "-c", f"core.excludesFile={os.devnull}", *args],
            cwd=cwd, env=self.env, input=input, text=True,
            capture_output=True, check=check, timeout=15,
        )

    def create_files(self, root, paths):
        for name in paths:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def test_each_writable_tree_declares_the_four_rules(self):
        for tree in TREES:
            with self.subTest(tree=tree):
                path = ROOT / tree / ".gitignore"
                self.assertTrue(path.is_file(), f"{path} must exist")
                rules = {
                    line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.strip().startswith("#")
                }
                self.assertLessEqual(PATTERNS, rules, f"{path} is missing a rule")

    def test_real_repository_ignores_credentials_at_every_depth(self):
        ignored = []
        for tree in TREES:
            ignored += [
                f"{tree}/.env",
                f"{tree}/.env.local",
                f"{tree}/.env.production",
                f"{tree}/.envrc",
                f"{tree}/.env.example",
                f"{tree}/example/.env.test",
                f"{tree}/certificate.pem",
                f"{tree}/nested/certificate.pem",
                f"{tree}/private.key",
                f"{tree}/nested/private.key",
                f"{tree}/.venv/pyvenv.cfg",
                f"{tree}/example/.venv/bin/python",
            ]
        result = self.git(ROOT, "check-ignore", "--no-index", "-z", "--stdin",
                          input="\0".join(ignored) + "\0")
        self.assertEqual(result.stdout.split("\0")[:-1], ignored)

    def test_real_repository_does_not_ignore_near_matches(self):
        controls = []
        for tree in TREES:
            controls += [
                f"{tree}/env.example",
                f"{tree}/example/certificate.pem.txt",
                f"{tree}/example/private.key.example",
                f"{tree}/example/.venv-notes/README.md",
                f"{tree}/example/main.py",
                f"{tree}/.gitignore",
            ]
        result = self.git(ROOT, "check-ignore", "--no-index", "-z", "--stdin",
                          input="\0".join(controls) + "\0", check=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_normal_add_excludes_sensitive_files_and_preserves_other_files(self):
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        self.git(repo, "init", "--quiet")
        controls = []
        ignored = []
        for tree in TREES:
            source = ROOT / tree / ".gitignore"
            target = repo / tree / ".gitignore"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            ignored += [
                f"{tree}/.env",
                f"{tree}/example/.env.test",
                f"{tree}/certificate.pem",
                f"{tree}/nested/private.key",
                f"{tree}/example/.venv/bin/python",
            ]
            controls += [
                f"{tree}/example/main.py",
                f"{tree}/example/env.example",
                f"{tree}/example/certificate.pem.txt",
                f"{tree}/example/private.key.example",
                f"{tree}/example/.venv-notes/README.md",
            ]
        self.create_files(repo, ignored + controls)
        self.git(repo, "add", "--all")
        staged = self.git(repo, "ls-files", "-z").stdout.split("\0")[:-1]
        expected = {f"{tree}/.gitignore" for tree in TREES} | set(controls)
        self.assertEqual(set(staged), expected)


if __name__ == "__main__":
    unittest.main()
