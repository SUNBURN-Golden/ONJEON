# Audit 8 보험료 관측의 가격 대상과 적용 기간

`PremiumObservation`은 상품(`product_ref`), 판매 구성 판(`sales_config_ref`), 특정 담보(`coverage_ref`), 주계약·특약별 담보와 가입금액(`components`)을 보존한다. 가격 원문의 `raw:sha256` 참조를 `source_revision`에 기록해 같은 URL의 개정을 구별한다. 새 필드는 원시 관측에서 선택이며, 미확인 구성이나 적용 기간이 있는 기존 관측도 읽을 수 있다. [JSON Schema](../../../packages/schemas/json/premium_observation.schema.json).

Rust 검사는 비교 자격에 확인된 금액·근거·조건·납입주기·비교 기준, 상품·판매 구성 판·완전한 담보 구성과 원문 판을 요구한다. 단일 담보에 부여한 가격은 그 담보와 구성의 유일한 담보가 일치해야 한다. 원문이 공시한 묶음은 담보 둘 이상을 요구한다. `source_as_of`는 확인된 적용 기간 안에 있어야 하며 시작일과 종료일을 모두 포함한다. 종료기한 없이 적용됨이 확인된 경우 `effective_open_ended=true`를 기록한다. [공유 계약 검사](../../../packages/schemas/src/checks.rs).

| 회귀 시험 | 검증 내용 |
|---|---|
| `test_premium_subject_and_period_field_shapes` | 가격 대상·원문 판의 식별자, 적용일 형식과 개방 여부의 자료형, 담보 구성 모양과 정수 원 가입금액 검사. |
| `premium_comparison_requires_a_complete_priced_subject_and_source_revision` | 대상·구성·원문 판·적용 기간 등이 누락된 관측의 비교 자격 거부와 원시 관측 보존. 단일 담보 가격의 일치 여부와 묶음의 구성 검사. |
| `premium_rejects_invalid_references_and_duplicate_components` | 가격 대상의 잘못된 식별자, 변경 가능한 URL을 원문 판으로 사용한 경우, 빈 구성과 중복 담보 거부. |
| `premium_effective_period_covers_the_basis_date` | 시작일·종료일 경계, 기간 밖 기준일, 존재하지 않는 날짜와 역순 기간, 명시적으로 종료기한이 없는 가격 검사. |
| `premium_round_trip_keeps_subjects_and_revisions_distinct` | 같은 금액과 비교 기준 ID에서도 판매 구성·가입금액·적용 기간·원문 판이 다른 관측을 왕복 후 구별. |
| `PremiumObservation` 픽스처 | 이전 원시 관측과 새 묶음·담보 관측의 Rust·Dart 왕복과 TypeScript 타입 검사. |

## 로컬 재실행

| 명령 | 결과 |
|---|---|
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | Rust 시험·문서 시험 542개 통과, 픽스처 재생성용 1개 기본 제외. 내장 Python API 시험 39개·계약 시험 140개 통과. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 30개 일치. Rust 빌드, TypeScript 5.9.3 타입 검사, Dart 3.13.5 분석·왕복 통과. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` | 이전 `contracts-*` 태그가 없어 자체 시험 통과. 시작 시점 스키마와 구조를 직접 대조해 선택 필드 8개와 구성 타입 1개 추가를 확인했다. 기존 원시 관측은 새 타입으로 읽히며, 불완전한 관측의 비교 자격 판정은 강화됐다. |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline` | 4개 통과. |
| 온톨로지 실행기 `cargo test --locked --offline` 및 `ontology_check.py` | Rust 4개 및 온톨로지 제약·릴리스·금액 검사 통과. |
| `python -m unittest discover -s tools/tests -v` 및 `python -m unittest discover -s tools/daemon/runner_verify/tests -v` | 도구 1,794개 및 실행기 검증 81개 통과. 도구 중 원본 보관소가 필요한 5개와 옛 botocore가 필요한 1개를 건너뛰었다. |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings`, `blueprint_counts.py`, `spec_check.py` | 통과. 명세 기계 검사 47/47, 존재 검사 72/72. |

P02·P09에는 공유 계약의 합성 회귀 증거로 연결했다. P02의 실제 공시 확보율, I7의 DB 저장 제약, P09의 실제 가격 비교·합산 차단은 각 제품 관문의 증거가 필요하다.
