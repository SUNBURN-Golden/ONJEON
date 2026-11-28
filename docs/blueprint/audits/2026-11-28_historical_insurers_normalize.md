# Audit 8 과거 보험사 원장 정규화

기준 원장의 49행은 Audit 2에서 이미 `entity_evidence`로 전환돼 있었다. 정규화기가 이 파일에서 공시·상품 목록 열을 생략해, 현행 협회 목록 밖에 있는 보험사의 과거 판매본과 보유계약을 수집 대상으로 표시할 수 없었다. [기준 범위](../../BLUEPRINT.md#71-범위) · [Audit 2 기록](2026-10-27_registry_excluded_not_normalized.md)

49행의 기존 16개 열은 기준 원장과 셀 단위로 일치한다. 나머지 원장 CSV 5개도 바이트 단위로 일치한다. 새 `disclosure_status`와 `product_list_status`는 49행 모두 `unqueried`다. 범위 근거가 부족한 DART 항목 37곳은 확인 대기로 남겼다. KIDI 목록에 사회보험·연금·심사 기관으로 기록된 6곳은 §7.1 범위 밖으로 표시했다. 범위 열이 없는 옛 CSV를 재처리하면 각 행을 확인 대기로 초기화한다. [현행 원장과 범위 열](../../../data/registry/README.md)

| 원판매 기관 | 공시 탐색을 위해 연결한 기관 | 확인한 사건과 근거 |
|---|---|---|
| MG손해보험 | 예별손해보험 | 2025-09-03 계약이전 결정. [금융위원회 발표](https://www.fsc.go.kr/no010101/85232) |
| 캐롯손해보험 | 한화손해보험 | 2025-10-01 흡수합병. [한화손해보험 합병 등 종료보고서](https://kind.krx.co.kr/external/2025/10/01/000937/20251001002482/12000.htm) |
| PCA생명보험 | 미래에셋생명 | 2018-03-05 통합 출범. [미래에셋생명 발표](https://life.miraeasset.com/micro/company/press/366.do) |
| 오렌지라이프생명보험 | 신한라이프 | 2021-05-12 신한생명과의 합병 인가. [금융위원회 발표](https://www.fsc.go.kr/no010101/75900) |
| 케이비생명보험 | KB라이프생명 | 2023-01-01 통합 출범. [KB라이프생명 공시](https://www.kblife.co.kr/api/archive/archives/download/posting/1504589/0) |
| 제일화재해상보험 | 한화손해보험 | 2009-12-29 흡수합병. [한화손해보험 분기보고서](https://kind.krx.co.kr/external/2026/05/29/000301/20260529000475/11013.htm) |

6개 승계 링크는 각 사건의 근거에 기록된 기관을 가리킨다. T-DT-04는 과거 원장을 입력으로 읽고, 공시 탐색에서 원판매사 ID를 유지하며 개인보험 판매본에 §7.1 상품 범위를 적용하도록 명시했다. 자동차보험·단체보험·퇴직연금은 후속 통합 대상이다. 실제 판매본·특약·공시 URL과 원문 확보율, 가입일 기준 판매본 선택 E2E는 남은 P01·P02 증거다. [T-DT-04 작업 계약](../proposals/설계검토_결과/tasks.json) · [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)

## 로컬 회귀 검증

- 정규화 시험은 과거 `status` 마이그레이션, 원래 식별자·메모 보존, 재실행 바이트 일치, 범위 확인 뒤 사유 갱신, 상품 목록 진행 상태 보존을 검사한다. 잘못된 범위 코드는 파일을 쓰기 전에 거부한다.
- CI 원장·어휘 검사는 공시·상품 상태 열 누락, 잘못된 범위·수집 사유, 범위 미확정 행의 확보 과장, 끊어진 승계 기관 ID와 근거 URL 누락을 검출한다. 검사기는 URL 형식과 원장 내 참조를 검사한다. 원문 링크는 위 공고·공시에서 확인했다.
- 기준 CSV 사본을 현행 어휘 검사기에 넣으면 첫 줄에서 `disclosure_status`, `product_list_status` 두 열의 누락을 보고한다. 현행 원장은 `python3 -I tools/registry_check.py`와 `python3 tools/vocab_check.py`를 통과했다.

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 96개 통과 |
| `python3 -m unittest discover -s tools/tests -p test_vocab_check.py -v` | 27개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,819개 실행, 1,813개 통과, 보관 원본·SDK 조건으로 6개 건너뜀. T-DT-04 입력 회귀 추가분은 위 원장 시험에서 통과 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | Rust 566개 통과, 1개 무시 |
| 규칙 해시 순서, 시나리오 API, 온톨로지 실행기 `cargo test --locked --offline` | 각각 2개, 4개, 4개 통과 |
| 설계 명세·온톨로지 검사, BLUEPRINT 집계 검사, 검증 자료 변이 시험 | 모두 통과 |
