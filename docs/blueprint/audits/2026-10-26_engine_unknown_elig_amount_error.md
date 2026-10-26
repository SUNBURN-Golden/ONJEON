# Audit 2: 자격 미정 시 금액 계산 오류 처리

기록일: 2026-10-26. 노드: `audit2-engine-unknown-elig-amount-error`.

`eligibility = flag`, `amount = add(amt, 1원)`인 합성 규칙에서 `flag=false, amt=i64::MAX`는 지급 대상 아님이다. `flag` 하나를 숨기면 기존 평가기는 금액 계산의 `Overflow`를 반환했다. 입력 정보가 줄었을 때 판정 불가 결과를 반환해야 하는 건전성 경로의 누락이었다.

[eval.rs](../../../packages/rules-engine/src/eval.rs)의 자격 미정 분기에서 기존 `eval_untaken`을 재사용한다. 금액 계산 오류는 `undetermined{conditional_amount: unknown}`으로 반환하며 자격의 누락 입력을 보존한다. 실패한 금액의 부분 trace는 금액 식의 `error: ...` 항목 하나로 대체한다. 성공한 조건부 금액·금액의 누락 입력, 자격 확정 시 금액 오류 반환은 유지한다. 출력 스키마와 상태 어휘 변경은 없다.

[soundness.rs](../../../packages/rules-engine/tests/soundness.rs)에 회귀 시험 3개를 추가했다. 기존 입력 숨김 검사기에 오버플로 사례를 넣고, 키 누락·명시적 `null`, 조건부 금액 모름, blocker, trace·전체 결과 재현성, 날짜 범위·런타임 타입 오류, 자격 참일 때의 오류 반환을 확인한다.

## 로컬 검증 증거

로그 위치: [tools/evidence/audit2-engine-unknown-elig-amount-error](../../../tools/evidence/audit2-engine-unknown-elig-amount-error/).

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --test soundness --offline` (수정 전) | 5개 통과·2개 실패. 오버플로·날짜 범위 오류 재현: [before.log](../../../tools/evidence/audit2-engine-unknown-elig-amount-error/before.log) |
| 같은 명령 (수정 후) | 7개 통과·실패 0: [focused.log](../../../tools/evidence/audit2-engine-unknown-elig-amount-error/focused.log) |
| `cargo test --all --offline` | Rust 단위·통합·문서 시험 405개 통과·실패 0·ignored 1: [rust-tests.log](../../../tools/evidence/audit2-engine-unknown-elig-amount-error/rust-tests.log). ignored는 기존 수동 fixture 재생성 시험 `regenerate_declared_abox_fixture`다 |
| `cargo fmt --all -- --check` | 종료 코드 0, 진단 없음: [rust-format.log](../../../tools/evidence/audit2-engine-unknown-elig-amount-error/rust-format.log) |
| `cargo clippy --all-targets --offline -- -D warnings` | 종료 코드 0: [rust-clippy.log](../../../tools/evidence/audit2-engine-unknown-elig-amount-error/rust-clippy.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 9개 등록 정합성 통과: [product-purpose.log](../../../tools/evidence/audit2-engine-unknown-elig-amount-error/product-purpose.log) |

## 제품 목적과 증명 범위

BLUEPRINT의 A2·A5, Q2·Q5, L6, I1, M5 및 R16(결정적 계산)에 해당한다. [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08(만약에 계산)·P16(결과를 바꾸는 미확인 조건)에 필요한 엔진 건전성 수정이다. 합성 회귀 시험과 저장소 통합 시험 증거이며 해당 행의 실제 릴리스·화면 시험 완료 증거를 대체하지 않는다. 출시 완료나 마일스톤 관문 통과를 주장하지 않는다.
