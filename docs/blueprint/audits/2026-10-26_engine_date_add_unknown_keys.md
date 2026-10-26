# Audit 2: `date_add` 미지원 파라미터 키 거부 검증

대상 노드: `audit2-engine-date-add-unknown-keys` (2026-10-26).

감리 지적은 `date_add`의 파라미터에 `"x":1`을 추가해도 로드된다는 것이다.
이 worktree의 시작 코드에는 이미 단위별 정확한 키 집합 검사와 기본 회귀 시험이 있다.
이번 변경은 기존 검사를 유지하고 두 DSL 버전의 회귀 시험과 재현 증거를 보강한다.
새 실행 동작을 추가했다고 주장하지 않는다.

## 확인한 로더 계약

[`rule.rs`의 `date_add`](../../../packages/rules-engine/src/rule.rs)는 필수 키의 값·타입을
검사한 뒤 객체의 키 개수를 확인한다. 필수 키가 모두 존재한 상태에서 개수를 검사하므로
아래 집합 밖의 키는 통과하지 못한다.

| 단위 | 정확한 허용 키 |
|---|---|
| `day` | `value`, `unit` |
| `calendar_month`, `calendar_year` | `value`, `unit`, `month_end` (`"clamp"` 필수) |

`day`의 `month_end`도 의미 없이 무시하지 않고 거부한다.
오류에는 중첩 식의 `date_add` 위치가 포함된다. 실행되지 않는 가지도 로드에서 검사한다.

## 시험과 실행 증거

[`loader_and_arith.rs`](../../../packages/rules-engine/tests/loader_and_arith.rs)의 검증 범위:

- `rule-0.1`·`rule-0.2`, 세 단위 전체에서 `x:1`, 불리언·null·객체 값을 가진 미지원 키 거부.
- 필수 키를 `x`로 바꿔 개수를 유지해도 거부하며 오류 경로·누락 키를 확인.
- 미선택 금액 가지의 `x:1` 및 `day`의 `month_end`(clamp·null)도 로드 거부.
- 정확한 키 집합으로 윤일의 일 계산, 월말 clamp, 윤일의 다음 해 clamp를 로드·평가.

검증은 이 worktree에서 Rust 1.98.1로 로컬 실행했다. 원격 CI 결과가 아니다.
로그 디렉터리: [`audit2-date-add-unknown-keys`](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/).

| 명령·대조 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --test loader_and_arith --offline` | 13개 통과 ([focused.log](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/focused.log)) |
| 키 집합 검사만 임시 제거 후 `cargo test -p onjeon-rules-engine --test loader_and_arith date_add_ --offline` | 3개 통과·2개 실패, `x:1`이 로드되어 거부 시험이 실패함. 이후 `rule.rs`를 바이트 단위로 원상 복구 ([check-removed.log](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/check-removed.log)) |
| 원상 복구 후 `cargo test --all --offline` | Rust 단위·통합·문서 시험 422개 통과·실패 0·기존 ignored 1. 포함된 Python 검사도 39개·129개 통과 ([workspace.log](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/workspace.log)) |
| `cargo fmt --all -- --check` | 통과, 진단 출력 없음 ([fmt.log](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/fmt.log)) |
| `cargo clippy --all-targets --offline -- -D warnings` | 전체 workspace 통과 ([clippy.log](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/clippy.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과 ([spec-check.log](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/spec-check.log)) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·G12 시험 ID 정적 검사 통과 ([product-purpose.log](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/product-purpose.log)) |

소스 원상 복구·보호 경로·문서 링크·`git diff --check`는
[최종 검사](../../../packages/rules-engine/evidence/audit2-date-add-unknown-keys/final-checks.log)에 기록했다.
commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 증명 범위

BLUEPRINT A2·A5, Q2·Q5, L6, I5, M0 엔진 유지보수 및
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의
P08(면책·감액 경계일 시나리오)의 계산 기반에 연결된다.
시험 규칙은 `fixture_only` 합성 규칙이다. 실제 상품 데이터·화면·출시 검증을 대신하지 않으며
P08 또는 첫 출시 완료로 판정하지 않는다.
