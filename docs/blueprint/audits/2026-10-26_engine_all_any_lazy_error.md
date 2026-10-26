# Audit 2: all/any의 확정 결과를 무관한 자식 오류에서 보존

기록일: 2026-10-26. 노드: `audit2-engine-all-any-lazy-error`.

`all`/`any`가 자식을 평가하면서 첫 오류를 즉시 반환하던 문제를 수정했다.
예를 들어 `all: [false, 날짜 범위를 벗어나는 비교]`는 이제 `Err(DateOutOfRange)` 대신
`not_payable`을 반환한다. `any`의 참도 같은 방식으로 보존된다.

[평가기](../../../packages/rules-engine/src/eval.rs)는 성공한 자식의 논리값을 먼저 결합하고,
`all`에 거짓 또는 `any`에 참이 있으면 다른 자식의 오류와 모름에 관계없이 그 값을 반환한다.
오류가 앞에 있어도 뒤의 확정 자식을 확인하므로 자식 순서에 의존하지 않는다.
결과를 확정하는 자식이 없으면 첫 오류를 그대로 반환한다. 모름과 오류만으로 확정값을 만들지 않는다.

모든 자식을 계속 평가하므로 기존 정상 평가의 trace는 유지된다.
기존 `if`의 오류 trace 도우미를 함께 사용해, 흡수한 오류는 해당 자식의 부분 trace 대신
`error: ...` 항목으로 남긴다. 확정 결과의 `missing_inputs`는 비어 있고,
미확정 결과에서는 필요한 입력을 계속 추적한다. `if`의 동작은 그대로다.

## 검증

모두 이 worktree에서 로컬 실행했다. rustc/cargo 1.98.1을 사용했고 원격 CI 실행을 주장하지 않는다.
로그 위치: [`packages/rules-engine/evidence/audit2-all-any-errors/`](../../../packages/rules-engine/evidence/audit2-all-any-errors/).

| 명령 | 결과·증거 |
|---|---|
| 수정 전 `cargo test -p onjeon-rules-engine --test all_any_errors --test soundness --offline` | 회귀 시험 4개 중 2개가 `DateOutOfRange`로 실패. Cargo가 첫 실패 대상에서 중단([before.log](../../../packages/rules-engine/evidence/audit2-all-any-errors/before.log)) |
| 수정 전 `cargo test -p onjeon-rules-engine --test soundness hiding_an_irrelevant_failing_input --offline` | 새 건전성 시험 1개가 같은 오류로 실패([soundness-before.log](../../../packages/rules-engine/evidence/audit2-all-any-errors/soundness-before.log)) |
| 수정 후 `cargo test -p onjeon-rules-engine --test all_any_errors --test soundness --test unknown_branch_errors --offline` | 17개 통과([focused.log](../../../packages/rules-engine/evidence/audit2-all-any-errors/focused.log)) |
| `cargo test --all --offline` | 407개 통과, 실패 0, 기존 ignored 1. 골든 trace·해시, 변이, 실제 조항, 엔진 호출 소비자와 문서 시험 포함([workspace.log](../../../packages/rules-engine/evidence/audit2-all-any-errors/workspace.log)) |
| `cargo fmt --all -- --check` | 통과([fmt.log](../../../packages/rules-engine/evidence/audit2-all-any-errors/fmt.log), 진단 출력 없음) |
| `cargo clippy --all-targets --offline -- -D warnings` | 통과([clippy.log](../../../packages/rules-engine/evidence/audit2-all-any-errors/clippy.log)) |

[회귀 시험](../../../packages/rules-engine/tests/all_any_errors.rs)은 `all`/`any` 각각에 대해
날짜 범위·오버플로·타입 오류와 모름을 포함한 자식 순서 6종(총 36조합), 확정 자식이 없을 때의
오류 유지·첫 오류 경로, 모름의 blocker, 흡수 오류 trace와 결과 직렬화의 재현성을 검증한다.
[건전성 시험](../../../packages/rules-engine/tests/soundness.rs)은 오류를 내는 날짜 입력을
생략하거나 `null`로 숨겨도 독립적인 확정 결과가 유지되는지, 결정 입력까지 숨기면
모름과 필요한 입력 목록이 반환되는지 두 연산·두 자식 순서에서 확인한다.

[경로 검사](../../../packages/rules-engine/evidence/audit2-all-any-errors/scope-check.log)로 변경이
허용 경로 안에 있고 보호 파일이 HEAD와 동일함을 확인했다. `git diff --check`와 문서의
로컬 링크 대상 확인도 통과했다. commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 증명 범위

BLUEPRINT의 A2·A5, Q2·Q5·Q7, L6, I1·I18, M0 엔진 기반 유지보수에 연결된다.
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08(가상 상황 계산)·P14(계산 trace)의
엔진 기반 수정 증거다. 시험 규칙은 모두 `fixture_only` 합성 규칙이다.
이 기록은 실제 릴리스 상품의 경계 시나리오나 화면→원문 좌표 증거를 대체하지 않으며,
P08·P14의 제품 완료 또는 첫 출시 준비 완료를 주장하지 않는다.
