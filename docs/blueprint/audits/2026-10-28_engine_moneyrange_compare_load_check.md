# Audit 3: MoneyRange 비교의 로드 단계 거부 재검증

검증일: 2026-10-28. 노드: `audit3-engine-moneyrange-compare-load-check`.
BLUEPRINT A2·A5, Q2·Q5, L6, I1·I4·I5, M0 및
[09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견과 현재 구현

발견 내용은 `compare`가 `MoneyRange`를 지원하지 않는데 로더가 범위 가능 식을
정확한 `Money`로 받아, 규칙이 로드된 뒤 입력에 따라 평가 오류를 냈다는 것이다.
예를 들어 `multiply_rate(p, "0.5", {rounding: "unspecified", unit: 1})`는
`p=200`이면 정확히 100원, `p=201`이면 100~101원이다.

이 작업 시작 시 [Audit 2 수정](2026-10-26_engine_range_compare_static.md)이 이미
반영되어 있었다. [로더](../../../packages/rules-engine/src/rule.rs)는 별도 정적 타입
`MoneyRange`로 범위 가능성을 추적하며, 금액 연산과 `if`를 통해 전파한다.
어느 쪽 피연산자든 범위 가능 식이면 비교 6종(`eq`·`ne`·`lt`·`lte`·`gt`·`gte`)을
로드에서 거부한다. 일부 입력·상수·미선택 가지에서 정확한 금액이 나오는 경우도
예외로 허용하지 않는다. 두 DSL 버전에 적용한다.

범위 비교의 의미를 새로 정의하지 않고 이 검증을 유지했다. 평가기와 로더의
운영 코드는 변경하지 않았다. 범위 출력과 범위 금액 계산은 계속 허용되며,
범위와 기준값 비교의 의미 확장은 BLUEPRINT §12 W3의 열린 설계로 남는다.

## 이번 보강

[range_comparisons.rs](../../../packages/rules-engine/tests/range_comparisons.rs)의
기존 시험 8개를 보존하고 2개를 추가했다.

- 기존 범위 비교 거부 행렬을 `Rule::from_json`과 `Rule::from_json_str` 양쪽에서
  검사한다. 오류의 비교 노드 경로와 `money_range` 진단도 확인한다.
- 두 DSL 버전 × 비교 6종 × 범위 피연산자 위치 3종(왼쪽·오른쪽·양쪽) ×
  중첩 문맥 7종 × 로드 진입점 2종, 총 504회 거부 검사를 추가했다.
  문맥은 확정하는 형제가 있는 `all`·`any`, `not`, 불리언 `if`의 조건·양쪽 가지,
  자격이 거짓이고 금액에서도 선택되지 않는 중첩 `if`다. 평가 입력 없이 거부된다.
- 정확한 금액 비교는 두 DSL 버전·명시적 반올림 4종·비교 6종에서
  기준값 아래·동일·위의 결과 144회, 누락·`null`의 판정 불가 및 blocker 96회를
  확인한다. 기존 자기 자신과의 비교 외에 실제 순서와 임계값을 검사한다.
- [음성 대조 스크립트](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/negative_control.py)는
  작업 트리 내부 임시 크레이트에서 정상 구현의 10개 통과를 먼저 확인한다.
  이후 `Ty::rounded`의 범위 생성 추론을 제거해 원래 결함을 재현하면 7개가
  의도한 로드 거부 실패로 종료한다(Cargo 종료 코드 101). 새 중첩 거부 시험도
  실패하고 정확한 금액 비교 시험은 통과한다. 실제 엔진 소스는 수정하지 않는다.

## 직접 실행한 검증

로그: [tools/evidence/audit3-engine-moneyrange-compare-load-check](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/).
원격 CI 실행은 주장하지 않는다. 기존 CI의 `cargo test --all`이 보강 시험을 실행한다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test range_comparisons` | 10개 통과: [focused.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/focused.log) |
| `python3 -I tools/evidence/audit3-engine-moneyrange-compare-load-check/negative_control.py` | 정상 복사본 통과·원래 결함 검출: [negative-control.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/negative-control.log) |
| `cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 469개 통과·실패 0·기존 무시 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/workspace.log) |
| `cargo fmt --all -- --check` | 통과, 진단 없음: [fmt.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/fmt.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 통과: [clippy.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/clippy.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_counts.py -v` | 17개 통과: [counts-tests.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/counts-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 14개 통과: [purpose-tests.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/purpose-tests.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 `python3 -I tools/blueprint_counts.py` | 엔진 단위·통합 등록 204개·doctest 3개 대조: [counts.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/counts.log), [counts-check.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/counts-check.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 연결·필수 시험 등록 검사 통과: [product-purpose.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/spec-check.log) |

허용 경로·보호 문서 불변·엔진 운영 코드 불변·로컬 링크·공백 검사는
[scope.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/scope.log)에 기록한다.

## 제품 목적과 한계

BLUEPRINT I5의 검사 근거와 엔진 README, 09 §7의 P08·P14 연결을 보강한다.
§11 등록 수는 `tools/blueprint_counts.py --write`로 갱신했다.
이 기록은 합성 규칙의 로드 안전성 회귀 증거다. 실제 상품 릴리스 정확도·전 상품
수집·소비자 화면·첫 출시 완료 또는 P08·P14 전체 완료 판정을 대신하지 않는다.
