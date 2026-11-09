# Audit 5: 무관한 가지 오류와 교보 면책 규칙 재검증

검증일: 2026-11-09. 노드: `audit5-engine-irrelevant-branch-error`.
BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I1·I18, M0 엔진 유지보수 및
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정과 변경

작업 시작 시 [평가기](../../../packages/rules-engine/src/eval.rs)의 두 결함은 이미
수정돼 있었다. `all`·`any`는 자식 오류를 보류하고 `all`의 거짓·`any`의 참을
우선한다. 확정 자식이 없으면 첫 오류를 반환한다. 자격 모름에서 금액 오류는
`undetermined{conditional_amount: unknown}`으로 흡수하며, 자격의 blocker와 오류
trace를 보존한다. 자격이 참이면 금액 오류가 전파되고 거짓이면 금액을 평가하지 않는다.
기존 [논리식 수정](2026-10-26_engine_all_any_lazy_error.md)·
[자격 모름 금액 수정](2026-10-26_engine_unknown_elig_amount_error.md)을 확인했다.

실행 코드는 변경하지 않았다. 기존 계약은 모든 논리식 자식을 평가해 오류를 trace에
남기는 논리적 단락 처리다. 실행을 생략하는 단락 처리로 변경하지 않았으며, 기존
골든 trace·내용 해시·입력 해시도 바꾸지 않았다. 이번 변경은 감리의 구체적 실제 조항
재현과 두 오류 처리 경로의 결합을 고정하는 회귀 시험·완료 증거다.

## 추가한 회귀 시험

[irrelevant_branch_errors.rs](../../../packages/rules-engine/tests/irrelevant_branch_errors.rs):

- `kyobo_waiting_exclusion_survives_an_out_of_range_waiting_date`: 기존
  `kyobo-1995-cancer-waiting.json`을 직접 로드한다. 계약일 `2199-11-01`, 진단일
  `2199-12-31`, `dx_in_cancer_annex=false`이면 3개월 가산의 날짜 범위 오류가
  있어도 `not_payable`, 빈 blocker를 반환하고 금액은 평가하지 않는다. 원본 DSL
  0.1·0.2 변형, 원래·반대 자식 순서, 금액 누락·null·알려짐을 검사한다. 암 분류
  입력이 참·null·누락이면 확정 제외가 없으므로 원래 날짜 오류·경로가 유지된다.
  재로딩 뒤 전체 결과 바이트도 비교한다.
- `logical_and_amount_errors_preserve_unknown_eligibility_together`: 두 DSL 버전·
  두 논리 연산·두 자식 순서에서 날짜 오류를 흡수한 논리식으로 `if`의 모르는
  자격을 선택한다. 금액 오버플로까지 발생해도 자격·조건부 금액은 모름이며 blocker는
  `flag`다. 두 오류 trace·부분 trace 제거, null/누락 결과 바이트 동일성, DSL 0.2
  조건부 계약 효과를 확인한다. 자격을 참으로 바꾸면 금액 오버플로가 전파되고,
  거짓으로 바꾸면 금액 평가 없이 `not_payable`이다.

새 시험은 기존 CI의 `cargo test --all`에 자동 포함된다. README 시험 표와 BLUEPRINT
§11 자동 생성 등록 수도 갱신한다. 공유 fixture는 수정하지 않았다.

[음성 대조 스크립트](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/negative_control.py)는
작업 트리 내부의 임시 크레이트에서 정상 평가기로 새 시험 2개가 통과하는지 확인한다.
이어 `all`·`any`의 자식 오류에 즉시 `?` 반환을 복원하면 교보 재현 시험이
`DateOutOfRange`로 실패하고, 자격 모름의 금액 오류에 `?`를 복원하면 결합 시험이
`Overflow`로 실패하는지 각각 확인한다. 원래 평가기·fixture는 변경하지 않는다.

## 직접 실행한 검증

Rust 1.98.1, 작업 트리 전용 `CARGO_TARGET_DIR`, `ONJ_REQUIRE_RULE_02=1`로 검증한다.
로그는 [검증 디렉터리](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/)에 둔다.
로컬 검증이며 원격 CI 실행 결과를 주장하지 않는다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test irrelevant_branch_errors --test all_any_errors --test unknown_branch_errors --test soundness` | 집중 시험 29개 통과: [focused.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/focused.log) |
| `cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 497개 통과, 실패 0, 기존 ignored 1개. 내부 Python 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/workspace.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 온톨로지 runner 시험 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/ontology-runner.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 통과: [fmt.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/clippy.log) |
| `python3 -I packages/rules-engine/evidence/audit5-irrelevant-branch-error/negative_control.py` | 정상 2개 통과, 두 결함 변이가 각각 새 시험 실패(101)를 확인: [요약](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/negative-control.log), [정상](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/control-baseline.log), [논리식 변이](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/control-eager-logical.log), [금액 변이](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/control-eager-amount.log) |
| `python3 -m unittest discover -s tools/tests -v` | 전체 Python 시험 1,403개 실행, 실패 0, skipped 6개: [python.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/python.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 같은 도구의 읽기 검사 | §11 엔진 등록 수 232개·doctest 3개로 갱신 후 일치: [counts.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업·필수 시험 연결 통과: [product-purpose.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 명세 검사 통과: [spec-check.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/spec-check.log) |
| `python3 -I tools/blueprint_status.py` | 결정 색인 일치: [status.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/status.log) |

모든 최상위 명령은 종료 코드 0이다. 음성 대조의 내부 Cargo 실패는 기대한 결함 검출이다.
[scope.log](../../../packages/rules-engine/evidence/audit5-irrelevant-branch-error/scope.log)에
허용 경로·보호 문서·평가기·공유 fixture 불변·로컬 링크·공백 검사를 기록한다.

## 증명 범위

P08·P14의 엔진 기반 회귀 증거다. 실제 조항 원본 규칙도 `fixture_only` 설계 검증
전용이며, 실제 상품 릴리스·전 상품 수집·소비자 화면·첫 출시 완료 증거를 대체하지 않는다.
이 작업 트리 안에서만 작업했으며 commit·push·GitHub 호출은 수행하지 않았다.
