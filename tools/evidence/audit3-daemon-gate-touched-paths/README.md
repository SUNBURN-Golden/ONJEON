# audit3-daemon-gate-touched-paths

기준 커밋 `e1c5f14c0de0e428e46fcb975e412f909d9557ed` 위 작업 트리의 로컬 실행 증거다. 변경 내용·실행 명령·결과·한계는 [감리 기록](../../../docs/blueprint/audits/2026-10-28_daemon_gate_touched_paths.md)에 있다.

`before.log`는 수정 전 최초 회귀 시험 12개의 실패 기록이고 `focused.log`는 최종 15개 회귀 시험의 통과 기록이다. 전체 데몬 보고서와 소스 해시는 [reports](../../daemon/reports/)에 있다. `ci-tests.log`의 의존성 검사 실패 2개는 `ci-baseline.log`에서 기준 커밋과 같은 위반 3건임을 확인했다. 이 디렉터리의 시험 통과는 제품 출시 완료 증거가 아니다.
