# Audit 3 — 원장 ID 교차 참조와 빈 접근 로그 정규화

대상: `audit3-registry-id-mismatch-and-check`.
연결: Blueprint A1·Q7·L0·I6(근거 사슬 기반)·V0, 09 제품 목적 대응표 P01·P02.

## 발견과 수정

- `sources.csv:49`의 `homepage_nonlife-mitsuisumitomo`를 `homepage_nonlife-mitsuisumitomo-kr`로 정정했다.
- `access_log.csv:77`의 `homepage:nonlife-mitsuisumitomo`를 `homepage:nonlife-mitsuisumitomo-kr`로, `:84`의 `homepage:other-epost`를 `homepage:public-epost`로 정정했다. 기관 원장에 이미 있는 정본 ID를 사용한다.
- 지적된 `excluded_or_historical.csv`의 옛 `status` 열은 작업 시작 기준 이미 [Audit 2](2026-10-27_registry_excluded_not_normalized.md)에서 `entity_evidence`로 정규화돼 있었다. 파일을 다시 바꾸지 않고 기존 정규화·어휘 회귀 검사를 재실행한다.
- `normalize_access_log`는 행이 없으면 쓰기 전에 0을 반환한다. 0바이트 파일과 헤더만 있는 파일에서 발생하던 `IndexError`와 파일 잘림을 막고 원래 바이트를 보존한다.

## CI와 회귀 검사

새 읽기 전용 검사기 [`tools/registry_check.py`](../../../tools/registry_check.py)를 `.github/workflows/ci.yml`의 일반 PR·push 검사에 추가했다. 네트워크·원본 보관소 접근 없이 다음을 검사한다.

- 기관 원장 3종의 `insurer_id`는 비어 있거나 앞뒤 공백이 있으면 실패하며, 파일 내부·파일 간 중복도 실패한다. 제외·과거 기관과 공제·기타 기관의 참조도 유지한다.
- `sources.csv`의 `source_id`도 비어 있거나 앞뒤 공백·중복이 있으면 실패한다. 기관 행 `listed_in`의 세미콜론 구분 출처는 모두 존재해야 한다. 시드 기관의 빈 목록은 허용한다.
- 출처 ID의 `homepage_`·`homepage_redirect_`·`disclosure_`, 접근 목적의 `homepage:`·`homepage_redirect:`·`disclosure:` 뒤 기관 ID를 기관 원장과 대조한다. `source:*`는 원래 조사 파일명이며, 기타 탐색 기록과 함께 기관 참조로 해석하지 않는다.
- 필수 파일·필수 열 누락, 빈 헤더·중복 열·잘못된 인용·행 길이 불일치·읽기 오류는 실패한다. 진단에 파일명과 CSV의 물리적 행 번호를 남긴다. 헤더만 있는 접근 로그는 유효하다.

[`test_registry_check.py`](../../../tools/tests/test_registry_check.py)는 실제 지적 3건의 재현, 모든 참조 종류·기관 표·중복·빈 값·잘못된 CSV, CLI 성공·실패 종료 코드·읽기 전용 동작, 실제 CSV 및 CI 연결을 검사한다. [`test_registry_normalize.py`](../../../tools/tests/test_registry_normalize.py)는 빈 접근 로그 3종의 2회 재실행과 바이트 보존을 추가로 검사한다. 제외·과거 기관의 정규화·메타데이터 보존·추적 열 미추가 회귀와 `vocab_check`의 과거 `status` 열 거부 시험은 유지한다.

## 증거와 실행 결과

- [수정 전 교차 참조 진단](../../../tools/evidence/audit3-registry-id-mismatch-and-check/before-cross-reference-check.log)은 실제 CSV의 지적 3건을 정확한 행 번호와 함께 보고한다.
- [수정 전 원장 시험](../../../tools/evidence/audit3-registry-id-mismatch-and-check/before-registry-tests.log)은 빈 접근 로그 3종의 `IndexError`와 실제 CSV 참조 실패를 재현한다. 신규 합성 시험의 출처 행 번호 기대값도 4→5로 정정한 뒤 재실행했다.
- [CSV 정정 대조](../../../tools/evidence/audit3-registry-id-mismatch-and-check/registry-correction.json)는 작업 시작 `HEAD` 대비 수정 셀 3개, 기존 행·열 수, 각 파일 해시를 기록한다. 나머지 셀은 동일하며 제외·과거 기관 파일은 바이트 단위로 동일하다(`two_or_more_sources` 2행, `one_source` 47행). 임시 복사본에서 정규화 2회 후에도 기관 원장 3종·접근 로그가 현재 파일과 바이트 단위로 동일함을 확인했다.
- [원장 시험](../../../tools/evidence/audit3-registry-id-mismatch-and-check/registry-tests.log): 55개 통과.
- `python3 -m unittest discover -s tools/tests -v`: 1,286개 실행, 1,280개 통과·6개 건너뜀, 종료 코드 0([전체 Python 시험](../../../tools/evidence/audit3-registry-id-mismatch-and-check/python-tests.log)). 건너뜀은 로컬 원본 보관소가 필요한 기존 시험 5개와 설치된 botocore가 이미 조건부 PUT을 지원해 해당하지 않는 구버전 시험 1개다. 신규 회귀는 모두 실행했다.
- `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked -- -D warnings`, `cargo test --all --locked`: 모두 성공. Rust 466개 통과·1개 무시, 내장 Python 시험 39개·129개 통과([Rust 검사](../../../tools/evidence/audit3-registry-id-mismatch-and-check/rust-checks.log)). `CARGO_TARGET_DIR`는 이 작업 트리의 `target`을 명시했다.
- 어휘·교차 참조·워크플로·검증 자료·검증기 selftest·Blueprint 결정 색인·현재 수치·제품 목적 연결·설계 명세·CRLF를 인정하는 `git diff --check`: 모두 종료 코드 0([일관성 검사](../../../tools/evidence/audit3-registry-id-mismatch-and-check/consistency-checks.log), [명령별 종료 코드](../../../tools/evidence/audit3-registry-id-mismatch-and-check/consistency-results.json)).
- 전체 Python 시험은 작업 트리에 [온톨로지 실행기를 빌드](../../../tools/evidence/audit3-registry-id-mismatch-and-check/ontology-build.log)한 뒤 `CARGO_TARGET_DIR`·`ONJEON_ONTOLOGY_RUNNER`에 이 트리 경로를 지정해 실행했다. 환경에서 상속된 공유 Cargo 경로를 쓰던 [최초 실행](../../../tools/evidence/audit3-registry-id-mismatch-and-check/python-tests-initial.log)은 중단했고 최종 결과에 산입하지 않는다.

이 증거는 V0 기관 원장의 ID·출처·상태 정합성과 정규화의 회귀 검사에 한정된다. 실제 공시 수집·R2 접근·자격 증명을 사용하지 않았다. 상품·특약·과거 판매본의 전수 분모, 실제 원본 확보율, 트윈·소비자 화면 또는 첫 출시 완료를 증명하지 않으며 P01·P02 전체의 완료를 대신하지 않는다.
