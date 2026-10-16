"""로컬 Compose 정적 시험(docker 불필요). 실제 기동은 smoke.sh의 2단계가 확인한다.

지키는 것:
- 저장소의 어느 파일에도 비밀값이 없다(compose는 값 없이 .env 참조만, .env.example의 비밀 항목은 비어 있다).
- 공개 DB와 개인 DB는 서로 다른 서버·사용자·비밀번호·볼륨·네트워크이고, 환경 변수 이름도 겹치지 않는다.
- 호스트 포트는 127.0.0.1에만 묶이고, 이미지는 태그가 고정되어 있다.
- up.sh가 만드는 .env는 모든 비밀값이 채워지고 서로 다르며, 다시 실행해도 바뀌지 않는다.
- 객체 저장소 신원 파일은 공개 영역 신원에 공개 버킷만, 개인 영역 신원에 개인 버킷만 준다.
- 신원 파일은 소유자만 여는 디렉터리(700) 안의 644 파일이다: 다른 호스트 사용자는 못 읽고, 컨테이너 사용자는 root가 아니어도 읽는다.
- smoke.sh의 부정 검사는 임의의 실패를 통과로 세지 않는다(거부 사유·응답 없음·접근 거부 응답을 요구).
"""
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

COMPOSE = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".sh", ".yml", ".psql", ".md", ".example", ".gitignore"}
SECRET_SUFFIX = re.compile(r"^[A-Z0-9_]+(_PASSWORD|_SECRET_KEY|_ACCESS_KEY)$")


def read(name):
    return (COMPOSE / name).read_text(encoding="utf-8")


def shipped_files():
    """검사 대상: 이 디렉터리의 추적 대상 파일(시험 코드·실행 증거·생성 파일 제외)."""
    out = []
    for p in sorted(COMPOSE.rglob("*")):
        rel = p.relative_to(COMPOSE)
        if not p.is_file() or rel.parts[0] in {"tests", "evidence", ".generated", "__pycache__"} or rel.name == ".env":
            continue
        if p.suffix in TEXT_SUFFIXES or p.name in {".env.example", ".gitignore"}:
            out.append(p)
    return out


def service_blocks(compose_text):
    """최상위 services: 아래의 서비스 이름 -> 본문. 이 저장소의 compose 파일은 2칸 들여쓰기 형식을 지킨다."""
    m = re.search(r"^services:\n(.*?)(?=^\S)", compose_text, re.S | re.M)
    assert m, "services section not found"
    parts = re.split(r"^  ([a-z0-9-]+):[ ]*\n", m.group(1), flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def env_names(block):
    return set(re.findall(r"\$\{([A-Z0-9_]+)", block))


def run_lib(state_dir, script, env_extra=None):
    env = dict(os.environ, ONJEON_COMPOSE_STATE_DIR=str(state_dir), **(env_extra or {}))
    return subprocess.run(["bash", "-c", f'. "{COMPOSE}/lib.sh"; set -e; {script}'],
                          env=env, capture_output=True, text=True)


def parse_env(path):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


class NoSecrets(unittest.TestCase):
    def test_compose_has_no_literal_credentials(self):
        for n, line in enumerate(read("docker-compose.yml").splitlines(), 1):
            m = re.match(r"\s+([A-Z0-9_]*(PASSWORD|SECRET|ACCESS_KEY)[A-Z0-9_]*):\s*(.*)", line)
            if m and not m.group(1).endswith("_ENDPOINT_URL"):
                self.assertRegex(m.group(3), r"^\$\{[A-Z0-9_]+:\?[^}]+\}$",
                                 f"docker-compose.yml:{n}: {m.group(1)} must be a required ${{VAR:?...}} reference")

    def test_env_example_secret_entries_are_empty(self):
        env = parse_env(COMPOSE / ".env.example")
        secrets = [k for k in env if SECRET_SUFFIX.match(k)]
        self.assertGreaterEqual(len(secrets), 10)
        for k in secrets:
            self.assertEqual(env[k], "", f".env.example must not carry a value for {k}")

    def test_no_secret_looking_strings_in_shipped_files(self):
        hexish = re.compile(r"\b[0-9a-f]{32,}\b|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY")
        for p in shipped_files():
            text = p.read_text(encoding="utf-8")
            if p.name == "PR_본문.md":  # 대상 커밋 SHA(40자리)는 여기서만 허용한다. 그 외 패턴은 그대로 검사한다.
                text = re.sub(r"\b[0-9a-f]{40}\b", "<sha>", text)
            self.assertIsNone(hexish.search(text), f"{p.name}: secret-looking string")

    def test_no_model_identifiers_in_shipped_files(self):
        pattern = re.compile("|".join(["clau" + "de", "gp" + "t-", "gem" + "ini", "anthro" + "pic", "open" + "ai"]), re.I)
        for p in shipped_files():
            self.assertIsNone(pattern.search(p.read_text(encoding="utf-8")), f"{p.name}: model identifier")

    def test_generated_and_env_files_are_gitignored(self):
        ignore = read(".gitignore").splitlines()
        self.assertIn(".env", ignore)
        self.assertIn(".generated/", ignore)

    def test_zone_sql_takes_values_from_environment(self):
        sql = read("initdb/zone-init.psql")
        self.assertNotRegex(sql, r"(?i)password\s+'")
        for var in ("APP_DB_USER", "APP_DB_PASSWORD", "ONJEON_ZONE"):
            self.assertIn(f"\\getenv", sql)
            self.assertIn(var, sql)
        self.assertIn("REVOKE ALL ON DATABASE", sql)
        self.assertIn("NOSUPERUSER", sql)


class ComposeShape(unittest.TestCase):
    def setUp(self):
        self.text = read("docker-compose.yml")
        self.services = service_blocks(self.text)

    def test_expected_services(self):
        self.assertEqual(set(self.services), {"db-public", "db-private", "s3", "s3-init", "s3-check"})

    def test_every_variable_is_declared_in_env_example(self):
        declared = set(parse_env(COMPOSE / ".env.example"))
        used = env_names(self.text) - {"ONJEON_S3_CONFIG"}  # 이 변수는 up.sh가 정한다
        self.assertEqual(used - declared, set())

    def test_host_ports_bind_loopback_only(self):
        ports = re.findall(r'^\s+- "([^"]*:\d+)"\s*$', self.text, re.M)
        self.assertEqual(len(ports), 3)
        for p in ports:
            self.assertTrue(p.startswith("127.0.0.1:"), p)

    def test_images_are_pinned(self):
        images = re.findall(r"^\s+image:\s*(\S+)\s*$", self.text, re.M)
        self.assertTrue(images)
        for image in images:
            self.assertRegex(image, r":[0-9][0-9A-Za-z._-]*$", f"{image} needs a version tag")
            self.assertNotIn("latest", image)

    def test_public_and_private_databases_share_nothing(self):
        pub, prv = self.services["db-public"], self.services["db-private"]
        shared_vars = env_names(pub) & env_names(prv)
        self.assertEqual(shared_vars, set(), "db-public and db-private must read different variables")
        self.assertIn("ONJEON_ZONE: public", pub)
        self.assertIn("ONJEON_ZONE: private", prv)
        self.assertIn("public-db-data:", pub)
        self.assertIn("private-db-data:", prv)
        self.assertNotIn("private-db-data", pub)
        self.assertNotIn("public-db-data", prv)
        self.assertIn("networks: [public-zone]", pub)
        self.assertIn("networks: [private-zone]", prv)

    def test_private_database_does_not_log_statements(self):
        prv = self.services["db-private"]
        self.assertIn("log_statement=none", prv)
        self.assertIn("log_min_duration_statement=-1", prv)
        # 제약 위반의 DETAIL("Failing row contains (...)")에 값이 실리지 않게 한다.
        self.assertIn("log_error_verbosity=terse", prv)
        self.assertIn("log_min_error_statement=panic", prv)
        # 오류 본문이 값을 인용할 수 있으므로 ERROR 수준 자체를 서버 로그에서 뺀다.
        self.assertIn("log_min_messages=log", prv)
        self.assertNotIn("log_min_messages", self.services["db-public"])
        self.assertNotIn("log_statement", self.services["db-public"])

    def test_databases_use_scram_and_health_check_over_tcp(self):
        for name in ("db-public", "db-private"):
            self.assertIn("password_encryption=scram-sha-256", self.services[name])
        self.assertIn("auth-host=scram-sha-256", self.text)
        for name in ("db-public", "db-private"):
            self.assertIn("pg_isready -h 127.0.0.1", self.services[name])

    def test_object_store_is_in_both_zones_and_check_service_is_opt_in(self):
        self.assertIn("networks: [public-zone, private-zone]", self.services["s3"])
        self.assertIn("profiles: [check]", self.services["s3-check"])

    def test_compose_files_referenced_by_mounts_exist(self):
        for rel in re.findall(r"^\s+- \./([^:]+):", self.text, re.M):
            self.assertTrue((COMPOSE / rel).exists(), rel)


class EnvGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onjeon-compose-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_ensure_env_fills_unique_secrets_and_is_idempotent(self):
        r = run_lib(self.tmp, "ensure_env")
        self.assertEqual(r.returncode, 0, r.stderr)
        env_file = self.tmp / ".env"
        self.assertEqual(stat.S_IMODE(env_file.stat().st_mode), 0o600)
        example, env = parse_env(COMPOSE / ".env.example"), parse_env(env_file)
        self.assertEqual(set(env), set(example))
        secrets = [k for k in example if SECRET_SUFFIX.match(k)]
        values = [env[k] for k in secrets]
        self.assertTrue(all(len(v) >= 20 for v in values))
        self.assertEqual(len(set(values)), len(values), "every secret must differ")
        for k in set(example) - set(secrets):
            self.assertEqual(env[k], example[k], f"{k} must keep its example value")
        first = env_file.read_text(encoding="utf-8")
        self.assertEqual(run_lib(self.tmp, "ensure_env").returncode, 0)
        self.assertEqual(env_file.read_text(encoding="utf-8"), first, "second run must not change .env")

    def test_ensure_env_keeps_a_value_the_user_set(self):
        (self.tmp / ".env").write_text("PUBLIC_DB_ADMIN_PASSWORD=chosen-by-user\n", encoding="utf-8")
        self.assertEqual(run_lib(self.tmp, "ensure_env").returncode, 0)
        self.assertEqual(parse_env(self.tmp / ".env")["PUBLIC_DB_ADMIN_PASSWORD"], "chosen-by-user")

    def test_ensure_env_adds_keys_new_in_example_without_touching_existing(self):
        # 예전에 만든 .env는 이후 .env.example에 키가 늘어도 그대로 쓸 수 있어야 한다.
        (self.tmp / ".env").write_text("PUBLIC_DB_ADMIN_PASSWORD=chosen-by-user\nPUBLIC_DB_NAME=my_db\n", encoding="utf-8")
        self.assertEqual(run_lib(self.tmp, "ensure_env").returncode, 0)
        env = parse_env(self.tmp / ".env")
        example = parse_env(COMPOSE / ".env.example")
        self.assertEqual(set(example) - set(env), set())
        self.assertEqual(env["PUBLIC_DB_NAME"], "my_db")
        self.assertEqual(env["PUBLIC_DB_ADMIN_PASSWORD"], "chosen-by-user")
        self.assertTrue(env["PRIVATE_DB_ADMIN_PASSWORD"])

    def test_ensure_env_leaves_no_temp_files(self):
        run_lib(self.tmp, "ensure_env")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), [".env"])


class ObjectStoreIdentities(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="onjeon-compose-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def render(self, ensure=True):
        return run_lib(self.tmp, ("ensure_env; " if ensure else "") + "render_s3_config")

    def test_each_zone_identity_reaches_only_its_buckets(self):
        r = self.render()
        self.assertEqual(r.returncode, 0, r.stderr)
        path = self.tmp / ".generated" / "s3.json"
        env = parse_env(self.tmp / ".env")
        ids = {i["name"]: i for i in json.loads(path.read_text(encoding="utf-8"))["identities"]}
        self.assertEqual(set(ids), {"admin", "public-zone", "private-zone"})
        buckets = lambda ident: {a.split(":", 1)[1] for a in ids[ident]["actions"] if ":" in a}
        self.assertEqual(buckets("public-zone"), {env["S3_PUBLIC_RAW_BUCKET"], env["S3_PUBLIC_DERIVED_BUCKET"]})
        self.assertEqual(buckets("private-zone"), {env["S3_PRIVATE_BUCKET"]})
        for zone in ("public-zone", "private-zone"):
            self.assertNotIn("Admin", ids[zone]["actions"])
            self.assertTrue(all(":" in a for a in ids[zone]["actions"]), "zone identity must not hold unscoped rights")
        self.assertIn("Admin", ids["admin"]["actions"])
        keys = [ids[n]["credentials"][0]["accessKey"] for n in ids]
        secrets = [ids[n]["credentials"][0]["secretKey"] for n in ids]
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(len(set(secrets)), 3)
        self.assertEqual(ids["public-zone"]["credentials"][0]["accessKey"], env["S3_PUBLIC_ACCESS_KEY"])
        self.assertEqual(ids["private-zone"]["credentials"][0]["secretKey"], env["S3_PRIVATE_SECRET_KEY"])

    def test_identity_file_is_closed_to_other_host_users_but_readable_by_any_container_user(self):
        # 바인드 마운트되는 것은 파일이므로 컨테이너 사용자(root가 아닐 수 있다)가 읽어야 한다: 644.
        # 호스트 쪽 보호는 디렉터리가 맡는다: 700이면 다른 호스트 사용자는 파일에 이르지 못한다. smoke.sh가 비root 컨테이너 사용자로 실제로 읽어 본다.
        r = self.render()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(stat.S_IMODE((self.tmp / ".generated").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.tmp / ".generated" / "s3.json").stat().st_mode), 0o644)
        self.assertFalse((self.tmp / ".generated" / "s3.json.tmp").exists())

    def test_render_refuses_unusable_values(self):
        run_lib(self.tmp, "ensure_env")
        env_file = self.tmp / ".env"
        good = env_file.read_text(encoding="utf-8")
        cases = {
            "same bucket twice": ("S3_PRIVATE_BUCKET=onjeon-private-contracts", "S3_PRIVATE_BUCKET=onjeon-raw-sources"),
            "quote in bucket name": ("S3_PRIVATE_BUCKET=onjeon-private-contracts", 'S3_PRIVATE_BUCKET=a"b'),
        }
        for label, (old, new) in cases.items():
            with self.subTest(label):
                env_file.write_text(good.replace(old, new), encoding="utf-8")
                self.assertNotEqual(self.render(ensure=False).returncode, 0)
                self.assertFalse((self.tmp / ".generated" / "s3.json.tmp").exists())
        env_file.write_text(good.replace(parse_env(env_file)["S3_PUBLIC_SECRET_KEY"], "", 1), encoding="utf-8")
        self.assertNotEqual(self.render(ensure=False).returncode, 0, "empty secret must be refused")


class Scripts(unittest.TestCase):
    def test_shell_syntax(self):
        scripts = [p for p in COMPOSE.rglob("*.sh") if "tests" not in p.parts and ".generated" not in p.parts]
        self.assertGreaterEqual(len(scripts), 7)
        for p in scripts:
            r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{p.name}: {r.stderr}")

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck not installed")
    def test_shellcheck(self):
        scripts = [str(p) for p in COMPOSE.rglob("*.sh") if "tests" not in p.parts]
        r = subprocess.run(["shellcheck", "-x", *scripts], capture_output=True, text=True, cwd=COMPOSE)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_entry_scripts_are_executable_and_strict(self):
        for name in ("up.sh", "down.sh", "smoke.sh", "initdb/10-zone.sh", "scripts/init-objects.sh", "scripts/check-objects.sh"):
            p = COMPOSE / name
            self.assertTrue(os.access(p, os.X_OK), f"{name} must be executable")
            self.assertRegex(p.read_text(encoding="utf-8"), r"(?m)^set -(euo pipefail|eu)$", name)

    def test_denial_checks_accept_only_access_denied(self):
        # 연결 실패 같은 다른 오류가 "거부됨"으로 세어지면 권한 시험이 아무것도 증명하지 못한다.
        text = read("scripts/check-objects.sh")
        self.assertRegex(text, r"AccessDenied\|Forbidden")
        self.assertIn("접근 거부가 아닌 오류", text)

    def test_object_scripts_bound_their_waiting(self):
        for name in ("scripts/init-objects.sh", "scripts/check-objects.sh"):
            self.assertIn("--cli-connect-timeout", read(name), name)

    def test_zone_init_script_does_not_exec_psql(self):
        # 이미지가 실행 비트 없는 .sh를 source할 수 있다. exec이면 이미지의 초기화 흐름이 끊긴다.
        self.assertNotRegex(read("initdb/10-zone.sh"), r"(?m)^\s*exec\b")

    def test_smoke_without_docker_fails_unless_static_only_is_requested(self):
        # 실제 기동 시험을 못 돌린 실행이 종료 코드 0(성공)으로 끝나면 안 된다.
        bin_dir = Path(tempfile.mkdtemp(prefix="onjeon-nodocker-"))
        self.addCleanup(shutil.rmtree, bin_dir, True)
        os.symlink(shutil.which("dirname"), bin_dir / "dirname")
        base = dict(os.environ, PATH=str(bin_dir), ONJEON_SMOKE_SKIP_STATIC="1")
        base.pop("ONJEON_SMOKE_STATIC_ONLY", None)
        run = lambda extra: subprocess.run(["/bin/bash", str(COMPOSE / "smoke.sh")], env=dict(base, **extra),
                                           capture_output=True, text=True)
        r = run({})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("LIVE: FAILED", r.stderr)
        self.assertNotIn("PASSED", r.stdout + r.stderr)
        r = run({"ONJEON_SMOKE_STATIC_ONLY": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("LIVE: SKIPPED", r.stdout)
        self.assertNotIn("PASSED", r.stdout)

    def test_smoke_negative_checks_do_not_pass_on_arbitrary_failure(self):
        text = read("smoke.sh")
        # 어떤 실패든 "ok"로 세는 도우미가 남아 있으면 안 된다(컨테이너가 죽어도 통과하는 시험이 된다).
        self.assertNotIn("check_not", text)
        self.assertIn("denied()", text)
        # 교차 영역 자격 증명 시험은 인증 실패 사유를, 앱 역할 권한 시험은 권한 거부 사유를 요구한다.
        self.assertRegex(text, r"denied \"공개 DB 자격으로 개인 DB에 들어갈 수 없다\(관리\)\" 'password authentication failed")
        self.assertRegex(text, r"denied \"앱 역할은 관리용 DB에 접속할 수 없다\(공개\)\" 'permission denied for database'")
        # 영역 간 도달 불가는 pg_isready의 "응답 없음"(종료 코드 2)만 인정한다. 0·1은 닿은 것이고 그 밖은 격리가 아닌 오류다.
        self.assertIn("unreachable()", text)
        self.assertRegex(text, r"(?m)^\s+2\) echo \"ok")
        self.assertRegex(text, r"(?m)^\s+0\|1\) echo \"FAIL")
        self.assertRegex(text, r"(?m)^\s+\*\) echo \"FAIL")
        self.assertRegex(text, r'unreachable "공개 DB 컨테이너에서 개인 DB 서버 주소에 닿지 않는다" dc exec -T db-public pg_isready')
        # 신원 파일은 비root 컨테이너 사용자로도 실제로 읽어 본다.
        self.assertIn("--user 65534:65534", text)
        self.assertIn("LIVE: PASSED", text)

    def test_smoke_helpers_reject_wrong_kinds_of_failure(self):
        # smoke.sh의 부정 검사 도우미를 그대로 떼어 가짜 명령으로 돌린다: 올바른 사유의 실패만 ok, 그 밖(다른 오류·성공·명령 없음)은 FAIL.
        text = read("smoke.sh")
        defs = "".join(re.findall(r"(?ms)^((?:denied|unreachable)\(\) \{.*?^\}\n)", text))
        self.assertIn("denied()", defs)
        self.assertIn("unreachable()", defs)

        def run(call):
            r = subprocess.run(["bash", "-c", f"fail=0\n{defs}\n{call}\necho fail=$fail"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout

        self.assertIn("ok   a\nfail=0", run("denied a 'permission denied' sh -c 'echo permission denied for database >&2; exit 1'"))
        self.assertIn("FAIL b (거부 사유가 아닌 오류)\nfail=1", run("denied b 'permission denied' sh -c 'echo connection refused >&2; exit 2'"))
        self.assertIn("FAIL c (거부되지 않음)\nfail=1", run("denied c 'permission denied' sh -c 'echo permission denied; exit 0'"))
        self.assertIn("FAIL d (거부 사유가 아닌 오류)\nfail=1", run("denied d 'permission denied' no-such-command-onjeon"))
        self.assertIn("ok   e\nfail=0", run("unreachable e sh -c 'exit 2'"))
        for rc in (0, 1):
            self.assertIn(f"FAIL f (닿았다: pg_isready 종료 코드 {rc})\nfail=1", run(f"unreachable f sh -c 'exit {rc}'"))
        for rc in (3, 126, 127):
            self.assertIn(f"FAIL g (격리가 아닌 오류: 종료 코드 {rc})\nfail=1", run(f"unreachable g sh -c 'exit {rc}'"))
        self.assertIn("FAIL h (격리가 아닌 오류: 종료 코드 127)\nfail=1", run("unreachable h no-such-command-onjeon"))

    def test_down_refuses_unknown_option(self):
        r = subprocess.run(["bash", str(COMPOSE / "down.sh"), "--wipe"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
