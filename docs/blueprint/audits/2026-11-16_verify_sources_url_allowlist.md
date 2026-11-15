# Audit 6 — 출처 URL의 HTTPS·레지스트리 호스트 제한

대상: `audit6-verify-sources-url-allowlist`, `tools/verify_sources.py`의 `fetch`·`PolicyRedirectHandler`.
설계 연결: BLUEPRINT A1·Q7·L0/L1·I6·M1 및
[제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P02·P03.

## 확인과 수정

시작 HEAD `94c8b64cefb1ced5341d3e24e690915d085b3d5b`에는 비HTTPS 최초 URL,
HTTPS→HTTP·다른 호스트·다른 포트 리다이렉트 거부가 이미 있었다.
`file://` 보관소 재현은 의도한 별도 기능이다. 남은 결함은 임의의 최초 HTTPS 호스트를
허용한다는 점이었다. 기존 방어와 이번 변경을 구분한다.

- `data/registry/source_fetch_hosts.json`에 호스트 68개를 명시적으로 등록했다.
  근거는 레지스트리 출처 URL·보험사 홈페이지/공시 URL·우체국보험 홈페이지와
  V1 법령 표본 `fss_std_terms_byl15`의 `www.law.go.kr`이다. 표본 URL을 바꾸는 것만으로
  새 호스트가 자동 허용되지 않는다. 등록은 상품 범위·접근 성공·실수집 승인이나 robots 해제를 뜻하지 않는다.
- `source_origin`이 기존 HTTPS·자격증명·유효 포트 검사를 통과한 URL의 정확한 호스트를
  허용 목록과 대조한다. 최초 요청은 opener 생성 전에, 리다이렉트는 다음 요청 전에,
  최종 URL은 본문 읽기 전에 검사한다. 대소문자·기본 포트 비교는 기존 동작을 유지한다.
- 서브도메인·유사 접미사·말미 점·인코딩된 호스트 문자열·로컬/메타데이터 주소는
  자동 허용하지 않는다. 목록 누락·잘못된 JSON·잘못된 호스트 형식·빈 목록·중복도
  `FetchRejected`로 처리하고 요청하지 않는다. 임의의 환경 변수나 CLI 우회 옵션을 추가하지 않았다.
- 등록된 다른 호스트로도 이동하지 않는다. 301·302·303·307·308의 중간 본문을 읽지 않고 닫는
  기존 처리, 최종 문서 크기·MIME·시그니처 검사, robots 보류, TLS 검증을 유지한다.
- `detect`는 거부를 `fetch_failed`·종료 1로 보고하고 새 캐시·원본·관측을 쓰지 않는다.
  정상 같은 출처 HTTPS 문서의 최종 URL·바이트·관측 기록과 로컬 `file://` 보관소 사용은 계속 지원한다.

## 회귀 증거

[`test_verify_sources_fetch.py`](../../../tools/tests/test_verify_sources_fetch.py)는 실제 허용 목록과
모의 응답, 루프백 HTTPS 서버·임시 로컬 보관소를 사용한다. 기존 모의 출처는 등록된
`www.kyobo.com`으로 바꿨으며 실제 보험사에는 요청하지 않는다. 루프백 호스트는 시험별
임시 레지스트리에만 등록하고, 제품 목록에는 넣지 않는다.

검사 범위는 등록 출처·모든 V1 표본의 호스트 포함, 최초 미등록 호스트의 요청/재시도 없음,
목록 오류 시 거부, 표본 추가와 호스트 등록의 분리, 모든 리다이렉트 코드의 호스트·프로토콜·포트
검사 및 닫힘, 최종 응답 URL 거부 시 읽기 없음, 정상 문서 보존과 실패 시 기존 파일 보존이다.

기준 HEAD와 호스트 검사·리다이렉트 출처 비교·HTTPS 검사 제거 변이를 메모리에만 로드해
회귀 시험의 assertion 실패로 검출한다. 작업 파일은 변이하지 않는다.
[재실행 스크립트](../../../tools/evidence/audit6-verify-sources-url-allowlist/check_mutations.py)와
[변이 로그](../../../tools/evidence/audit6-verify-sources-url-allowlist/mutations.log)를 남긴다.

실행 결과와 명령은 [증거 안내](../../../tools/evidence/audit6-verify-sources-url-allowlist/README.md)에 기록한다.
초기 수집 시험은 루프백 호스트가 등록되지 않아 15개 하위 사례/시험에서 실패했다.
[초기 로그](../../../tools/evidence/audit6-verify-sources-url-allowlist/initial-tests.log)를 보존하며,
시험용 임시 레지스트리를 명시한 뒤 재검증했다.

이는 수집 도구 finding의 로컬 완료 증거다. 실제 공시 수집·R2 접근·관측 대조·변경 재처리·
상품/계약 트윈·소비자 화면·P02/P03 전체·첫 출시 완료는 이 노드에서 판정하지 않는다.
