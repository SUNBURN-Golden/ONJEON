# Audit 8 I7 가격 관측의 누락 차원과 비교 자격

`check_premium_observation`은 `conditions`, `package_binding`, `source_as_of`, `payment_cycle`, `comparison_basis_id`의 실제 누락과 `missing_dimensions`를 양방향으로 대조한다. 전달되지 않은 필드, `null`, 공백 문자열, 빈 조건 객체를 확인한다. 조건 객체에 들어온 개별 조건도 공백이면 누락으로 기록해야 하고, 값이 있으면 누락 목록에서 제외해야 한다. 상품군별 조건 차원은 열린 집합이므로 관측이 갖고 있지 않은 개별 조건 키도 누락 목록에 기록할 수 있다. [공유 계약 검사](../../../packages/schemas/src/checks.rs) · [O04 동일 조건 결정](../../decisions/DEC-O04.md).

최상위 `payment_cycle`이 빠진 원시 관측은 조건 객체에 같은 이름의 값이 있어도 `payment_cycle`을 누락 목록에 적어 보존할 수 있다. 조건 객체 쪽의 누락은 `conditions.payment_cycle`로 신고한다. 공개 DB에서 사용하는 `as_of` 표기는 최상위 `source_as_of`의 별칭이다. 개별 조건 `as_of`는 `conditions.as_of`로 신고한다. 기존 `channel`처럼 최상위 필드 및 별칭과 겹치지 않는 조건 키는 그대로 쓸 수 있다. 스키마와 Rust 검사기는 빈 이름, 유니코드 `White_Space` 문자뿐인 이름, 접두사 뒤의 키가 빈 이름을 거부한다. [시스템 계약 §8](../SYSTEM_CONTRACT.md#8-가격-데이터와-비교의-계약).

비교 자격을 부여하려면 납입주기와 비교 기준 ID를 포함한 다섯 필드가 있고, 관측 또는 산출 금액과 검수 결정이 있으며, 검수 상태가 `accepted`이고 누락 목록이 비어 있어야 한다. 누락을 정확히 기록한 원시 관측은 비교 자격 없이 공유 계약 검사를 통과한다. [가격 관측 스키마](../../../packages/schemas/json/premium_observation.schema.json).

| 회귀 시험 | 검증 내용 |
|---|---|
| `premium_missing_dimensions_match_comparison_fields` | 다섯 필드 각각의 누락·`null`·빈 값을 신고하지 않은 경우와 값이 있는데 누락으로 신고한 경우를 거부한다. 공백을 신고한 원시 관측을 허용하고 비교 적격 플래그가 켜지면 거부한다. |
| `premium_missing_dimensions_match_open_condition_keys` | 원래 조건 객체에 없는 키의 누락 신고를 허용한다. 같은 키를 실제 값으로 채우고 신고를 지우면 비교가 가능하다. 공백 값은 누락 신고를 요구하며, 공백이나 신고된 누락이 있으면 비교 적격 플래그를 거부한다. |
| `premium_missing_dimensions_distinguish_top_level_fields_from_conditions` | 이름이 같은 최상위 필드와 개별 조건을 별도로 대조한다. 한쪽 또는 양쪽이 빠진 원시 관측을 보존하며 최상위 납입주기가 빠진 관측의 비교는 거부한다. |
| `premium_missing_dimensions_accept_legacy_as_of_as_a_top_level_marker` | `conditions.as_of`에 값이 있어도 비어 있는 `source_as_of`를 기존 표기, 정식 표기 또는 두 표기로 신고할 수 있다. 비어 있는 날짜는 비교를 막으며, 날짜에 값이 있으면 기존 누락 표기는 거부한다. 비어 있는 개별 조건은 `conditions.as_of`로 신고한다. |
| `premium_missing_dimensions_strip_the_condition_prefix_once` | `conditions.`로 시작하는 조건 키도 접두사를 붙여 명시할 수 있다. |
| `premium_missing_dimensions_reject_blank_names`, `test_premium_missing_dimensions_accept_scoped_names_and_reject_blank_names`, `test_premium_missing_dimensions_pattern_in_ecmascript` | Rust·Python 검증과 Node.js의 ECMAScript 정규식 모두 `U+0085`를 포함한 `White_Space` 문자뿐인 이름을 거부한다. `U+001C`와 `U+FEFF`는 이 공백 집합에 속하지 않아 이름에 쓸 수 있다. 접두사 뒤에도 같은 규칙을 적용한다. |
| `premium_comparison_eligibility_needs_the_full_condition_set` | 값과 검수 결정이 있는 정상 관측과 산출 0원을 허용하고, 금액이 미확인인 관측의 비교 적격 플래그를 거부한다. |

## 로컬 재실행

| 명령 | 결과 |
|---|---|
| `cargo test -p onjeon-contracts --locked --offline premium_missing_dimensions` | 수정 전 새 회귀 시험 2개가 실패했다. 고정 필드 공백의 미신고와 값이 있는 개별 조건의 누락 신고를 검출했다. |
| `cargo test -p onjeon-contracts --locked --offline premium` | 수정 후 가격 관측 시험 4개 통과. main의 가격 대상·기간 시험과 합친 트리에서 8개 통과. |
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | 검토 개정 `fff165a` 트리에서 Rust 시험과 문서 시험 544개 통과, 픽스처 재생성용 1개 기본 제외. 내장 Python API 시험 39개와 계약 시험 140개 통과. 계약 시험은 TypeScript 5.9.3을 `TSC`로, Dart 3.13.5를 PATH로 지정해 실행했다. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 확인, Rust 빌드, TypeScript 타입 검사, Dart 분석과 JSON 왕복 통과. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` 및 `compat.py`로 작업 시작점과 직접 비교 | 이전 `contracts-*` 태그가 없어 `--latest`는 자체 시험까지 통과했다. 작업 시작점과 대조한 결과 스키마 구조 변경 0건, 이전 Rust·TypeScript·Dart 생성물의 문서 12종 읽기 또는 타입 검사 통과. |
| `cargo fmt --all -- --check` 및 `cargo clippy --locked --offline --all-targets -- -D warnings` | 통과. |
| Scenario API와 온톨로지 실행기 `cargo test --locked --offline` | 각각 4개 통과. |
| `python -m unittest discover -s tools/tests -v` | 기본 OS 임시 경로로 실행해 1,800개 중 1,794개 통과. 로컬 원본 보관소가 필요한 5개와 구버전 botocore가 필요한 1개 건너뜀. |
| `python -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과. |
| 설계 묶음 `spec_check.py`, 온톨로지 `ontology_check.py`, `python3 -I tools/validation_check.py --selftest` | 명세 기계 검사 47/47, 존재 검사 72/72, 온톨로지 검사와 검증 도구 변이 40개 통과. |
| `bash infra/db/public/test.sh` | 임시 PostgreSQL 17.12에서 기존 제약 검사 171개 통과. |

### 4차 검토 대응 재실행

| 명령 | 결과 |
|---|---|
| `cargo test -p onjeon-contracts --locked --offline premium_missing_dimensions` | 수정 전 충돌, 접두사, 공백 이름 회귀 시험 3개가 실패했다. |
| `cargo test -p onjeon-contracts --locked --offline premium` | 수정 후 가격 관측 시험 11개 통과. |
| `python3 -I -m unittest discover -s packages/schemas/codegen/tests -p test_schemas.py -k premium -v` | 수정 전 새 스키마 시험에서 빈 이름 다섯 개가 통과해 실패했다. 수정 후 가격 관측 스키마 시험 3개 통과. |
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | Rust 시험과 문서 시험 562개 통과, 픽스처 재생성용 1개 기본 제외. 내장 Python API 시험 39개와 계약 시험 143개 통과. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 확인, Rust 빌드, TypeScript 타입 검사, Dart 분석과 JSON 왕복 통과. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` | 이전 `contracts-*` 태그 없이 자체 시험 통과. 수정 전 작업 트리와의 구조 비교에서 `missing_dimensions`의 문자열 항목 패턴만 추가됐다. |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings`, `git diff --check` | 통과. |
| Scenario API와 온톨로지 실행기 `cargo test --locked --offline`, `bash infra/db/public/test.sh` | Rust 시험 각각 4개와 임시 PostgreSQL 제약 시험 171개 통과. |
| `python -m unittest discover -s tools/tests -v` | 1,809개 중 1,803개 통과. 로컬 원본 보관소가 필요한 5개와 구버전 botocore가 필요한 1개 건너뜀. |
| `python -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 중 80개 통과. `test_expired_lease_cannot_obtain_or_replace_builder_credentials`의 초기화에서 임대 지시가 없어 오류가 났다. 해당 시험 단독 재실행과 `CredentialLeaseFencing` 10개 전체 재실행은 통과했다. |
| 설계 묶음 `spec_check.py`, 온톨로지 `ontology_check.py`, `python3 -I tools/validation_check.py --selftest` | 명세 기계 검사 47/47, 존재 검사 72/72, 온톨로지 검사와 검증 도구 변이 40개 통과. |

### 5차 검토 대응 재실행

| 명령 | 결과 |
|---|---|
| `cargo test -p onjeon-contracts --locked --offline premium` | 수정 전 기존 `as_of`를 쓴 행의 새 회귀 시험이 실패했다. 수정 후 가격 관측 Rust 시험 12개 통과. |
| `python3 -I -m unittest discover -s packages/schemas/codegen/tests -p test_schemas.py -k premium -v` | 수정 전 Python에서 `U+001C`, Node.js에서 `U+0085`와 `U+FEFF`의 판정 차이를 확인했다. 수정 후 Node.js 회귀를 포함한 스키마 시험 4개 통과. |
| Rust `trim()` 결과와 Node.js `RegExp`의 전체 유니코드 스칼라 대조 | 일반 이름과 `conditions.` 접두사 이름 각각 1,112,064자에서 일치했다. ECMAScript `u` 플래그 유무를 모두 시험했다. |
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | Rust 시험과 문서 시험 563개 통과, 픽스처 재생성용 1개 기본 제외. 내장 Python API 시험 39개와 계약 시험 144개 통과. |
| `bash infra/db/public/test.sh` | PostgreSQL 17.12에서 기존 표기 `as_of`와 값이 있는 `conditions.as_of`를 함께 가진 행의 삽입을 확인했다. 첫 실행에서 거부 오류의 제약 이름이 맞아도 `grep -q` 파이프가 실패할 수 있는 검사 도우미를 발견해 셸 문자열 검사로 바꿨다. 이후 두 번의 재실행에서 각각 172개 통과. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 확인, Rust 빌드, TypeScript 타입 검사, Dart 분석과 JSON 왕복 통과. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` 및 검토 개정 `03a2033` 대조 | 이전 `contracts-*` 태그 없이 자체 시험 통과. 미출시 검토 개정과의 구조 검사는 항목의 공백 판정 변경을 호환성 파괴로 보고했다. 그 개정의 Rust·TypeScript·Dart 생성물을 사용한 문서 12종 읽기 또는 타입 검사는 통과했다. |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings`, `git diff --check` | 통과. |
| Scenario API와 온톨로지 실행기 `cargo test --locked --offline` | 각각 4개 통과. |
| `python -m unittest discover -s tools/tests -v` | 1,809개 중 1,803개 통과. 로컬 원본 보관소가 필요한 5개와 구버전 botocore가 필요한 1개 건너뜀. |
| `python -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과. |
| 설계 묶음 `spec_check.py`, 온톨로지 `ontology_check.py`, `python3 -I tools/validation_check.py --selftest` | 명세 기계 검사 47/47, 존재 검사 72/72, 온톨로지 검사와 검증 도구 변이 40개 통과. |

검증에는 공유 Rust 검사, JSON Schema 이름 검사, 합성 관측의 공개 DB 삽입을 사용했다. 공개 DB에 기준일이 없는 행을 쓸 때 필요한 `as_of`를 공유 검사기도 인정한다. 상품군별 전체 조건 차원의 완전성은 라벨 사전과 함께 검사해야 한다. 공개 DB의 나머지 제약, P02 공시 문서 확보율, P09 실제 담보 비교 E2E는 각 구현과 완료 근거를 따른다. [공개 DB 제약](../../../infra/db/public/01_schema.sql) · [제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
