# Audit 6 — fnDown·따옴표 없는 href·data-href 변경 감지 재검증

대상: `audit6-html-hash-link-extraction`, `tools/html_content_hash.py`.
연결: BLUEPRINT A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 기준 코드와 이번 변경

감사의 정규식 결함은 기준 커밋 `96a1fa44273aed8be9b6fa585334d80f4328e628`에서
이미 해결돼 있다. [Audit 2](2026-10-27_content_hash_onclick_links.md)의 v3는
`HTMLParser`로 속성 이름을 정확히 비교하고, 따옴표 없는 값과 전체 `onclick`을
보존한다. 따라서 실제 `href` 앞의 `data-href`를 링크로 취급하지 않는다.
이번에는 운영 코드·규칙 이름 `html-visible-text-v3`을 유지하면서 감사의 정확한
재현 입력과 속성 순서에 대한 회귀 시험을 추가했다.

- [해시 시험](../../../tools/tests/test_html_content_hash.py): `fnDown('x.pdf')`의
  파일명 변경을 링크·버튼·입력 요소, 대문자 속성·반환문·따옴표 없는 핸들러·엔티티
  인수에서 검사한다. `href=x.pdf`의 정확한 정규화 결과와 파일명 변경을 검사한다.
  `data-href`가 실제 `href` 앞/뒤에 있는 경우를 큰따옴표·작은따옴표·따옴표 없음으로
  검사해 실제 링크 변경은 감지하고 `data-href`만의 변경은 무시하는지 확인한다.
- [CLI 시험](../../../tools/tests/test_verify_sources.py): 실제 기준 바이트 SHA-256과
  v3 콘텐츠 해시를 등록하고 모의 응답을 처리한다. 동일 응답은 `unchanged_bytes`,
  실제 파일명 변경은 `changed`, `data-href`만 바뀐 응답은
  `bytes_changed_content_same`이어야 한다. 보고서의 기준·현재 바이트 해시와
  저장된 응답 바이트도 검사한다.
- [변이 검사](../../../tools/evidence/audit6-html-hash-link-extraction/check_link_mutations.py):
  `fnDown` 핸들러 누락, 따옴표 없는 `href` 누락, 앞선 `data-href`의 실제 링크 가림을
  메모리에서 각각 재현한다. 각 결함을 해시 시험과 CLI 시험이 모두 검출해야 성공한다.

## 실행 증거와 범위

명령·결과·로그는 [증거 안내](../../../tools/evidence/audit6-html-hash-link-extraction/README.md)에
기록한다. 합성 HTML·모의 다운로드·임시 로컬 파일을 사용했다. 기존 세션 전용 변경,
v1/v2 기준선 비교 금지와 원본 바이트 보존 계약도 관련 시험으로 재검증한다.

이 증거는 변경 감지 도구 finding의 완료 증거다. 실제 공시 확보율·R2 관측 대조·변경
전파·상품 트윈·소비자 화면·P02/P03 전체·첫 출시 완료 증거를 대신하지 않는다.
