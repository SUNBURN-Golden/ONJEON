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
외부 DSL 키·입력 타입·출력 형식·내용 해시는 변경하지 않았다.
범위 타입 검사는 로더에서 수행한다. 아래 Fix round 1의 평가기 변경은 동반 적격 처리 수정이다.
범위 비교를 모름으로 계산할지 등 비교 의미의 확장은 BLUEPRINT §12의 W3 열린 결정으로 남는다.

## 검증

첫 수정 검증은 이 worktree에서 로컬 실행했다. rustc/cargo 1.98.1, Cargo 검사에 `--offline`을 사용했으며
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

## Fix round 1: CI 실패 재현과 통합 fixture 수정

제공된 CI 실행 `40266306859`의 실패는 Python 검사나 lint가 아니라
`soundness::unknown_eligibility_also_absorbs_amount_date_and_runtime_type_errors`의
로드 실패였다. 이 시험은 범위 비교를 런타임 `Type` 오류 예제로 사용했기 때문에
새 로더가 `amount.if.lt: money_range operands cannot be compared`로 거부했다.

이 worktree의 시작 커밋 `3a8cede`에는 해당 시험과 모름 적격의 금액 오류 흡수 수정이
없었다. 로컬 Git 객체 `a38b836`(동반 `audit2-engine-unknown-elig-amount-error` 수정)의
`src/eval.rs`와 `tests/soundness.rs`만 가져와 CI의 9개 건전성 시험을 재현했다.
브랜치 merge나 commit은 하지 않았다. 이 상태에서 8개 통과·해당 1개 실패와
CI와 동일한 오류 경로·메시지를 확인했다
([soundness-before.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/soundness-before.log)).

범위 비교 fixture를 역순 `days_between`의 런타임 `Type` 오류로 교체했다.
정적 범위 비교 거부는 유지하며, 두 오류 종류(날짜 범위·런타임 타입) 모두
적격 모름에서는 조건부 금액 모름·`flag` blocker·흡수 오류 trace,
적격 참에서는 정확한 오류 경로·메시지 전파, 적격 거짓에서는 `not_payable`을 검증한다.
동반 수정의 오버플로·성공 금액·`all`/`any` 통합 시험도 함께 보존했다.
README의 범위 비교 한계 문구도 로드 단계 거부로 명확히 했다.

아래 재검증은 로컬 실행이며 원격 CI 재실행 결과가 아니다.
Rust 1.98.1과 CI가 지정한 boto3 1.43.100을 사용했다.
`rules-engine` job의 모든 검사 명령을 저장소 루트에서 실행했고,
전체 workspace clippy와 전체 Rust 시험은 CI와 같은 명령(`--offline` 없음)을 사용했다.
증거는 [round1 로그 디렉터리](../../../packages/rules-engine/evidence/audit2-range-compare/round1/)에 둔다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --test soundness --test range_comparisons --test all_any_errors --test unknown_branch_errors --offline` | 29개 통과, 건전성 9개·범위 비교 8개 포함([focused.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/focused.log)) |
| `python3 tools/vocab_check.py` | 49개 축·269개 값 통과([vocab.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/vocab.log)) |
| `python3 tools/validation_check.py` | 내부 일관성 통과, 원본 재검증 아님([validation.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/validation.log)) |
| `python3 tools/validation_check.py --selftest` | 변조 38종 모두 의도한 이유로 거부([validation-selftest.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/validation-selftest.log)) |
| `python3 -m unittest discover -s tools/tests -v` | 915개 실행, 실패 0, 환경 조건에 따른 skip 6(원본 아카이브·pdftotext 관련 5개, 구형 botocore 전용 1개). boto3 1.43.100([python-tests.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/python-tests.log)) |
| `cargo fmt --all -- --check` | 통과([fmt.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/fmt.log)) |
| `cargo clippy --all-targets -- -D warnings` | 저장소 루트의 전체 workspace 통과([workspace-clippy.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/workspace-clippy.log)) |
| `cargo test --all` | Rust 단위·통합·문서 시험 419개 통과, 실패 0, 기존 ignored 1([workspace-tests.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/workspace-tests.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과([spec-check.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/spec-check.log)) |

변경 경로·보호 파일·문서 링크·`git diff --check`와 실행 환경·소스 해시는
[final-checks.log](../../../packages/rules-engine/evidence/audit2-range-compare/round1/final-checks.log)에 기록했다.
이번 수정에서도 commit·push·GitHub 호출은 수행하지 않았다.

## Fix round 2: main 병합 충돌 해결

진행 중인 main 병합의 충돌 두 곳(`packages/rules-engine/README.md`,
`tests/soundness.rs`)을 해결했다. README는 main의 자격 미정 오류 처리 설명·증거 링크와
이 노드의 범위 비교 로드 거부 설명을 함께 유지한다. 적격 거짓이면 금액을 평가하지 않는
동작도 명시한다.

`soundness`는 범위 비교 대신 역순 `days_between`으로 런타임 타입 오류를 만드는
round 1 fixture와 적격 모름·참·거짓, 오류 trace 검증을 유지한다. main의
금액 내부 `all`/`any` 오류 흡수 회귀 시험도 보존했다. 범위 비교는 로드에서 거부하므로
런타임 오류 예제로 되돌리지 않는다. 두 의도를 합치는 데 추가 실행 코드 변경은 필요하지 않았다.

이 worktree에서 병합 후 다시 실행한 결과다. 원격 CI 결과가 아니며,
증거는 [round2 로그 디렉터리](../../../packages/rules-engine/evidence/audit2-range-compare/round2/)에 둔다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --test soundness --test range_comparisons --test all_any_errors --test unknown_branch_errors --offline` | 29개 통과·실패 0([focused.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/focused.log)) |
| `cargo test --all --offline` | Rust 단위·통합·문서 시험 419개 통과·실패 0·기존 ignored 1([workspace.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/workspace.log)) |
| `cargo fmt --all -- --check` | 통과([fmt.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/fmt.log)) |
| `cargo clippy --all-targets --offline -- -D warnings` | 통과([clippy.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/clippy.log)) |
| `python3 tools/vocab_check.py` | 통과([vocab.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/vocab.log)) |
| `python3 tools/validation_check.py` 및 `--selftest` | 모두 통과([validation.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/validation.log), [validation-selftest.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/validation-selftest.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 통과([spec-check.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/spec-check.log)) |
| `python3 -I tools/ci/check_product_purpose.py` | 통과([product-purpose.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/product-purpose.log)) |
| `python3 -m unittest discover -s tools/tests -v` | 915개 실행·실패 0·환경에 따른 skip 6([python-tests.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/python-tests.log)) |

충돌 표시·미해결 파일·보호 경로·문서 링크·`git diff --check` 검사는
[final-checks.log](../../../packages/rules-engine/evidence/audit2-range-compare/round2/final-checks.log)에 기록한다.
충돌 해결을 index에 반영했으며 병합 commit은 감독자가 수행하도록 남겨 둔다.
commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 증명 범위

BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I4·I5, R16, M0 엔진 기반 유지보수에 연결된다.
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의
P08(시나리오 계산)·P14(계산 경로 추적)를 위한 엔진 기반 검증이다.
시험 규칙은 모두 `fixture_only` 합성 규칙이다. 실제 릴리스 상품 시나리오·화면 시험·출시 증거를
대체하지 않으며 P08·P14 또는 첫 출시 완료로 판정하지 않는다.
