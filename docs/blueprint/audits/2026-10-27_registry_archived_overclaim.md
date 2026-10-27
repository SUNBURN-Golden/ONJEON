# Audit 2 — 공시 접근 확인과 원문 보관 구별

대상: `audit2-registry-archived-overclaim`, `tools/registry_normalize.py`와 `data/registry/`.
연결: Blueprint A1·Q7·L0/L1·I6(근거 사슬 기반)·M1, 09 제품 목적 대응표 P01·P02.

## 발견과 수정

정규화기는 공시 URL이 있고 `disclosure_access=reachable`이면 `disclosure_status=archived`를 기록했다. 그러나 원장 README는 원문 HTML을 저장소 밖 scratchpad에만 두었다고 명시한다. 정상 응답·응답 해시는 어휘의 `archived` 정의인 원문 수신·무결성 검사·불변 보관의 완료 증거가 아니다.

접근 확인과 보관 상태를 분리했다. 정상 응답을 확인한 8곳은 `disclosure_access=reachable`을 유지하고, `disclosure_status=unqueried`와 `공시 URL 접근 확인(reachable). 원문 무결성 검사·불변 보관 전`을 기록한다. `reachable`은 `host_access` 값이므로 `acquisition_status` 열에 새 값으로 넣지 않는다. 여기의 `unqueried`는 원문 보관 작업 전을 뜻하며, 홈페이지·공시실 미조회와는 사유 열로 구별한다. 이 도구는 보관 증거를 검증하지 않으므로 기존 `archived` 주장이나 `host_access.maps_to`만으로 보관 완료를 생성하지 않는다. 어휘 정본은 변경하지 않았다.

`disclosure_entry_missing`은 공시 URL이 없거나 접근 결과가 `reachable`이 아닐 때 붙인다. 보관 전인 8곳을 진입점 누락으로 다시 세지 않도록 URL·접근 결과로 판정한다. 상품 목록 열거 상태와 국내 IP 환경 관문은 계속 별도로 추적한다.

## 데이터 정정 증거

[정정 전후 대조](../../../tools/evidence/audit2-registry-archived-overclaim/registry-correction.json)는 작업 시작 시 `HEAD:data/registry/insurers.csv`와 수정 CSV를 행·열별로 비교한 결과다. 정확히 8개 행의 `disclosure_status`·`disclosure_gap_reason`만 변경됐다. 나머지 45개 행과 8곳의 URL·접근 결과 원문·관측 시각·기관 근거·상품 목록 정보는 동일하다. 다른 registry CSV는 변경되지 않았다.

| 구분 | 정정 전 | 정정 후 |
|---|---|---|
| 공시 원문 `archived` | 8 | 0 |
| 공시 원문 `unqueried` | 11 | 19(접근 확인 후 보관 전 8 + 미조회 11) |
| 공시 원문 `failed` / `blocked` | 31 / 3 | 31 / 3 |
| 접근 확인 `reachable` | 8 | 8 |
| 공시 진입점 누락 | 45 | 45 |
| 상품 목록 `unqueried` | 53 | 53 |

재생성 명령은 `python3 tools/registry_normalize.py`다. CSV는 기존 CRLF 형식을 유지했다.

## 회귀 증거

- [정규화 시험](../../../tools/tests/test_registry_normalize.py): HTTP 200·리다이렉트, 호스트 접근 결과의 모든 조합, 기존 `archived` 주장 정정, 접근 근거 보존과 멱등성을 검사한다. 접근 결과만으로는 `archived`가 되지 않는다.
- [분모 시험](../../../tools/tests/test_registry_denominator.py): 실제 보험사 53곳과 공제·기타 16곳의 상태·사유·어휘 준수, 정정된 집계, 공시 URL·접근 결과와 진입점 누락의 관계, CSV 재정규화 불변성을 검사한다. O19·D-04 관련 기존 시험도 유지한다.
- [수정 전 실행](../../../tools/evidence/audit2-registry-archived-overclaim/before.log): 새 기대값으로 33개 시험을 실행해 하위 사례를 포함한 실패 28건을 확인했다. 이후 코드·데이터·README를 정정했다.

## 실행 결과

이 작업 트리의 CSV·합성 입력·임시 파일로 실행했다. 실제 공시 요청·R2 접근·자격 증명을 사용하지 않았다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 33개 통과, 종료 코드 0 | [원장 시험](../../../tools/evidence/audit2-registry-archived-overclaim/registry-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 992개 실행, 986개 통과·6개 건너뜀, 종료 코드 0 | [Python 전체 시험](../../../tools/evidence/audit2-registry-archived-overclaim/python-tests.log) |
| `cargo test --all --locked` | Rust 447개 통과·1개 무시, 내장 Python 39개·129개 통과, 종료 코드 0 | [Rust 전체 시험](../../../tools/evidence/audit2-registry-archived-overclaim/rust-tests.log) |
| 온톨로지 실행기 빌드·`ontology_check.py` | 모두 종료 코드 0 | [빌드](../../../tools/evidence/audit2-registry-archived-overclaim/ontology-build.log), [검사](../../../tools/evidence/audit2-registry-archived-overclaim/ontology-check.log) |
| 어휘·검증 자료·검증기 selftest·Blueprint 결정 색인·제품 목적 연결·설계 명세 | 모두 종료 코드 0 | [일관성 검사](../../../tools/evidence/audit2-registry-archived-overclaim/consistency-checks.log) |
| `git -c core.whitespace=cr-at-eol diff --check` | 종료 코드 0. 기존 CSV의 CRLF를 줄 끝으로 인정 | [일관성 검사](../../../tools/evidence/audit2-registry-archived-overclaim/consistency-checks.log) |

초기 일관성 실행의 잘못된 `blueprint_status.py --check` 옵션은 기본 조회 명령으로 고쳤고, 일반 `git diff --check`가 CSV의 CR을 공백으로 보고한 것은 기존 CRLF를 인정하는 검사로 확인했다([초기 로그](../../../tools/evidence/audit2-registry-archived-overclaim/consistency-checks-initial.log)).

Python 전체 시험의 건너뜀 6개는 비공개 원본 보관소가 필요한 기존 시험 5개와 설치된 botocore가 이미 조건부 PUT을 지원하여 해당하지 않는 구버전 시험 1개다. 신규 회귀는 모두 실행했다. 전체 시험 전에 이 작업 트리 안에 온톨로지 실행기를 빌드했다.

이 정정은 회사 원장의 보관 과대 집계를 막는 로컬 증거다. 원본 보존·구획 추출·판 연결, 실제 상품·문서 확보율, 화면 또는 출시 완료를 증명하지 않으며 P01·P02 전체의 완료를 대신하지 않는다.
