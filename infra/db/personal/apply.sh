#!/usr/bin/env bash
# 개인 영역 DB에 스키마와 권한을 적용한다. 공개 영역 DB와 다른 DB(다른 서버)에 적용한다. 접속 정보는 psql 환경 변수 또는 첫 인자의 접속 URL.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target=()
[ $# -ge 1 ] && target=(--dbname "$1")
run() { psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet --single-transaction "${target[@]}" -f "$1"; }
run "$here/00_roles.sql"
run "$here/01_schema.sql"
run "$here/02_grants.sql"
