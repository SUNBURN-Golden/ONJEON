#!/usr/bin/env bash
# 시험: bash services/docproc/test_sandbox.sh
#  1) 정적 시험(docker 불필요): 추출기 단위 시험(합성 PDF, 인용-좌표 대조, 지문 fp-0.1,
#     ClauseOccurrence ID 형식·재추출 신규 ID, 격리 구성 단언)을 실행한다.
#  2) 실제 격리 시험(docker compose 필요): tests/container_network.py로 이미지를 빌드하고
#     network_mode:none 컨테이너 안에서 외부 IPv4·IPv6 연결 시도가 실패하는지 확인한다(I13).
# docker가 없으면 2)를 실행하지 못하므로 "LIVE: SKIPPED"를 출력한다. 이것은 I13 확인의
# 근거가 아니다(완료는 "LIVE: PASSED"). 격리 실행이 의무인 환경(CI 증거 채취 등)에서는
# DOCPROC_SANDBOX_REQUIRE_LIVE=1로 docker 부재를 실패(종료 코드 1)로 만든다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

echo "== 1) 정적 시험 =="
python3 -B -m unittest discover -s services/docproc/tests -v

echo "== 2) 실제 격리 시험 =="
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  if [ "${DOCPROC_SANDBOX_REQUIRE_LIVE:-0}" = 1 ]; then
    echo "LIVE: FAILED (docker compose 없음, DOCPROC_SANDBOX_REQUIRE_LIVE=1). I13 격리 시험을 실행하지 못했다." >&2
    exit 1
  fi
  echo "LIVE: SKIPPED (docker compose 없음). I13 격리는 실행으로 확인하지 못했다. 증거가 필요하면 DOCPROC_SANDBOX_REQUIRE_LIVE=1."
  exit 0
fi

python3 -B services/docproc/tests/container_network.py
echo "LIVE: PASSED"
