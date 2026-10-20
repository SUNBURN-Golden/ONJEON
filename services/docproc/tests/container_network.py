import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROBE = """import socket
for family, address in [(socket.AF_INET, ('192.0.2.1', 443)), (socket.AF_INET6, ('2001:db8::1', 443))]:
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        try:
            sock.connect(address)
        except OSError:
            continue
        raise SystemExit('I13 failed: outbound connection succeeded')
print('I13 outbound IPv4 and IPv6 connections failed')
"""


def main():
    with tempfile.TemporaryDirectory() as input_dir:
        env = {**os.environ, "DOCPROC_INPUT_DIR": input_dir}
        command = ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "run", "--build", "--rm", "--entrypoint", "python3", "docproc", "-c", PROBE]
        try:
            return subprocess.run(command, env=env, timeout=600).returncode
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("I13 NOT VERIFIED: Docker unavailable or execution timed out")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
