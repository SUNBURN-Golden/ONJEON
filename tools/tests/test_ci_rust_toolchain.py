"""Workspace Cargo must work with CI's pin and no rustup global default."""
import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "docs/blueprint/proposals/온톨로지/검증/runner"


def ci_toolchain():
    # The workflow uses a block-style, workflow-level env mapping.
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    env, = re.findall(r'(?m)^env:\n((?:  [^\n]*\n)+)', workflow)
    channel, = re.findall(r'(?m)^  RUSTUP_TOOLCHAIN: "([0-9]+\.[0-9]+\.[0-9]+)"$', env)
    return channel


@contextlib.contextmanager
def isolated_rustup(channel):
    installed = subprocess.run(
        ["rustup", "which", "--toolchain", channel, "rustc"], cwd=ROOT,
        capture_output=True, text=True, check=True, timeout=30,
    )
    toolchain = Path(installed.stdout.strip()).parent.parent
    (ROOT / "target").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "target") as directory:
        home = Path(directory)
        (home / "toolchains").mkdir()
        (home / "toolchains" / toolchain.name).symlink_to(toolchain, target_is_directory=True)
        env = dict(os.environ, RUSTUP_HOME=str(home))
        env.pop("RUSTUP_TOOLCHAIN", None)
        yield home, env


class CiRustToolchain(unittest.TestCase):
    def test_ci_build_lint_and_test_commands_use_the_lockfile(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        commands = re.findall(r'(?m)^\s+run: (cargo (?:build|clippy|test)\b[^\n]*)', workflow)
        self.assertEqual(len(commands), 5)  # two runner builds, runner test, workspace lint/test
        for command in commands:
            with self.subTest(command=command):
                self.assertIn("--locked", command.split())

    def test_workspace_and_runner_select_the_same_toolchain(self):
        pin = (RUNNER / "rust-toolchain.toml").read_text(encoding="utf-8")
        channel, = re.findall(r'(?m)^channel = "([^"]+)"$', pin)
        self.assertEqual(ci_toolchain(), channel)

    @unittest.skipUnless(shutil.which("rustup") and shutil.which("cargo"), "Rust tools not installed")
    def test_root_cargo_with_ci_pin_and_no_global_default(self):
        channel = ci_toolchain()
        with isolated_rustup(channel) as (_, env):
            # An isolated rustup home has the installed toolchain but no default.
            missing = subprocess.run(["cargo", "--version"], cwd=ROOT, env=env,
                                     capture_output=True, text=True, timeout=30)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("no default is configured", missing.stderr)
            env["RUSTUP_TOOLCHAIN"] = channel
            result = subprocess.run(
                ["cargo", "metadata", "--no-deps", "--format-version=1", "--locked", "--offline"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(json.loads(result.stdout)["workspace_root"]), ROOT)

    @unittest.skipUnless(shutil.which("rustup") and shutil.which("cargo"), "Rust tools not installed")
    def test_directory_override_works_without_affecting_other_checkouts(self):
        channel = ci_toolchain()
        with isolated_rustup(channel) as (home, env):
            checkout, sibling = home / "checkout", home / "sibling"
            checkout.mkdir()
            sibling.mkdir()
            subprocess.run(
                ["rustup", "override", "set", "--path", str(checkout), channel],
                cwd=checkout, env=env, capture_output=True, text=True, check=True, timeout=30,
            )
            # No environment pin or global default: plain Cargo uses only this directory's override.
            selected = subprocess.run(["cargo", "--version"], cwd=checkout, env=env,
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertIn(f"cargo {channel} ", selected.stdout)
            unrelated = subprocess.run(["cargo", "--version"], cwd=sibling, env=env,
                                       capture_output=True, text=True, timeout=30)
            self.assertNotEqual(unrelated.returncode, 0)
            self.assertIn("no default is configured", unrelated.stderr)


if __name__ == "__main__":
    unittest.main()
