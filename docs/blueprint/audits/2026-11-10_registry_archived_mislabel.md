# Audit 5 — 공시 보관 오표기·빈 접근 로그의 CLI 재검증

대상: `audit5-registry-archived-mislabel`, `tools/registry_normalize.py`.
연결: Blueprint A1·Q7·L0/L1·I6(근거 보존 기반)·V0/M1, 09 제품 목적 대응표 P01·P02.

작업 시작 시 [Audit 2 정정](2026-10-27_registry_archived_overclaim.md),
[Audit 3 실제 8행 회귀](2026-10-28_registry_archived_mislabel.md),
[Audit 4 빈 로그 처리·원자적 저장·CI](2026-11-03_registry_normalize_tests.md)가 이미 반영돼 있었다.
이번 작업은 기존 구현을 다시 수정했다고 주장하지 않고, 실제 CLI를 통한 두 결함의 결합 회귀와 실행 증거를 추가한다.

`disclosure()`는 접근 확인만으로 `archived`를 만들지 않는다. 공시 URL이 있고
`disclosure_access=reachable`이면 `disclosure_status=unqueried`와
`공시 URL 접근 확인(reachable). 원문 무결성 검사·불변 보관 전`을 기록한다.
`normalize_access_log()`는 빈 파일·헤더만 있는 CSV에서 0을 반환하고 파일을 쓰지 않는다.
`archived`의 정본 정의는 원문을 받아 무결성 검사 후 불변 보관한 상태다.
`host_access.reachable.maps_to=archived` 메타데이터는 이 도구에서 보관 증거로 사용하지 않는다.

[신규 CLI 회귀 시험](../../../tools/tests/test_registry_normalize.py)의
`RegistryCli.test_repairs_legacy_registry_with_empty_access_log_from_another_directory`는 다음을 확인한다.

1. 실제 원장 네 파일·스크립트·어휘 정본을 임시 트리에 복사한다. 실제 보험사 53행 중 접근 확인 8행만 과거 `archived`·빈 사유로 되돌린다.
2. 접근 로그를 0바이트 또는 헤더만 있는 CSV로 바꾼 뒤 저장소 루트와 다른 디렉터리에서 Python 프로세스로 CLI를 실행한다.
3. 정상 종료와 출력 행 수 `53 / 16 / 49 / 0`을 확인한다. 정정된 보험사 파일이 현재 정본과 바이트 단위로 같아야 하므로 나머지 45행과 접근 상세·URL·시각·메모 등 다른 열도 보존해야 한다.
4. 다른 원장 두 파일과 빈 로그가 바이트 그대로 유지되고 임시 CSV가 남지 않아야 한다. 두 번째 CLI 실행도 같은 출력을 내고 모든 파일이 같아야 한다. 저장소 원본 네 CSV도 변하지 않아야 한다.

[변이 검사](../../../tools/evidence/audit5-registry-archived-mislabel/mutation_check.py)는
시험이 만드는 임시 스크립트만 변경한다. `reachable → archived` 분기를 되살리면
두 로그 형태·각 두 실행에서 총 4개 바이트 대조가 실패한다. 빈 로그 조기 반환을
제거하면 두 형태 모두 `IndexError`와 비정상 CLI 종료를 검출한다.
이 실패는 의도한 회귀 검출이며 현재 구현은 신규 시험을 통과한다.

실행 명령·결과·로그는 [Audit 5 작업 증거](../../../tools/evidence/audit5-registry-archived-mislabel/README.md)에 기록한다.
기존 전용 CI 단계가 같은 시험 파일을 실행하므로 새 시험도 포함된다. GitHub CI 실행 결과는 주장하지 않는다.
실제 원장 데이터와 정규화기 동작은 변경하지 않았다.

이 증거는 P01·P02의 원장 도구 finding 해결에 한정된다. 실제 상품·특약 분모,
원문 불변 보관·확보율, 트윈·소비자 화면 또는 첫 출시 완료를 증명하지 않는다.
제품 완료는 계속 09의 완료 증거와 T-OP-08로 판정한다.
