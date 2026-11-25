# Audit 8 계약 스냅샷 민감도와 공개 응답 타입 경계

`ContractSnapshot.sensitivity`는 02 §1.4의 `private_policy`와 `private_health`만 허용한다. JSON Schema와 Rust·TypeScript·Dart는 어휘 정본의 같은 부분집합에서 생성한다. 전체 `sensitivity` 축은 공시 상품·개인 계약·건강·유전정보 분류에 쓰인다.

공개 담보 상세의 `layers[].lines[].dependency`와 공유 시나리오·필요성 판단의 `dependency`는 보류 상태와 미확인 항목을 담는다. 인증된 개인 계산의 `EvaluationResponse.dependency.excluded_contracts`는 부분 합산에서 제외된 계약 ID를 보존한다. 개별 결과에는 보류 상태가 남는다.

## 회귀 증거

- 변경 전 JSON Schema 시험은 `public_product`와 `genetic_private`를 허용해 실패했다. 변경 후 허용 값 두 개의 JSON Schema 검증·Rust 역직렬화와 왕복, TypeScript 타입 검사, Dart 왕복이 통과했고 제한된 두 값은 거부됐다.
- `test_i12_public_response_type_graph_excludes_private_contract_types`는 공개 OpenAPI 응답에서 객체 필드·배열 항목·맵 값을 따라가는 형식 참조를 검사한다. 변경 전 담보 상세·시나리오·필요성 판단의 성공 응답에서 모두 `ContractId`에 도달했다. 변경 후 모든 공개 응답의 검사가 통과했다. 같은 시험에서 인증 합산 응답이 `ContractId`에 도달하는 것을 확인한다. 세 공유 응답에 `excluded_contracts`를 삽입하면 JSON Schema가 거부한다.
- 작업 시작 시점과의 구조 대조는 `ContractSnapshot.sensitivity`와 세 공유 응답의 `dependency` 변경을 비호환으로 분류했다. 이 체크아웃에는 선행 `contracts-*` 태그가 없다. 계약 크레이트의 판을 올리려면 허용 경로 밖의 루트 `Cargo.lock`을 갱신해야 하므로 태그 없는 초판의 크레이트 판을 유지했다.

[스키마 시험](../../../packages/schemas/codegen/tests/test_schemas.py) · [공개 응답 그래프 시험](../../../packages/schemas/codegen/tests/test_openapi.py) · [Rust 역직렬화 시험](../../../packages/schemas/src/view_model_tests.rs)

## 로컬 재실행

| 명령 | 결과 |
|---|---|
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | Rust 시험·문서 시험 558개 통과, 픽스처 재생성용 시험 1개 기본 제외. 내장 Python 시험은 OpenAPI 40개와 스키마 생성·호환 등 146개 통과. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 30개 일치. Rust 빌드, TypeScript 5.9.3 타입 검사, Dart 3.13.5 분석·왕복 통과. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` | 선행 태그 부재 확인과 필드 삭제 자체 시험 통과. |
| 시나리오 API 및 온톨로지 실행기의 `cargo test --locked --offline` | 각 4개 통과. |
| `python3 -m unittest discover -s tools/tests -v` | 1,809개 중 1,800개 통과, 6개 건너뜀, 3개 실패. 실패한 세 시험은 작업 트리 내부로 지정한 `TMPDIR` 때문이었다. 기본 임시 경로로 다시 실행한 `test_ontology_check_tempfile.py` 6개는 모두 통과했다. 건너뛴 시험은 원본 보관소가 필요한 5개와 옛 botocore가 필요한 1개다. |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과. |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings` | 모두 통과. |
| `vocab_check.py --additive-since`, `blueprint_counts.py`, `validation_check.py --selftest`, `검증/spec_check.py`, `ontology_check.py` | 모두 통과. 어휘 축·값 증감 0, 검증 자료 변이 40개 탐지. |

I12의 증거 범위는 공유 계약의 타입 경계다. 서비스 저장·권한 연결과 실제 출시 경로의 누출 검증은 [09 P20](../proposals/설계검토_결과/09_제품목적_대응표.md#4a-개인정보-보호복구)의 완료 증거를 따른다.
