# Audit 8 출처 변경 감지 전송 경계

`audit8-detect-fetch-hardening` · 2026-11-28 · BLUEPRINT §4 L1 · 09 P02·P03

기준 브랜치에는 등록 호스트와 HTTPS 제한, 같은 출처로 제한한 리다이렉트, 조사에 근거한 `pub.insure.or.kr` 보류가 있었다. 변경 감지 도구의 별도 urllib 경로는 브라우저형 User-Agent를 보내고 등록된 출처의 현재 robots 정책을 조회하지 않았다.

`verify_sources.py detect`는 공용 `UrllibTransport`와 `RobotsCache`를 사용한다. 등록된 HTTPS 출처의 `/robots.txt`를 먼저 확인하고, User-Agent에는 `ONJEON-SourceArchiver`와 설정된 공개 연락처를 넣는다. 출처 문서와 robots 응답의 3xx는 본문을 읽거나 대상을 요청하기 전에 거부한다. `pub.insure.or.kr`의 기존 전면 보류는 robots 요청 전에도 적용한다. 수동 `sources` 워크플로에서 공개 연락처는 `ONJEON_CRAWLER_CONTACT` 저장소 변수로 전달하며 네트워크 허용 플래그는 detect 단계에서 설정한다.

변경 판정은 `status`에, 프래그먼트를 제외한 문서 응답 URL과 숫자 HTTP 상태는 `final_url`과 `http_status`에 기록한다. 문서 응답 헤더가 도착하면 바로 메타데이터를 기록해 본문 읽기에서 120초 제한을 넘겨도 보존한다. 문서 응답 전에 실패하면 두 값은 `null`이다. 성공한 새 보관 관측에는 `requested_url`, `final_url`, `http_status`를 함께 기록한다. 본문 상한은 공용 전송 계층의 64 MiB를 적용한다.

## 검증

- 기준 커밋 `3cb1b528`의 다운로드 경로를 같은 루프백 서버에서 실행했다. `Mozilla/` 식별자로 robots 금지 경로를 직접 요청했고 같은 출처의 302 대상까지 요청했다.
- 루프백 HTTPS에서 robots 조회 순서, 봇 User-Agent, 환경 프록시 무시를 확인했다. 경로 금지, robots 리다이렉트·401·403·429·503·연결 실패는 문서 요청 전에 중단했고, 404는 공용 정책에 따라 문서 요청을 허용했다.
- 같은 출처 이동을 포함한 3xx, 비HTTPS·미등록 최초 URL, HTTP 오류, MIME 불일치, 차단 페이지, 초과·불완전 응답을 거부했다. 임시 보관소에서 실패 전후의 바이트를 대조했고, 성공 관측과 실패 보고서에서 URL·상태를 검사했다.
- 출처별 제한이 헤더 대기·본문 스트리밍·재시도 대기에 함께 적용된다. 본문 스트리밍 시간 초과의 보고서에도 이미 받은 상태 200과 응답 URL이 남았다.
- 워크플로 시험은 공개 설정의 단계 범위와 요약의 HTTP 상태·최종 URL 열을 검증한다. [출처 시험](../../../tools/tests/test_verify_sources_fetch.py) · [워크플로 시험](../../../tools/tests/test_workflow_sources.py).
- 공개 연락처를 비우고 `python3 -I tools/verify_sources.py detect`를 실행했다. 표본 14건 중 연락처 설정 오류 12건과 조사에 근거한 robots 보류 2건이 보고됐고, 다운로드 경로를 만들지 않고 종료 코드 1을 반환했다.

| 명령 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 64개 통과, 보관본이 필요한 3개 건너뜀 |
| `python3 -m unittest discover -s tools/tests -p test_crawler_config_ua_robots.py -v` | 83개 통과 |
| `python3 -m unittest discover -s tools/tests -p test_workflow_sources.py -v` | 7개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,812개 통과, 보관본이 필요한 5개와 구버전 botocore 전용 1개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 566개 통과, 기존 1개 무시. 삽입 순서·시나리오 API·온톨로지 실행기의 추가 시험은 2·4·4개 통과 |

워크플로 고정·권한 검사, 공시 원장과 검증 자료 일관성 검사, 변조 자체 시험 40건, 제품 목적 대응표와 설계 묶음 검사도 통과했다. 첫 전체 Python 실행은 실행 도중 교체한 작업 프로세스의 출력 형식을 기존 부모가 읽어 실패했다. 표에는 같은 소스의 부모·작업 프로세스로 다시 실행한 결과를 기록했다.

이 로컬 증거는 출처 변경 감지 감사 항목을 닫는다. 실제 공시 확보율, R2 관측 대조와 변경 후 재처리는 각 행에서 증거를 요구한다. [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
