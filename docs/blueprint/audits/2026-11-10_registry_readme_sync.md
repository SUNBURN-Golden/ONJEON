# Audit 5 — registry README 접근 결과 정정과 감독당국 재교차검증

대상: `audit5-registry-readme-sync`, `data/registry/README.md`의 `home_access` 표와 알려진 공백 1·10.
작업일: 2026-11-10. 연결: Blueprint A1·Q7·L0·I17·V0/M3, 09 제품 목적 대응표 P01·P02.

## 판정과 변경

finding 두 가지를 모두 실제 증거로 해소했다.

1. `home_access`의 `tls_error`가 두 번 나열돼 있었다. 실제 `insurers.csv` 값은 3행(한화생명·동양생명·현대해상)뿐이었다. 중복 bullet을 하나의 표로 합치고, 표의 결과별 합계가 `insurers.csv`와 정확히 맞도록 고쳤다(점검 42 + `not_checked` 11 = 53).
2. 2026-10-11 이후 미뤄 둔 FISIS 재조회를 2026-11-10에 수행했다. FISIS 금융회사 목록과 파인 제도권 금융회사 조회를 실제로 받아 응답 시각·URL·sha256을 `sources.csv`·`access_log.csv`에 남기고, 기관별 대조를 `authority_crosscheck_2026-11-10.csv`(57행)로 커밋했다. README 알려진 공백 1은 "미수행" 안내에서 수행 결과·한계 안내로 바꿨다.

## 조회 결과

- FISIS: 생명보험 `PART_DIV=H` 22행, 손해보험 `PART_DIV=I` 34행, 기준년월 202606(FISIS 최신). 두 번의 POST 응답을 출처 2건으로 기록했다.
- 파인: 국내생명 14, 외국생명 8, 국내손해 18, 외국손해 16으로 56행. 페이지 7건을 출처 7건으로 기록했다.
- 두 목록의 교집합은 55곳이다. FISIS에만 젠워스 모기지 인슈어런스 코퍼레이션 한국지점, 파인에만 동경해상일동화재보험(주)서울지점이 있다.
- 합집합 57곳 중 현행 `insurers.csv` 53곳은 모두 두 목록에 있다. 나머지 4곳은 MG손해보험·캐롯손해보험(두 목록에 있고 `excluded_or_historical.csv`에 기록), 동경해상일동화재보험(파인에만 있고 DART 영문명 `AioiNissayDowaInsuranceCo.,Ltd.`와 같은 기관으로 추정), 젠워스(registry 두 파일에 없음)다.
- 명칭 비교는 exact 4, legal_suffix 31, alias 18, 비교 대상 아님 4다.

## 저장소에 있는 증거

- `data/registry/sources.csv`: 2026-11-10 감독당국 응답 9건 추가(총 75건). 모두 HTTP 200과 64자 sha256이 있다.
- `data/registry/access_log.csv`: 같은 조회의 요청 14건 추가(총 112건). 모두 `http_code=200`, `curl_exit=0`, `result=200`, `host_access=reachable`이다. 2026-10-09 중단 안내 4건은 그대로 보존했다.
- `data/registry/authority_crosscheck_2026-11-10.csv`: 기관별 대조 57행. `insurers.csv` 53곳은 각각 한 번, `comparison=matched`로만 나온다.
- `data/registry/README.md`: 파일 표, `home_access` 집계, 감독당국 교차검증 절, 알려진 공백 1·5·10을 현재 증거에 맞게 고쳤다.

## 한계

이번 대조는 **기관 목록**에 한정된다. 상품·특약·판매본 목록이 아니며 `product_list_status`는 53곳 모두 `unqueried`다. `entity_evidence`와 `two_or_more_sources`도 이번 조회로 다시 계산하지 않았다. 젠워스와 동경해상일동화재보험을 `insurers.csv` 분모에 넣을지는 편입 근거와 Aioi 중복 여부를 확인한 뒤 결정한다. 상품·문서 분모는 계속 T-DT-04의 D-04·O19 실데이터 관문을 따른다.

## 회귀 검증과 완료 범위

- `tools/tests/test_registry_authority_crosscheck.py`: 대조 CSV 57행의 범주·비교 결과·명칭 분류, 53곳 1:1 커버리지, 예외 4곳, 2026-11-10 출처 9건·요청 14건, README 집계를 검사한다(13개 시험).
- `tools/tests/test_registry_crosscheck_note.py`: 2026-10-09 중단 증거 보존과 2026-11-10 수행·한계 문구를 함께 검사한다(5개 시험).
- `python3 -m unittest discover -s tools/tests -v`: 1,520개 실행, 1,514개 통과·기존 건너뜀 6개, 실패·오류 0.
- `python3 tools/vocab_check.py`: 어휘 49축·270값 및 레지스트리 검사 통과.
- `python3 tools/registry_normalize.py`: 보험사 53·공제 16·제외 49·접근 로그 112행, 종료 코드 0.
- `git -c core.whitespace=cr-at-eol diff --check`: 공백 오류 0(CRLF CSV의 `\r`을 오류로 세지 않음).

명령·결과·조회 로그는 [실행 증거](../../../tools/evidence/audit5-registry-readme-sync/README.md)에 있다. 이 finding의 완료 범위는 README 정정과 기관 목록 재교차검증이다. 상품·문서 분모, 09 P01·P02 또는 첫 출시의 완료 증거는 아니다.
