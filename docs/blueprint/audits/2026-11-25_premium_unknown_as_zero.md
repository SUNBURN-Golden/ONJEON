# Audit 8 보험료 관측에서 금액과 미확인 사유 구분

`PremiumObservation`은 `observed`·`derived`에서 정수 원 금액을 요구한다. 명시적으로 확인하거나 산출한 0원은 유효하다. `not_found`·`unreadable`·`conflicting`·`not_applicable`·`not_disclosed`에서는 금액을 생략하고 공백이 아닌 `unknown_reason`을 기록한다. 이 다섯 상태의 관측은 비교 자격이 없다.

[JSON Schema](../../../packages/schemas/json/premium_observation.schema.json)는 두 필드의 자료형과 사유의 공백 검사를 정의한다. 상태에 따른 필드 의무와 비교 자격은 다른 교차 필드 불변식과 같이 Rust의 [`check_premium_observation`](../../../packages/schemas/src/checks.rs)에서 검증한다.

| 회귀 시험 | 검증 내용 |
|---|---|
| `premium_amount_and_reason_follow_value_state` | 일곱 상태를 검사한다. `observed`·`derived`에서 0원을 허용하고 금액 누락과 사유 혼입을 거부한다. 나머지 상태에서 0원과 양수 대체값, 사유 누락·빈 문자열·공백 문자열을 거부한다. |
| `premium_comparison_eligibility_needs_the_full_condition_set` | 조건·구성·기준일과 검수 결정이 있는 관측에서도 금액 없이 비교 자격을 부여하면 거부한다. 산출한 0원은 기존 비교 조건을 충족하면 허용한다. |
| `PremiumObservation.unavailable.fixture.json` | `not_found` 관측이 `raw_amount` 없이 사유와 근거를 보존한다. Python 스키마 검사, Rust·Dart JSON 왕복, TypeScript 타입 검사에 같은 픽스처를 사용한다. |

## 로컬 재실행

| 명령 | 결과 |
|---|---|
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | Rust 시험·문서 시험 538개 통과, 픽스처 재생성용 시험 1개 기본 제외. 내장 Python 시험은 API 39개·계약 139개 통과. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | Rust 빌드, TypeScript 5.9.3 타입 검사, Dart 3.13.5 분석·왕복 통과. 생성물 30개 일치. |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과. |
| 온톨로지 실행기 `cargo test --locked --offline` 및 `ontology_check.py` | Rust 4개와 온톨로지 제약·릴리스·금액 검사 통과. |
| `python -m unittest discover -s tools/tests -v` 및 `python -m unittest discover -s tools/daemon/runner_verify/tests -v` | 도구 1,800개 중 1,794개 통과. 원본 보관소가 필요한 5개와 옛 botocore가 필요한 1개 건너뜀. 실행기 검증 81개 통과. |
| `cargo fmt --all -- --check` 및 `cargo clippy --locked --offline --all-targets -- -D warnings` | 통과. |
| `python3 -I tools/blueprint_counts.py` 및 설계 묶음의 `검증/spec_check.py` | 통과. 명세 기계 검사 47/47, 존재 검사 72/72. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` | 이전 `contracts-*` 태그가 없어 자체 시험만 통과. 작업 시작 시점의 스키마를 직접 비교하면 `raw_amount`의 선택 필드 전환이 깨지는 변경으로 검출되고 `unknown_reason`의 선택 필드 추가가 보고된다. |

P02·P09에 연결한 증거의 범위는 공유 계약의 합성 회귀다. 공개 DB 검토본에는 `raw_amount NOT NULL` 제약이 남아 있으며, 실제 수집·DB 적재·가격 비교 화면은 각 제품 관문의 증거가 필요하다. 계약 패키지는 태그가 없는 초판 개발 상태다. 호환성 검사에 필요한 패키지 버전 상향은 이 노드의 허용 경로 밖인 루트 `Cargo.lock` 갱신을 수반한다.
