#!/usr/bin/env bash
# 로컬 스택을 내린다: bash infra/compose/down.sh
# 기본은 컨테이너와 네트워크만 지우고 데이터 볼륨은 남긴다. --purge는 볼륨과 생성 파일(.generated)까지 지운다.
# .env는 지우지 않는다: 볼륨에 남은 DB 비밀번호와 짝이므로, 볼륨을 남긴 채 .env만 지우면 접속할 수 없게 된다.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

purge=0
case "${1:-}" in
  "") ;;
  --purge) purge=1 ;;
  *) die "usage: down.sh [--purge]" ;;
esac

need_docker
# .env가 없으면 compose가 필수 변수 오류를 내므로, 내릴 대상도 없는 경우다.
[ -f "$ENV_FILE" ] || { echo "down: $ENV_FILE 이 없어 내릴 스택이 없다"; exit 0; }
# 신원 파일이 없어도 compose 해석이 되도록 빈 파일을 두었다가 정리한다.
mkdir -p "$GENERATED_DIR"
[ -f "$S3_CONFIG_FILE" ] || : >"$S3_CONFIG_FILE"
if [ "$purge" = 1 ]; then
  dc --profile check down --volumes --remove-orphans
  rm -rf "$GENERATED_DIR"
  echo "down: 컨테이너·네트워크·볼륨·생성 파일을 지웠다"
else
  dc --profile check down --remove-orphans
  echo "down: 컨테이너·네트워크를 지웠다 (데이터 볼륨은 남김)"
fi
