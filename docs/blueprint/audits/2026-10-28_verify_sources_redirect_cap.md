# Audit 3 — detect 리다이렉트와 응답 크기 제한

대상: `audit3-verify-sources-redirect-cap`, `tools/verify_sources.py`의 `fetch`·`detect`.

설계 연결: BLUEPRINT A1·A2, Q7, L1, I6, M1 및 [제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P02·P03. 이 기록은 수집 경계의 로컬 회귀 증거다. 실제 공시 확보율·R2 접근/관측 대조·변경 재처리·소비자 화면·출시 완료를 뜻하지 않는다.

## 기준 코드와 수정

작업 시작 HEAD에는 Audit 1·2에서 추가한 같은 출처 리다이렉트 검사와 최종 응답 256 MiB 상한이 이미 있었다. 다른 호스트(서브도메인 포함)·유효 포트·프로토콜로 이동하면 다음 요청 전에 거부하며 HTTPS→HTTP도 거부한다. 같은 출처의 상대 경로·기본 포트 명시는 허용한다. 선언 길이 초과는 읽기 전에 거부하고 실제 스트림은 상한 + 1바이트에서 중단한다. 이 정책을 완화하지 않았다.

남은 무제한 읽기는 Python `HTTPRedirectHandler.http_error_302` 내부의 `fp.read()`였다. 이 호출은 다음 URL을 열기 전에 중간 리다이렉트 본문 전체를 읽으므로 최종 응답의 `read_capped`에 도달하기 전에 발생한다. 새 회귀 시험을 기준 HEAD의 처리기에 적용하면 허용 리다이렉트 20개 하위 사례가 실패한다([baseline-regression.log](../../../tools/evidence/audit3-verify-sources-redirect-cap/baseline-regression.log)).

`PolicyRedirectHandler`는 중간 응답 연결을 읽지 않고 닫고, 빈 메모리 스트림을 표준 처리기에 전달한다. 301·302·303·307·308 모두 같은 처리를 쓴다. 표준 URL 정규화·상대 경로 해석·루프 제한과 기존 출처 검사는 계속 적용한다. 최종 문서만 크기·상태·MIME·시그니처 검사를 통과한 뒤 다운로드·해시·보관 대상이 된다.

## 회귀 범위

[`test_verify_sources_fetch.py`](../../../tools/tests/test_verify_sources_fetch.py)는 모의 응답과 실제 루프백 HTTP 서버·임시 로컬 보관소를 사용한다. 보험사·R2·외부 네트워크 요청은 하지 않는다.

| 경계 | 검사한 결과 |
|---|---|
| 301·302·303·307·308 × 길이 누락/잘못된 값/작은 값/상한 초과 | 중간 응답의 `read` 호출 0회, 연결 닫힘, 허용된 다음 요청과 루프 이력 유지 |
| 다른 호스트·HTTPS→HTTP·비HTTP 리다이렉트 거부 | 응답 닫힘, 본문 읽기·다음 요청 없음 |
| 기존 출처 검사 | 모든 리다이렉트 코드에서 서브도메인·유사 도메인·포트 변경·자격증명 포함 URL 등 거부, 같은 출처·기본 포트 허용 |
| 기본 256 MiB 상한 | 초과 `Content-Length` 응답 읽기 0회, 재시도 없음 |
| 여러 읽기 청크에 걸친 최종 응답 | 상한 + 1바이트까지만 읽고 거부; 길이 누락·거짓·잘못된 값도 기존 시험으로 확인 |
| 실제 HTTP 리다이렉트 | 중간 응답이 상한 초과 길이를 선언하고 본문을 보내지 않아도 최종 문서 수집 성공; 상한과 같은 최종 바이트만 캐시·원본·관측에 저장 |
| 여러 단계·프로토콜 상대 URL의 다른 호스트 이동 | 금지 대상 요청 없음, `fetch_failed`·종료 1, 기존 캐시·보관 파일 바이트 보존 |
| 초과 최종 응답·리다이렉트 루프·차단 페이지 | `fetch_failed`·종료 1, 원본·관측·새 해시 없음, 기존 파일 보존 |

## 검증 기록

실행 로그: [`tools/evidence/audit3-verify-sources-redirect-cap/`](../../../tools/evidence/audit3-verify-sources-redirect-cap/). 실행 명령·종료 코드·최종 코드 해시는 같은 디렉터리의 `run-summary.json`에 기록한다.

| 실행 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 종료 0, 59개 중 56 통과·3 건너뜀 | [focused-tests.log](../../../tools/evidence/audit3-verify-sources-redirect-cap/focused-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER=<로컬 빌드 경로> python3 -m unittest discover -s tools/tests -v` | 종료 0, 1,241개 중 1,235 통과·6 건너뜀 | [python-tools.log](../../../tools/evidence/audit3-verify-sources-redirect-cap/python-tools.log) |
| `cargo test --offline --locked --all --no-fail-fast` | 종료 0, Rust 466 통과(문서 시험 3 포함)·1 무시, 내부 Python 39 + 129 통과 | [rust-tests.log](../../../tools/evidence/audit3-verify-sources-redirect-cap/rust-tests.log) |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 종료 1, 20개 중 18 통과·2 실패(아래 기존 의존성 위반) | [python-ci.log](../../../tools/evidence/audit3-verify-sources-redirect-cap/python-ci.log) |
| `vocab_check.py`, `validation_check.py`, `validation_check.py --selftest`, `blueprint_status.py`, `spec_check.py`, `workflow_check.py`, `git diff --check` | 모두 종료 0 | [static-checks.log](../../../tools/evidence/audit3-verify-sources-redirect-cap/static-checks.log) |

별도 `tools/ci/tests` 시험의 실패 2개는 기존 의존성 위반 3개 때문이다: `packages/ontology/Cargo.toml`의 규칙 엔진 의존성, `packages/ontology/tests/common/mod.rs`·`packages/ontology/tests/fixture_origin/main.rs`의 엔진 import. HEAD의 검사기·규칙·소스 입력을 임시 디렉터리에 내보내 같은 3건과 종료 1을 재현했다([baseline-deps.log](../../../tools/evidence/audit3-verify-sources-redirect-cap/baseline-deps.log)). 이 노드의 수정으로 발생한 실패나 통과로 표시하지 않으며 해당 입력·검사 규칙은 수정하지 않았다.

비공개 원본을 사용하는 재현 시험은 로컬 보관소가 없어 건너뛴다. 실제 공시·R2를 요청하지 않았으므로 과거 관측 기록과 서비스 데이터 확보 상태는 갱신하지 않았다.
