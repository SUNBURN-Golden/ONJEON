import contextlib
import copy
import errno
import importlib.util
import io
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


n = load_module("network_probe")
h = load_module("container_network")


class SandboxTests(unittest.TestCase):
    def test_refusal_timeout_and_unexpected_errors_are_not_isolation(self):
        for error in (ConnectionRefusedError(errno.ECONNREFUSED, "fixture_only"),
                      TimeoutError(), OSError(errno.EACCES, "fixture_only")):
            sock = MagicMock()
            sock.__enter__.return_value = sock
            sock.connect.side_effect = error
            with patch.object(n.socket, "socket", return_value=sock), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(n.probe([["ipv4", "fixture_only", 1]], isolated=True), 2)

    def test_only_unreachable_is_accepted_and_both_families_checked(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.connect.side_effect = OSError(errno.ENETUNREACH, "fixture_only")
        with patch.object(n.socket, "socket", return_value=sock) as factory, contextlib.redirect_stdout(io.StringIO()):
            endpoints = [["ipv4", "fixture_only", 1], ["ipv6", "fixture_only", 1]]
            self.assertEqual(n.probe(endpoints, isolated=True), 0)
            self.assertEqual(factory.call_count, 2)
            self.assertEqual(n.probe(endpoints, isolated=False), 2)

    def test_wrong_endpoint_response_fails_positive_control(self):
        sock = MagicMock()
        sock.__enter__.return_value = sock
        sock.recv.side_effect = [b"wrong fixture_only endpoint", b""]
        with patch.object(n.socket, "socket", return_value=sock), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(n.probe([["ipv4", "fixture_only", 1]], isolated=False), 2)

    def test_live_controlled_endpoint_detects_enabled_network(self):
        # A real local socket proves that the actual probe rejects enabled networking.
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()

            def serve():
                for _ in range(2):
                    client, _ = server.accept()
                    with client:
                        client.sendall(n.PAYLOAD)

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            endpoints = [["ipv4", "127.0.0.1", server.getsockname()[1]]]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(n.probe(endpoints, isolated=False), 0)
                self.assertEqual(n.probe(endpoints, isolated=True), 1)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

    def test_container_configuration_is_scoped_to_docproc(self):
        service = {"network_mode": "none", "read_only": True, "user": "65532:65532",
                   "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
                   "volumes": [{"target": "/input", "read_only": True}]}
        config = {"services": {"docproc": service}}
        h.validate_config(config)
        for key, value in (("network_mode", "default"), ("read_only", False),
                           ("user", "0:0"), ("cap_drop", []), ("security_opt", []),
                           ("volumes", [{"target": "/input", "read_only": False}])):
            bad = copy.deepcopy(config)
            bad["services"]["unrelated_fixture_only"] = copy.deepcopy(service)
            bad["services"]["docproc"][key] = value
            with self.assertRaises(AssertionError):
                h.validate_config(bad)

    def test_docker_absence_fails_by_default_and_when_required(self):
        # Only the availability wrapper is stubbed, not extraction or network evidence.
        with tempfile.TemporaryDirectory() as bindir:
            (Path(bindir) / "dirname").symlink_to("/usr/bin/dirname")
            python = Path(bindir) / "python3"
            python.symlink_to("/usr/bin/true")
            for required in ("0", "1"):
                result = subprocess.run(["/bin/bash", str(ROOT / "test_sandbox.sh")],
                                        env={"PATH": bindir, "DOCPROC_SANDBOX_REQUIRE_LIVE": required},
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("LIVE: FAILED", result.stderr)
            for required, expected in (("0", 0), ("1", 1)):
                result = subprocess.run(["/bin/bash", str(ROOT / "test_sandbox.sh")],
                                        env={"PATH": bindir, "DOCPROC_SANDBOX_REQUIRE_LIVE": required,
                                             "DOCPROC_SANDBOX_STATIC_ONLY": "1"}, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected)
                self.assertIn("LIVE: SKIPPED" if expected == 0 else "LIVE: FAILED", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
