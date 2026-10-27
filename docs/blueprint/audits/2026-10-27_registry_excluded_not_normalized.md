# Audit 2 — 제외·과거 기관 정규화와 CSV 어휘 검사

대상: `audit2-registry-excluded-not-normalized`.
연결: Blueprint A1·Q7·L0·I6(근거 사슬 기반)·V0, 09 제품 목적 대응표 P01·P02.

## 발견과 수정

`tools/registry_normalize.py` 실행 대상에서 `excluded_or_historical.csv`가 빠져 있어, 49행이 과거 `status` 열과 `verified_2_sources`·`verified_1_source` 값을 유지했다. `tools/vocab_check.py`는 문서만 검사해 CSV의 어휘 회귀를 거부하지 못했다.

정규화 실행에 제외·과거 기관 파일을 추가했다. 기존 `has_disclosure=False` 경로로 기관 근거·접근 결과만 정규화하므로 현행 보험사의 공시 보관·상품 목록 추적 열을 추가하지 않는다. 정본 어휘는 변경하지 않았다. 입력 CSV 읽기도 컨텍스트 관리와 `newline=""`를 사용해 파일을 닫고 인용된 줄바꿈을 보존한다.

`vocab_check`는 이제 `data/registry/*.csv`를 CSV 파서로 읽어 다음을 검사한다. CI의 기존 어휘 검사 명령에 포함되며, 검사로 CSV를 수정하지 않는다(`--write`도 어휘 문서만 생성한다).

- `entity_evidence`는 기관 근거 축, `host_access`·`home_access`·`disclosure_access`는 접근 축, `disclosure_status`·`product_list_status`는 수집 축의 현행 값만 허용한다. 과거 별칭·임의 값·빈 값·공백을 붙인 값·다른 축의 값을 거부한다.
- 과거 `status` 열과 알려진 원장 4종의 필수 상태 열 누락을 거부한다. 제외·과거 기관에는 기관 근거·두 접근 열만 필수다.
- 빈 헤더·중복 헤더·행의 셀 수 불일치·잘못된 인용부호를 거부한다. 경로와 물리적 행 번호를 보고한다.
- `result`·`*_detail`·메모·출처 등 원문 증거는 상태 코드로 해석하지 않는다. 문서의 어휘 검사 제외 표시는 구조화된 CSV 값에 적용하지 않는다.

## 정정·회귀 증거

[정정 전후 대조](../../../tools/evidence/audit2-registry-excluded-not-normalized/registry-correction.json)는 작업 시작 기준 `HEAD`와 수정 CSV를 행·열별로 비교한 결과다. 기관 ID·출처·관측 시각·제외 사유 등 기존 상태 외의 모든 값은 동일하다. 두 접근 상세 열만 빈 값으로 추가됐다. 49행 모두 현행 협회 목록 밖이라는 표기를 유지하며 다른 원장 CSV 4개는 바이트 단위로 동일하다. 정규화 재실행도 모든 CSV가 바이트 단위로 동일하다(기존 CRLF 유지).

| 기관 근거 | 정정 전 | 정정 후 | 행 수 |
|---|---|---|---|
| 여러 기관 출처 | `verified_2_sources` | `two_or_more_sources` | 2 |
| 한 기관 출처 | `verified_1_source` | `one_source` | 47 |

- [수정 전 정규화 시험](../../../tools/evidence/audit2-registry-excluded-not-normalized/before-normalize.log): 실행 대상 누락으로 확장된 CLI 회귀 시험이 실패했다.
- [수정 전 어휘 시험](../../../tools/evidence/audit2-registry-excluded-not-normalized/before-vocab.log): CSV 검사 부재로 새 시험이 실패했다.
- [데이터 정정 전 CSV 검사](../../../tools/evidence/audit2-registry-excluded-not-normalized/before-csv-check.log): 구현된 검사기가 기존 파일의 과거 열과 현행 열 누락을 보고했다.
- [어휘 회귀 시험](../../../tools/tests/test_vocab_check.py): 임시 CSV의 모든 상태 열·정본의 모든 현행 값과 과거 별칭, 축 혼용, 필수 열, CSV 구조, 원문 보존, CLI 실패와 읽기 전용 동작을 검사한다. 실제 제외 파일 49행과 기관 근거 집계도 확인한다.
- [정규화 시험](../../../tools/tests/test_registry_normalize.py): 격리된 트리의 CLI 실행으로 원장 4종을 정규화하고, 제외 행의 메타데이터 보존·추적 열 미추가·재실행 멱등성을 검사한다.

## 실행 결과

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_vocab_check.py' -v` | 27개 통과 | [어휘 시험](../../../tools/evidence/audit2-registry-excluded-not-normalized/vocab-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 33개 통과 | [원장 시험](../../../tools/evidence/audit2-registry-excluded-not-normalized/registry-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,000개 실행, 994개 통과·6개 건너뜀, 종료 코드 0 | [Python 전체 시험](../../../tools/evidence/audit2-registry-excluded-not-normalized/python-tests.log) |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked -- -D warnings`, `cargo test --all --locked` | 모두 종료 코드 0. Rust 447개 통과·1개 무시, 내장 Python 39개·129개 통과 | [Rust 검사](../../../tools/evidence/audit2-registry-excluded-not-normalized/rust-checks.log) |
| 온톨로지 실행기 빌드·온톨로지 검사 | 모두 종료 코드 0 | [빌드](../../../tools/evidence/audit2-registry-excluded-not-normalized/ontology-build.log), [검사](../../../tools/evidence/audit2-registry-excluded-not-normalized/consistency-checks.log) |
| 어휘·검증 자료·검증기 selftest·Blueprint 결정 색인·제품 목적 연결·설계 명세·CRLF를 인정하는 `git diff --check` | 모두 종료 코드 0 | [일관성 검사](../../../tools/evidence/audit2-registry-excluded-not-normalized/consistency-checks.log) |

초기 일관성 실행의 잘못된 제품 목적 검사 파일명과 온톨로지 실행기 경로는 실제 파일명·로컬 빌드 경로로 고쳤다([초기 로그](../../../tools/evidence/audit2-registry-excluded-not-normalized/consistency-checks-initial.log)). 최종 Rust 검사·Python 전체 시험에는 이 작업 트리의 `CARGO_TARGET_DIR`를 명시했고 온톨로지 실행기도 이 트리 안에 빌드했다.

Python 전체 시험의 건너뜀은 로컬 원본 보관소가 필요한 기존 시험 5개와 설치된 botocore가 이미 조건부 PUT을 지원해 해당하지 않는 구버전 시험 1개다. 신규 회귀는 모두 실행했다.

이 증거는 회사 원장의 어휘 정규화와 CI 검사에 한정된다. 실제 공시 요청·R2 접근·자격 증명을 사용하지 않았다. 상품·특약·과거 판매본의 전수 분모, 원문 확보율, 소비자 화면 또는 첫 출시 완료를 증명하지 않으며 P01·P02 전체의 완료를 대신하지 않는다.
