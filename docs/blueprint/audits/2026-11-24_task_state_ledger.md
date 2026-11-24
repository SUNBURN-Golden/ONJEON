# Audit 8 — 과제 상태 원장과 출시 증거 판정

T-OP-08의 `purpose-rows-all-closed`와 진척 보고서가 같은 [과제 상태 원장](../../progress/tasks_state.json)을 읽는다. 원장은 등록된 과제 ID별로 관측된 상태, 전체 병합 SHA, 증거 디렉터리 기준 상대 경로를 담는다. 판정기는 각 연결 과제에 유효한 병합 뒤 상태·SHA·증거 파일을 요구하고, `readiness.json`에서 행·기능별 완료 증거와 수락 실행 결과를 확인한다. 갱신 절차와 입력 형식은 [판정기 안내](../../../tools/release_readiness/README.md#version-1-task-ledger)에 있다.

기준 커밋 `8c758444489a45b54c012f97eff5191505138dee`에서 `git log --first-parent --merges --format='%H %s' HEAD`의 과제 브랜치 ID와 기존 병합 목록을 대조했다. 20개 ID와 SHA 전부가 일치했다. 이전 목록은 원장으로 이전했고, 승인 상태와 검토된 출시 증거 경로는 `null`로 두었다. 진척 보고서는 병합 SHA 20/65와 닫힌 목적 행 0/19를 표시했다.

## 1차 수정

기본 Cargo 캐시에서 `serde_json`을 찾지 못해 오프라인 실행기 빌드가 종료 코드 101을 반환했다. 이제 실패한 설정에서 Cargo 진단과 의존성을 준비하는 명령을 확인할 수 있다. 실제 Cargo 잠금 시험은 의존성이 없는 임시 패키지와 빈 Cargo 캐시에서 5초 제한과 잠금 진단을 확인한다.

전체 Python 재실행에는 작업 트리의 Cargo 캐시와 `boto3==1.43.100`을 설치한 가상 환경을 사용했다. `ONJEON_ONTOLOGY_RUNNER`를 해제해 실제 오프라인 빌드를 실행했다. 잠금 시험과 사전 빌드 실행기를 지정하는 CI 경로도 별도로 확인했다. [로컬 시험 준비](../../../README.md#로컬-시험).

## 2차 수정

Python 시험은 통과했지만 이어지는 `cargo fmt --all -- --check`가 `rustup could not choose a version of cargo to run`으로 종료 코드 1을 반환했다. 셸 환경 변수는 새 프로세스에 남지 않으므로, 전역 기본값이 없는 작업 트리에서는 plain `cargo`가 도구 체인을 고르지 못했다. [로컬 시험](../../../README.md#로컬-시험)의 재정의 절차대로 이 작업 트리에 `rustup override set --path "$PWD" 1.98.1`을 등록하고, README가 환경 변수 대신 작업 트리 한정 재정의를 안내하도록 고쳤다. 이후 같은 명령에서 `cargo` 1.98.1이 선택됐다.

## 검증

| 실행 | 관측 결과 |
|---|---|
| `python3 -I tools/release_readiness/check.py` | P행 open=19, closed=0, excluded=0. 기능 open=64, closed=0, excluded=0. 종료 코드 1 |
| `test_release_readiness.py`, `test_purpose_progress.py`, `test_evidence_paths.py` | 37개 통과. 합성 입력에서 정상 원장은 행·기능을 닫는다. 미병합·승인 무효·누락된 SHA·유효하지 않은 증거 파일은 해당 항목을 열어 둔다. 중복·미등록 ID와 잘못된 레코드는 입력 오류를 반환한다. 두 CLI 기본 원장의 판정이 일치하고, 출시 과제는 원장에 쓰기 권한이 없다 |
| `test_audit6_missing_gates.py`, `test_blueprint_current_state.py` | 18개 통과. 라벨 수락 실패·누락을 계속 검출하고 설계도 집계가 실제 판정과 일치한다 |
| `test_ontology_runner_io_error.py` | 설정 회귀 6개 통과. 빈 Cargo 캐시에서 실제 잠금 제한을 확인했다. 사전 빌드 실행기를 지정한 CI 경로에서는 전체 15개 통과 |
| `python3 -m unittest discover -s tools/tests -v` (`boto3==1.43.100`) | 1,779개 실행, 실패 0개. 로컬 원본 보관본이 필요한 사례 5개와 구버전 botocore 동작을 확인하는 사례 1개 건너뜀 |
| 데몬 검증기와 CI 검사기 Python 시험 | 각각 81개와 21개 통과. 데몬 모의 실행도 검사 695개 통과, 필수 시험 ID 33개 전부 실행 |
| `cargo test --all --locked --offline` (Rust 1.98.1) | 537개 통과, 기존 무시 1개 |
| 시나리오 API와 온톨로지 실행기 Cargo 시험 | 각각 4개 통과 |
| `python3 -m unittest discover -s packages/schemas/codegen/tests -v` | 138개 실행, 실패 0개. TypeScript·Dart 도구가 필요한 호환성 시험 2개 건너뜀 |
| 설계 계약 검사, 제품 목적 정적 검사, `validation_check.py --selftest` | 기계 47/47·존재 72/72, 제품 목적 연결 통과, 의도된 변이 40건 검출 |

판정기는 원장의 SHA 형식과 로컬 증거 파일을 검사한다. 통합 담당자가 Git 이력과 승인 기록을 대조하며, T-OP-08이 실제 데이터·화면·출시 증거의 내용을 검토한다.
