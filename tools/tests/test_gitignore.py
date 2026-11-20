"""Verify the subtree ignore rules with Git and empty synthetic files."""
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
PATTERNS = {".env*", "*.pem", "*.key", "credentials*", ".aws/", "*.tfstate", ".venv/"}
IGNORED_PATHS = (
    ".env",
    ".env.local",
    ".env.production",
    ".envrc",
    ".env.example",
    "example/.env.test",
    "certificate.pem",
    "example/certificate.pem",
    "private.key",
    "example/private.key",
    "credentials",
    "example/credentials-local.json",
    "example/credentials-cache/config.toml",
    ".aws/config",
    "example/.aws/config",
    "terraform.tfstate",
    "example/terraform.tfstate",
    ".venv/pyvenv.cfg",
    "example/.venv/bin/python",
)
CONTROL_PATHS = (
    "env.example",
    "example/certificate.pem.txt",
    "example/private.key.example",
    "example/sample-credentials.json",
    "example/.aws-notes/README.md",
    "example/standalone/.aws",
    "example/terraform.tfstate.example",
    "example/.venv-notes/README.md",
    "example/main.py",
)


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

    def test_each_tree_declares_the_required_rules(self):
        for tree in TREES:
            with self.subTest(tree=tree):
                path = ROOT / tree / ".gitignore"
                self.assertTrue(path.is_file(), f"{path} must exist")
                rules = {
                    line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.strip().startswith("#")
                }
                self.assertLessEqual(PATTERNS, rules, f"{path} is missing a rule")

    def test_real_repository_ignores_root_and_nested_paths_in_each_tree(self):
        ignored = [f"{tree}/{name}" for tree in TREES for name in IGNORED_PATHS]
        result = self.git(ROOT, "check-ignore", "--no-index", "-z", "--stdin",
                          input="\0".join(ignored) + "\0", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split("\0")[:-1], ignored)

    def test_real_repository_does_not_ignore_near_matches(self):
        controls = [f"{tree}/{name}" for tree in TREES for name in (*CONTROL_PATHS, ".gitignore")]
        result = self.git(ROOT, "check-ignore", "--no-index", "-z", "--stdin",
                          input="\0".join(controls) + "\0", check=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")

    def test_normal_add_excludes_sensitive_files_and_preserves_other_files(self):
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        self.git(repo, "init", "--quiet")
        for tree in TREES:
            source = ROOT / tree / ".gitignore"
            target = repo / tree / ".gitignore"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        ignored = [f"{tree}/{name}" for tree in TREES for name in IGNORED_PATHS]
        controls = [f"{tree}/{name}" for tree in TREES for name in CONTROL_PATHS]
        self.create_files(repo, ignored + controls)
        self.git(repo, "add", "--all")
        staged = self.git(repo, "ls-files", "-z").stdout.split("\0")[:-1]
        expected = {f"{tree}/.gitignore" for tree in TREES} | set(controls)
        self.assertEqual(set(staged), expected)


if __name__ == "__main__":
    unittest.main()
