#!/usr/bin/env bash
# 시험: bash infra/compose/smoke.sh
#  1) 정적 시험(docker 불필요): 자격 증명 비노출, 포트·이미지, 영역 분리 구성, 환경 파일 생성, 신원 파일 생성.
#  2) 실제 기동 시험(docker compose 필요): 격리된 프로젝트로 두 번 올리고, 영역별 접속·큐·객체 권한과
#     영역 간 거부를 확인하고, 내린 뒤 컨테이너·볼륨이 남지 않았는지 확인한다.
# docker가 없으면 2)는 "SKIPPED"로 출력하고 통과로 세지 않는다. 그 환경에서 막으려면 ONJEON_SMOKE_REQUIRE_DOCKER=1.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ONJEON_SMOKE_SKIP_STATIC=1은 정적 시험이 smoke.sh 자신을 다시 부를 때 되풀이를 막는 용도다.
if [ "${ONJEON_SMOKE_SKIP_STATIC:-0}" != 1 ]; then
  echo "== 1) 정적 시험 =="
  python3 -I -m unittest discover -s "$HERE/tests" -t "$HERE/tests" -v
fi

echo "== 2) 실제 기동 시험 =="
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "LIVE: SKIPPED (docker compose 없음). 한 명령 기동·종료와 영역 분리는 이 환경에서 실행으로 확인하지 못했다."
  if [ "${ONJEON_SMOKE_REQUIRE_DOCKER:-0}" = 1 ]; then
    echo "ONJEON_SMOKE_REQUIRE_DOCKER=1 이므로 실패로 처리한다." >&2
    exit 1
  fi
  exit 0
fi

# 개발용 스택(.env, 볼륨, 포트)을 건드리지 않도록 상태 디렉터리·프로젝트 이름·포트를 따로 쓴다.
STATE="$(mktemp -d "${TMPDIR:-/tmp}/onjeon-compose-smoke.XXXXXX")"
export ONJEON_COMPOSE_STATE_DIR="$STATE"
PROJECT="onjeon-smoke-$$"
# shellcheck source=lib.sh
. "$HERE/lib.sh"

cleanup() {
  status=$?
  bash "$HERE/down.sh" --purge >/dev/null 2>&1 || true
  rm -rf "$STATE"
  exit "$status"
}
trap cleanup EXIT

ensure_env
sed -i -e "s/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME=$PROJECT/" \
       -e 's/^PUBLIC_DB_PORT=.*/PUBLIC_DB_PORT=/' -e 's/^PRIVATE_DB_PORT=.*/PRIVATE_DB_PORT=/' \
       -e 's/^S3_API_PORT=.*/S3_API_PORT=/' "$ENV_FILE"

fail=0
check() { # check <label> <command...>
  label="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "ok   $label"; else echo "FAIL $label"; fail=1; fi
}
check_not() {
  label="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "FAIL $label"; fail=1; else echo "ok   $label"; fi
}

echo "-- 한 명령으로 기동 (두 번: 멱등)"
bash "$HERE/up.sh"
bash "$HERE/up.sh" >/dev/null
echo "ok   up.sh 두 번 실행"

# 기동 중 .env가 바뀌지 않았는지(두 번째 실행이 자격 증명을 새로 만들지 않는지)
pub_admin_user="$(env_get PUBLIC_DB_ADMIN_USER)"; pub_admin_pw="$(env_get PUBLIC_DB_ADMIN_PASSWORD)"
pub_app_user="$(env_get PUBLIC_DB_APP_USER)";     pub_app_pw="$(env_get PUBLIC_DB_APP_PASSWORD)"
prv_admin_user="$(env_get PRIVATE_DB_ADMIN_USER)"; prv_admin_pw="$(env_get PRIVATE_DB_ADMIN_PASSWORD)"
prv_app_user="$(env_get PRIVATE_DB_APP_USER)";     prv_app_pw="$(env_get PRIVATE_DB_APP_PASSWORD)"
pub_db="$(env_get PUBLIC_DB_NAME)"; prv_db="$(env_get PRIVATE_DB_NAME)"

psql_in() { # psql_in <service> <user> <password> <db> <sql>
  dc exec -T -e PGPASSWORD="$3" "$1" psql -h 127.0.0.1 -U "$2" -d "$4" -v ON_ERROR_STOP=1 -tA -c "$5"
}

echo "-- 자격 증명 분리"
dups="$(grep -E '_(PASSWORD|SECRET_KEY|ACCESS_KEY)=' "$ENV_FILE" | cut -d= -f2- | sort | uniq -d | wc -l)"
empties="$(grep -E '_(PASSWORD|SECRET_KEY|ACCESS_KEY)=$' "$ENV_FILE" | wc -l)"
[ "$dups" = 0 ] && [ "$empties" = 0 ] && echo "ok   비밀값이 모두 채워져 있고 서로 다르다" || { echo "FAIL 비밀값 중복 또는 빈 값"; fail=1; }
[ "$pub_admin_pw" != "$prv_admin_pw" ] && [ "$pub_app_pw" != "$prv_app_pw" ] && [ "$pub_admin_user" != "$prv_admin_user" ] \
  && echo "ok   공개·개인 DB의 사용자와 비밀번호가 다르다" || { echo "FAIL 공개·개인 DB 자격 증명이 같다"; fail=1; }

echo "-- 영역별 DB"
[ "$(psql_in db-public "$pub_app_user" "$pub_app_pw" "$pub_db" "SELECT current_setting('onjeon.zone')")" = public ] \
  && echo "ok   공개 DB의 영역 표지" || { echo "FAIL 공개 DB의 영역 표지"; fail=1; }
[ "$(psql_in db-private "$prv_app_user" "$prv_app_pw" "$prv_db" "SELECT current_setting('onjeon.zone')")" = private ] \
  && echo "ok   개인 DB의 영역 표지" || { echo "FAIL 개인 DB의 영역 표지"; fail=1; }
# 넣고, SKIP LOCKED로 하나 꺼내 running으로 바꾼 뒤 되돌린다(데이터를 남기지 않는다).
queue_sql="BEGIN; INSERT INTO queue.jobs (queue_name) VALUES ('smoke'); UPDATE queue.jobs SET state = 'running', locked_by = 'smoke', attempts = attempts + 1 WHERE id = (SELECT id FROM queue.jobs WHERE queue_name = 'smoke' AND state = 'ready' AND run_after <= now() ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1); ROLLBACK;"
queue_ok() { local out; out="$(psql_in "$@")" && grep -qx 'UPDATE 1' <<<"$out"; }
check "공개 DB 큐에 앱 역할이 넣고 꺼낸다" queue_ok db-public "$pub_app_user" "$pub_app_pw" "$pub_db" "$queue_sql"
check "개인 DB 큐에 앱 역할이 넣고 꺼낸다" queue_ok db-private "$prv_app_user" "$prv_app_pw" "$prv_db" "$queue_sql"
check_not "앱 역할은 관리용 DB에 접속할 수 없다(공개)" psql_in db-public "$pub_app_user" "$pub_app_pw" postgres "SELECT 1"
check_not "앱 역할은 관리용 DB에 접속할 수 없다(개인)" psql_in db-private "$prv_app_user" "$prv_app_pw" postgres "SELECT 1"
check_not "공개 DB 앱 역할은 테이블을 만들 수 없다" psql_in db-public "$pub_app_user" "$pub_app_pw" "$pub_db" "CREATE TABLE public.probe (x int)"
check_not "개인 DB 앱 역할은 테이블을 만들 수 없다" psql_in db-private "$prv_app_user" "$prv_app_pw" "$prv_db" "CREATE TABLE public.probe (x int)"
[ "$(psql_in db-public "$pub_app_user" "$pub_app_pw" "$pub_db" "SELECT rolsuper FROM pg_roles WHERE rolname = current_user")" = f ] \
  && echo "ok   앱 역할은 슈퍼유저가 아니다" || { echo "FAIL 앱 역할이 슈퍼유저"; fail=1; }
check_not "공개 DB 자격으로 개인 DB에 들어갈 수 없다(관리)" psql_in db-private "$pub_admin_user" "$pub_admin_pw" "$prv_db" "SELECT 1"
check_not "공개 DB 자격으로 개인 DB에 들어갈 수 없다(앱)"   psql_in db-private "$pub_app_user" "$pub_app_pw" "$prv_db" "SELECT 1"
check_not "개인 DB 자격으로 공개 DB에 들어갈 수 없다(관리)" psql_in db-public "$prv_admin_user" "$prv_admin_pw" "$pub_db" "SELECT 1"
check_not "개인 DB 자격으로 공개 DB에 들어갈 수 없다(앱)"   psql_in db-public "$prv_app_user" "$prv_app_pw" "$pub_db" "SELECT 1"
check_not "공개 DB 컨테이너에서 개인 DB 서버가 보이지 않는다" dc exec -T db-public pg_isready -h db-private -t 2
check_not "개인 DB 컨테이너에서 공개 DB 서버가 보이지 않는다" dc exec -T db-private pg_isready -h db-public -t 2

echo "-- 객체 저장소 영역 권한"
if dc --profile check run --rm -T s3-check; then echo "ok   객체 저장소 권한 분리"; else echo "FAIL 객체 저장소 권한 분리"; fail=1; fi

echo "-- 내리기"
bash "$HERE/down.sh" --purge
left="$(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT" | wc -l)"
vols="$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" | wc -l)"
nets="$(docker network ls -q --filter "label=com.docker.compose.project=$PROJECT" | wc -l)"
[ "$left" = 0 ] && [ "$vols" = 0 ] && [ "$nets" = 0 ] && echo "ok   내린 뒤 컨테이너·볼륨·네트워크가 남지 않았다" \
  || { echo "FAIL 남은 자원: 컨테이너 $left, 볼륨 $vols, 네트워크 $nets"; fail=1; }

if [ "$fail" = 0 ]; then echo "LIVE: PASSED"; else echo "LIVE: FAILED" >&2; exit 1; fi
