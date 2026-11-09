# Audit 5: 종신보험 윤년 말일 자해 사망의 G13-pending 고정

검증일: 2026-11-10. 노드: `audit5-engine-flag-g13-wholelife`.
BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I2·I18, M0 엔진 기반과
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 변경과 의미

[엔진 소유 추가 사례](../../../packages/rules-engine/tests/fixtures/cases/real/kyobo-wholelife-death.cases.json)의
`w34_g13_pending_leap_day_self_harm_two_years`는 계약일·보장개시일을
`2028-02-29`, 자유로운 의사의 자해 사망일을 `2030-02-28`로 둔다.
현재 `kyobo-wholelife-disease-death` 규칙의 `calendar_year`·`month_end=clamp`와
`gte`에 따라 2년 경계 당일로 계산되어 70,000,000원 지급 결과가 나온다.
이는 기본보험금액 100,000,000원의 50%와 가입금액 100,000,000원의 20%를 합한 값이다.

사례의 `note`에 **G13-pending**을 명시했다. 공유 사례 `y03_month_end_leap`처럼
말일 처리의 원문 근거가 미확인임을 드러내며, 2년 경계 당일 포함 여부도
[GAP_REPORT G13](../validation/GAP_REPORT.md)의 열린 공백으로 유지한다.
엔진 실행 코드·공유 규칙·공유 사례·내용 해시 고정값은 변경하지 않았다.

[회귀 시험](../../../packages/rules-engine/tests/real_clauses.rs)
`whole_life_leap_day_self_harm_boundary_is_g13_pending`은 실제 확장 사례 집합에서
해당 사례를 찾아 규칙 ID, 입력 덮어쓰기, 부활 아님·심신상실 아님, `fixture_only`,
`G13-pending` 표시, 70,000,000원 기대값과 실제 결과를 검사한다.
전날 `2030-02-27`은 부적격, 다음 날 `2030-03-01`은 같은 금액으로 적격인지도 검사한다.
표시 제거·입력 변경·기대값과 로직의 동시 변경으로 이 가정을 조용히 확정할 수 없다.

사례 수는 실제 조항 106개(공유 47개 + 엔진 소유 59개), 전체 추가 사례는
합성 1개를 포함한 60개로 고정했다. 새 사례는 기존 전체 사례 실행·변이·건전성·
재로딩 결정성·결과 내용 해시 검사에도 포함된다. BLUEPRINT §11 등록 시험 수와
엔진 README를 함께 갱신한다.

## 직접 실행한 검증

Rust 1.98.1을 사용했다. Cargo 빌드·임시 파일은 이 작업 트리의
`target/`을 사용했다(`CARGO_TARGET_DIR`, Python 전체 시험의 `TMPDIR`). 원격 CI 결과가 아니다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --test real_clauses --test fixture_supplements --test golden --locked --offline` | 24개 통과·실패 0: [focused.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/focused.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 513개 통과·실패 0·기존 ignored 1개, 내부 Python 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/workspace.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,403개 실행 중 기존 R2 checkpoint 시험 1개 시간 상한 초과(120초 한도·129초 소요), skipped 6개: [python.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/python.log). 변경 대상 시험은 통과했다. |
| `python3 -m unittest discover -s tools/tests -p test_r2_checkpoint.py -k test_repeated_audits_at_cap_leave_metered_checkpoint_admission_possible -v` | 실패한 시험만 독립 재실행하여 1개 통과(6.187초): [python-timeout-recheck.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/python-timeout-recheck.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 runner 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/ontology-runner.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/clippy.log) |
| `python3 -I tools/validation_check.py`·동일 명령 `--selftest` | 정합성·변조 40건 검출 통과: [validation.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/validation.log), [validation-selftest.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/validation-selftest.log) |
| `python3 -I tools/blueprint_counts.py --write`·동일 명령 대조 | §11 등록 수 248개·doctest 3개 갱신·대조: [counts-write.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/counts-write.log), [counts.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/counts.log) |
| `python3 -I tools/blueprint_status.py`·`python3 -I tools/ci/check_product_purpose.py`·`python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 상태 색인·제품 목적·명세 정합성 통과: [status.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/status.log), [product-purpose.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/product-purpose.log), [spec-check.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/spec-check.log) |

Python 전체 실행의 시간 초과 로그를 보존했다. 해당 시험을 변경 없이 독립 재실행하면 통과했으며, 전체 Python 실행이 모두 통과했다고 보고하지 않는다.
[scope.log](../../../packages/rules-engine/evidence/audit5-flag-g13-wholelife/scope.log)에 허용 경로·보호 파일·링크·공백 검사를 기록한다.

## 증명 범위

원문에 없는 날짜 관례를 `G13-pending`으로 표시하고 현재 엔진 가정을 재현하는
`fixture_only` 회귀 증거다. G13 날짜 해석의 해결·실제 지급 확정·승인 상품 트윈·
소비자 화면 연결·P08·P14 전체 완료·첫 출시 완료 증거로 승격하지 않는다.
commit·push·GitHub 호출은 수행하지 않았다.
