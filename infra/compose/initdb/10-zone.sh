#!/bin/sh
# postgres 이미지가 빈 데이터 디렉터리의 첫 기동에서 한 번 실행한다. 영역(public/private)은 환경 변수로 정한다.
# 비밀번호는 환경 변수로만 읽고(psql \getenv) 명령줄·로그에 싣지 않는다.
set -eu
: "${POSTGRES_USER:?}" "${POSTGRES_DB:?}" "${APP_DB_USER:?}" "${APP_DB_PASSWORD:?}"
case "${ONJEON_ZONE:-}" in
  public|private) ;;
  *) echo "ONJEON_ZONE must be public or private" >&2; exit 1 ;;
esac
psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -f /opt/onjeon/zone-init.psql
