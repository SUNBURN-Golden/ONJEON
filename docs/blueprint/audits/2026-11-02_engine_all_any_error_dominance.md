# Audit 4: `all`·`any` 확정값과 다중 오류 우선순위

검증일: 2026-11-02. 노드: `audit4-engine-all-any-error-dominance`.
BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I1·I18, M0 엔진 유지보수 및
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정

감리의 `all: [false, 오류]`가 오류로 끝나는 결함은 작업 시작 시점에
[Audit 2 수정](2026-10-26_engine_all_any_lazy_error.md)으로 이미 해결돼 있었다.
[평가기](../../../packages/rules-engine/src/eval.rs)는 첫 오류를 보류한 뒤 성공한
자식을 결합하고, `all`에 거짓 또는 `any`에 참이 있으면 오류보다 확정값을 우선한다.
오류가 앞에 있어도 뒤의 확정 자식이 답을 정한다. 확정 자식이 없으면 첫 오류를 반환한다.

기존 [Audit 3 시험](2026-10-28_engine_all_any_short_circuit.md)은 역순
`days_between`을 불리언 비교 안에 넣은 정확한 2항 사례를 두 DSL 버전·두 자식 순서에서
검증한다. `days_between` 자체는 정수 식이므로 감리의 축약 예시를 그대로 불리언
자식으로 쓰면 로드 타입 검사에서 거부된다.

실행 코드는 변경하지 않았다. 기존 계약대로 모든 자식을 평가하고 흡수된 오류를
trace에 남기는 논리적 단락 처리이며, 확정 이후의 자식을 실행에서 생략하지 않는다.
기존 골든 trace·규칙 내용 해시·입력 스냅샷 해시 고정값은 유지한다.

## 추가한 회귀 시험

[all_any_errors.rs](../../../packages/rules-engine/tests/all_any_errors.rs)에 두 시험을 추가했다.

- `multiple_errors_cannot_override_a_decisive_child_in_both_versions`: 날짜 범위 오류,
  금액 오버플로, 역순 `days_between` 타입 오류를 함께 넣고 오류 순서 6종과 확정 자식의
  위치 5곳을 바꾼다. 누락 불리언 입력과 오류 셋이 함께 있어도 정확한 자격·지급액과
  빈 blocker를 반환한다. 오류 trace 3개·부분 trace 제거, JSON 재로딩·null/키 누락의
  전체 결과 바이트 일치(두 해시 포함)를 검사한다.
- `multiple_errors_preserve_the_first_error_without_a_decision_in_both_versions`:
  같은 조합에서 확정 자식을 중립값(`all`의 참, `any`의 거짓)으로 바꾸면 모름이 있어도
  첫 오류의 종류·내용·식 경로가 유지된다. 첫 오류는 세 종류 모두가 될 수 있다.

각 시험은 두 DSL 버전 × 두 연산 × 오류 순서 6종 × 위치 5곳 × null/키 누락 2종,
240조합이다. 두 시험의 주 평가 조합은 총 480개이며 재로딩·대조 평가는 별도다.
기존 2항·중첩·`if`·모름 blocker·건전성 시험도 유지한다.

[음성 대조 스크립트](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/negative_control.py)는
작업 트리 내부 임시 크레이트에서 정상 평가기의 9개 시험을 통과시킨다. 이어서 자식
오류를 즉시 반환하는 `?` 복원과, 결합 후에도 확정값보다 첫 오류를 우선하는 변이를
각각 독립적으로 적용한다. 새 확정값 시험이 두 변이 모두에서 Cargo 종료 코드 101과
`DateOutOfRange`로 실패하는지 검사한다. 실제 평가기 파일은 변경하지 않는다.

## 직접 실행한 검증

로컬 rustc/cargo 1.98.1, 작업 트리 전용 `CARGO_TARGET_DIR="$PWD/target"`,
`ONJ_REQUIRE_RULE_02=1`로 실행했다. 원격 CI 결과를 주장하지 않는다.
로그는 [검증 디렉터리](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/)에 기록한다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test all_any_errors --test unknown_branch_errors --test soundness` | 27개 통과: [focused.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/focused.log) |
| `cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 478개 통과, 실패 0, 기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/workspace.log) |
| `python3 -I packages/rules-engine/evidence/audit4-all-any-error-dominance/negative_control.py` | 정상 9개 통과, 두 변이는 각각 새 시험 실패(101)를 확인: [요약](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/negative-control.log), [정상](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/control-baseline.log), [즉시 오류 반환](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/control-eager-error.log), [결합 후 오류 우선](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/control-error-dominance.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 통과: [fmt.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 같은 명령의 읽기 검사 | §11 등록 수 213개·doctest 3개로 갱신 후 일치: [갱신](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/counts-write.log), [검사](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/counts.log) |
| `cargo test -p onjeon-rules-engine --locked --offline --test readme_test_table` | 4개 통과: [readme-tests.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/readme-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_counts.py -v` | 19개 통과: [doc-tests.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/doc-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 17개 통과: [purpose-tests.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/purpose-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업·필수 시험 연결 통과: [product-purpose.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과: [spec-check.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/spec-check.log) |
| `python3 -I tools/blueprint_status.py` | 결정 색인 일치: [status.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/status.log) |

모든 최상위 명령은 종료 코드 0이다. 음성 대조의 내부 Cargo 실패는 기대한 결함 검출이다.
[scope.log](../../../packages/rules-engine/evidence/audit4-all-any-error-dominance/scope.log)에
허용 경로·보호 문서 및 평가기·기존 fixture 불변·공백·로컬 링크 검사를 기록한다.
commit·push·GitHub 호출은 수행하지 않았다.

## 증명 범위

독립적으로 확정된 지급 제한·자격이 무관한 계산 오류로 가려지는 회귀를 막는 엔진
기반 증거다. 시험은 `fixture_only` 합성 규칙이며 실제 상품 릴리스 시나리오,
화면→원문 추적, P08·P14 전체 또는 첫 출시 완료 판정을 대신하지 않는다.
