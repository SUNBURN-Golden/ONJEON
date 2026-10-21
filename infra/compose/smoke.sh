#!/usr/bin/env bash
# 시험: bash infra/compose/smoke.sh
#  1) 정적 시험(docker 불필요): 자격 증명 비노출, 포트·이미지, 영역 분리 구성, 환경 파일 생성, 신원 파일 생성.
#  2) 실제 기동 시험(docker compose 필요): 격리된 프로젝트로 두 번 올리고, 영역별 접속·큐·객체 권한과
#     영역 간 거부를 확인하고, 내린 뒤 컨테이너·볼륨이 남지 않았는지 확인한다.
#     부정 검사는 "실패했다"로 통과하지 않는다: 거부 사유(denied), 응답 없음(unreachable), 접근 거부 응답(check-objects.sh)을 요구한다.
# docker가 없으면 2)를 실행하지 못한 것이므로 실패(종료 코드 1)다. 정적 시험만 돌리려면 ONJEON_SMOKE_STATIC_ONLY=1:
# 그때는 "LIVE: SKIPPED"를 출력하고 0으로 끝나지만, 이것은 과제 완료의 근거가 아니다(완료는 "LIVE: PASSED").
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ONJEON_SMOKE_SKIP_STATIC=1은 정적 시험이 smoke.sh 자신을 다시 부를 때 되풀이를 막는 용도다.
if [ "${ONJEON_SMOKE_SKIP_STATIC:-0}" != 1 ]; then
  echo "== 1) 정적 시험 =="
  python3 -I -m unittest discover -s "$HERE/tests" -t "$HERE/tests" -v
fi

echo "== 2) 실제 기동 시험 =="
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  if [ "${ONJEON_SMOKE_STATIC_ONLY:-0}" = 1 ]; then
    echo "LIVE: SKIPPED (ONJEON_SMOKE_STATIC_ONLY=1, docker compose 없음). 기동·영역 분리는 실행으로 확인하지 못했다."
    exit 0
  fi
  echo "LIVE: FAILED (docker compose 없음). 실제 기동 시험을 실행하지 못했다. 정적 시험만 돌리려면 ONJEON_SMOKE_STATIC_ONLY=1." >&2
  exit 1
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
# unreachable <label> <command...>: pg_isready가 "응답 없음"(종료 코드 2)으로 끝나야 통과한다.
# 0(수락)·1(응답은 있으나 거부)은 닿은 것이다. 3(시도 못 함)·126·127(명령 없음)·그 밖(컨테이너 정지 등)은 격리의 근거가 아니다.
unreachable() {
  label="$1"; shift
  rc=0; "$@" >/dev/null 2>&1 || rc=$?
  case "$rc" in
    2) echo "ok   $label" ;;
    0|1) echo "FAIL $label (닿았다: pg_isready 종료 코드 $rc)"; fail=1 ;;
    *) echo "FAIL $label (격리가 아닌 오류: 종료 코드 $rc)"; fail=1 ;;
  esac
}
# denied <label> <정규식> <command...>: 명령이 실패하고 출력이 정규식(거부 사유)에 맞아야 통과한다.
# 컨테이너가 죽었거나 명령이 없어서 실패한 경우를 "거부됨"으로 세지 않기 위해서다.
denied() {
  label="$1"; pattern="$2"; shift 2
  if out="$("$@" 2>&1)"; then echo "FAIL $label (거부되지 않음)"; fail=1
  elif grep -Eqi "$pattern" <<<"$out"; then echo "ok   $label"
  else echo "FAIL $label (거부 사유가 아닌 오류)"; fail=1; fi
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
# grep은 일치가 없으면 1을 돌려주므로(pipefail) 개수는 awk로 센다.
dups="$(grep -E '_(PASSWORD|SECRET_KEY|ACCESS_KEY)=' "$ENV_FILE" | cut -d= -f2- | sort | uniq -d | awk 'END { print NR }')"
empties="$(awk '/_(PASSWORD|SECRET_KEY|ACCESS_KEY)=$/ { n++ } END { print n + 0 }' "$ENV_FILE")"
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
denied "앱 역할은 관리용 DB에 접속할 수 없다(공개)" 'permission denied for database' psql_in db-public "$pub_app_user" "$pub_app_pw" postgres "SELECT 1"
denied "앱 역할은 관리용 DB에 접속할 수 없다(개인)" 'permission denied for database' psql_in db-private "$prv_app_user" "$prv_app_pw" postgres "SELECT 1"
denied "공개 DB 앱 역할은 테이블을 만들 수 없다" 'permission denied' psql_in db-public "$pub_app_user" "$pub_app_pw" "$pub_db" "CREATE TABLE public.probe (x int)"
denied "개인 DB 앱 역할은 테이블을 만들 수 없다" 'permission denied' psql_in db-private "$prv_app_user" "$prv_app_pw" "$prv_db" "CREATE TABLE public.probe (x int)"
[ "$(psql_in db-public "$pub_app_user" "$pub_app_pw" "$pub_db" "SELECT rolsuper FROM pg_roles WHERE rolname = current_user")" = f ] \
  && echo "ok   앱 역할은 슈퍼유저가 아니다" || { echo "FAIL 앱 역할이 슈퍼유저"; fail=1; }
denied "공개 DB 자격으로 개인 DB에 들어갈 수 없다(관리)" 'password authentication failed|no pg_hba.conf entry' psql_in db-private "$pub_admin_user" "$pub_admin_pw" "$prv_db" "SELECT 1"
denied "공개 DB 자격으로 개인 DB에 들어갈 수 없다(앱)" 'password authentication failed|no pg_hba.conf entry' psql_in db-private "$pub_app_user" "$pub_app_pw" "$prv_db" "SELECT 1"
denied "개인 DB 자격으로 공개 DB에 들어갈 수 없다(관리)" 'password authentication failed|no pg_hba.conf entry' psql_in db-public "$prv_admin_user" "$prv_admin_pw" "$pub_db" "SELECT 1"
denied "개인 DB 자격으로 공개 DB에 들어갈 수 없다(앱)" 'password authentication failed|no pg_hba.conf entry' psql_in db-public "$prv_app_user" "$prv_app_pw" "$pub_db" "SELECT 1"
# 도달 가능성으로 본다. 이름 해석은 쓰지 않는다: 일부 환경의 상위 DNS는 모르는 이름에도 응답한다.
# 자기 영역 컨테이너의 실제 IP에는 닿고(대조), 상대 영역 컨테이너의 실제 IP에는 닿지 않아야 한다.
ip_of() { docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(dc ps -q "$1")"; }
pub_ip="$(ip_of db-public)"; prv_ip="$(ip_of db-private)"
[ -n "$pub_ip" ] && [ -n "$prv_ip" ] && [ "$pub_ip" != "$prv_ip" ] && echo "ok   두 DB 컨테이너의 주소가 다르다" || { echo "FAIL DB 컨테이너 주소를 얻지 못했다"; fail=1; }
check "공개 DB 컨테이너는 자기 영역 주소에 닿는다(대조)" dc exec -T db-public pg_isready -h "$pub_ip" -t 3
check "개인 DB 컨테이너는 자기 영역 주소에 닿는다(대조)" dc exec -T db-private pg_isready -h "$prv_ip" -t 3
unreachable "공개 DB 컨테이너에서 개인 DB 서버 주소에 닿지 않는다" dc exec -T db-public pg_isready -h "$prv_ip" -t 3
unreachable "개인 DB 컨테이너에서 공개 DB 서버 주소에 닿지 않는다" dc exec -T db-private pg_isready -h "$pub_ip" -t 3
check "객체 저장소는 두 영역 모두에서 풀린다(대조)" dc exec -T db-public getent hosts s3
check "객체 저장소는 두 영역 모두에서 풀린다(대조, 개인)" dc exec -T db-private getent hosts s3

echo "-- 객체 저장소 신원 파일"
# 신원 파일은 호스트 파일의 바인드 마운트다. 이미지가 비root로 바뀌거나 rootless Docker여도 읽혀야 하므로 임의의 비root 사용자로 읽어 본다.
check "신원 파일은 컨테이너 사용자가 root가 아니어도 읽힌다" \
  dc run --rm -T --no-deps --user 65534:65534 --entrypoint sh s3 -c 'grep -q "\"identities\"" /etc/seaweedfs/s3.json'

echo "-- 개인 DB 서버 로그에 값이 남지 않는다(I11 서버 설정 부분)"
# 값이 오류 본문(타입 변환 오류)과 DETAIL(제약 위반의 "Failing row contains")에 실리는 두 경우를 일으킨다.
marker="LEAKMARK-$(rand_hex 6)"
psql_in db-private "$prv_app_user" "$prv_app_pw" "$prv_db" "INSERT INTO queue.jobs (queue_name, state, payload) VALUES ('smoke', 'running', '{\"k\":\"$marker\"}')" >/dev/null 2>&1 || true
psql_in db-private "$prv_app_user" "$prv_app_pw" "$prv_db" "SELECT '$marker'::int" >/dev/null 2>&1 || true
# 대조: 로그가 살아 있음을 보이려고 접속 실패(FATAL)를 일으킨다.
psql_in db-private "$prv_app_user" "wrong-$marker" "$prv_db" "SELECT 1" >/dev/null 2>&1 || true
sleep 1
prv_log="$(dc logs --no-color db-private 2>&1)"
grep -q "FATAL" <<<"$prv_log" && echo "ok   (대조) 접속 실패(FATAL)는 로그에 남는다" || { echo "FAIL (대조) 로그에 FATAL이 없어 아래 검사가 의미 없다"; fail=1; }
! grep -q "$marker" <<<"$prv_log" && echo "ok   개인 DB 로그에 payload·질의 값이 없다" || { echo "FAIL 개인 DB 로그에 값이 남았다"; fail=1; }
! grep -qE "^.*(ERROR|STATEMENT|DETAIL):" <<<"$prv_log" && echo "ok   개인 DB 로그에 ERROR·STATEMENT·DETAIL 줄이 없다" || { echo "FAIL 개인 DB 로그에 ERROR·STATEMENT·DETAIL 줄이 있다"; fail=1; }

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
