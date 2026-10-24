#!/usr/bin/env bash
# 공개 영역 DB(그리고 같은 DB의 criteria 스키마)에 스키마와 권한을 적용한다. 접속 정보는 psql 환경 변수(PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD) 또는
# 첫 인자의 접속 URL로 준다. 비밀번호를 명령줄에 쓰지 말고 환경 변수로 준다. 관리 역할(역할·스키마 생성 권한)로 실행한다.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target=()
[ $# -ge 1 ] && target=(--dbname "$1")
run() { psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet --single-transaction "${target[@]}" -f "$1"; }
run "$here/00_roles.sql"
run "$here/01_schema.sql"
run "$here/../criteria/01_criteria.sql"
run "$here/02_grants.sql"
run "$here/../criteria/02_grants.sql"
