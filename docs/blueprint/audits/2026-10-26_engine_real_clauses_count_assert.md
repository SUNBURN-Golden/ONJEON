# Audit 2: 실제 조항 사례 수와 규칙별 사례 보유 검사

기록일: 2026-10-26. 노드: `audit2-engine-real-clauses-count-assert`.

## 발견과 수정

[real_clauses.rs](../../../packages/rules-engine/tests/real_clauses.rs)의 `n >= 40`은 사례 누락을 허용했다. 감사에서 언급한 공유 사례는 47개이며, 현재 공통 로더는 엔진 소유 경계 사례 58개를 추가하므로 실제 실행 수는 105개다(합성 규칙용 추가 사례 1개는 이 수에 포함하지 않는다).

실행 수를 `EXPECTED_REAL_CLAUSE_CASES = 47 + 58`과 정확히 비교한다. 파일 탐색 결과에서 기대 수를 계산하지 않으며, 사례를 의도적으로 변경할 때만 고정 수를 갱신한다. 실행한 규칙 ID 집합과 로드된 규칙 ID 집합이 일치해야 한다는 기존 검사도 같은 검증 함수에 유지한다. 개수만 맞고 사례가 없는 규칙이 있는 상태도 실패한다. 공유 픽스처와 규칙 본문은 변경하지 않는다.

## 회귀 시험

- 사례 파일 6개를 각각 하나씩 제외하면 반드시 **개수 검사**가 실패한다.
- 모든 규칙에 사례가 남아 있어도 사례 하나를 삭제하면 실패한다.
- 정상 사례를 하나 복제해 실행 수가 106개가 되어도 실패한다.
- 실행 수가 정확히 105개여도 사례 없는 규칙을 추가하면 **규칙별 사례 보유 검사**가 실패한다.
- 기존의 알 수 없는 규칙·규칙 참조 누락·공유 파일 내 여러 규칙 검사와 지급 결과·근거·화면 금액 검증을 유지한다.

## 직접 실행한 검증 증거

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --offline --test real_clauses` (개수 검사 수정 전) | 종료 코드 101, 8개 통과·2개 실패. 기존 검사는 단일 사례 삭제를 통과시키며 파일 삭제에서도 개수 오류를 내지 않았다: [before.log](../../../tools/evidence/audit2-engine-real-clauses-count-assert/before.log) |
| `cargo test -p onjeon-rules-engine --offline --test real_clauses` (수정 후) | 종료 코드 0, 기존 7개·추가 4개 모두 통과: [focused.log](../../../tools/evidence/audit2-engine-real-clauses-count-assert/focused.log) |
| `cargo test --all --offline` | 종료 코드 0, Rust 단위·통합·문서 시험 443개 통과·실패 0·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../tools/evidence/audit2-engine-real-clauses-count-assert/workspace.log) |
| `cargo fmt --all -- --check` | 종료 코드 0, 진단 없음: [fmt.log](../../../tools/evidence/audit2-engine-real-clauses-count-assert/fmt.log) |
| `cargo clippy --all-targets --offline -- -D warnings` | 종료 코드 0: [clippy.log](../../../tools/evidence/audit2-engine-real-clauses-count-assert/clippy.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 등록 정합성 통과: [product-purpose.log](../../../tools/evidence/audit2-engine-real-clauses-count-assert/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit2-engine-real-clauses-count-assert/spec-check.log) |

## 제품 목적과 한계

BLUEPRINT A1·A2·A5, Q1·Q2·Q5·Q7, L6, I6, V1·M1 엔진 기반과 [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08·P14에 연결된다. 실제 조항을 옮긴 `fixture_only` 설계 검증 규칙의 회귀 안전장치다. 실제 릴리스 상품·전 상품 수집·소비자 화면·출시 완료 증거를 대체하지 않는다.
