# Audit 6 — 원장 CSV 참조·상태·접근 근거 검사와 CI

대상: `audit6-registry-csv-ci-check`. 작업일: 2026-11-16.
연결: Blueprint A1·Q7·L0·I6(근거 사슬 기반)·I17·V0/M3, 09 P01·P02.

## 정정한 내용

- `access_log.csv:84`의 `homepage:other-epost`를 현행 기관 ID `homepage:public-epost`로 바꿨다.
- `access_log.csv:77`의 `homepage:nonlife-mitsuisumitomo`와 `sources.csv:49`의 `homepage_nonlife-mitsuisumitomo`에 현행 기관 ID의 `-kr` 접미사를 복원했다. 출처 URL·시각·응답 해시·접근 결과는 유지했다.
- `insurers.csv:29`의 현대해상 메모를 초기 `200_js_shell` 응답과 후속 `/index.jsp`의 `tls_handshake_fail` 실패로 구분했다. 기존 `home_access=tls_error`, 접근 상세·접근 로그·공시 미확인 상태를 유지했다.
- `excluded_or_historical.csv`는 기준 HEAD에서 이미 정규화돼 있었다([Audit 2](2026-10-27_registry_excluded_not_normalized.md)). 49행 모두 `status` 열 없이 `entity_evidence`를 사용하며 `two_or_more_sources` 2행·`one_source` 47행이다. 파일은 바이트 단위로 그대로 보존했고 CI에서 과거 열·값의 재유입을 거부하는 시험을 추가했다.

[셀별 정정 대조](../../../tools/evidence/audit6-registry-csv-ci-check/registry-correction.json)는 6개 CSV의 행 수와 나머지 모든 셀 보존, 변경 셀 4개를 확인한다.

## 검사 계약과 회귀

`tools/registry_check.py`는 표준 라이브러리만 사용하며 CSV를 수정하지 않는다. 필수 원장·열·CSV 구조를 확인한 뒤 기존 `vocab_check.lint_registry`를 재사용한다. 후자는 정본 `vocabulary.json`의 각 상태 축, 과거 `status` 열·별칭을 검사한다. 새 검사는 다음을 추가한다.

- 세 기관 원장 전체의 기관 ID 및 출처 ID의 빈 값·주변 공백·중복 거부, `listed_in`의 출처 ID 확인.
- `homepage`·`homepage_redirect`·`disclosure` 접근 목적과 대응하는 회사 페이지 출처 ID의 기관 참조 확인. `source:*.html`·`probe:*` 등의 조사 산출물 이름은 기관/출처 ID로 오인하지 않는다.
- 접근 로그의 원문 결과·기관 접근 상세를 정본 접근 코드와 대조. 기관별 홈페이지/리다이렉트·공시 요약은 관측 시각상 마지막 접근 결과와 대조하므로 CSV 행 순서에 의존하지 않는다.
- 회사 페이지 출처를 동일 목적·URL·시각·원래 결과의 접근 관측으로 추적. 초기 현대해상 JS 응답은 성공한 출처로 남겨 두고 후속 TLS 실패와 혼동하지 않는다.

`.github/workflows/ci.yml`의 별도 단계에서 의존성 설치·Rust 빌드 전에 검사한다. 회귀 17개는 원래 잘못된 참조 3곳을 각각 되돌리는 변이, 현대해상 메모·접근 상세·최종 결과, 과거 제외 상태 열·값, 누락 파일·열·CSV 구조, ID 중복, 원문 분류·출처 추적, 다중 행 셀의 물리적 줄 번호를 검사한다. 실제 CI의 검사 명령도 임시 원장에서 정상 통과·과거 참조 3곳과 제외 상태 열 회귀의 개별 실패·CSV 바이트 보존을 확인한다. 메모의 일반적 의미를 자동 판정하는 검사는 아니며 현대해상 메모는 특정 회귀 시험으로 고정한다.

## 실행 증거와 범위

[실행 증거](../../../tools/evidence/audit6-registry-csv-ci-check/README.md)에 정정 전 검사의 세 참조 오류, 정정 전 회귀 실패, 정정 후 회귀·전체 프로젝트 시험과 일관성 검사 결과를 기록한다.

이번 완료 범위는 로컬 원장 정정과 CI의 무결성 검사다. 외부 기관 요청·R2 접근·자격 증명을 사용하지 않았으며 실제 GitHub Actions 실행은 하지 않았다. 실제 상품·특약·과거 판매본 분모, 공시 보관·확보율, 트윈·소비자 화면·P01/P02 전체·첫 출시 완료를 뜻하지 않는다.
