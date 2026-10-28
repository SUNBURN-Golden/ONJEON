# Audit 3: `all`·`any`의 무관한 오류 흡수 재검증

검증일: 2026-10-28. 노드: `audit3-engine-all-any-short-circuit`.
BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I1·I18, M0 엔진 유지보수 및
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정과 변경

감리의 `all: [false, 오류]`가 오류를 반환한다는 문제는 이 작업 시작 시점에
[Audit 2 오류 보류 수정](2026-10-26_engine_all_any_lazy_error.md)으로 이미 해결돼 있었다.
[현재 평가기](../../../packages/rules-engine/src/eval.rs)는 자식의 첫 오류를 보류하고
성공 결과를 결합한다. `all`에 거짓 또는 `any`에 참이 있으면 확정 결과를 반환하며,
없으면 첫 오류를 반환한다. 오류가 먼저 나와도 뒤의 확정 자식을 확인한다.
평가기 실행 코드는 이번 작업에서 변경하지 않았다.

이는 오류의 관련성을 판단하는 논리적 단락 처리다. 모든 자식을 평가하고 흡수한
오류를 `error: ...` trace로 남긴다는 기존 공개 계약을 유지한다. 자식을 생략하는
실행 최적화는 하지 않았으며 정상 골든 trace·내용 해시·입력 해시 고정값도 유지했다.

[회귀 시험](../../../packages/rules-engine/tests/all_any_errors.rs)에 시험 3개를 추가했다.

- `all_false_absorbs_runtime_errors_in_both_versions`·`any_true_absorbs_runtime_errors_in_both_versions`:
  rule-0.1·rule-0.2 각각에서 날짜 범위·금액 오버플로·런타임 타입 오류를 확정 자식의
  앞뒤에 놓는 24조합. 정확한 자격·지급 결과, 빈 blocker, 오류 trace 1개와 전체 결과
  직렬화 재현성을 검증한다. 자식 둘만으로 감리 예시를 직접 고정한다.
- `nested_all_any_and_if_keep_decisions_and_relevant_errors`: 두 DSL 버전·두 논리 연산·
  오류 3종에서 내부 논리식이 실패해도 외부의 확정 자식이 앞뒤 어디서든 결과를 보존한다.
  미확정 `if`의 양쪽 가지가 오류 흡수 뒤 같은 값이면 조건의 blocker가 사라진다.
  반대로 선택된 가지에 결과를 정할 자식이 없으면 원래 오류 종류·내용·경로가 유지된다.

기존 자식 순서 6종·모름의 blocker·첫 오류 보존·부분 trace 제거 및 건전성·`if` 회귀도
그대로 실행했다. 기존 CI의 `cargo test --all`이 새 시험을 실행한다.

## 직접 실행한 검증

로컬 rustc/cargo 1.98.1로 실행했다. 원격 CI 결과를 주장하지 않는다.
로그 위치: [packages/rules-engine/evidence/audit3-all-any-short-circuit/](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/).
아래 명령은 모두 종료 코드 0이다. 음성 대조 안의 Cargo 실패는 기대한 종료 코드
101과 두 시험의 실패 진단을 검사한 결과다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test all_any_errors --test unknown_branch_errors --test soundness` | 집중 시험 24개 통과: [focused.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/focused.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 469개 통과, 실패 0, 기존 ignored 1개. 내부 Python 시험 39개·129개 통과. 골든 trace·해시·변이·건전성·실제 조항 포함: [workspace.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/workspace.log) |
| `python3 -I packages/rules-engine/evidence/audit3-all-any-short-circuit/negative_control.py` | 작업 트리 내부 임시 크레이트에서 정상 평가기 7개 통과. 자식 평가에 즉시 반환 `?`를 복원하면 새 2항 시험 둘 모두 `DateOutOfRange`로 실패(101). 실제 평가기는 변경하지 않음: [음성 대조 요약](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/negative-control.log), [정상 로그](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/control-baseline.log), [변이 로그](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/control-eager-error.log) |
| `cargo test -p onjeon-rules-engine --locked --offline --test readme_test_table` | 최종 README와 시험 목록 정합성 4개 통과: [readme-tests.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/readme-tests.log) |
| `cargo fmt --all -- --check` | 통과, 진단 없음: [fmt.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/fmt.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 통과: [clippy.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 `python3 -I tools/blueprint_counts.py` | §11 엔진 등록 수 204개·doctest 3개와 정본 일치: [counts-write.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/counts-write.log), [counts.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/counts.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_counts.py -v` | 17개 통과: [counts-tests.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/counts-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 14개 통과: [purpose-tests.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/purpose-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 등록 검사 통과: [product-purpose.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과: [spec-check.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/spec-check.log) |
| `python3 -I tools/blueprint_status.py` | 결정 색인 일치: [status.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/status.log) |

엔진 README에 직접 예시와 시험·증거 연결을 추가하고 09 §7에 P08·P14의 증명 범위를
기록했다. [scope.log](../../../packages/rules-engine/evidence/audit3-all-any-short-circuit/scope.log)는
허용 경로·보호 문서 불변·평가기와 기존 fixture 불변·로컬 링크·공백 검사를 기록한다.
commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 한계

독립적인 제한 조건이 확정돼도 무관한 계산 오류로 전체 계산이 실패하는 회귀를 막는
엔진 기반 증거다. 시험은 `fixture_only` 합성 규칙이며 실제 상품 릴리스 시나리오,
화면 숫자→원문 좌표의 사슬, P08·P14 전체 또는 첫 출시 완료 판정을 대체하지 않는다.
