#!/usr/bin/env bash
# up.sh, down.sh, smoke.sh가 공유하는 함수. 직접 실행하지 않는다.
# 상태 파일 위치는 ONJEON_COMPOSE_STATE_DIR(기본: 이 디렉터리)로 바꿀 수 있다. smoke.sh가 격리 실행에 쓴다.

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${ONJEON_COMPOSE_STATE_DIR:-$COMPOSE_DIR}"
ENV_FILE="$STATE_DIR/.env"
GENERATED_DIR="$STATE_DIR/.generated"
S3_CONFIG_FILE="$GENERATED_DIR/s3.json"

# 비밀값이어야 하는 키: 비어 있으면 무작위 값으로 채운다. 접미사로 판별한다.
SECRET_KEY_RE='^[A-Z0-9_]+(_PASSWORD|_SECRET_KEY|_ACCESS_KEY)$'

die() { echo "error: $*" >&2; exit 1; }

# 무작위 16진 문자열 N바이트. 외부 도구에 의존하지 않도록 /dev/urandom을 쓴다.
rand_hex() {
  od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'
}

# .env가 없으면 .env.example을 복사하고, 비어 있는 비밀값만 채운다. 이미 채워진 값은 바꾸지 않는다.
ensure_env() {
  mkdir -p "$STATE_DIR"
  [ -f "$ENV_FILE" ] || { (umask 077; cp "$COMPOSE_DIR/.env.example" "$ENV_FILE"); }
  chmod 600 "$ENV_FILE"
  local tmp key val
  tmp="$(mktemp "$STATE_DIR/.env.XXXXXX")"
  chmod 600 "$tmp"
  while IFS= read -r line || [ -n "$line" ]; do
    key="${line%%=*}"
    if [[ "$line" == *=* && "$key" =~ $SECRET_KEY_RE ]]; then
      val="${line#*=}"
      if [ -z "$val" ]; then
        case "$key" in
          *_ACCESS_KEY) val="$(rand_hex 10)" ;;
          *) val="$(rand_hex 24)" ;;
        esac
        line="$key=$val"
      fi
    fi
    printf '%s\n' "$line" >>"$tmp"
  done <"$ENV_FILE"
  mv "$tmp" "$ENV_FILE"
}

# .env에서 키 하나를 읽는다. 값을 셸로 평가하지 않는다.
env_get() {
  local line
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1)" || true
  printf '%s' "${line#*=}"
}

check_ident() {
  [[ "$2" =~ ^[A-Za-z0-9_-]+$ ]] || die "$1 must match [A-Za-z0-9_-]+ (got an unusable value)"
}

# 객체 저장소 신원 파일을 만든다. 공개 영역 신원은 공개 버킷 둘에만, 개인 영역 신원은 개인 버킷에만 권한이 있다.
# 관리 신원은 버킷 생성과 시험 정리에만 쓴다. 파일에는 비밀키가 들어 있으므로 .generated(gitignore)에만 둔다.
render_s3_config() {
  local k
  for k in S3_ADMIN_ACCESS_KEY S3_ADMIN_SECRET_KEY S3_PUBLIC_ACCESS_KEY S3_PUBLIC_SECRET_KEY \
           S3_PRIVATE_ACCESS_KEY S3_PRIVATE_SECRET_KEY S3_PUBLIC_RAW_BUCKET S3_PUBLIC_DERIVED_BUCKET S3_PRIVATE_BUCKET; do
    [ -n "$(env_get "$k")" ] || die "$k is empty in $ENV_FILE"
    check_ident "$k" "$(env_get "$k")"
  done
  local raw derived private
  raw="$(env_get S3_PUBLIC_RAW_BUCKET)"; derived="$(env_get S3_PUBLIC_DERIVED_BUCKET)"; private="$(env_get S3_PRIVATE_BUCKET)"
  [ "$raw" != "$derived" ] && [ "$raw" != "$private" ] && [ "$derived" != "$private" ] \
    || die "bucket names must be three different names"
  mkdir -p "$GENERATED_DIR"
  chmod 700 "$GENERATED_DIR"
  (umask 077; : >"$S3_CONFIG_FILE.tmp")
  {
    printf '{\n  "identities": [\n'
    printf '    {"name": "admin", "credentials": [{"accessKey": "%s", "secretKey": "%s"}], "actions": ["Admin", "Read", "Write", "List", "Tagging"]},\n' \
      "$(env_get S3_ADMIN_ACCESS_KEY)" "$(env_get S3_ADMIN_SECRET_KEY)"
    printf '    {"name": "public-zone", "credentials": [{"accessKey": "%s", "secretKey": "%s"}], "actions": ["Read:%s", "Write:%s", "List:%s", "Read:%s", "Write:%s", "List:%s"]},\n' \
      "$(env_get S3_PUBLIC_ACCESS_KEY)" "$(env_get S3_PUBLIC_SECRET_KEY)" "$raw" "$raw" "$raw" "$derived" "$derived" "$derived"
    printf '    {"name": "private-zone", "credentials": [{"accessKey": "%s", "secretKey": "%s"}], "actions": ["Read:%s", "Write:%s", "List:%s"]}\n' \
      "$(env_get S3_PRIVATE_ACCESS_KEY)" "$(env_get S3_PRIVATE_SECRET_KEY)" "$private" "$private" "$private"
    printf '  ]\n}\n'
  } >"$S3_CONFIG_FILE.tmp"
  chmod 600 "$S3_CONFIG_FILE.tmp"
  mv "$S3_CONFIG_FILE.tmp" "$S3_CONFIG_FILE"
}

# docker compose 호출. 프로젝트 디렉터리와 환경 파일을 고정한다.
dc() {
  local project
  project="$(env_get COMPOSE_PROJECT_NAME)"
  # -p를 명시한다: 격리 실행(smoke.sh)이 개발용 스택과 같은 프로젝트 이름으로 섞이지 않게 한다.
  ONJEON_S3_CONFIG="$S3_CONFIG_FILE" docker compose --project-directory "$COMPOSE_DIR" \
    -p "${project:-onjeon-local}" --env-file "$ENV_FILE" -f "$COMPOSE_DIR/docker-compose.yml" "$@"
}

need_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found"
  docker compose version >/dev/null 2>&1 || die "docker compose v2 plugin not found"
}
