# Audit 2 — 출처 변경 감지의 리다이렉트·응답 검증

대상: `audit2-fetch-redirect-blockpage`, `tools/verify_sources.py`의 `fetch`·`detect`.
연결: Blueprint A1·A2·A4·Q7·L0~L1·I6의 입력 근거·M1, 09 제품 목적 대응표 P02·P03.

## 수정 범위

기존 `PolicyRedirectHandler`는 조사에 기록된 robots 금지 호스트만 거부했다. 그 밖의 호스트·프로토콜 이동은 urllib 기본 동작으로 따라갔고, 보고서와 불변 보관 관측은 입력 URL을 출처로 기록했다. MIME과 문서 형식 검증도 없어 HTTP 200 차단 페이지가 `changed`로 분류되어 `--archive-new`로 원본 보관될 수 있었다. **256 MiB 크기 제한은 이미 구현되어 있었다.** 이 변경은 이를 유지·보강하고 회귀 시험으로 재검증한다.

- 리다이렉트는 같은 scheme·host·유효 port에서만 허용한다. 호스트 대소문자와 기본 포트 명시는 동일하게 취급한다. 301·302·303·307·308 모두 다음 요청 전에 검사하며 HTTPS→HTTP, 다른 호스트·하위 도메인·포트·스킴·자격 증명 URL은 거부한다. HTTP→HTTPS도 자동으로 따라가지 않는다. robots 보류는 그대로 우선 적용하며 리다이렉트 반복은 urllib의 기존 제한으로 종료한다.
- `fetch`는 `(body, content_type, final_url)`을 반환한다. 보고서·새 보관 관측의 `url`·`final_url`에는 실제 최종 응답 URL을, `requested_url`에는 입력 URL을 기록한다. 리다이렉트 후 HTTP 오류나 본문 거부도 최종 응답 URL이 있으면 보고한다. 아직 요청하지 않은 거부 대상은 최종 응답 URL로 기록하지 않는다.
- HTTP 200과 표본의 기대 형식·MIME·시그니처를 검사한 뒤에만 캐시·해시·원본·관측을 만든다. PDF 계열(`pdf`·`text_pdf`·`scanned_pdf`)은 `application/pdf`와 실제 공시 다운로드에서 쓰는 `application/octet-stream`·`binary/octet-stream`을 허용하되 `%PDF-`가 필수다. HTML은 `text/html`·`application/xhtml+xml`과 마크업 시작을 요구한다. MIME 누락·다른 형식·빈 본문·길이 불일치도 실패다.
- HTML 앞 64 KiB를 기존 UTF-8/EUC-KR/CP949 디코더로 읽고 알려진 접근 거부·WAF·CAPTCHA·로그인·점검 문구와 챌린지 마크업·비밀번호 입력을 검사한다. 일반 로그인 링크나 PDF 내부의 같은 단어만으로 차단하지 않는다.
- 선언된 길이가 상한을 넘으면 본문을 읽지 않는다. 길이가 없거나 잘못되거나 실제보다 작아도 스트리밍은 상한 + 1바이트에서 멈추며, 호출자가 상한을 없애거나 높일 수 없다. 네트워크 오류만 재시도하고 HTTP 오류·정책 거부·형식 거부·초과 응답은 재시도하지 않는다.

모든 거부는 기존 상태 `fetch_failed`와 구체적 `detail`, 종료 코드 1로 남는다. 기준 해시·표본 분모는 유지하며 `sha256_now`·새 원본·성공 관측은 만들지 않는다. 기존 캐시·보관 원본도 덮어쓰지 않는다.

## 회귀 증거

[`test_verify_sources_fetch.py`](../../../tools/tests/test_verify_sources_fetch.py)는 모의 HTTP 응답과 실제 루프백 HTTP 서버를 함께 사용한다. 실제 urllib 리다이렉트 사슬과 로컬 보관소의 객체·관측 JSON을 검사하므로 `put_raw` 호출 여부만 확인하는 시험이 아니다.

| 검사 | 확인한 결과 |
|---|---|
| 5종 리다이렉트 상태·다른 호스트/포트/스킴 | 허용 범위를 벗어나면 다음 요청 전에 거부·응답 닫기. 루프백에서 거부 대상 경로의 요청 0회 |
| 정상 2단계 리다이렉트 | 최종 쿼리 URL이 보고서·실제 관측 JSON에 일치하고 입력 URL도 별도 보존. 원본 바이트 동일 |
| 리다이렉트 후 403 | 최종 오류 URL 기록, 재시도·다운로드·원본·관측 없음 |
| 200 WAF·Cloudflare 챌린지·로그인·위장 PDF | `fetch_failed`, 캐시와 원본 보관소의 모든 기존 파일·바이트 동일 |
| 선언 초과·길이 없는 초과·허위/잘못된 길이·잘린 본문 | 상한·길이 검증으로 거부. 선언 초과는 읽기 0회, 스트리밍 초과는 상한 + 1바이트 소비 |
| 정상 HTML·정상/변경 PDF | `unchanged_bytes`·`changed`와 보관 동작 유지. generic PDF MIME 허용, HTML 본문 해시 보조 판정과 robots 보류의 기존 시험 유지 |

실행 로그는 [evidence/audit2_fetch_redirect_blockpage](../validation/evidence/audit2_fetch_redirect_blockpage/)에 있다. 실행 명령과 최종 결과는 아래에 기록한다.

| 실행 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 종료 0, 53개 중 50 통과·3 건너뜀(비공개 보관본 필요) | [focused-tests.log](../validation/evidence/audit2_fetch_redirect_blockpage/focused-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 종료 0, 948개 중 942 통과·6 건너뜀 | [python-tools.log](../validation/evidence/audit2_fetch_redirect_blockpage/python-tools.log) |
| `cargo test --offline --locked --all --no-fail-fast` | 종료 0, Rust 447 통과(문서 시험 3 포함)·1 무시. 내부 실행 Python 39 + 129 통과 | [rust-tests.log](../validation/evidence/audit2_fetch_redirect_blockpage/rust-tests.log) |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 종료 1, 20개 중 18 통과·2 실패. 기존 의존성 위반(아래) | [python-ci.log](../validation/evidence/audit2_fetch_redirect_blockpage/python-ci.log) |
| `vocab_check.py`, `validation_check.py`, `validation_check.py --selftest`, `blueprint_status.py`, `git diff --check` | 모두 종료 0. 내부 일관성·어휘·38종 변조·결정 색인 확인 | [static-checks.log](../validation/evidence/audit2_fetch_redirect_blockpage/static-checks.log) |

별도 CI 시험 2개의 실패는 `check_deps`가 탐지하는 기존 위반 3개다: `packages/ontology/Cargo.toml`의 `onjeon-rules-engine` 의존성과 `packages/ontology/tests/common/mod.rs`·`packages/ontology/tests/fixture_origin/main.rs`의 같은 엔진 import. 이 노드에서 해당 경로·검사기·의존성 규칙을 수정하지 않았다. 수정 전 HEAD `807b06e998a42d66172be8646c1ab27a6500a1ef`의 관련 입력을 임시 디렉터리로 내보내 같은 검사기를 실행했고 같은 3개 위반과 종료 1을 재현했다([baseline-deps.log](../validation/evidence/audit2_fetch_redirect_blockpage/baseline-deps.log)). 이를 이번 수정의 통과로 표시하지 않는다.

[run-summary.json](../validation/evidence/audit2_fetch_redirect_blockpage/run-summary.json)은 실행 명령·종료 코드·검사 수와 최종 구현/시험 파일의 SHA-256을 기록한다.

## 검증의 한계

이 검사는 문서 MIME·시그니처와 알려진 차단 페이지 신호의 수집 전 검증이다. 완전한 PDF/HTML 파싱, 모든 차단 페이지 탐지, 실시간 robots나 모든 출처의 접근 허가 검증을 뜻하지 않는다. 처음 64 KiB 밖의 신호나 새로운 차단 문구는 놓칠 수 있다. 다른 출처로 이동하는 정상 공시는 자동 보관하지 않고 출처 재검토 대상으로 실패 처리한다.

보험사·감독기관·R2를 새로 요청하지 않았고, 과거 보관본·관측·샘플 기준선은 수정하지 않았다. 루프백과 합성 바이트 시험은 이 감리 결함의 수정 증거이며 P02의 실제 확보율·판 연결, P03의 R2 목록 대조·변경 재처리·출시 완료 증거를 대체하지 않는다. 제품 목적 행을 완료 처리하지 않는다.
