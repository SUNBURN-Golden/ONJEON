# Audit 8 기관 원장 무결성 검증

`audit8-registry-integrity-test`는 기관 원장을 검증하며 P01·P02에 연결된다. 시작 시점에 CI는 이미 `registry_check.py`를 실행해 CSV 행 폭, ID 중복, `listed_in`의 출처 참조, 정본 어휘의 상태 코드와 감독당국 대조를 검사했다. 같은 단계에 조사 회차별 건수와 접근 로그의 SHA-256 연결 검증을 추가했다. `listed_in`의 빈 값은 출처 미확인 시드에만 허용한다. [BLUEPRINT §6](../../BLUEPRINT.md#6-공유-어휘-enum-레지스트리) · [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).

| 파일 | 2026-10-09 기관 조사 | 2026-11-10 감독당국 재조회 | 현재 데이터 행 |
|---|---:|---:|---:|
| `insurers.csv` | 53 | — | 53 |
| `cooperatives_and_others.csv` | 16 | — | 16 |
| `excluded_or_historical.csv` | 49 | — | 49 |
| `sources.csv` | 66 | 9 | 75 |
| `access_log.csv` | 98 | 14 | 112 |

출처와 요청 행은 각각 `retrieved_at`과 `attempted_at`의 날짜로 센다. 같은 총수라도 날짜별 배분이 달라지면 실패한다. 새 조사 회차를 이 원장에 추가할 경우 해당 회차 건수를 검사 기준과 함께 갱신한다.

## SHA-256 연결

`python3 -I tools/registry_check.py --access-digests`가 HTTP 200·`reachable`인 68건의 행 번호, 요청 시각, 목적, 요청·최종 URL, 해시 종류, 해시와 출처를 CSV로 출력한다. 요청 시각과 요청 URL을 사용해 같은 URL의 다른 응답을 구별한다. 최초 조사 49건의 응답 본문 해시는 `sources.csv`에서, 재조회 14건의 해시는 당시 요청 기록에서 읽는다. 재조회 기록의 호스트·최종 URL·요청 방식과 POST 인자를 접근 로그와 대조하고, 그중 출처 원장에도 있는 9건은 두 해시가 일치해야 한다. [감독당국 요청 기록](../../../tools/evidence/audit5-registry-readme-sync/requests.tsv).

최초 조사 탐색 5건은 저장소에 당시 응답 본문이나 그 해시가 없어 `access_record_only`로 표시한다. 이 해시는 원래 CSV 행의 전체 필드를 키가 정렬된 공백 없는 UTF-8 JSON 객체로 직렬화해 계산한다. 검사기에 고정한 다음 다섯 기록에만 이 방식이 적용되며, 다른 요청의 응답 해시 누락은 실패한다.

| `access_log.csv` 행 | 탐색 목적 |
|---:|---|
| 10 | DART 홈 |
| 14 | 한국화재보험협회 홈 |
| 15 | 금융위원회 홈 |
| 20 | 한국어 위키백과 홈 |
| 27 | DART 기업개황 검색 폼 첫 요청 |

이 검증은 저장소의 기관 조사 기록을 확인한다. P01·P02의 상품·특약·판매본 분모와 공시 원문 보존·확보율에는 별도 완료 증거가 필요하다.

## 로컬 확인

```sh
python3 -I tools/registry_check.py
python3 -I tools/registry_check.py --access-digests
python3 -m unittest discover -s tools/tests -p 'test_registry*.py' -v
```

기본 검사 결과는 `68 reachable HTTP 200 observations: 63 response body digests, 5 access record digests`다. 회귀 시험은 CI의 명령을 임시 원장에 실행해 폭·중복 ID·참조·상태 코드·건수·해시 연결 오류를 거부하고 입력을 보존하는지 확인한다. 해시 CSV를 원래 요청 기록과 전수 대조하고, 모호한 참조·잘못된 해시·재조회 기록 불일치도 검출한다. [회귀 시험](../../../tools/tests/test_registry_check.py).

| 로컬 실행 | 결과 |
|---|---|
| 원장 회귀 시험 | 104개 통과 |
| `tools/tests` 전체 | 1,822개 통과, 6개 건너뜀 |
| 데몬 실행기 검증 | 81개 통과 |
| Rust 1.98.1 워크스페이스 | 566개 통과, 1개 제외 |
| 규칙 순서·시나리오 API·온톨로지 실행기 | 각각 2개·4개·4개 통과 |
| 워크플로·어휘·설계 명세·검증 자료·온톨로지 검사 | 통과 |
