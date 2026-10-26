# Audit 2: R2 비밀값의 워크플로 단계 범위 제한

기록일: 2026-10-26. 노드: `audit2-ci-secrets-step-scope`.

## 발견과 수정

`sources.yml`의 `reproduce.env`가 R2 endpoint·검증용 키 쌍·예산 원장 쓰기용 키 쌍을 작업 전체에 제공했다. 의존성 설치와 checkout·artifact 액션에도 같은 환경이 상속되는 범위 문제였다.

[sources.yml](../../../.github/workflows/sources.yml)에서 다섯 비밀값 참조를 `Every archived key matches the pinned listing`과 `Reproduce from the archive`의 개별 `env`로 옮겼다. 두 단계 모두 원본을 읽고 예산 예약·정산을 원장에 기록하므로 검증용·원장용 키가 필요하다. 작업 공통 `env`에는 비밀값이 아닌 `JOB` 경로만 남는다. 설치·checkout·artifact·detect 단계에는 R2 비밀값을 제공하지 않는다. 수동 실행, 버킷 변수 관문, 예산 동시 실행 제한, 실행 시간 제한, OCR 옵션, `always()` 및 보고서 경로는 유지했다.

이 작업의 시작 상태에서 두 워크플로의 모든 액션 참조는 이미 전체 40자리 SHA로 고정되어 있었고 [ci.yml](../../../.github/workflows/ci.yml)의 최상위 권한도 이미 `contents: read`였다. 해당 설정은 유지하고 기존 회귀 검사로 확인했다. 버전 태그나 SHA를 조회하기 위한 GitHub 호출은 하지 않았다.

## 회귀 시험과 증거

[test_workflow_secret_scope.py](../../../tools/tests/test_workflow_secret_scope.py)는 실제 `sources.yml`의 두 소비 단계에 각각 정확한 다섯 바인딩이 있는지 검사한다. 다른 위치의 비밀값 참조·자격 환경변수 정의를 거부하며, 작업/워크플로 범위 복원, 설치·액션·다른 작업에 노출, 바인딩 누락·중복·오연결, 소비 단계 누락·중복을 변이 시험으로 검사한다. 기존 Python CI 전체 시험에서 자동 발견된다. 표준 라이브러리만 쓰며 현재의 블록형 단계·환경변수 배치를 검사하는 계약 시험이다. 일반 YAML 파서가 아니므로 배치를 바꾸면 검사도 검토해야 한다.

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_workflow_secret_scope.py -v` (수정 전) | 8개 중 실제 워크플로 검사 1개 실패로 작업 범위 노출 재현: [before.log](../../../tools/evidence/audit2-ci-secrets-step-scope/before.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v` | 32개 통과. 새 범위 검사 8개와 기존 SHA·토큰 권한 검사 포함: [workflow-tests.log](../../../tools/evidence/audit2-ci-secrets-step-scope/workflow-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 923개 실행·실패 0·기존 skip 6개: [python-tests.log](../../../tools/evidence/audit2-ci-secrets-step-scope/python-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 정합성 통과(정적 검사): [product-purpose.log](../../../tools/evidence/audit2-ci-secrets-step-scope/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit2-ci-secrets-step-scope/spec-check.log) |
| `python3 tools/vocab_check.py` | 통과: [vocabulary.log](../../../tools/evidence/audit2-ci-secrets-step-scope/vocabulary.log) |
| `python3 tools/validation_check.py` 및 `--selftest` | 내부 정합성·변이 38개 통과: [validation.log](../../../tools/evidence/audit2-ci-secrets-step-scope/validation.log), [validation-selftest.log](../../../tools/evidence/audit2-ci-secrets-step-scope/validation-selftest.log) |
| `cargo fmt --all -- --check` | 종료 코드 0: [fmt.log](../../../tools/evidence/audit2-ci-secrets-step-scope/fmt.log) |
| `cargo clippy --all-targets --offline -- -D warnings` | 통과: [clippy.log](../../../tools/evidence/audit2-ci-secrets-step-scope/clippy.log) |
| `cargo test --all --offline` | Rust 단위·통합·문서 시험 447개 통과·실패 0·기존 ignored 1개: [rust-tests.log](../../../tools/evidence/audit2-ci-secrets-step-scope/rust-tests.log) |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --offline --target-dir target/audit2-ontology` 및 `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit2-ontology/debug/ontology-case-runner` | 빌드·온톨로지 검사 통과: [ontology-build.log](../../../tools/evidence/audit2-ci-secrets-step-scope/ontology-build.log), [ontology-check.log](../../../tools/evidence/audit2-ci-secrets-step-scope/ontology-check.log) |

추가 검사 `python3 -I -m unittest discover -s tools/ci/tests -v`는 20개 중 2개 실패했다([ci-tests.log](../../../tools/evidence/audit2-ci-secrets-step-scope/ci-tests.log)). 두 실패는 `check_deps`의 기존 경계 위반 3건(온톨로지의 엔진 dev 의존성 1건·시험 코드 import 2건)을 보고한다. 작업 시작 HEAD `5e77d80961c591f9dd7801fa7d0ebd6ccce80edd`를 작업 트리 내부의 무시되는 `target/audit2-ci-baseline`에 `git archive HEAD`로 복원하고 `python3 -I -m unittest discover -s target/audit2-ci-baseline/tools/ci/tests -v`를 실행해 같은 2개 실패·같은 3개 위반을 확인했다([baseline-ci-tests.log](../../../tools/evidence/audit2-ci-secrets-step-scope/baseline-ci-tests.log)). 이 별도 검사군은 현재 `ci.yml` 실행 항목이 아니며, 이번 노드는 경계 규칙이나 온톨로지를 변경하지 않았다.

SHA 고정 6곳·`ci.yml` 권한·실행 스크립트/조건 보존·보호 파일 무변경·문서 링크·공백 검사는 [final-checks.log](../../../tools/evidence/audit2-ci-secrets-step-scope/final-checks.log)에 기록했다.

## 제품 목적과 한계

BLUEPRINT A1~A4, L1·L2, M0 및 [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P03의 원본 보존·재현 검증을 지원하는 CI 권한 범위 보강이다. 로컬 정적·회귀 증거이며 실제 GitHub Actions 실행이나 R2 목록 대조, P03 또는 출시 완료 증거를 대체하지 않는다. 비밀값 조회·외부 R2 접근·commit·push는 수행하지 않았다. 단계별 환경변수 범위 제한은 의존성 전체의 신뢰성 검증이나 단계 사이의 프로세스 격리를 보장하지 않는다.
