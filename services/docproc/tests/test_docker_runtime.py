"""fixture_only regressions for daemon selection, ownership and failure handling."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("docker_runtime", Path(__file__).with_name("docker_runtime.py"))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def result(stdout="", code=0):
    return subprocess.CompletedProcess([], code, stdout, "")


class DockerRuntimeTests(unittest.TestCase):
    def test_bootstrap_never_replaces_selected_daemon(self):
        with patch.object(r.Path, "exists", return_value=False), patch.object(r, "run") as call:
            for env in ({"DOCKER_HOST": "unix:///fixture_only.sock"}, {"DOCKER_CONTEXT": "fixture_only"}):
                self.assertFalse(r.bootstrap_allowed(env))
            call.assert_not_called()
        with patch.object(r.Path, "exists", return_value=True), patch.object(r, "run") as call:
            self.assertFalse(r.bootstrap_allowed({}))
            call.assert_not_called()
        for context, endpoint, code, allowed in (
                ("default", "unix:///var/run/docker.sock", 0, True),
                ("fixture_only", "unix:///var/run/docker.sock", 0, False),
                ("default", "unix:///fixture_only.sock", 0, False),
                ("default", "unix:///var/run/docker.sock", 1, False)):
            with patch.object(r.Path, "exists", return_value=False), \
                    patch.object(r, "run", side_effect=[result(context), result(endpoint, code)]):
                self.assertEqual(r.bootstrap_allowed({}), allowed)

    def test_working_daemon_is_reused_without_privileged_process(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "unix:///fixture_only.sock"}, clear=True), \
                patch.object(r, "run", return_value=result()), \
                patch.object(r.subprocess, "Popen") as start, contextlib.redirect_stdout(io.StringIO()):
            with r.docker_environment() as env:
                self.assertEqual(env["DOCKER_HOST"], "unix:///fixture_only.sock")
            start.assert_not_called()

    def test_unavailable_explicit_daemon_fails_without_bootstrap(self):
        with patch.object(r, "run", return_value=result(code=1)), \
                patch.object(r, "bootstrap_allowed", return_value=False), \
                patch.object(r.subprocess, "Popen") as start:
            with self.assertRaisesRegex(RuntimeError, "refusing to replace"):
                with r.docker_environment():
                    self.fail("Unavailable daemon must not yield acceptance environment")
            start.assert_not_called()

    def test_missing_daemon_or_privileges_fails(self):
        for daemon in (None, "/fixture_only/dockerd"):
            def which(name, **kwargs):
                return daemon if name == "dockerd" else "/fixture_only/sudo"

            with patch.object(r, "run", return_value=result(code=1)), \
                    patch.object(r, "bootstrap_allowed", return_value=True), \
                    patch.object(r.os, "geteuid", return_value=1000), \
                    patch.object(r.shutil, "which", side_effect=which), \
                    patch.object(r.tempfile, "mkdtemp") as mkdir:
                with self.assertRaisesRegex(RuntimeError, "needs Docker"):
                    with r.docker_environment():
                        self.fail("Missing prerequisites must fail")
                mkdir.assert_not_called()

    def exercise_owned_daemon(self, *, early_exit=False, body_failure=False, data_mount=False):
        process = MagicMock()
        process.poll.return_value = 1 if early_exit else None
        calls = []

        def call(args, **kwargs):
            calls.append(args)
            return result(code=1 if len(calls) == 1 else 0)

        def which(name, **kwargs):
            return "/fixture_only/dockerd" if name == "dockerd" else None

        with tempfile.TemporaryDirectory() as parent, patch.object(r, "ROOT", Path(parent)), \
                patch.object(r, "run", side_effect=call), \
                patch.object(r, "bootstrap_allowed", return_value=True), \
                patch.object(r.os, "geteuid", return_value=0), \
                patch.object(r.os.path, "ismount", return_value=data_mount), \
                patch.object(r.shutil, "which", side_effect=which), \
                patch.object(r.subprocess, "Popen", return_value=process) as start, \
                contextlib.redirect_stdout(io.StringIO()):
            def execute():
                with r.docker_environment() as env:
                    socket = Path(env["DOCKER_HOST"].removeprefix("unix://"))
                    self.assertEqual(socket.parent.parent, Path(parent))
                    self.assertTrue(socket.parent.exists())
                    # Simulate the daemon's pidfile, never target a real PID in this test.
                    (socket.parent / "daemon.pid").write_text("12345")
                    if body_failure:
                        raise ValueError("fixture_only body failure")

            if early_exit:
                with self.assertRaisesRegex(RuntimeError, "failed to become ready"):
                    execute()
            elif body_failure:
                with self.assertRaisesRegex(ValueError, "fixture_only body failure"):
                    execute()
            else:
                execute()
            self.assertEqual(list(Path(parent).iterdir()), [])
            args = start.call_args.args[0]
            self.assertIn("--data-root", args)
            self.assertIn("--exec-root", args)
            self.assertIn("vfs", args)
            self.assertEqual(args[args.index("--bridge") + 1], "none")
            if not early_exit:
                self.assertIn(["kill", "-TERM", "12345"], calls)
                process.wait.assert_called_once_with(timeout=30)
            if data_mount:
                unmount = next(args for args in calls if args[0] == "umount")
                self.assertEqual(Path(unmount[1]).name, "data")
                self.assertEqual(Path(unmount[1]).parent.parent, Path(parent))

    def test_owned_daemon_is_stopped_and_state_removed(self):
        self.exercise_owned_daemon()

    def test_owned_daemon_is_cleaned_when_acceptance_fails(self):
        self.exercise_owned_daemon(body_failure=True)

    def test_failed_daemon_start_cannot_pass_acceptance(self):
        self.exercise_owned_daemon(early_exit=True)

    def test_owned_data_bind_mount_is_unmounted_before_removal(self):
        self.exercise_owned_daemon(data_mount=True)


if __name__ == "__main__":
    unittest.main()
