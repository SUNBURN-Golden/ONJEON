"""Local checks must not reuse another worktree's Cargo metadata."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "tools/ci/with_worktree_target.py"


class WorktreeTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "target").mkdir(exist_ok=True)

    def test_overrides_shared_target_for_command_and_descendant_from_any_cwd(self):
        # A Python check can invoke Cargo indirectly. Exercise the environment
        # across both process boundaries, including an invocation outside ROOT.
        child = "import os; print(os.environ['CARGO_TARGET_DIR'])"
        parent = (
            "import json, os, subprocess, sys; "
            "print(json.dumps([os.getcwd(), os.environ['CARGO_TARGET_DIR'], "
            "subprocess.check_output([sys.executable, '-c', sys.argv[1]], text=True).strip()]))"
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "target") as temporary:
            shared = Path(temporary) / "shared"
            shared.mkdir()
            sentinel = shared / "sentinel"
            sentinel.write_text("unchanged", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-I", str(WRAPPER), sys.executable, "-c", parent, child],
                cwd=temporary, env=dict(os.environ, CARGO_TARGET_DIR=str(shared)),
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout),
                             [str(ROOT), str(ROOT / "target"), str(ROOT / "target")])
            self.assertEqual(list(shared.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")

    def test_arguments_and_failure_exit_code_reach_caller(self):
        args = ["space here", "$(literal)", "--offline"]
        result = subprocess.run(
            [sys.executable, "-I", str(WRAPPER), sys.executable, "-c",
             "import json, sys; print(json.dumps(sys.argv[1:])); sys.exit(19)", *args],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 19)
        self.assertEqual(json.loads(result.stdout), args)

    def test_missing_command_fails(self):
        for args, code, message in [
            ([], 2, "usage:"),
            (["/nonexistent-onjeon-command"], 127, "command not found:"),
        ]:
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, "-I", str(WRAPPER), *args],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, code)
                self.assertIn(message, result.stderr)

    def test_ci_sets_worktree_target_before_python_and_cargo_checks(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        env, = re.findall(r"(?m)^env:\n((?:  [^\n]*\n)+)", workflow)
        self.assertIn("  CARGO_TARGET_DIR: ${{ github.workspace }}/target\n", env)

    @unittest.skipUnless(shutil.which("cargo"), "cargo not installed")
    def test_real_engine_api_build_ignores_stale_library_from_another_checkout(self):
        # Preserve source mtimes, as worktree/snapshot copies do. Seed a shared
        # cache with a library that lacks the public API, reproduce E0432, then
        # run the same check through the actual wrapper in the second checkout.
        engine = ROOT / "packages/rules-engine"
        with tempfile.TemporaryDirectory(dir=ROOT / "target") as temporary:
            base = Path(temporary)
            old = base / "old"
            shutil.copytree(engine / "src", old / "src")
            (old / "Cargo.toml").write_text(
                (engine / "Cargo.toml").read_text(encoding="utf-8") + "\n[workspace]\n",
                encoding="utf-8",
            )
            shutil.copy2(ROOT / "Cargo.lock", old / "Cargo.lock")
            original = (old / "src/lib.rs").read_text(encoding="utf-8")
            self.assertIn("pub use rule::{parse_rule_json,", original)
            (old / "src/lib.rs").write_text(
                original.replace("pub use rule::{parse_rule_json,", "pub use rule::{"),
                encoding="utf-8",
            )
            current = base / "current"
            shutil.copytree(old, current)
            lib = current / "src/lib.rs"
            lib.write_text(original, encoding="utf-8")
            os.utime(lib, (1, 1))
            (current / "tests").mkdir()
            shutil.copy2(engine / "tests/duplicate_json_keys.rs", current / "tests")
            env = dict(os.environ, CARGO_TARGET_DIR=str(base / "shared"))

            def check(cwd, *prefix, tests=False):
                return subprocess.run(
                    [*prefix, "cargo", "check", "--locked", "--offline",
                     "--tests" if tests else "--lib"],
                    cwd=cwd, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, timeout=120,
                )

            baseline = check(old)
            self.assertEqual(baseline.returncode, 0, baseline.stdout)
            stale = check(current, tests=True)
            self.assertNotEqual(stale.returncode, 0, stale.stdout)
            self.assertIn("unresolved import `onjeon_rules_engine::parse_rule_json`", stale.stdout)
            self.assertIn("E0432", stale.stdout)
            wrapper = current / "tools/ci/with_worktree_target.py"
            wrapper.parent.mkdir(parents=True)
            shutil.copy2(WRAPPER, wrapper)
            isolated = check(current, sys.executable, "-I", str(wrapper), tests=True)
            self.assertEqual(isolated.returncode, 0, isolated.stdout)
            # Also exercise the workflow-level setting with an unwrapped command.
            env["CARGO_TARGET_DIR"] = str(current / "target")
            plain = check(current, tests=True)
            self.assertEqual(plain.returncode, 0, plain.stdout)


if __name__ == "__main__":
    unittest.main()
