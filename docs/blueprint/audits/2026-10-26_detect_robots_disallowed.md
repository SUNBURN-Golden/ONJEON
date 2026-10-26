# Audit 2 — 변경 감지의 robots 금지 출처 요청 차단

대상: `audit2-detect-robots-disallowed`, `tools/verify_sources.py`의 `detect`.
연결: Blueprint A1·L0~L1·M1, 09 제품 목적 대응표 P01·P02·P03.

## 발견과 수정

[출처 조사 §6](../../research/2026-10-10_source_survey/A_klia.md#6-접근-제한과-실패)는 `pub.insure.or.kr`의 일반 사용자 에이전트 규칙을 `Disallow: /`로 기록했다. 기존 변경 감지는 이 기록을 적용하지 않고 `samples.csv`의 해당 호스트 2건을 요청했다.

이제 조사 기록을 보수적 호스트 보류로 적용한다. `cmd_detect`는 요청 전에 차단하고, `fetch` 자체와 HTTP 리다이렉트 처리에도 같은 검사를 적용한다. 호스트는 URL 파서로 분리하고 대소문자·말미 점을 정규화한다. 경로·스킴·포트가 바뀌어도 차단하며 다른 호스트의 경로나 쿼리에 같은 문자열이 있다는 이유로 차단하지 않는다. 다른 출처의 정상 리다이렉트·바이트 상한 검사는 유지한다.

차단 결과는 정본 어휘 `source_change.fetch_failed`와 `detail: robots_disallow: …`로 표시한다. 상세 사유에는 조사 경로와 규칙을 남긴다. 샘플 ID·URL·기준 해시를 결과 분모에 유지하고 현재 해시·성공 관측·새 원본을 만들지 않는다. 다른 허용 표본은 계속 검사하되, 차단 표본이 있으면 종료 코드 1이다. 모든 출처를 확인한 것으로 보고하지 않는다.

이는 실시간 robots 검사나 모든 사이트의 접근 허가 검증이 아니다. 조사 기반 보류를 해제하려면 근거 재검토가 필요하며 실행 옵션으로 우회할 수 없다. 과거 원본·과거 관측 JSON·`reproduce` 판정·샘플 기준선은 변경하지 않았다. 금지 출처를 실제로 재요청하지 않았다.

## 회귀 증거

[`test_verify_sources.py`](../../../tools/tests/test_verify_sources.py)의 신규 시험 7개가 다음을 검사한다.

- 실제 샘플 목록의 KLIA 2건을 포함한 전체 분모를 유지한다. 다른 표본은 모의 응답으로 처리하고 KLIA의 요청·다운로드·원본 보존·성공 관측이 없음을 검증한다.
- 금지 표본만 고른 CLI 실행도 보고서를 쓰고 종료 코드 1을 반환한다. fetch 호출은 0회다.
- 대소문자·말미 점·HTTP/HTTPS·포트·새 경로로 보류를 피하지 못한다. 다른 호스트의 경로·쿼리·유사 호스트는 허용한다.
- 301·302·303·307·308 리다이렉트가 금지 호스트로 향하면 다음 요청 전에 거부한다. 허용 리다이렉트는 표준 처리기에 위임한다.
- fetch에 정책 리다이렉트 처리기가 실제로 연결되며 차단은 재시도하지 않고 사유를 보고한다.

[오프라인 CLI 로그](../../../tools/evidence/audit2-detect-robots-disallowed/blocked-samples.log)와 [보고서](../../../tools/evidence/audit2-detect-robots-disallowed/blocked-samples.json)는 실제 `samples.csv`에서 차단 2행만 선택하고 fetch를 mock으로 교체한 실행이다. 기대 종료 코드 1, fetch 0회, 출력 디렉터리 미생성을 확인했다. 보고서의 `source: network`는 detect의 입력 종류 표시이며 이 실행에서 네트워크를 사용했다는 뜻이 아니다. 새 robots 관측이나 사이트 변경 관측의 증거로 사용하지 않는다.

## 실행 결과

- `python3 -m unittest discover -s tools/tests -p test_verify_sources.py -v`: 35개 실행, 32개 통과·3개 건너뜀. 비공개 보관본과 추출기가 필요한 기존 재현 시험 3개다. [로그](../../../tools/evidence/audit2-detect-robots-disallowed/focused-tests.log).
- `python3 tools/vocab_check.py`, `python3 tools/validation_check.py`, `python3 tools/validation_check.py --selftest`, `python3 -I tools/ci/check_product_purpose.py`: 모두 종료 코드 0. [로그](../../../tools/evidence/audit2-detect-robots-disallowed/consistency-checks.log).

- `cargo test --all --locked`: 종료 코드 0, Rust 결과 합계 447개 통과·실패 0개·1개 무시. 내장 Python 검사 39개·129개도 통과. [로그](../../../tools/evidence/audit2-detect-robots-disallowed/rust-tests.log).

- `python3 -m unittest discover -s tools/tests -v`: 종료 코드 0, 930개 실행·924개 통과·6개 건너뜀. [로그](../../../tools/evidence/audit2-detect-robots-disallowed/python-tests.log).

이 수정은 수집 도구의 회귀 검증이다. 09의 실제 확보율·화면 렌더링·변경 재처리·출시 완료 증거를 대신하지 않으며 P01·P02·P03을 완료 처리하지 않는다.
