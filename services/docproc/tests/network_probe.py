"""fixture_only: classify connections to live controlled endpoints, never public hosts."""
import errno
import json
import socket
import sys

PAYLOAD = b"fixture_only docproc I13 endpoint\n"
UNREACHABLE = {errno.ENETUNREACH, errno.EHOSTUNREACH}


def probe(endpoints, isolated):
    for family_name, host, port in endpoints:
        family = {"ipv4": socket.AF_INET, "ipv6": socket.AF_INET6}[family_name]
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(3)
            try:
                sock.connect((host, port))
                received = b""
                while len(received) < len(PAYLOAD):
                    part = sock.recv(len(PAYLOAD) - len(received))
                    if not part:
                        break
                    received += part
            except OSError as error:
                if isolated and error.errno in UNREACHABLE:
                    print(f"{family_name}: blocked by network reachability errno={error.errno}", flush=True)
                    continue
                print(f"{family_name}: unexpected connection error errno={error.errno}", flush=True)
                return 2
            if isolated:
                print(f"{family_name}: isolation failed, endpoint reachable", flush=True)
                return 1
            if received != PAYLOAD:
                print(f"{family_name}: controlled endpoint response mismatch", flush=True)
                return 2
            print(f"{family_name}: controlled endpoint reachable", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(probe(json.loads(sys.argv[1]), sys.argv[2] == "isolated"))
