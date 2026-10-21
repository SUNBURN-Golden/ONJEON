#!/usr/bin/env bash
# 한 명령으로 로컬 스택을 올린다: bash infra/compose/up.sh
# 처음에는 .env(무작위 자격 증명)와 객체 저장소 신원 파일을 만든다. 이미 있으면 그대로 쓴다. 여러 번 실행해도 안전하다.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need_docker
ensure_env
render_s3_config

dc up -d --wait db-public db-private s3
dc run --rm -T s3-init

public_port="$(dc port db-public 5432 | sed 's/.*://')"
private_port="$(dc port db-private 5432 | sed 's/.*://')"
s3_port="$(dc port s3 8333 | sed 's/.*://')"
cat <<EOF
up: 로컬 스택이 떴다 (자격 증명: $ENV_FILE)
  공개 DB   127.0.0.1:$public_port  db=$(env_get PUBLIC_DB_NAME)  user=$(env_get PUBLIC_DB_APP_USER)
  개인 DB   127.0.0.1:$private_port  db=$(env_get PRIVATE_DB_NAME)  user=$(env_get PRIVATE_DB_APP_USER)
  객체 저장소 http://127.0.0.1:$s3_port  (공개 영역·개인 영역 신원이 따로 있다)
내리기: bash infra/compose/down.sh   (데이터까지 지우기: down.sh --purge)
EOF
