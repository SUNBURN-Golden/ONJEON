# Audit 8 출처 변경 감지 전송 경계

`audit8-detect-fetch-hardening` · 2026-11-28 · BLUEPRINT §4 L1 · 09 P02·P03

기준 브랜치에는 등록 호스트와 HTTPS 제한, 같은 출처로 제한한 리다이렉트, 조사에 근거한 `pub.insure.or.kr` 보류가 있었다. 변경 감지 도구의 별도 urllib 경로는 브라우저형 User-Agent를 보내고 등록된 출처의 현재 robots 정책을 조회하지 않았다.

`verify_sources.py detect`는 공용 `UrllibTransport`와 `RobotsCache`를 사용한다. 등록된 HTTPS 출처의 `/robots.txt`를 먼저 확인하고, User-Agent에는 `ONJEON-SourceArchiver`와 설정된 공개 연락처를 넣는다. 출처 문서와 robots 응답의 3xx는 본문을 읽거나 대상을 요청하기 전에 거부한다. `pub.insure.or.kr`의 기존 전면 보류는 robots 요청 전에도 적용한다. 수동 `sources` 워크플로에서 공개 연락처는 `ONJEON_CRAWLER_CONTACT` 저장소 변수로 전달하며 네트워크 허용 플래그는 detect 단계에서 설정한다.

변경 판정은 `status`에, 프래그먼트를 제외한 문서 응답 URL과 숫자 HTTP 상태는 `final_url`과 `http_status`에 기록한다. 문서 응답 헤더가 도착하면 바로 메타데이터를 기록해 본문 읽기에서 120초 제한을 넘겨도 보존한다. 문서 응답 전에 실패하면 두 값은 `null`이다. 성공한 새 보관 관측에는 `requested_url`, `final_url`, `http_status`를 함께 기록한다. 본문 상한은 공용 전송 계층의 64 MiB를 적용한다.

robots 조회에서 호스트를 보류하면 작업 프로세스가 보류 사유와 만료 시각을 부모에 전달한다. 같은 실행에서 해당 호스트의 이후 표본은 UTC 자정까지 요청 없이 같은 사유를 기록한다. 대소문자와 관계없이 제품 토큰과 일치하는 모든 그룹의 경로 규칙을 합치고, 일치 그룹이 없으면 `*` 그룹의 규칙을 합친다. 해당 그룹들의 `Crawl-delay` 중 가장 긴 값을 적용한다. [RFC 9309 §2.2.1](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.2.1).

경로와 쿼리를 비교할 때 비예약 ASCII의 퍼센트 인코딩은 해제하고, `%2F` 같은 예약 문자 이스케이프는 보존한다. `Crawl-delay` 등 확장 레코드 사이에 놓인 `User-agent` 행들도 규칙이 시작되기 전까지 같은 그룹에 속한다. [RFC 9309 §2.2.2](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.2.2) · [RFC 9309 §2.2.4](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.2.4).

공용 전송 계층은 `Content-Length`가 반복되면 같은 숫자 값만 허용하고, 선언 길이와 읽은 본문의 길이가 다르면 실패 처리한다. 불완전하게 전송된 robots 응답은 `robots_unreachable`로 호스트를 보류하며, 본문 길이가 일치하지 않는 문서는 `length_mismatch`로 거부한다. robots의 206 또는 `Content-Range`가 있는 다른 2xx도 본문을 읽기 전에 `robots_unreachable`로 호스트를 보류한다. [RFC 9112 §6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3) · [RFC 9110 §15.3.7](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.7).

문서 응답이 429이거나 `Retry-After`가 있는 503이면 해당 호스트의 이후 robots·문서 요청을 같은 실행에서 보류한다. `Retry-After`의 초 또는 HTTP 날짜로 만료 시각을 정하며, 사용할 수 있는 미래 시각이 없으면 다음 UTC 자정을 사용한다. 첫 보고 행은 받은 `final_url`과 `http_status`를 기록하고, 보류로 요청을 건너뛴 행은 두 필드를 `null`로 기록한다. 작업 프로세스가 헤더를 기록한 뒤 시간 초과로 종료돼도 부모는 그 호스트의 보류를 적용한다. [RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).

## 검증

- 기준 커밋 `3cb1b528`의 다운로드 경로를 같은 루프백 서버에서 실행했다. `Mozilla/` 식별자로 robots 금지 경로를 직접 요청했고 같은 출처의 302 대상까지 요청했다.
- 루프백 HTTPS에서 robots 조회 순서, 봇 User-Agent, 환경 프록시 무시를 확인했다. 경로 금지, robots 리다이렉트·401·403·429·503·연결 실패는 문서 요청 전에 중단했고, 404는 공용 정책에 따라 문서 요청을 허용했다.
- 같은 출처 이동을 포함한 3xx, 비HTTPS·미등록 최초 URL, HTTP 오류, MIME 불일치, 차단 페이지, 초과·불완전 응답을 거부했다. 임시 보관소에서 실패 전후의 바이트를 대조했고, 성공 관측과 실패 보고서에서 URL·상태를 검사했다.
- 출처별 제한이 헤더 대기·본문 스트리밍·재시도 대기에 함께 적용된다. 본문 스트리밍 시간 초과의 보고서에도 이미 받은 상태 200과 응답 URL이 남았다.
- 워크플로 시험은 공개 설정의 단계 범위와 요약의 HTTP 상태·최종 URL 열을 검증한다. [출처 시험](../../../tools/tests/test_verify_sources_fetch.py) · [워크플로 시험](../../../tools/tests/test_workflow_sources.py).
- 검토 기준 `0ab5c960`에서 루프백 회귀 시험 4건이 실패했다. 수정 후에는 robots 429 뒤 같은 호스트의 추가 요청 0건, 불완전한 robots 응답 또는 뒤쪽 일치 그룹의 금지 뒤 문서 요청 0건, 반복 길이 값을 가진 불완전한 문서의 캐시·보관 쓰기 0건을 확인했다.

공개 연락처를 비우고 저장소 루트에서 아래 명령을 실행했다. 표본 14건 중 연락처 설정 오류 12건과 조사에 근거한 robots 보류 2건이 보고됐고, 다운로드 경로를 만들지 않고 종료 코드 1을 반환했다.

```sh
mkdir -p target/audit8-detect-fetch-hardening/fix-round1
ONJEON_CRAWLER_CONTACT= ONJEON_CRAWLER_ALLOW_NETWORK=1 \
  python3 -I -B tools/verify_sources.py detect \
    --out target/audit8-detect-fetch-hardening/fix-round1/missing-contact-downloads \
    --report target/audit8-detect-fetch-hardening/fix-round1/missing-contact.json
```

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 68개 통과, 보관본이 필요한 3개 건너뜀 |
| `python3 -m unittest discover -s tools/tests -p test_crawler_config_ua_robots.py -v` | 88개 통과 |
| `python3 -m unittest discover -s tools/tests -p test_workflow_sources.py -v` | 7개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,821개 통과, 보관본이 필요한 5개와 구버전 botocore 전용 1개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 566개 통과, 기존 1개 무시. 삽입 순서·시나리오 API·온톨로지 실행기의 추가 시험은 2·4·4개 통과 |

워크플로 고정·권한 검사, 공시 원장과 검증 자료 일관성 검사, 변조 자체 시험 40건, 제품 목적 대응표와 설계 묶음 검사도 통과했다.

## 2차 검토 수정 검증

- 루프백 HTTPS에서 예약 문자 이스케이프를 포함한 경로와 `Crawl-delay`가 사이에 있는 `User-agent` 그룹에 대해 금지 규칙이 적용됐다. 각 경우에 `/robots.txt` 요청 1건, 문서 요청·캐시·보관 쓰기 0건을 확인했다.
- `Content-Length`가 부분 본문의 실제 길이와 일치하는 robots 206도 문서 요청 전에 보류했다. 캐시 단위 시험은 `Content-Range`가 없는 206과 `Content-Range`가 있는 200도 본문을 읽지 않고 포트와 무관하게 호스트를 보류하는지 확인했다.
- 문서 429와 `Retry-After: 600` 뒤 같은 호스트의 두 표본을 검사했다. 첫 robots·문서 요청만 발생했고 이후 요청은 0건이었다. 첫 행의 응답 URL과 429, 뒤 두 행의 `null` 메타데이터와 실패 사유를 대조했다. 단위 시험은 초·날짜 형식, UTC 자정을 넘기는 보류, 헤더가 없거나 사용할 수 없는 경우, 응답 헤더 직후 작업 프로세스 시간 초과를 확인했다.
- 호스트 등록 파일 설명에 HTTPS와 문서·robots 리다이렉트 거부를 명시하고 기존 68개 호스트 항목을 대조했다.

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 72개 통과, 보관본이 필요한 3개 건너뜀 |
| `python3 -m unittest discover -s tools/tests -p 'test_crawler*.py' -v` | 309개 통과 |
| `python3 -m unittest discover -s tools/tests -p test_workflow_sources.py -v` | 7개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,829개 통과, 보관본이 필요한 5개와 구버전 botocore 전용 1개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 566개 통과, 기존 1개 무시. 삽입 순서·시나리오 API·온톨로지 실행기의 추가 시험은 2·4·4개 통과 |

공시 원장, 워크플로 권한·고정 검사, 검증 자료 검사와 변조 자체 시험 40건, 제품 목적 대응표·설계 묶음·온톨로지 검사도 통과했다.

로컬 시험은 출처 변경 감지의 전송 경계와 보고서 기록을 검증했다. 실제 공시 확보율, R2 관측 대조와 변경 후 재처리는 각 행에서 증거를 요구한다. [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
