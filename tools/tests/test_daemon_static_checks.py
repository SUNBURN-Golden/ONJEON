"""Audit 3: inspect unsafe source without executing it; exercise the actual checker CLI."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from daemon import static_checks  # noqa: E402

RULES = ROOT / "docs/blueprint/proposals/설계검토_결과/daemon_rules.json"
TASKS = ROOT / "tools/daemon/mock_tasks.json"

# Independent of the implementation's deny list: every os process-launch variant.
PROCESS_NAMES = (
    "system", "popen", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "posix_spawn", "posix_spawnp", "fork", "forkpty", "startfile",
)


class StaticBypasses(unittest.TestCase):
    def check_source(self, source, check=static_checks.no_network_or_cli, filename="probe.py"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
            return check(Path(directory))

    def test_builtins_mapping_and_attribute_access(self):
        for source in (
            '__builtins__["eval"]("1")', '__builtins__["exec"]("pass")',
            'b = __builtins__; f = b["eval"]', '__builtins__.eval("1")',
            'globals()["__builtins__"]["eval"]("1")', 'fn.__builtins__["eval"]("1")',
        ):
            with self.subTest(source=source):
                self.assertTrue(self.check_source(source))

    def test_reflective_forbidden_members(self):
        for name in (*PROCESS_NAMES, "eval", "exec", "compile", "__import__", "import_module", "__builtins__"):
            source = f'import os as operating\nf = getattr(operating, {name!r})\n'
            with self.subTest(name=name):
                self.assertTrue(self.check_source(source))

    def test_process_attributes_and_aliases(self):
        for name in PROCESS_NAMES:
            for expression in (f'os.{name}("unused")', f'launch = os.{name}'):
                with self.subTest(expression=expression):
                    self.assertTrue(self.check_source("import os\n" + expression))

    def test_from_os_import_aliases_and_star(self):
        for name in (*PROCESS_NAMES, "*"):
            source = f'from os import {name}' + (' as launch\n' if name != "*" else '\n')
            with self.subTest(name=name):
                self.assertTrue(self.check_source(source))

    def test_native_execution_imports(self):
        for module in ("ctypes", "ctypes.util", "_ctypes", "posix", "nt"):
            for source in (f'import {module} as native', f'from {module} import system as launch'):
                with self.subTest(source=source):
                    self.assertTrue(self.check_source(source))

    def test_relative_forbidden_imports(self):
        for name in ("ctypes", "socket", "subprocess", "importlib", "builtins"):
            with self.subTest(name=name):
                self.assertTrue(self.check_source(f'from . import {name} as helper'))

    def test_safe_operations_and_data_are_allowed(self):
        source = '''import os
import re
import json
pattern = re.compile("a")
value = json.loads("1")
path = os.path.join("a", "b")
label = getattr(record, "label", None)
value = getattr(record, field_name, None)
data = {"eval": "description", "system": "label"}
# __builtins__["eval"] and getattr(os, "system") are only documentation here.
'''
        self.assertEqual(self.check_source(source), [])

    def test_same_named_files_are_checked(self):
        for filename in ("static_checks.py", "nested/static_checks.py"):
            with self.subTest(filename=filename):
                self.assertTrue(self.check_source('eval("1")', filename=filename))

    def test_only_canonical_checker_and_runner_directory_are_exempt(self):
        files = static_checks._py_files(static_checks.HERE)
        self.assertNotIn(Path(static_checks.__file__), files)
        self.assertIn(Path(static_checks.__file__), static_checks._py_files(static_checks.HERE, include_self=True))
        self.assertTrue(files)
        self.assertFalse(any(static_checks.RUNNER_VERIFY in path.parents for path in files))
        # An unrelated directory with the same name must not inherit the exemption.
        self.assertTrue(self.check_source('eval("1")', filename="runner_verify/probe.py"))

    def test_truthy_literal_loops_are_rejected(self):
        for condition in ("True", "1", "2", "-1", "1.0", "'forever'", "[1]", "{'x': 1}"):
            with self.subTest(condition=condition):
                self.assertTrue(self.check_source(f'while {condition}:\n    pass\n',
                                                 static_checks.no_scheduler_or_runner))

    def test_finite_and_false_literal_loops_and_comments_are_allowed(self):
        for source in ('while pending:\n    pending.pop()\n', 'while clock.now() < end:\n    step()\n',
                       'while False:\n    pass\n', 'while 0:\n    pass\n',
                       '# while True:\ntext = "while True:"\n'):
            with self.subTest(source=source):
                self.assertEqual(self.check_source(source, static_checks.no_scheduler_or_runner), [])

    def test_existing_scheduler_bans_still_hold(self):
        for source in ("import sched", "import apscheduler", "signal.signal(1, handler)", "os.fork()"):
            with self.subTest(source=source):
                self.assertTrue(self.check_source(source, static_checks.no_scheduler_or_runner))


class StaticCli(unittest.TestCase):
    def run_cli(self, script, *arguments):
        # A different cwd and isolated Python exercise path defaults and the standalone entry point.
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run([sys.executable, "-I", str(script), *arguments], cwd=directory,
                                  capture_output=True, text=True, timeout=30)

    def test_no_arguments_runs_all_checks(self):
        result = self.run_cli(Path(static_checks.__file__))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("[PASS]"), len(static_checks.all_static(RULES)))
        self.assertIn("failed: 0", result.stdout)

    def test_cli_rejects_planted_violations_without_executing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            daemon = Path(directory) / "daemon"
            shutil.copytree(static_checks.HERE, daemon,
                            ignore=shutil.ignore_patterns("runner_verify", "reports", "__pycache__"))
            script = daemon / "static_checks.py"
            for source in ('__builtins__["eval"]("1")', 'getattr(os, "system")("unused")',
                           'from os import system as s', 'os.execvpe("unused", [], {})',
                           'os.posix_spawn("unused", [], {})', 'import ctypes', 'while 1:\n    pass'):
                with self.subTest(source=source):
                    (daemon / "core/static_checks.py").write_text(source, encoding="utf-8")
                    result = self.run_cli(script, "--rules", str(RULES), "--tasks", str(TASKS))
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("[FAIL]", result.stdout)
                    self.assertIn("static_checks.py:", result.stdout)

    def test_cli_input_errors_are_nonzero_and_explained(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "rules.json"
            for content in (None, "{", "{}"):
                with self.subTest(content=content):
                    if content is not None:
                        invalid.write_text(content, encoding="utf-8")
                    result = self.run_cli(Path(static_checks.__file__), "--rules", str(invalid))
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("[ERROR]", result.stderr)
                    self.assertNotIn("[PASS]", result.stdout)

    def test_cli_invalid_source_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            daemon = Path(directory) / "daemon"
            shutil.copytree(static_checks.HERE, daemon,
                            ignore=shutil.ignore_patterns("runner_verify", "reports", "__pycache__"))
            (daemon / "core/broken.py").write_text('if\n', encoding="utf-8")
            result = self.run_cli(daemon / "static_checks.py", "--rules", str(RULES), "--tasks", str(TASKS))
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("[ERROR]", result.stderr)
            self.assertIn("broken.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
