# Audit 2: `days_between` 역순 날짜 거부

기록일: 2026-10-26. 노드: `audit2-engine-days-between-negative`.

## 발견과 확정 동작

감사 지적은 역순 날짜에서 포함 플래그를 무시하고 음수 차이를 반환하면 `days_between < 90` 같은 경과 기간 조건을 잘못 충족한다는 것이다. 이 작업 시작 시점의 [평가기](../../../packages/rules-engine/src/eval.rs)에는 이미 역순 날짜의 `EvalError::Type` 거부와 `loader_and_arith`의 기본 회귀 시험이 있었다. 기존 거부 구현을 유지하고, 그 이유를 코드 주석에 명시했으며, 연산 계약·감사 전용 회귀 시험·검증 증거를 보강했다. 새 런타임 수정이 필요했던 것으로 기록하지 않는다.

`rule-0.1`·`rule-0.2` 모두 다음 계약을 따른다.

- 시작일 ≤ 종료일: `max(0, 종료일-시작일-1 + inclusive_start + inclusive_end)`일(참=1, 거짓=0). 같은 날은 양 끝을 모두 포함할 때만 1일이고, 나머지는 0일이다. 하루 차이에서 양 끝을 제외하면 0일이다.
- 시작일 > 종료일: 포함 플래그와 관계없이 평가 시 해당 식 경로의 `EvalError::Type` 오류다. 음수 반환·절댓값·날짜 자동 교환·0 보정은 하지 않는다. 0 보정도 `lt 90` 우회를 허용하므로 거부를 계산 전에 적용한다.
- 날짜가 누락되거나 `null`: 모름을 반환하고 필요한 날짜 입력만 blocker로 남긴다. 알려진 두 날짜가 있어야 역순 여부를 판정한다.
- 오류를 포함한 식의 결합은 기존 계약을 따른다. 독립적으로 확정되는 `all`/`any`, 조건이 모름인 `if`, 자격이 모름인 금액 계산에서는 오류가 흡수될 수 있고 trace에 남는다. 따라서 역순 날짜가 규칙 전체에서 항상 최상위 오류가 된다고 주장하지 않는다.

## 회귀 시험

[days_between.rs](../../../packages/rules-engine/tests/days_between.rs)의 시험 4개가 두 DSL 버전과 포함 플래그 4조합을 모두 검사한다.

| 시험 | 검증 |
|---|---|
| `reversed_dates_cannot_satisfy_comparison_thresholds` | 비교 6종(`eq/ne/lt/lte/gt/gte`) × 임계값 0/1/90/180 × 역순 1일·180일·지원 범위 양 끝, 총 576회 오류 종류·경로·메시지 확인 |
| `reversed_literal_and_computed_dates_are_also_rejected` | 날짜 리터럴과 `date_add`가 만든 역순 날짜도 평가 시 같은 오류·경로, 총 16회 |
| `forward_and_same_day_intervals_preserve_all_inclusive_boundaries` | 같은 날·하루 차이·윤일 경유·180일·지원 범위 양 끝의 같은 날, 총 48회 기대 일수·지급 결과·blocker 없음·trace·직렬화 재현성 |
| `missing_dates_stay_unknown_and_report_only_missing_endpoints` | 한쪽·양쪽 누락 및 `null`, 총 48회 모름 자격·조건부 금액·정확한 blocker·모름 trace |

음성 대조로 평가기의 거부 분기를 일시적으로 (1) 원시 음수 반환, (2) 역순도 정상 계산 후 0 보정하도록 바꿔 동일 시험을 실행했다. 각 변이는 역순 입력 및 리터럴·계산 날짜 시험 2개에 잡혔고, 정상 날짜·누락 입력 시험 2개는 통과했다. 두 실행 모두 종료 코드 101이며 [mutation.log](../../../tools/evidence/audit2-engine-days-between-negative/mutation.log)에 기록했다. 각 변이 후 원래 평가기를 복원하고 아래 검증을 실행했다. 변이 코드가 최종 산출물에 남아 있지 않다.

## 실행 증거

로그 경로: [tools/evidence/audit2-engine-days-between-negative/](../../../tools/evidence/audit2-engine-days-between-negative/).

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --offline --test days_between --test loader_and_arith` | 17개 통과: [focused.log](../../../tools/evidence/audit2-engine-days-between-negative/focused.log) |
| `cargo test --all --offline` | Rust 단위·통합·문서 시험 436개 통과·실패 0·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../tools/evidence/audit2-engine-days-between-negative/workspace.log) |
| `cargo fmt --all -- --check` | 종료 코드 0, 진단 없음: [fmt.log](../../../tools/evidence/audit2-engine-days-between-negative/fmt.log) |
| `cargo clippy --all-targets --offline -- -D warnings` | 종료 코드 0, 경고 없음: [clippy.log](../../../tools/evidence/audit2-engine-days-between-negative/clippy.log) |
| `python3 -m unittest discover -s tools/tests -v` | 915개 실행·실패 0·기존 skip 6개: [python-tests.log](../../../tools/evidence/audit2-engine-days-between-negative/python-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 정합성 통과: [product-purpose.log](../../../tools/evidence/audit2-engine-days-between-negative/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit2-engine-days-between-negative/spec-check.log) |

## 제품 목적과 한계

BLUEPRINT A2·A5, Q2·Q5, L6, I1·I18, M0 엔진 기반 및 [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08 시나리오 계산의 날짜 조건 검증에 해당한다. 역전 입력을 유효한 경과 기간으로 사용하는 것을 차단하는 로컬 합성 회귀 증거다. 실제 약관의 포함일 해석을 새로 정하지 않으며, 실제 릴리스 상품의 감액·면책 경계일 시나리오·화면·출시 완료 증거를 대신하지 않는다.
