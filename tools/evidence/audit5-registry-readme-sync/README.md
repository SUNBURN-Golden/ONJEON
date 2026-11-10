# Audit 5 — registry README 동기화·감독당국 재교차검증 증거

실행일: 2026-11-10. [판정·변경 범위](../../../docs/blueprint/audits/2026-11-10_registry_readme_sync.md).

레지스트리 README의 중복 `tls_error` 표기를 합치고 `home_access` 집계를 `insurers.csv`와 일치시켰다. 이어 2026-10-11 이후 미뤄 둔 FISIS·파인 재조회를 실제로 수행해 기관별 대조를 커밋했다. 상품·특약 목록은 열거하지 않았고 53곳 모두 `unqueried`다.

## 통제 조회

- 실행: 2026-11-10 11:09:04–11:09:42 UTC, 이 샌드박스(해외 IP).
- FISIS: 홈 → `fsv302.jsp` → `fsv302_getPartDiv.do` → `fsv000_selectEndMonth.do` → `fsv302_getFinanceList.do` POST 2회(`partDiv=H`/`I`, `baseMonth=202606`).
- 파인: 홈 → 제도권 금융회사 조회 7페이지(국내생명 2, 외국생명 1, 국내손해 2, 외국손해 2).
- 요청 간 1.2초 대기, 리다이렉트 1회까지 추적, 40초 타임아웃. 모든 요청은 `requests.tsv`에 시작·종료 시각, URL, POST 본문, HTTP 코드, curl 종료 코드, 크기, sha256, 최종 URL로 남겼다.
- 원문 응답 본문은 저장소 밖 scratchpad에만 두었다(기존 README의 원문 비커밋 원칙과 같다). `sources.csv`에는 목록을 실제로 담은 안정적인 응답 9건만 해시로 기록했다. `fsv302.jsp`는 요청마다 내용이 달라 출처로 기록하지 않았다.
- FISIS는 `partDiv=SH`/`SI`로 조회하면 빈 목록이 왔다. 페이지 스크립트가 `#slt0` 값의 첫 글자를 잘라 쓰므로 `H`/`I`를 사용해야 했다.

## 검증 명령·결과

| 검증 명령·방법 | 결과 | 로그 |
|---|---|---|
| 새 시험을 `git show HEAD:data/registry/README.md`로 복원한 README에 실행 | 18개 중 21개 실패·1개 오류. 중복 `tls_error`, 낡은 "미수행" 문구, 파일 표 불일치를 검출 | [수정 전](before.log) |
| `python3 -m unittest tools.tests.test_registry_authority_crosscheck tools.tests.test_registry_crosscheck_note tools.tests.test_registry_denominator -v` | 34개 통과 | [레지스트리 시험](registry-tests.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,520개 실행, 1,514개 통과·기존 건너뜀 6개, 실패·오류 0 | [Python 전체](python-tests.log) |
| `python3 tools/vocab_check.py` | 어휘 49축·270값 및 레지스트리 검사 통과 | [어휘 검사](vocabulary.log) |
| `python3 tools/registry_normalize.py` | 보험사 53·공제 16·제외 49·접근 로그 112행, 종료 코드 0 | [정규화](normalize.log) |
| `git -c core.whitespace=cr-at-eol diff --check` 및 CSV 행 수 | 공백 오류 0, `sources.csv` 75·`access_log.csv` 112·교차검증 57행 | [무결성 검사](integrity-check.log) |

수정 전 검증은 `data/registry`를 임시 디렉터리에 복사하고 README만 HEAD 버전으로 바꾼 뒤, 두 시험 모듈의 `REG`·`CROSSCHECK`를 그 디렉터리로 지정해 실행했다. 작업 트리의 CSV는 수정하지 않았다. 정상 실행과 수정 전 실패를 함께 남겨 중복 표기와 낡은 문구의 재등장을 검출함을 확인한다.

조회 원본 로그는 [requests.tsv](requests.tsv)에 있다. 새 시험은 기존 CI의 Python 발견 단계에 자동 포함된다. 미래에 기관 목록이나 상품 열거 증거가 바뀌면 이 날짜의 상태 설명과 회귀 기대값도 함께 갱신해야 한다.
