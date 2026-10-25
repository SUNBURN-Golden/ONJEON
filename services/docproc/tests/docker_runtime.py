"""Own a temporary acceptance-test daemon when the default daemon is absent."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, timeout=15, **kwargs)


def bootstrap_allowed(env):
    # Never replace a caller-selected endpoint, context, or existing system socket.
    if env.get("DOCKER_HOST") or env.get("DOCKER_CONTEXT") or Path("/var/run/docker.sock").exists():
        return False
    context = run(["docker", "context", "show"], env=env)
    endpoint = run(["docker", "context", "inspect", "default", "--format", "{{.Endpoints.docker.Host}}"], env=env)
    return (context.returncode == endpoint.returncode == 0 and context.stdout.strip() == "default"
            and endpoint.stdout.strip() == "unix:///var/run/docker.sock")


@contextmanager
def docker_environment():
    env = dict(os.environ)
    if run(["docker", "info"], env=env).returncode == 0:
        print("RUNTIME: using caller's working Docker daemon", flush=True)
        yield env
        return
    if not bootstrap_allowed(env):
        raise RuntimeError("Selected Docker daemon is unavailable; refusing to replace it")
    system_path = env.get("PATH", "") + os.pathsep + "/usr/sbin:/sbin"
    daemon = shutil.which("dockerd", path=system_path)
    privilege = [] if os.geteuid() == 0 else ["sudo", "-n"]
    if not daemon or (privilege and (not shutil.which("sudo") or run([*privilege, "true"]).returncode)):
        raise RuntimeError("Live acceptance needs Docker, dockerd and noninteractive local daemon privileges")
    # containerd appends socket names; keep this path below Unix socket limits.
    directory = Path(tempfile.mkdtemp(prefix=".d-", dir=ROOT))
    process = None
    log = directory / "daemon.log"
    try:
        # No global daemon config, default socket, or iptables alternatives are changed.
        # The local daemon has no default bridge. Only image builds use host networking;
        # runtime probes still use Compose network_mode:none and a temporary internal net.
        bindir = directory / "bin"
        bindir.mkdir()
        for name in ("iptables", "ip6tables"):
            legacy = shutil.which(name + "-legacy", path=system_path)
            if legacy:
                (bindir / name).symlink_to(legacy)
        daemon_path = str(bindir) + os.pathsep + system_path
        socket = directory / "docker.sock"
        pidfile = directory / "daemon.pid"
        env["DOCKER_HOST"] = "unix://" + str(socket)
        args = [*privilege, "env", "PATH=" + daemon_path, daemon,
                "--host", env["DOCKER_HOST"], "--group", str(os.getgid()),
                "--data-root", str(directory / "data"), "--exec-root", str(directory / "e"),
                "--pidfile", str(pidfile), "--storage-driver", "vfs", "--bridge", "none"]
        print("RUNTIME: starting owned temporary Docker daemon (no default bridge)", flush=True)
        with log.open("w") as stream:
            process = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        while process.poll() is None and time.monotonic() < deadline:
            if run(["docker", "info"], env=env).returncode == 0:
                break
            time.sleep(0.2)
        else:
            print(log.read_text()[-6000:], flush=True)
            raise RuntimeError("Temporary Docker daemon failed to become ready")
        yield env
    finally:
        # Stop only the daemon we started, after the harness cleans its containers/nets.
        # Do not erase its state if shutdown cannot be confirmed.
        if process is not None and process.poll() is None:
            if pidfile.exists():
                pid = int(pidfile.read_text().strip())
                run([*privilege, "kill", "-TERM", str(pid)], check=True)
            else:
                process.terminate()
            process.wait(timeout=30)
        if privilege:
            if os.path.ismount(directory / "data"):
                run([*privilege, "umount", str(directory / "data")], check=True)
            run([*privilege, "rm", "-rf", "--", str(directory)], check=True)
        else:
            if os.path.ismount(directory / "data"):
                run(["umount", str(directory / "data")], check=True)
            shutil.rmtree(directory)
        print("RUNTIME: owned temporary daemon stopped and state removed", flush=True)
