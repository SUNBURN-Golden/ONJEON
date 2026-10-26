# Audit 2: 범위 금액 비교를 로드 단계에서 거부

기록일: 2026-10-26. 노드: `audit2-engine-range-compare-static`.

## 문제와 수정

기존 정적 타입 `money`는 정확한 금액과 범위를 구분하지 않았다.
`multiply_rate(p, "0.5", {rounding: "unspecified", unit: 1})`를 비교에 쓰면
`p=200`에서는 100원으로 평가되지만 `p=201`에서는 100~101원이라 런타임 비교가 실패했다.

[로더](../../../packages/rules-engine/src/rule.rs)는 이제 내부 정적 타입 `MoneyRange`로
범위 가능성을 추적한다. 어느 쪽 피연산자든 범위가 될 수 있으면
`eq`·`ne`·`lt`·`lte`·`gt`·`gte`를 로드에서 거부하고 비교 노드의 경로와
`money_range` 진단을 반환한다. `rule-0.1`·`rule-0.2` 모두 적용한다.

- `multiply_rate`·`pro_rata`·`divide_count`의 `unspecified` 반올림은 범위 가능 타입을 만든다.
- 모든 금액 연산은 입력의 범위 가능성을 이어받는다. 명시적 반올림도 서로 다른 양 끝값을 항상 하나로 만들지는 않으므로 범위 타입을 유지한다.
- `if`는 어느 가지에 범위가 있어도 범위 가능 타입이다. 정확한 금액과 범위를 섞은 가지는 금액 계산·출력에서 계속 허용한다.
- 상수 계산·상한·0배·확정 조건의 도달성으로 범위가 사라지는 예외는 추론하지 않는다. 일부 입력에서 정확한 값이 되더라도 비교에는 사용할 수 없다.
- `pro_rata`의 `part`·`whole`은 기존 실행 계약대로 둘 다 int 또는 둘 다 정확한 money여야 한다. 세분화한 타입으로 범위 인자를 로드에서 거부한다. 첫 번째 금액 인자는 범위를 계속 허용한다.

정확한 금액 비교와 범위 금액 계산·출력, 모름 처리는 유지한다.
외부 DSL 키·입력 타입·출력 형식·내용 해시와 평가기는 변경하지 않았다.
범위 비교를 모름으로 계산할지 등 비교 의미의 확장은 BLUEPRINT §12의 W3 열린 결정으로 남는다.

## 검증

모두 이 worktree에서 로컬 실행했다. rustc/cargo 1.98.1, `--offline`을 사용했으며
원격 CI 실행을 주장하지 않는다. [로그 디렉터리](../../../packages/rules-engine/evidence/audit2-range-compare/).

| 명령 | 결과·증거 |
|---|---|
| 수정 전 `cargo test -p onjeon-rules-engine --test range_comparisons --offline` | 8개 중 거부 회귀 시험 6개 실패, 기존 동작 보존 시험 2개 통과([before.log](../../../packages/rules-engine/evidence/audit2-range-compare/before.log)) |
| 수정 후 `cargo test -p onjeon-rules-engine --test range_comparisons --test static_types --test review_fixes --test rule_02 --test all_any_errors --test unknown_branch_errors --offline` | 82개 통과([focused.log](../../../packages/rules-engine/evidence/audit2-range-compare/focused.log)) |
| `cargo test --all --offline` | Rust 단위·통합·문서 시험 415개 통과, 실패 0, 기존 ignored 1. 골든·변이·건전성·엔진 소비자 포함([workspace.log](../../../packages/rules-engine/evidence/audit2-range-compare/workspace.log)) |
| `cargo fmt --all -- --check` | 통과, 진단 출력 없음([fmt.log](../../../packages/rules-engine/evidence/audit2-range-compare/fmt.log)) |
| `cargo clippy --all-targets --offline -- -D warnings` | 통과([clippy.log](../../../packages/rules-engine/evidence/audit2-range-compare/clippy.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44, 존재 검사 72/72 통과. 제품 목적 대응표의 구조·관문 연결 검사 포함([spec-check.log](../../../packages/rules-engine/evidence/audit2-range-compare/spec-check.log)) |

[새 회귀 시험 8개](../../../packages/rules-engine/tests/range_comparisons.rs)는 `p=200`·`p=201`의
정확/범위 출력 차이, 비교 6종의 좌·우·양쪽 범위, 금액 연산·중첩 `if`를 통한 범위 전파,
실행되지 않는 가지 안의 비교 거부와 오류 경로, 명시적 반올림 4종의 정확한 금액 비교,
혼합 `if`의 정확/범위/미입력 결과, `pro_rata`의 정확한 비율 인자 제약을 검증한다.

첫 전체 실행은 기존 `all_any_errors`가 범위 비교를 런타임 `Type` 오류 예제로 써서
로드에서 실패했다([workspace-before-fixture-update.log](../../../packages/rules-engine/evidence/audit2-range-compare/workspace-before-fixture-update.log)).
이제 로드할 수 없는 예제이므로 `all_any_errors`와 `unknown_branch_errors`의 해당 예제를
역순 `days_between`의 런타임 `Type` 오류로 교체했다. 오류 흡수·전파의 검증 범위는 유지하며,
선택된 가지에서는 여전히 해당 오류가 발생하는지도 확인한다.

변경 경로·보호 파일·로컬 문서 링크와 `git diff --check`도
[최종 검사](../../../packages/rules-engine/evidence/audit2-range-compare/final-checks.log)에서 확인했다.
commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 증명 범위

BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I4·I5, R16, M0 엔진 기반 유지보수에 연결된다.
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의
P08(시나리오 계산)·P14(계산 경로 추적)를 위한 엔진 기반 검증이다.
시험 규칙은 모두 `fixture_only` 합성 규칙이다. 실제 릴리스 상품 시나리오·화면 시험·출시 증거를
대체하지 않으며 P08·P14 또는 첫 출시 완료로 판정하지 않는다.
