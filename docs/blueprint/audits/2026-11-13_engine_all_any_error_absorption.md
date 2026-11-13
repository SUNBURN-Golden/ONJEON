# Audit 6: `all`·`any` 역순 날짜 오류 흡수

검증일: 2026-11-13. 노드: `audit6-engine-all-any-error-absorption`.
기준 커밋: `61f632345515dbd968d6276d633458c8cffca290` 위 미커밋 변경.
BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I1·I18, M0 엔진 유지보수 및
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08·P14에 연결된다.

## 발견 판정

작업 시작 시점의 [평가기](../../../packages/rules-engine/src/eval.rs)는 이미
`eval_deferred`로 자식 오류를 보류한다. 성공한 자식을 결합한 뒤 `all`의 거짓 또는
`any`의 참이 있으면 확정값을 반환하고, 없으면 첫 오류를 반환한다.
[Audit 2](2026-10-26_engine_all_any_lazy_error.md)의 수정과
[Audit 3](2026-10-28_engine_all_any_short_circuit.md)·
[Audit 4](2026-11-02_engine_all_any_error_dominance.md)의 회귀 시험이 존재했다.
이번에는 평가기 실행 코드를 변경하지 않고 감리 사례의 회귀 범위를 보강했다.

모든 자식을 평가해 trace를 남기는 기존 계약을 유지한다. 오류가 확정 자식의 앞에
있어도 답은 같고, 확정 자식 뒤의 오류도 결론을 바꾸지 않는다. 흡수된 오류는 실패한
자식의 부분 trace를 대신하는 `error: ...` 항목 하나로 남는다.
`days_between`은 정수 식이므로 `lt 90`으로 감싸 불리언 자식으로 사용했다.
역순 날짜 자체를 정상 값으로 바꾸거나, 모름을 거짓·0으로 바꾸지 않는다.

## 추가한 시험

[all_any_errors.rs](../../../packages/rules-engine/tests/all_any_errors.rs)에 두 시험을 추가했다.
각 시험은 두 DSL 버전 × 두 연산 × 포함 플래그 4조합 × 자식 순서 2종을 다룬다.

- `reversed_days_between_errors_are_absorbed_only_by_input_decisions`:
  `1900-01-02` → `1900-01-01` 역순 구간을 불리언 입력 `flag`와 결합한다.
  확정 입력이면 정확한 자격·지급액과 빈 blocker, 정확한 오류 trace·부분 trace 제거,
  JSON 텍스트 재로딩 후 전체 결과 바이트(두 해시 포함)의 일치를 검사한다.
  같은 규칙에서 입력이 중립값·null·누락이면 원래 `EvalError::Type`의 내용과 경로가
  그대로 반환되는지 검사한다. 리터럴 확정값에만 의존하지 않는다.
- `missing_date_blockers_survive_until_an_input_decides_all_any`:
  날짜가 없을 때 확정 입력이면 확정값·빈 blocker, 중립 입력이면 모름·`d` blocker,
  불리언도 모름이면 모름·`d`와 `flag` blocker를 검사한다.
  오류 trace가 없고 날짜·불리언의 누락/null 표현이 전체 결과 바이트를 보존하는지 확인한다.

[음성 대조](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/negative_control.py)는
이 작업 트리 내부 임시 크레이트에 소스·시험·잠금 파일을 복사한다.
정상 평가기의 11개 시험이 통과한 뒤, 자식 오류의 즉시 반환과 결합 후 오류 우선
변이를 각각 독립적으로 적용한다. 두 변이에서 새 역순 날짜 시험이 날짜 순서
`Type` 오류로 실패하고 Cargo가 101을 반환하는지 확인한다. 실제 평가기는 수정하지 않는다.

## 직접 실행한 검증

로컬 rustc/cargo 1.98.1, 잠긴 오프라인 의존성, 작업 트리 내부
`CARGO_TARGET_DIR="$PWD/target"`로 실행했다. 음성 대조는 증거 디렉터리의 `target`,
온톨로지 실행기는 `$PWD/target/ontology`를 사용했다. 원격 CI 결과를 주장하지 않는다.
로그 위치는 [검증 디렉터리](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/)다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test all_any_errors --test days_between --test unknown_branch_errors --test soundness` | 33개 통과: [focused.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/focused.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 517개 통과, 실패 0, 기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/workspace.log) |
| `cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/ontology-runner.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,609개 실행, 실패·오류 0, 기존 skip 6개: [python-tests.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/python-tests.log) |
| `python3 -I packages/rules-engine/evidence/audit6-all-any-error-absorption/negative_control.py` | 정상 11개 통과, 오류 우선 변이 둘 모두 새 시험으로 검출: [negative-control.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/negative-control.log), [정상](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/control-baseline.log), [즉시 오류](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/control-eager-error.log), [오류 우선](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/control-error-priority.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 통과: [fmt.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 같은 명령의 읽기 검사 | 등록 수 갱신·일치: [갱신](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/counts-write.log), [검사](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/counts.log) |
| `python3 -I tools/blueprint_status.py` | 결정 색인 일치: [status.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/status.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업·필수 시험 연결 통과: [product-purpose.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 46/46·존재 72/72 통과: [spec-check.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/spec-check.log) |

엔진 README의 시험 표, BLUEPRINT §11의 자동 생성 시험 등록 수(251개·doctest 3개),
09 §7의 P08·P14 기반 증거 연결을 갱신했다.
[scope.log](../../../packages/rules-engine/evidence/audit6-all-any-error-absorption/scope.log)에
허용 경로·보호 문서 불변·평가기와 공유 fixture 불변·로컬 링크·공백 검사를 기록한다.
최상위 검증 명령의 종료 코드는 모두 0이다. 음성 대조 내부 Cargo의 101은 기대한
결함 검출이다. Python의 기존 skip 6개는 원본 보관소 환경 미설정 2개,
로컬 보관소·pdftotext 필요 3개, 현재 botocore에서 해당하지 않는 구버전 거부 시험 1개다.
새 엔진 회귀 시험의 skip은 없다.

## 증명 범위

독립적으로 확정된 지급 제한·자격이 무관한 날짜 계산 오류로 가려지지 않는다는
`fixture_only` 엔진 기반 증거다. 실제 상품 릴리스·소비자 화면·원문 좌표까지의 근거
사슬·P08/P14 전체·첫 출시 완료 판정을 대체하지 않는다.
이 작업 트리에서만 작업했으며 commit·push·GitHub 호출은 수행하지 않았다.
