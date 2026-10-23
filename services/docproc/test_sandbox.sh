#!/usr/bin/env bash
# 시험: bash services/docproc/test_sandbox.sh
#  1) 정적 시험(docker 불필요): 추출기 단위 시험(합성 PDF, 인용-좌표 대조, 지문 fp-0.1,
#     ClauseOccurrence ID 형식·재추출 신규 ID, 격리 구성 단언)을 실행한다.
#  2) 실제 시험: 이미지 빌드, native Poppler 24.02 추출 시험, 제어 가능한 IPv4·IPv6
#     서버 양성 대조, 네트워크 활성 변이 실패, network_mode:none 격리를 확인한다(I13).
# 기본은 Docker가 없으면 실패한다. 정적 시험만 필요하면 명시적으로
# DOCPROC_SANDBOX_STATIC_ONLY=1을 쓴다. 이는 수락 증거가 아니다.
# 기본 데몬이 없을 때는 하네스가 작업 트리 안에 전용 임시 데몬을 시작·정리한다.
# dockerd와 비대화식 로컬 실행 권한이 필요하며, 명시한 endpoint는 교체하지 않는다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

echo "== 1) 정적 시험 =="
python3 -B -m unittest discover -s services/docproc/tests -v

echo "== 2) 실제 격리 시험 =="
if [ "${DOCPROC_SANDBOX_STATIC_ONLY:-0}" = 1 ]; then
  if [ "${DOCPROC_SANDBOX_REQUIRE_LIVE:-0}" = 1 ]; then
    echo "LIVE: FAILED (static-only conflicts with required live acceptance)" >&2
    exit 1
  fi
  echo "LIVE: SKIPPED (explicit static-only; not acceptance evidence)"
  exit 0
fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "LIVE: FAILED (docker compose 없음). I13 격리 시험을 실행하지 못했다." >&2
  exit 1
fi

python3 -B services/docproc/tests/container_network.py
echo "LIVE: PASSED"
