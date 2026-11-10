# Audit 5 — 따옴표 없는 링크·fileDown 파일명 변경 감지

대상: `audit5-content-hash-unquoted-links`, `tools/html_content_hash.py`.
연결: BLUEPRINT A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 기준 코드 확인과 보강

감사에서 지적한 `LINK_RE` 누락은 이 작업 트리의 기준 코드에 이미 수정돼 있었다.
[Audit 2 기록](2026-10-27_content_hash_onclick_links.md)의 v3는 `HTMLParser`로
따옴표 없는 `href`와 전체 `onclick`을 보존한다. 따라서 운영 로직과 규칙 이름
`html-visible-text-v3`을 유지하고, 감사에 명시된 정확한 형태의 회귀 증거를 보강했다.

- [해시 시험](../../../tools/tests/test_html_content_hash.py): `fileDown('x.pdf')`의
  파일명만 변경한다. 링크·버튼, 대문자 속성, 반환문, 따옴표 없는 핸들러,
  엔티티로 감싼 인수를 검사한다. 따옴표 없는 `href`는 파일명·실제 문서 ID·fragment를
  보존하면서 세션 값만 제거하는지 검사한다.
- [CLI 시험](../../../tools/tests/test_verify_sources.py): `href=x.pdf`, 링크와 버튼의
  `onclick="fileDown('x.pdf')"`에 실제 기준 바이트 SHA-256과 콘텐츠 해시를 등록한다.
  동일 바이트는 `unchanged_bytes`, 파일명만 바꾼 응답은 `changed`인지 검사하고,
  JSON 보고서의 기준·현재 바이트 해시, 규칙 이름, 저장된 응답 바이트도 확인한다.
- [변이 검사](../../../tools/evidence/audit5-content-hash-unquoted-links/check_link_mutations.py):
  따옴표 없는 `href` 또는 `onclick` 보존을 각각 메모리에서 제거한다. 두 변이 모두
  해당 해시 시험과 CLI 시험이 각각 실패해야 검사 자체가 통과한다. 운영 파일을 수정하지 않는다.

기존 시험은 링크 세션 값만 바뀔 때 `bytes_changed_content_same`을 유지하고,
v1·v2 기준선과 v3 해시를 비교하지 않는 동작도 검증한다. 실제 원본·관측·기준선은
재계산하지 않았다. `onclick`은 실행하지 않고 전체를 보존하므로 핸들러 코드나 그 안의
세션 값 변경도 콘텐츠 변경으로 판정할 수 있다는 기존 보수적 계약을 유지한다.

## 실행 증거와 한계

실행 명령·결과·로그는 [증거 안내](../../../tools/evidence/audit5-content-hash-unquoted-links/README.md)에
기록한다. 합성 HTML, 모의 다운로드와 임시 로컬 파일을 사용했으며 실제 공시 요청·R2 접근·자격 증명은
사용하지 않았다. 이 증거는 변경 감지 도구의 회귀 검증이다. 실제 전 상품 수집·변경 전파·트윈·소비자
화면·P02/P03 전체·첫 출시 완료 증거를 대신하지 않는다.
