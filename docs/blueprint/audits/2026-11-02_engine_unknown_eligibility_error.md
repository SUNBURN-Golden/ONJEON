# Audit 4: 자격 미정 금액 오류 건전성 재검증

기록일: 2026-11-02. 노드: `audit4-engine-unknown-eligibility-error`.

지적된 동작은 [Audit 2](2026-10-26_engine_unknown_elig_amount_error.md)에서 이미 수정되어 있었다. 현재 [평가기](../../../packages/rules-engine/src/eval.rs)의 `Rule::evaluate`는 자격이 모름이면 `eval_deferred`로 금액을 평가한다. 계산 오류는 `undetermined{conditional_amount: unknown}`으로 반환하고 자격의 누락 입력을 보존하며 실패한 금액의 부분 trace를 `error: ...` 항목으로 대체한다. 자격이 거짓이면 금액을 평가하지 않고, 참이면 금액 오류를 반환한다. 이번 변경은 이 구현을 유지하고 회귀 검증을 보강한다.

[soundness.rs](../../../packages/rules-engine/tests/soundness.rs)의 `hiding_eligibility_with_nested_amount_errors_is_sound_in_both_dsl_versions`는 `rule-0.1`·`rule-0.2` 각각에서 `add`·`min`·`max` 안의 중첩 오버플로를 검사한다. 각 금액 식은 정상 자식 `0원`과 실패하는 `add(amt, 1원)`을 함께 갖는다. 특히 `min(0, 오류)`에서도 정상 자식만 답으로 삼지 않는다.

- `flag=false, amt=i64::MAX`: `not_payable`, 누락 입력 없음, 금액 trace 없음.
- 알려진 입력을 하나씩 null·키 누락으로 숨기는 기존 건전성 검사: 조합 24개, 다른 확정 결론으로 바뀌지 않음.
- `flag=null`·키 누락: 자격 모름, 조건부 금액 모름, blocker는 `flag`. 금액 trace는 최상위 식의 오류 항목 하나이고 메시지는 실제 중첩 오류 경로를 보존한다.
- 반복 실행과 null·키 누락 간 전체 결과 JSON 바이트 일치: trace·입력 스냅샷 해시·규칙 식별 정보 포함.
- `flag=true`: 원래 중첩 경로의 `EvalError::Overflow` 반환.

오류 보류 분기를 과거의 `eval(...)?` 즉시 오류 반환으로 일시 교체하면 새 테스트가 `Overflow { path: "amount.add[1]" }`로 실패한다. [변이 검증 로그](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/mutation.log)에 실패와 종료 코드 101을 기록했다. 검증 스크립트의 `finally`에서 `eval.rs`를 바이트 단위로 복구한 뒤 정상 구현으로 시험을 다시 실행했다.

검증 로그는 [evidence 디렉터리](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/)에 보관한다. 각 로그는 실행 명령과 종료 코드를 포함한다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test soundness --test unknown_branch_errors --test all_any_errors` | 25개 통과: [focused.log](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/focused.log) |
| `cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 476개 통과, 실패 0, 기존 수동 픽스처 재생성 시험 `regenerate_declared_abox_fixture` 1개 ignored. 내장 Python 시험도 통과: [workspace.log](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/workspace.log) |
| `cargo fmt --all -- --check` | 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/fmt.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 종료 코드 0: [clippy.log](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 같은 검사(`--write` 없음) | 엔진 단위·통합 시험 등록 수 210→211 갱신·대조 통과: [counts.log](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 정합성 통과(정적 검사): [product-purpose.log](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/product-purpose.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_blueprint*.py' -v` | 48개 통과: [docs-tests.log](../../../packages/rules-engine/evidence/audit4-engine-unknown-eligibility-error/docs-tests.log) |

BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I1·I18, M5, R16에 해당한다. [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P16에 연결되는 합성 엔진 회귀 증거다. 실제 릴리스 상품 시나리오·소비자 화면·출시 완료 증거나 마일스톤 관문 통과를 뜻하지 않는다.
