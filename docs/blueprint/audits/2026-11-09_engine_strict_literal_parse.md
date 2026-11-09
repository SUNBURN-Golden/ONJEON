# Audit 5: 날짜·요율 리터럴의 엄격한 파싱

검증일: 2026-11-09. 노드: `audit5-engine-strict-literal-parse`.
BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I2·I5·I18, M0 엔진 기반과
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정과 수정

날짜 지적 `2026-+1-+5`는 시작 시점의 `parse_date`가 이미 거부했다.
[Audit 2 수정](2026-10-26_engine_parse_date_plus_sign.md)과
[Audit 3 보강](2026-10-28_engine_parse_date_strict.md)의 ASCII 숫자 검사가 존재하며,
기존 날짜 단위·통합 시험으로 부호·0 채움 누락·비ASCII 숫자·JSON 이스케이프 거부와
정상 날짜·윤일·범위 경계·재로딩 해시 보존을 다시 확인했다. 날짜 실행 코드는 변경하지 않았다.

요율 지적은 재현됐다. `parse_rate`는 소수점 앞이나 뒤가 비어도 0으로 해석해서
`5.`와 `.5`를 로드할 수 있었다. 새 통합 시험을 먼저 실행했을 때
[수정 전 로그](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/before-fix.log)에서
정상 대조 1개는 통과하고 거부 시험 3개는 실패했다. 로그에는 잘못된 요율을 가진 규칙이
내용 해시를 얻는 사례도 남아 있다.

[파서](../../../packages/rules-engine/src/value.rs)는 이제 정수부를 필수로 검사하며,
소수점이 있으면 소수부도 필수로 검사한다. 허용 문법은 ASCII 숫자의
`[0-9]{1,9}(\.[0-9]{1,9})?`다. 기존 비음수·각 부분 9자리 제한과 정수 유리수 계산을 유지한다.
호출 지점 모두 같은 파서를 쓰므로 일반 요율 문자열, 명시적 `rate`,
rule-0.2 `anniversary_band` 구간표에 적용된다.

이 수정은 내용 해시를 의미 단위로 정규화하지 않는다. 기존 계약대로 `0.5`·`0.50`·
명시적 `rate` 표현은 허용하며 각 원본 JSON 값에 따른 해시를 갖는다.
선행 0도 계속 허용한다. 공유 fixture·골든 해시는 갱신하지 않았다.

## 회귀 시험

새 단위 시험 2개와 [rate_format 통합 시험](../../../packages/rules-engine/tests/rate_format.rs)
4개를 추가했다.

- 두 DSL 버전·두 공개 로더에서 `5.`·`.5`·`0.`·`.0`·빈 값·소수점만 있는 값·
  중복 소수점·부호·공백·지수·비ASCII 숫자·10자리 초과를 오류 경로와 함께 거부한다.
  소수점을 `\u002e`로 쓴 JSON도 동일한 값으로 디코딩됨과 거부를 확인한다.
- 평가에서 선택되지 않는 `if` 가지와 rule-0.2 구간표의 미래 행도 검증한다.
- 정상 정수·소수·선행/후행 0·최소 소수 단위·양쪽 9자리 최대값의 지급액을 직접 대조한다.
  원본 JSON, 내용 해시, 결과의 해시와 재로딩 후 전체 결과 바이트를 보존한다.
- `.5`·`5.`를 선언된 입력 이름이나 명시적 문자열로 사용하는 기존 동작은 유지한다.
  같은 이름이 선언되어 있어도 명시적 `rate`의 잘못된 값은 거부한다.

## 직접 실행한 검증

Rust 1.98.1과 작업 트리 전용 `CARGO_TARGET_DIR="$PWD/target"`를 사용했다.
아래 로그는 로컬 실행 증거다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --lib --test date_format --test rate_format --test content_hash_scope` | 27개 통과·실패 0: [focused.log](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/focused.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 505개 통과·실패 0·기존 ignored 1개, 내부 Python 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/workspace.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,403개 실행·실패 0·skipped 6개: [python.log](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/python.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 온톨로지 runner 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/ontology-runner.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write`·`python3 -I tools/blueprint_counts.py` | §11 등록 수 240개·doctest 3개 갱신·대조: [갱신](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/counts-write.log), [대조](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/counts.log) |
| `python3 -I tools/blueprint_status.py`·`python3 -I tools/ci/check_product_purpose.py`·`python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 모두 종료 코드 0: [상태](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/status.log), [제품 목적](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/product-purpose.log), [명세](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/spec-check.log) |

최초 `python3 -I -m unittest` 실행은 사용자 설치 boto3를 제외하여 46개를 건너뛰었으므로
README의 `python3 -m unittest discover -s tools/tests -v` 명령으로 재검증했다.
최초 실행은 [python-isolated.log](../../../packages/rules-engine/evidence/audit5-strict-literal-parse/python-isolated.log)에 보존한다.
최종 skipped 6개는 로컬 원본 보관소·재현 도구나 구버전 botocore가 필요한 기존 조건부 시험이다.

수정 전 거부 시험의 Cargo 종료 코드 101은 기대한 결함 재현이다. 수정 후 검증 명령은
모두 종료 코드 0이다. 변경은 이 작업 트리의 허용 경로에만 있으며 보호 문서,
공유 fixture·골든값은 변경하지 않았다. commit·push·GitHub 호출은 수행하지 않았다.

## 증명 범위

잘못된 날짜·요율이 실행 규칙으로 로드되는 것을 차단하는 엔진 기반의 로컬 회귀 증거다.
합성 규칙은 `fixture_only`이며 실제 상품 릴리스가 아니다. 실제 전 상품 데이터 확보·
소비자 화면·P08·P14 전체 완료·첫 출시 완료 증거를 대체하지 않는다.
