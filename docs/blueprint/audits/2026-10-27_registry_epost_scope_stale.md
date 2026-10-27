# Audit 2 — 우체국보험 등 공제·기타 행의 범위 메모를 ADR-0018에 맞춤

대상: `audit2-registry-epost-scope-stale`.
연결: Blueprint §5 대상 범위(ADR-0004·0018)·V0, 09 제품 목적 대응표 P01·P02.

## 발견과 수정

`data/registry/cooperatives_and_others.csv:15`(`public-epost` 우체국보험)의 `notes`가 "공제 상품공시 URL 미탐색(범위 결정 대기)"로 남아 있었다. ADR-0018(2026-10-10 확정)은 우체국보험을 **포함**하고 기관 유형을 보험사와 구분해 관리하도록 정했다. 같은 파일의 다른 14행도 같은 문구를 유지했다. 공제 13곳은 ADR-0018로 **제외**됐고, 한국무역보험공사는 "범위 결정 필요"로 남아 있었지만 ADR-0018 구현자 해석은 범위 밖이다. `data/registry/README.md`의 범위 표는 이미 결정을 반영했으므로 행 메모만 표와 어긋나 있었다.

`notes`의 대기 문구를 행별 결정으로 바꿨다.

| 행 | 바뀐 메모(끝부분) |
|---|---|
| `public-epost` | `ADR-0018: 범위 포함(기관 유형은 보험사와 구분). 상품공시 URL 미탐색`. 공제가 아니므로 "공제" 표기를 지웠다 |
| `coop-*` 13행 | `ADR-0018: 공제는 범위·확보율 분모 제외. 공제 상품공시 URL은 탐색하지 않음` |
| `public-ksure` | `ADR-0018 구현자 해석: 범위 제외(기업 대상 정책보험이며 개인보험 상품군 아님. 사용자 확인 대상)`. "범위 결정 필요"를 지웠다 |

`seed-coop-nh`에는 대기 문구가 없어 그대로 두었다. README 알려진 공백 9번에 공제를 ADR-0018로 제외해 공시 URL을 탐색하지 않는다는 점과 행 메모가 범위 표를 따른다는 점을 적었다. 결정 문서(ADR-0018, 결정 원장)는 바꾸지 않았다.

## 정정·회귀 증거

- [정정 전후 대조](../../../tools/evidence/audit2-registry-epost-scope-stale/registry-correction.json): 작업 시작 기준 `HEAD`(b29da0e)와 비교했다. 16행 중 15행의 `notes` 열만 바뀌었고 헤더·행 순서·다른 열·CRLF 줄바꿈은 그대로다. 다른 원장 CSV 4개는 바이트 단위로 동일하다.
- [수정 전 시험](../../../tools/evidence/audit2-registry-epost-scope-stale/before.log): 데이터와 README를 고치기 전에 새 시험을 실행해 6개 중 5개 시험에서 32개 하위 검사가 실패했다(대기 문구 16셀 — 우체국 1, 공제 13, 무역보험 2 —, 우체국 포함·공제 13행·무역보험 제외 표기 부재, README 공백 9번).
- [범위 메모 시험](../../../tools/tests/test_registry_scope.py): 원장 CSV의 어떤 셀에도 "범위 결정 대기"·"범위 결정 필요"가 없을 것, 우체국 행이 ADR-0018 포함과 기관 유형 구분을 적고 공제·제외로 표기되지 않을 것, 공제 13행이 제외를, 무역보험 행이 구현자 해석의 제외와 사용자 확인 대상을 적을 것, ADR-0018 확정 문구와 README 범위 표·공백 9번이 이와 맞을 것을 검사한다.
- 기존 [원장 시험](../../../tools/tests/test_registry_denominator.py)의 정규화기 고정점 검사가 수정 CSV를 `tools/registry_normalize.py`로 다시 정규화해도 바이트 단위로 같음을 확인한다.

## 실행 결과

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v` | 39개 통과 | [원장 시험](../../../tools/evidence/audit2-registry-epost-scope-stale/registry-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_vocab_check.py' -v`, `python3 tools/vocab_check.py` | 모두 종료 코드 0 | [어휘 검사](../../../tools/evidence/audit2-registry-epost-scope-stale/vocab-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,006개 실행, 1,000개 통과·6개 건너뜀, 종료 코드 0 | [Python 전체 시험](../../../tools/evidence/audit2-registry-epost-scope-stale/python-tests.log) |
| 어휘·검증 자료·Blueprint 결정 색인·제품 목적 연결·설계 명세·온톨로지 검사, CRLF를 인정하는 `git diff --check` | 모두 종료 코드 0 | [일관성 검사](../../../tools/evidence/audit2-registry-epost-scope-stale/consistency-checks.log) |

첫 전체 실행은 이 작업 트리에 온톨로지 실행기 바이너리가 없어 `test_ontology_runner_io_error` 2개가 오류였다([초기 로그](../../../tools/evidence/audit2-registry-epost-scope-stale/python-tests-initial.log)). 실행기를 이 트리 안에 빌드(`CARGO_TARGET_DIR=target cargo build --locked`)한 뒤 다시 실행했다. 건너뜀 6개는 로컬 원본 보관소·`ONJEON_ARCHIVE_RAW`가 필요한 기존 시험 5개와 설치된 botocore가 이미 조건부 PUT을 지원해 해당하지 않는 구버전 시험 1개다. 이번 변경은 데이터 메모·README·Python 시험뿐이라 Rust 검사는 다시 실행하지 않았다.

## 남은 공백

- 이 파일에는 범위 열이 없다. 정규화기는 제외 행에도 `product_list_status=unqueried`와 `awaiting_T-DT-04`·`awaiting_domestic_env` 사유를 붙이고 `product_list_reason`은 "전 대상을 추적"이라고 적는다. README 공백 9번에 이 사유 코드가 분모 편입을 뜻하지 않는다고 적었지만, 구조화된 범위 열(과 필요하면 어휘 축)로 제외 행을 분모 계산에서 기계적으로 빼는 일은 후속이다.
- 결정 원장 O01 행(공제·우체국보험 포함 여부)의 종결 표기는 이 노드 범위가 아니다.

이 증거는 회사 원장 메모를 확정된 범위 결정에 맞춘 것에 한정된다. 실제 공시 요청·우체국보험 상품 목록 열거·R2 접근을 하지 않았다. 상품·특약·과거 판매본의 전수 분모, 원문 확보율, 소비자 화면 또는 첫 출시 완료를 증명하지 않으며 P01·P02 전체의 완료를 대신하지 않는다.
