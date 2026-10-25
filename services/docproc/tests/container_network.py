"""Mandatory live I13 and native Poppler acceptance harness. All data is fixture_only."""
import json
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docker_runtime import docker_environment
from shared_contract import SCHEMA_FILES, check_output, load_schema, schema_dir

ROOT = Path(__file__).resolve().parents[1]
PROBE = (ROOT / "tests/network_probe.py").read_text()
SERVER = """import socket, threading, time
def serve(family, host):
    sock = socket.socket(family, socket.SOCK_STREAM)
    if family == socket.AF_INET6:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    sock.bind((host, 18080))
    sock.listen()
    while True:
        client, _ = sock.accept()
        with client:
            client.sendall(b'fixture_only docproc I13 endpoint\\n')
for family, host in [(socket.AF_INET, '0.0.0.0'), (socket.AF_INET6, '::')]:
    threading.Thread(target=serve, args=(family, host), daemon=True).start()
while True:
    time.sleep(1)
"""


def validate_config(config):
    service = config["services"]["docproc"]
    assert service["network_mode"] == "none", "docproc network_mode must be none"
    assert service["read_only"] is True
    assert service["user"] == "65532:65532"
    assert "ALL" in service["cap_drop"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert any(v["target"] == "/input" and v["read_only"] for v in service["volumes"])


def live(env):
    name = "docproc-fixture-" + uuid.uuid4().hex[:12]
    network, server, test_image = name + "-net", name + "-server", name + "-tests"
    with tempfile.TemporaryDirectory() as input_dir:
        env = {**env, "DOCPROC_INPUT_DIR": input_dir}
        # Shared contract shapes (packages/schemas) judge ids on the host and, mounted read-only, inside the suite.
        schema = load_schema()
        shared = Path(input_dir) / "schemas"
        shared.mkdir(mode=0o755)
        for schema_file in SCHEMA_FILES:
            shutil.copy(schema_dir() / schema_file, shared / schema_file)
            (shared / schema_file).chmod(0o644)
        compose = ["docker", "compose", "-p", name, "-f", str(ROOT / "compose.yaml")]

        def call(args, **kwargs):
            return subprocess.run(args, env=env, timeout=600, check=True, **kwargs)

        try:
            config = json.loads(call([*compose, "config", "--format", "json"], capture_output=True, text=True).stdout)
            validate_config(config)
            print("CONFIG: scoped services.docproc settings passed", flush=True)
            image = config["services"]["docproc"].get("image", name + "-docproc")
            # Build-time registry/package access only; runtime remains network_mode:none.
            call(["docker", "build", "--network", "host", "-t", image, str(ROOT)])
            call(["docker", "image", "inspect", image, "--format", "PRODUCTION IMAGE: {{.Id}}"])
            call(["docker", "build", "--network", "host", "--target", "test", "-t", test_image, str(ROOT)])
            test_command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                            "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:size=64m,noexec,nosuid",
                            "-v", f"{shared}:/schemas:ro", "-e", "DOCPROC_SCHEMA_DIR=/schemas",
                            "-e", "DOCPROC_REQUIRE_PINNED=1", "--entrypoint", "python3", test_image, "-B"]
            call([*test_command, "-c", "import docproc; print('NATIVE POPPLER:', docproc.tool_version(), flush=True)"])
            call([*test_command, "-m", "unittest", "discover", "-s", "/app/tests", "-v"])
            call([*test_command, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
            print("PINNED EXTRACTION: PASSED (native version, no identity mock)", flush=True)
            fixture_spec = importlib.util.spec_from_file_location("fixture_only", ROOT / "tests/test_docproc.py")
            fixture = importlib.util.module_from_spec(fixture_spec)
            fixture_spec.loader.exec_module(fixture)
            input_path = Path(input_dir)
            input_path.chmod(0o755)
            fixture.synthetic_pdf(input_path / "fixture_only.pdf")
            (input_path / "segments.fixture_only.json").write_text(json.dumps([
                {"page_from": 1, "page_to": 2, "doc_role": "terms", "seg_rule_ver": "explicit-0.1"}]))
            cli = [*compose, "run", "--rm", "--no-deps", "docproc", "/input/fixture_only.pdf"]
            result = call([*cli, "--segments", "/input/segments.fixture_only.json", "--origin", "fixture"], capture_output=True, text=True)
            output = json.loads(result.stdout)
            if not output["segments"] or not output["clauses"] or not all(c["extractor"]["version"].startswith("24.02.") for c in output["clauses"]):
                raise RuntimeError("Production CLI extraction failed")
            segments, clauses = check_output(output, schema)
            print(f"SHARED CONTRACT: PASSED ({segments} segment id(s), {clauses} clause id(s) and doc_role codes "
                  "accepted by packages/schemas SegmentRef/ClauseRef/doc_role)", flush=True)
            (input_path / "output.fixture_only.json").write_text(result.stdout)
            call([*cli, "--verify", "/input/output.fixture_only.json"])
            print("PRODUCTION CLI: PASSED (fixture extraction and quote/coordinate verification)", flush=True)
            subnet = "fd" + uuid.uuid4().hex[:2] + ":" + uuid.uuid4().hex[:4] + ":" + uuid.uuid4().hex[:4] + "::/64"
            call(["docker", "network", "create", "--internal", "--ipv6", "--subnet", subnet, network], capture_output=True)
            call(["docker", "run", "-d", "--rm", "--name", server, "--network", network,
                  "--read-only", "--cap-drop", "ALL", "--entrypoint", "python3", image, "-B", "-c", SERVER], capture_output=True)
            addresses = json.loads(call(["docker", "inspect", server], capture_output=True, text=True).stdout)[0]["NetworkSettings"]["Networks"][network]
            endpoints = json.dumps([["ipv4", addresses["IPAddress"], 18080], ["ipv6", addresses["GlobalIPv6Address"], 18080]])
            override = Path(input_dir) / "enabled.fixture_only.json"
            override.write_text(json.dumps({"services": {"docproc": {"network_mode": network}}}))
            enabled = [*compose, "-f", str(override), "run", "--rm", "--no-deps", "--entrypoint", "python3", "docproc", "-B", "-c", PROBE, endpoints]
            # Only endpoint startup is retried. Every actual isolation result is checked once.
            for attempt in range(20):
                positive = subprocess.run([*enabled, "reachable"], env=env, timeout=30, capture_output=True, text=True)
                if positive.returncode == 0:
                    print(positive.stdout, end="", flush=True)
                    break
                time.sleep(0.2)
            else:
                print(positive.stdout + positive.stderr, flush=True)
                raise RuntimeError("Controlled endpoint positive control failed")
            print("POSITIVE CONTROL: IPv4 and IPv6 reachable", flush=True)
            mutation = subprocess.run([*enabled, "isolated"], env=env, timeout=30, capture_output=True, text=True)
            print(mutation.stdout, end="", flush=True)
            if mutation.returncode != 1:
                raise RuntimeError("Enabled-network mutation was not detected")
            print("MUTATION: enabled networking rejected by isolation probe (exit 1)", flush=True)
            call([*compose, "run", "--rm", "--no-deps", "--entrypoint", "python3", "docproc", "-B", "-c", PROBE, endpoints, "isolated"])
            # The endpoint must remain reachable after the isolated probe as well.
            call([*enabled, "reachable"])
            print("I13: PASSED (controlled IPv4/IPv6 endpoints, before/after positive controls)", flush=True)
            return 0
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, AssertionError, RuntimeError) as error:
            if isinstance(error, subprocess.CalledProcessError):
                print(f"FAILED COMMAND: {error.cmd!r}; exit={error.returncode}", flush=True)
                if error.stderr:
                    print(error.stderr, flush=True)
            print(f"LIVE: FAILED ({type(error).__name__}); I13 and pinned extraction are not accepted", flush=True)
            return 1
        finally:
            for command in (["docker", "rm", "-f", server],
                            [*compose, "down", "--remove-orphans", "--rmi", "local"], ["docker", "network", "rm", network],
                            ["docker", "image", "rm", test_image]):
                try:
                    subprocess.run(command, env=env, timeout=60, capture_output=True)
                except (OSError, subprocess.SubprocessError):
                    pass


def main():
    try:
        with docker_environment() as env:
            return live(env)
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        print(f"LIVE: FAILED ({type(error).__name__}: {error}); I13 and pinned extraction are not accepted", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
