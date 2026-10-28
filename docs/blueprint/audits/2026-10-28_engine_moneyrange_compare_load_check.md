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

## Fix round 1: main 병합 충돌 해결

진행 중인 main 병합의 문서 충돌 두 곳을 해결했다. 09 §7에는 이 노드의
I5·범위 금액 비교 로드 거부 증거와 main의 `all`·`any` 오류 흡수 회귀 증거를
모두 유지했다. 엔진 README의 두 계약과 각 회귀 시험도 함께 보존한다.
로더·평가기 운영 코드는 변경하지 않았다.

BLUEPRINT §11의 충돌 값 204개·205개 중 하나를 선택하지 않고
`tools/blueprint_counts.py --write`로 병합 결과를 다시 셌다. 엔진 단위·통합
등록 수는 **207개**, doctest는 3개다. 기존 `test_each_live_count_change_requires_refresh`와
`test_cli_is_read_only_until_explicit_write_and_returns_drift`가 수치 변동의
거부·갱신 후 통과를 검증한다. main에서 들어온 실행 로그의 끝 빈 줄 하나도
제거해 공백 검사를 통과시켰다.

아래는 이 worktree에서 병합 후 직접 실행한 결과다. 원격 CI 결과가 아니다.
Cargo 산출물과 음성 대조의 임시 크레이트는 이 worktree 안에만 생성했다.
증거는 [round1 로그 디렉터리](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/)에 둔다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test range_comparisons --test all_any_errors --test unknown_branch_errors --test soundness --test readme_test_table` | 38개 통과. 범위 비교 10개·main의 논리 오류 회귀 7개 포함: [focused.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/focused.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 472개 통과·실패 0·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/workspace.log) |
| `python3 -I tools/evidence/audit3-engine-moneyrange-compare-load-check/negative_control.py` | 정상 복사본 10개 통과·범위 타입 추론 제거 시 원래 결함 검출: [negative-control.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/negative-control.log) |
| `cargo fmt --all -- --check` 및 `cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 통과: [fmt.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/fmt.log), [clippy.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 일반 검사 | 등록 207개·doctest 3개 일치: [counts-write.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/counts-write.log), [counts.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/counts.log) |
| `test_blueprint_counts.py`·`test_product_purpose.py`의 unittest discovery | 각각 17개·14개 통과: [counts-tests.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/counts-tests.log), [purpose-tests.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/purpose-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py`·`spec_check.py`·`tools/blueprint_status.py` | 모두 통과: [product-purpose.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/product-purpose.log), [spec-check.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/spec-check.log), [status.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/status.log) |
| `python3 tools/vocab_check.py`·`tools/validation_check.py` 및 `--selftest` | 모두 통과. 검증 자료 내부 일관성·변조 38종 검사이며 원본 재검증이 아니다: [vocab.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/vocab.log), [validation.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/validation.log), [validation-selftest.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/validation-selftest.log) |
| 온톨로지 runner 빌드 후 `python3 -m unittest discover -s tools/tests -v` | 1,271개 실행·실패 0·skip 6. boto3 1.43.100, runner 경로를 `ONJEON_ONTOLOGY_RUNNER`로 전달: [ontology-build.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/ontology-build.log), [python-tests.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/python-tests.log) |

미해결 index 항목·충돌 표시·허용 경로·보호 문서·운영 코드·main 시험 보존·
로컬 링크·공백 검사는 [scope.log](../../../tools/evidence/audit3-engine-moneyrange-compare-load-check/round1/scope.log)에 기록한다.
충돌 해결을 index에 반영했으며 병합 commit은 supervisor가 수행하도록 남긴다.
commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 한계

BLUEPRINT I5의 검사 근거와 엔진 README, 09 §7의 P08·P14 연결을 보강한다.
§11 등록 수는 `tools/blueprint_counts.py --write`로 갱신했다.
이 기록은 합성 규칙의 로드 안전성 회귀 증거다. 실제 상품 릴리스 정확도·전 상품
수집·소비자 화면·첫 출시 완료 또는 P08·P14 전체 완료 판정을 대신하지 않는다.
