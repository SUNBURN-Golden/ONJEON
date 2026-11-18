# Audit 7 — 보험사 감독당국 목록 교차검증

`audit7-registry-supervisory-crosscheck-overdue` · 2026-11-19 KST · BLUEPRINT L0/V0 · 09 P01 기관 목록

## 판정

Audit 5에서 2026-10-11 이후로 예정했던 감독당국 목록을 2026-11-10 11:09 UTC에 다시 조회했다. 당시 대조 기록에서 현행 원장 53곳이 FISIS(기준년월 `202606`)와 파인 두 목록에 모두 나타났다. 이번 변경에서 각 기관의 ID를 조회 출처에 연결하고, README의 공백 1을 해소로 표시했다. [당시 재조회 기록](2026-11-10_registry_readme_sync.md) · [요청별 시각·메서드·URL·응답 SHA-256](../../../tools/evidence/audit5-registry-readme-sync/requests.tsv).

| `insurers.csv`의 `entity_evidence` | 원장 행 | 두 목록에 기관 ID와 출처가 있는 행 |
|---|---:|---:|
| `two_or_more_sources` | 43 | 43 |
| `one_source` | 10 | 10 |
| 합계 | 53 | 53 |

`registry_table=insurers.csv`인 대조 행에서 `registry_id`로 보험사 `insurer_id`를 조인한다. `fisis_source_id`는 해당 업권 응답 1건을, `fine_source_ids`는 해당 분류의 페이지 전체를 가리킨다. 파인의 개별 기관 페이지는 미확인이다. 두 출처 열로 응답 9건의 URL·시각·SHA-256과 정상 요청을 추적한다. 기존 대조표 57행의 원래 10개 열과 기관 원장 3종, 출처 원장, 접근 로그를 기준 이력과 대조했다. [기관별 대조표](../../../data/registry/authority_crosscheck_2026-11-10.csv) · [출처 원장](../../../data/registry/sources.csv) · [접근 로그](../../../data/registry/access_log.csv).

2026-11-19 KST에 FISIS·파인 공개 조회 페이지와 FSS 홈페이지에 다시 접속했을 때 현재 환경에서는 HTTP 응답 전 TLS 연결이 종료됐다. 증거 기준일은 2026-11-10이며, 저장소의 기관별 대조 기록과 원본 응답 해시를 사용했다. 젠워스와 동경해상일동화재보험의 편입 여부는 알려진 공백 10에서 추적한다. 53곳 모두 `product_list_status=unqueried`이며, 상품·특약·판매본과 실제 확보율은 09 P01·P02에서 검증한다. [레지스트리 README](../../../data/registry/README.md) · [제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).

## 회귀 검증

`python3 -I tools/registry_check.py`는 기존 CI 단계에서 읽기 전용으로 실행된다. 대조 행과 양쪽 목록 ID의 누락, 중복 ID, 잘못된 기관 조인, 조회 분류나 파인 페이지 참조 오류, 출처 누락, 성공 요청과 URL·시각·FISIS POST 인자의 불일치를 검출한다. 회귀 시험은 복사한 원장에서 위 경우를 재현한다. 별도 증거 시험은 열거된 53곳을 기존 증거 등급별로 집계하고, 출처 9건의 해시·URL·시각을 당시 요청 기록과 대조한다. [CI 회귀 시험](../../../tools/tests/test_registry_check.py) · [조회 증거 시험](../../../tools/tests/test_registry_authority_crosscheck.py).

| 실행 | 결과 |
|---|---|
| `python3 -I tools/registry_check.py` | 변경 전 대조표에서 두 출처 열 누락 검출, 변경 후 통과 |
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 88개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,717개 중 1,711개 통과, 기존 건너뜀 6개, 실패·오류 0 |
| `cargo test --all --locked --offline` | 536개 통과, 기존 무시 1개 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과 |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline --target-dir target/ontology-runner` | 4개 통과 |

어휘·설계도 수치 및 결정 색인·09 연결·설계 묶음·V1 내부 일관성 및 40개 변조 검사, Rust 포맷·Clippy, Git 공백 검사도 통과했다.
