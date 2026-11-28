# Audit 8 과거 보험사 원장 정규화

기준 원장의 49행은 Audit 2에서 이미 `entity_evidence`로 전환돼 있었다. 정규화기가 이 파일에서 공시·상품 목록 열을 생략해, 현행 협회 목록 밖에 있는 보험사의 과거 판매본과 보유계약을 수집 대상으로 표시할 수 없었다. [기준 범위](../../BLUEPRINT.md#71-범위) · [Audit 2 기록](2026-10-27_registry_excluded_not_normalized.md)

49행의 기존 16개 열은 병합한 main 원장과 셀 단위로 일치한다. 나머지 원장 CSV 5개는 main과 바이트 단위로 일치한다. 새 `disclosure_status`와 `product_list_status`는 49행 모두 `unqueried`다. 범위 근거가 부족한 DART 항목 36곳은 확인 대기로 남겼다. KIDI 목록에 사회보험·연금·심사 기관으로 기록된 6곳은 §7.1 범위 밖으로 표시했다. 범위 열이 없는 옛 CSV를 재처리하면 각 행을 확인 대기로 초기화한다. [현행 원장과 범위 열](../../../data/registry/README.md)

| 원판매 기관 | 공시 탐색을 위해 연결한 기관 | 확인한 사건과 근거 |
|---|---|---|
| 그린손해보험 | MG손해보험(당시 지에프엠아이손해보험) | 금융위가 2013-05-03 그린손보의 모든 보험계약을 지에프엠아이손보로 이전하도록 결정했고, 2013-10-02 발표에서 MG손보로의 계약이전 완료를 확인했다. 예별손해보험의 2025-10-01 보호금융상품 목록 붙임 1의 274·275번에 판매중단된 그린라이프 이가튼튼 치아보험(1202)과 투게더상해보험(H4)이 등재돼 있다. [계약이전 결정](https://www.fsc.go.kr/po010103/70689) · [계약이전 완료 확인](https://www.fsc.go.kr/no010101/70854) · [예별손해보험 상품 목록](https://www.mggeneralins.com/webdocs/resources/files/pb061010dm/boho_sp01_2025.pdf#page=9) |
| MG손해보험 | 예별손해보험 | 2025-09-03 계약이전 결정. [금융위원회 발표](https://www.fsc.go.kr/no010101/85232) |
| 캐롯손해보험 | 한화손해보험 | 2025-10-01 흡수합병. [한화손해보험 합병 등 종료보고서](https://kind.krx.co.kr/external/2025/10/01/000937/20251001002482/12000.htm) |
| PCA생명보험 | 미래에셋생명 | 2018년 3월 합병 및 통합 출범. [미래에셋생명 2025년 사업보고서, 회사의 연혁](https://kind.krx.co.kr/external/2026/04/20/000545/20260420001513/11011.htm) |
| 오렌지라이프생명보험 | 신한라이프 | 2021-05-12 신한생명과의 합병 인가. [금융위원회 발표](https://www.fsc.go.kr/no010101/75900) |
| 케이비생명보험 | KB라이프생명 | 2023-01-01 KB라이프생명(구 푸르덴셜생명)을 존속법인으로 합병 완료. [KB금융지주 2022회계연도 영업보고서, 35쪽](https://www.kbfg.com/common/jsp/fileDownUtil.jsp?filepath=%2Fkor%2Fir%2Fdisclosure%2Fsales%2F__attachFile%2F2022%ED%9A%8C%EA%B3%84%EC%97%B0%EB%8F%84_KB%EA%B8%88%EC%9C%B5%EC%A7%80%EC%A3%BC_%EC%98%81%EC%97%85%EB%B3%B4%EA%B3%A0%EC%84%9C.pdf) |
| 제일화재해상보험 | 한화손해보험 | 2009-12-29 흡수합병. [한화손해보험 분기보고서](https://kind.krx.co.kr/external/2026/05/29/000301/20260529000475/11013.htm) |

검색 색인에서 제공하는 예별손해보험 PDF 본문으로 상품 항목을 확인했다. 로컬 환경의 직접 요청은 웹 방화벽 안내를 반환했다.

7개 승계 링크는 각 사건의 근거에 기록된 기관을 가리킨다. 그린손보는 원판매사 ID `dart-592232da`로 T-DT-04의 개인보험 판매본 추적에 포함한다. 공시 탐색에서는 `hist-nonlife-mg`의 승계 링크를 통해 `nonlife-yebyeol`까지 이어진다. T-DT-04는 과거 원장을 입력으로 읽어 원판매사 ID를 유지하고 개인보험 판매본에 §7.1 상품 범위를 적용한다. 자동차보험·단체보험·퇴직연금은 후속 통합 대상이다. 실제 판매본·특약·공시 URL과 원문 확보율, 가입일 기준 판매본 선택 E2E는 남은 P01·P02 증거다. [T-DT-04 작업 계약](../proposals/설계검토_결과/tasks.json) · [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)

## 로컬 회귀 검증

- 정규화 시험은 과거 `status` 마이그레이션, 원래 식별자·메모 보존, 재실행 바이트 일치, 범위 확인 뒤 사유 갱신, 상품 목록 진행 상태 보존을 검사한다. 공시실의 조회 결과를 홈페이지 결과보다 우선한다. 홈페이지 미조회 상태에서도 공시실 `geo_blocked`를 `blocked`와 공시실 접근 사유로 기록하는 회귀 시험을 추가했다.
- CI 원장·어휘 검사는 공시·상품 상태 열 누락, 잘못된 범위·수집 사유, 범위 미확정 행의 확보 과장, 끊어진 승계 기관 ID와 근거 URL 누락을 검출한다. 승계 ID는 현행·과거 원장의 보험사 업종을 가리켜야 한다. 그린손보→MG손보 링크는 통과하고, 국민건강보험공단·보험대리점에 연결한 시험 행은 거부한다. 검사기는 URL 형식과 원장 내 참조를 검사한다. 원문 링크는 위 공고·공시에서 확인했다.
- 기준 CSV 사본을 현행 어휘 검사기에 넣으면 첫 줄에서 `disclosure_status`, `product_list_status` 두 열의 누락을 보고한다. 현행 원장은 `python3 -I tools/registry_check.py`와 `python3 tools/vocab_check.py`를 통과했다.
- main과 통합한 검사기의 `--denominator`는 V0 기관 ID 54개를 출력한다. 우체국보험은 한 번 포함되며 과거 판매본은 T-DT-04에서 별도로 추적한다. MG손보의 승계 ID가 깨진 시험 데이터에서는 종료 코드 1과 오류를 반환하고 기관 ID 출력은 비운다. T-DT-04 계약이 현행 보험사·공제 및 기타 기관·과거 기관 원장 세 개를 모두 받는지도 확인했다. [V0 기관 범위 검증](2026-11-28_registry_scope_column.md)
- 2차 수정에서 시간 초과가 보고된 데몬 CLI 실패 경로 시험은 실제 검사기와 빈 `core/rules.py`, 검사 대상 파일만 포함한 임시 트리를 사용한다. 위반 10건과 구문 오류의 종료 코드를 기존 30초 제한 안에서 확인했다. 인자 없는 CLI 시험은 전체 데몬 트리를 검사한다. [정적 검사 회귀 시험](../../../tools/tests/test_daemon_static_checks.py)

아래는 main과의 충돌 해소 뒤 3차 수정에서 다시 실행한 결과다.

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 101개 통과 |
| `python3 -m unittest discover -s tools/tests -p test_vocab_check.py -v` | 27개 통과 |
| `python3 -m unittest discover -s tools/tests -p test_daemon_static_checks.py -v` | 19개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,825개 중 1,819개 통과, 로컬 보관 원본이 필요한 5개와 이전 botocore가 필요한 1개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | Rust 566개 통과, 1개 무시 |
| 규칙 해시 순서, 시나리오 API, 온톨로지 실행기 `cargo test --locked --offline` | 각각 2개, 4개, 4개 통과 |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings` | 모두 통과 |
| 설계 명세·온톨로지 검사, BLUEPRINT 집계 검사, 검증 자료 변이 시험 | 모두 통과 |

4차 수정 전에는 추가한 공시실 접근 결과 시험과 비보험사 승계 시험이 실패했다. 수정 뒤 아래 명령을 다시 실행했다.

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 106개 통과 |
| `python3 -I tools/registry_check.py`, `python3 tools/vocab_check.py` | 모두 통과. `--denominator` 결과는 고유 기관 ID 54개이며 우체국보험은 1회 포함 |
| `python3 -m unittest discover -s tools/tests -v` | 1,824개 통과, 로컬 보관 원본이 필요한 5개와 이전 botocore가 필요한 1개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 566개 통과, 1개 무시 |
| 규칙 해시 순서, 시나리오 API, 온톨로지 실행기 `cargo test --locked --offline` | 각각 2개, 4개, 4개 통과 |
| Rust 포맷·린트, 설계 명세·온톨로지·BLUEPRINT 집계·검증 자료 검사와 변이 시험, 데몬 모의 전이 검사 | 모두 통과 |
