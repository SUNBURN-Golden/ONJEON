# Audit 2: 빈 규칙 ID·근거와 중복 근거의 로드 거부

기록일: 2026-10-26. 노드: `audit2-engine-empty-ids-evidence`.

## 발견과 수정

감사 지적은 `rule_id: ""`, `evidence_refs: [""]`, 중복 근거 참조가 로드되고 빈 문자열 하나로 공개 규칙의 근거 요건을 채울 수 있다는 것이었다. 이 worktree의 수정 전 코드에는 빈 근거 참조를 거부하는 검사가 이미 있었다. 새 시험으로 빈 ID·중복 근거가 여전히 로드되는 것을 재현했고, 기존 빈 근거 거부도 확인했다.

[규칙 로더](../../../packages/rules-engine/src/rule.rs)는 이제 빈 문자열 또는 공백만 있는 `rule_id`를 `rule_id` 경로의 오류로 거부한다. 기존 빈 근거 검사는 유지하고, `evidence_refs`에서 같은 문자열이 반복되면 두 번째 등장한 배열 위치(`evidence_refs[i]`)에서 `duplicate evidence reference` 오류를 반환한다. 인접하지 않은 중복도 거부한다. 검사는 `rule-0.1`·`rule-0.2`와 `fixture_only`·`candidate`·`released` 모두에 적용된다.

입력 값을 trim·정렬·중복 제거하지 않는다. 정상 규칙의 원본 JSON, 근거 순서와 내용 해시를 보존한다. 빈 근거 목록 `[]`은 계속 `fixture_only`에서만 허용한다. 한 규칙 안의 근거 문자열 중복을 검사하며, 별도 규칙 사이의 ID 등록·근거 존재 여부·원문 사슬 완전성을 판정하는 기능은 아니다.

## 회귀 시험과 로컬 증거

[identity_evidence.rs](../../../packages/rules-engine/tests/identity_evidence.rs)의 5개 시험은 두 DSL 버전 × 세 공개 상태 × 두 공개 로드 진입점(`from_json`·`from_json_str`)을 검사한다. 빈 문자열, ASCII·유니코드 공백, 첫 번째·후속 빈 근거, 인접·비인접 중복, 오류 경로, 빈 목록의 상태별 허용 여부를 확인한다. 정상 규칙은 로드·재로드·평가 후 ID·근거 순서·해시가 유지되는지도 확인한다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --test identity_evidence --offline` (로더 수정 전) | 3개 통과·2개 실패. 빈 ID·중복 근거 로드 재현: [before.log](../../../tools/evidence/audit2-engine-empty-ids-evidence/before.log) |
| 같은 명령 (수정 후) | 5개 통과·실패 0: [focused.log](../../../tools/evidence/audit2-engine-empty-ids-evidence/focused.log) |
| `cargo test --all --offline` | 종료 코드 0. Rust 단위·통합·문서 시험 424개 통과·실패 0·기존 ignored 1개(`regenerate_declared_abox_fixture`). 내부 Python 시험 39개·129개도 통과: [workspace.log](../../../tools/evidence/audit2-engine-empty-ids-evidence/workspace.log) |
| `cargo fmt --all -- --check` | 종료 코드 0, 진단 없음: [fmt.log](../../../tools/evidence/audit2-engine-empty-ids-evidence/fmt.log) |
| `cargo clippy --all-targets --offline -- -D warnings` | 종료 코드 0: [clippy.log](../../../tools/evidence/audit2-engine-empty-ids-evidence/clippy.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 9개 등록의 정적 정합성 통과: [product-purpose.log](../../../tools/evidence/audit2-engine-empty-ids-evidence/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit2-engine-empty-ids-evidence/spec-check.log) |

## 제품 목적과 한계

BLUEPRINT A1·A5, Q5·Q7, L6, §5.2 근거 사슬, I6의 엔진 입력 검증 및 I18, M0 엔진 기반에 해당한다. [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08(시나리오 계산)·P14(규칙·약관 근거 추적)를 뒷받침하는 로컬 검증이다. 합성 규칙 시험이며 실제 데이터·화면·출시 완료 증거를 대체하지 않는다. I6 전체 구현이나 P08·P14 완료, 출시 관문 통과를 주장하지 않는다.
