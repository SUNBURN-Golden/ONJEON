# Audit 8 09 대응표의 시험 담당 과제와 요구 추적 검증

2026-11-24 검증. 비교 기준은 `1945f7afcd504a36f186c6fbba4544e3236afa02`다. [09 제품 목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md).

| 행 | 검증한 연결 |
|---|---|
| P02 | T-DT-04의 `acquisition-reason-not-counted`와 T-AP-04의 `coverage-status-counts-acquired-only` |
| P03 | T-WB-01의 공개 웹 릴리스 이력과 `npm test -- releases` |
| P08 | T-MB-04의 만약에 경계일 화면 시험 `what_if_boundary_days` |
| P16 | T-MB-04의 `decisive-conditions-not-hidden` |
| P18 | R01, 비로그인으로 원문·확인 조건에 도달하는 `entry_points`와 개인 영역 전환 전 미전송 시험 |
| P20 | R19·R20·R22·R23, T-PS-03의 동의·삭제·백업 복원, T-PS-04의 누출 시험, T-OP-05의 안전한 롤백 |

기준 커밋의 09를 임시 파일로 추출해 갱신된 `check_product_purpose.py --purpose <기준 파일>`로 검사했다. P02·P03·P08·P16의 누락 과제 5건, P18에 연결할 익명 열람 과제 3건, 누락 행 P20을 지목하며 종료 코드 1을 반환했다. 현재 표는 동일한 검사에서 종료 코드 0을 반환했다.

회귀 시험은 R01~R26의 대응표 참조를 대조하고, 행에서 담당 과제를 하나씩 빼면 등록부에 과제 ID가 있어도 정적 검사가 실패함을 확인한다. 출시 판정 시험에서는 P20의 과제 상태·증거·성공 로그가 빠지거나 환경이 `fixture`이면 P20이 열린다. PR 본문 검사는 P20을 추적 식별자로 받아들이고 P21을 거부한다.

| 실행 | 결과 |
|---|---|
| `python3 -I tools/ci/check_product_purpose.py` 및 두 추적 검사기의 `--selftest` | 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47, 존재 72/72 통과 |
| `python3 -I tools/release_readiness/progress.py` | P20 포함 0/20 행 닫힘, 20/66 과제 병합 집계 |
| `python3 -I tools/release_readiness/check.py --json` | 예상 종료 코드 1. 행 20개·기능 64개 전체 미완료 |
| 영향 범위 Python 회귀 | 143개 통과 |
| `python -m unittest discover -s tools/tests -v` | 총 1,787개 중 1,778개 통과, 기존 환경 조건으로 6개 건너뜀. 작업 트리 안으로 지정한 `TMPDIR` 때문에 실패한 온톨로지 임시 파일 시험 3개는 해당 모듈 6개를 OS 기본 임시 경로로 재실행해 모두 통과 |
| `python -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 537개 통과, 기존 1개 무시 |
| 시나리오 API와 온톨로지 실행기의 `cargo test --locked --offline` | 각각 4개 통과 |

실제 동의·삭제·복원·누출·롤백 실행 기록은 P20 출시 증거로 수집해야 한다. 이 기록은 대응표와 판정 도구의 감리 수정에 해당한다.
