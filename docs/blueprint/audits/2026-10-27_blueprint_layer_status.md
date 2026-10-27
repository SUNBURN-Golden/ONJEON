# Audit 2: BLUEPRINT §4 계층 상태와 구현 범위 정정

검증일: 2026-10-27. 노드: `audit2-blueprint-layer-status`.
연결: A1·A2·A5, L0·L1·L6, I1·I2·I6·I17, M0·V0·V1, 제품 목적 대응표 P01·P02·P03·P08·P14.

## 수정과 근거

§4의 L0·L1은 “설계”, L6은 “구현(합성 규칙 범위)”로 남아 §11과 달랐다. 세 행을 “부분 구현”으로 맞추고 구현 범위와 남은 작업을 같은 상태 셀에 명시했다. 책임·출력 계약·금지 사항과 다른 계층의 상태는 유지한다. 기존 구현의 현황 정정이며 설계·결정·마일스톤 관문 변경은 없다.

| 계층 | 구현 근거 | 남은 범위 |
|---|---|---|
| L0 | `data/registry/`의 V0 기관 목록·접근 결과·공백 기록, `tools/registry_normalize.py`의 정본 어휘 정규화. `tools/tests/test_registry_denominator.py`가 보험사 53곳·접근 확인 8곳·공시 진입점 미확보 45곳·상품 목록 미열거 53곳을 대조한다 | 상품·특약 단위 분모 미열거. 접근 확인은 원문 보관 완료가 아니며 `archived`는 0 |
| L1 | `tools/crawler/`, `tools/source_archive.py`, `services/collect/`의 수집·해시 기반 불변 보존·관측 기록 도구. `tools/tests/test_source_archive*.py`와 수집기 시험이 임시 보관소·모의 응답으로 검증한다. V1의 고정 R2 기록은 아래 참조 | 전 상품 일일 수집 미완료. 도구 존재·시험 통과는 실제 수집 가동이나 확보율의 증거가 아님 |
| L6 | `packages/rules-engine/`의 DSL 로더·평가기와 합성·실제 조항 규칙. `packages/rules-engine/tests/real_clauses.rs`는 실제 조항 규칙이 `fixture_only`이고 설계 검증용인지 검사하며 등록된 사례를 평가한다 | 승인 데이터→규칙→서비스 연결 미완료. 실제 조항에서 옮긴 검증 규칙도 서비스 릴리스가 아님 |

V1 표본의 R2 보존·다운로드 대조는 `validation/source_checks/2026-10-09_r2_listing_raw.json`, `2026-10-09_r2_listing_derived_v2.json`, `2026-10-09_r2_verify_samples.json`, `2026-10-09_r2_reproduce_ocr.json`의 **2026-10-09 관측 기록**이다. 원본 58키·파생 v2 61키의 바이트 일치, 원본 해시·인용 14/14, 완전 재현 8/14이며 파생 6건은 미검증이다. `tools/tests/test_storage_provider_docs.py`가 이 기록과 설계도의 수치를 대조한다. 이번 작업에서 외부 공시나 R2에 접근하지 않았다. D-04·O14·O17·O19 관문과 V1 미통과 상태는 그대로다.

## 검증

`tools/tests/test_blueprint_layer_status.py`에 회귀 시험 5개를 추가했다. 세 계층의 부분 구현 상태, 계층별 구현 경로와 미완료 범위, 실제 조항의 `fixture_only` 한계, 과거 관측일, 출시 완료 증거 경계를 검사한다. 기존 Python 전체 시험 CI가 자동 발견한다.

문서 수정 전 5개 시험에서 하위 검사 27건이 실패했다([수정 전 로그](../../../tools/evidence/audit2-blueprint-layer-status/before.log)). 수정 후에는 모두 통과했다. 실행 로그는 [tools/evidence/audit2-blueprint-layer-status/](../../../tools/evidence/audit2-blueprint-layer-status/)에 보관한다.

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_blueprint_layer_status.py -v` | 5개 통과: [layer-tests.log](../../../tools/evidence/audit2-blueprint-layer-status/layer-tests.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,125개 실행: 통과 1,119·건너뜀 6·실패/오류 0. 기존 온톨로지 시험이 기대하는 로컬 빌드 경로를 사용하도록 공유 빌드 경로 환경을 해제했다: [python-tests.log](../../../tools/evidence/audit2-blueprint-layer-status/python-tests.log) |
| `cargo test --all` | Rust 447개 통과·무시 1·실패 0(문서 시험 포함): [rust-tests.log](../../../tools/evidence/audit2-blueprint-layer-status/rust-tests.log) |
| `python3 tools/vocab_check.py` | 통과: [vocabulary.log](../../../tools/evidence/audit2-blueprint-layer-status/vocabulary.log) |
| `python3 tools/validation_check.py` 및 `--selftest` | 내부 일관성 통과·변조 38종 검출: [validation.log](../../../tools/evidence/audit2-blueprint-layer-status/validation.log), [validation-selftest.log](../../../tools/evidence/audit2-blueprint-layer-status/validation-selftest.log) |
| `python3 -I tools/blueprint_status.py` | 결정 색인·내용 해시 일치: [status.log](../../../tools/evidence/audit2-blueprint-layer-status/status.log) |
| `python3 -I tools/blueprint_counts.py` | 현재 등록 수 일치: [counts.log](../../../tools/evidence/audit2-blueprint-layer-status/counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 제품 목적 대응표 검사 통과: [product-purpose.log](../../../tools/evidence/audit2-blueprint-layer-status/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 44/44·존재 72/72 통과: [spec-check.log](../../../tools/evidence/audit2-blueprint-layer-status/spec-check.log) |

## 제품 목적 완료 증거와의 관계

P01·P02·P03의 수집 기반과 P08·P14의 엔진 기반에 대한 현황·회귀 검사 증거다. 실제 상품·특약 분모, 전 상품 확보·변경 재처리, 승인 릴리스의 상품 트윈, 소비자 화면에서 원문까지의 연결은 이 문서로 완료 처리하지 않는다. 첫 출시 완료는 [09_제품목적_대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P01~P19 완료 증거와 T-OP-08 관문으로 판정한다.
