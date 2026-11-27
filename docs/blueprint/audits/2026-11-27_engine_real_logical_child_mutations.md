# Audit 8 실제 조항의 논리 조건 제거 검증

노드 `audit8-real-rules-mutation-harness` · 2026-11-27

감리 지적은 공유 사례에 교보의 `harmed_by_beneficiary_or_contractor` 참 입력과 KB 운전자 특약의 여러 분기를 단독으로 검증하는 입력이 빠져 있다는 것이다. 수정 전 작업 트리에서 이미 범용 변이 시험 7개가 통과했고, 합성·실제 조항 규칙에서 만든 336개 변이는 엔진 보충 사례를 합친 골든 표에서 모두 검출됐다. 이번에 실제 조항의 제거 지점 수와 각 지점을 검출하는 사례를 별도 시험으로 고정했다. [변이 하네스](../../../packages/rules-engine/tests/mutation.rs).

## 검출 기준

- `eligibility`와 `amount`의 중첩 식을 순회해 `all`·`any` 자식을 한 번에 하나씩 제거한다. DSL의 최소 인수 수는 1이므로 단항식의 자식을 제거하면 빈 논리곱은 `true`, 빈 논리합은 `false`로 표현한다. `not` 아래와 금액 `if` 조건 아래의 단항식도 시험한다.
- 모든 원본 사례의 자격·지급(금액 포함)·누락 입력을 골든 기대값과 대조한다. 각 변이는 로드와 평가를 성공한 상태에서 같은 규칙의 골든 사례 하나 이상과 결과가 달라야 한다. 로그에는 규칙 ID, 제거 경로, 최초 불일치 사례 ID가 남는다.
- 실제 조항 규칙별로 제거 변이 수를 고정한다. 공유 47사례만 사용한 대조군에서는 65개 중 36개가 살아남고, 엔진 보충 사례를 포함한 111사례에서는 65개를 모두 검출한다.

| 실제 조항 규칙 | 제거·검출 건수 | 검출 사례 예 |
|---|---:|---|
| `kb-driver-fine` | 8/8 | `f08_hit_and_run_excluded`, `f09_racing_or_test_use_excluded`, `f10_intentional_insured_excluded`, `f11_intentional_contractor_excluded`, `f12_intentional_beneficiary_excluded` |
| `kb-driver-lawyer-fee` | 20/20 | `l09_formal_trial_requested_only`, `l11_not_referred_with_major_violation`, `l18_major_violation_unknown_blocks_grade_route` |
| `kyobo-1995-cancer-waiting` | 2/2 | `y05_not_a_listed_cancer` |
| `kyobo-cancer-main-dx` | 8/8 | `k18_harmed_by_beneficiary_or_contractor` |
| `kyobo-small-cancer-skin` | 8/8 | `s15_same_disease_flag_is_only_for_renewals` |
| `kyobo-wholelife-accident-death` | 9/9 | `w15_accident_harmed_by_beneficiary` |
| `kyobo-wholelife-disease-death` | 10/10 | `w20_disease_harmed_by_beneficiary` |

미확정 입력 보충 5사례도 추가했다. `k19`·`w35`·`w36`은 수익자 또는 계약자의 가해가 미확정인 경우, `f13`은 단독 수익자의 고의가 미확정인 경우, `l21`은 사망 사고에서 경찰 불송치 여부가 미확정인 경우다. 각 사례의 `unknown` 자격, 조건부 지급액, 누락 입력 이름을 고정했다. [엔진 보충 사례](../../../packages/rules-engine/tests/fixtures/cases/real).

## 실행 증거

```sh
CARGO_TARGET_DIR="$PWD/target" cargo test -p onjeon-rules-engine --locked --offline \
  --test mutation -- logical_child --nocapture --test-threads=1
```

전용 시험 3개가 통과했다. 제거 경로 65개와 경로별 골든 사례 ID, 공유 사례만 사용한 대조 결과를 보존했다. 로그의 제거 경로를 실제 규칙 JSON에서 독립적으로 열거한 경로와 대조했다. [실행 로그](../../../packages/rules-engine/evidence/audit8-real-rules-mutation-harness/child-removals.log).

| 로컬 명령 | 결과 |
|---|---|
| `cargo test --all --locked --offline --no-fail-fast` | Rust 559개 통과, 기존 무시 1개. 내부 Python 39개 및 142개 실행, 전체 실패 0, 건너뜀 2개 |
| README의 독립 Cargo 시험 3종 | 키 순서 2개, 시나리오 API 4개, 온톨로지 실행기 4개 모두 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 시스템 기본 임시 디렉터리에서 1,809개 실행, 실패 0, 건너뜀 6개 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo fmt --all -- --check` 및 `cargo clippy --all-targets --locked --offline -- -D warnings` | 통과 |
| `tools/blueprint_counts.py`, `tools/blueprint_status.py`, `tools/ci/check_product_purpose.py`, 설계 묶음 `검증/spec_check.py` | 통과. 엔진 단위·통합 시험 272개, 제품목적 대응 P01~P20, 기계 검사 47/47·존재 검사 72/72 확인 |
| `validation_check.py` 본검사·자체 시험, `ontology_check.py`, `vocab_check.py`, `registry_check.py` | 통과 |

첫 Python 전체 실행은 `TMPDIR`을 작업 트리 내부로 지정해 온톨로지 임시 파일의 저장소 외부 위치를 검사하는 3개 시험이 실패했다. 해당 재정의를 제거한 뒤 전체를 다시 실행했다.

검증 범위는 `fixture_only` 엔진 회귀다. 실제 릴리스 상품 트윈의 경계일 시나리오와 소비자 화면에서 원문 좌표까지의 추적은 P08·P14의 완료 기준으로 남아 있다. [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
