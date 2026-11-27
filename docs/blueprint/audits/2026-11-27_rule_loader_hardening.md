# Audit 8 규칙 로더와 날짜 검증

노드 `audit8-rule-loader-hardening`의 로컬 엔진 검증 기록이다. 실제 릴리스 상품의 경계일 시나리오는 P08, 화면 숫자에서 원문 좌표까지의 추적은 P14의 완료 조건으로 남는다. [제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)

## 구현과 회귀 시험

- `Rule::from_json`은 식 파싱·정규 JSON 해시 계산·원본 복사 전에 규칙 JSON 전체를 순회한다. `MAX_DEPTH`는 64, `MAX_NODES`는 8,192다. 루트를 깊이 1과 값 1개로 세며 객체 키는 세지 않는다. 객체·배열·스칼라 값과 메타데이터를 포함하고, 한도 초과 시 `$` 경로에 해당 한도를 반환한다. `Rule::from_json_str`은 엄격한 JSON 역직렬화 뒤 같은 검사에 진입한다. [로더](../../../packages/rules-engine/src/rule.rs)
- 두 DSL 버전·모든 공개 상태·두 로드 진입점에서 깊이 64와 값 8,192개를 허용하고 깊이 65와 값 8,193개를 거부한다. `evidence_refs` 배열과 `inputs` 객체도 값 개수에 포함된다. 각각 로드 가능한 `eligibility`와 `amount`를 한 문서에 넣어 합산 한도도 확인했다. 구현 전에는 새 회귀 3개가 초과 규칙을 허용해서 실패했고 구현 후에는 모두 통과했다. [로더 회귀](../../../packages/rules-engine/tests/loader_tightening.rs)
- 기존 검사는 두 DSL 버전에서 빈 문자열·유니코드 공백만 있는 `rule_id`를 `rule_id` 경로에서 거부한다. `2026-+1-+5`와 월·일 각각에 부호가 붙은 날짜는 날짜 리터럴과 평가 입력에서 거부한다. 로더의 JSON 이스케이프 입력도 재검증했다. [규칙 ID 회귀](../../../packages/rules-engine/tests/identity_evidence.rs) · [날짜 형식 회귀](../../../packages/rules-engine/tests/date_format.rs)
- 월별 일수와 윤년으로 1900-01-01부터 2199-12-31까지 109,573일을 열거했다. 각 날짜의 파싱 결과가 연속적인 epoch 일수와 일치하고, 그 일수를 서식화하면 원래 문자열이 나오는지 확인한다. 1900년과 2100년은 평년, 2000년은 윤년으로 열거한다. [날짜 단위 시험](../../../packages/rules-engine/src/date.rs)

## 로컬 실행 결과

| 명령 | 결과 |
|---|---|
| `cargo test --locked --offline --test loader_tightening rule_json_` (수정 전 로더의 작업 트리 내 복사본) | 초과 규칙을 허용한 회귀 3개 검출, 종료 코드 101 |
| `cargo test -p onjeon-rules-engine --locked --offline --test loader_tightening --test identity_evidence --test date_format` | 20개 통과 |
| `cargo test -p onjeon-rules-engine --locked --offline --lib date::tests` | 6개 통과 |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 561개 통과, 기존 무시 1개 |
| `cargo test --locked --offline` (키 삽입 순서 보존·시나리오 API·온톨로지 실행기 별도 매니페스트) | 각각 2개·4개·4개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 표준 임시 디렉터리에서 1,812개 실행, 1,805개 통과·기존 건너뜀 6개·데몬 정적 검사 시간 초과 1개. 해당 모듈 재실행 19개 모두 통과 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `python3 -I -m unittest discover -s packages/schemas/codegen/tests` | 142개 실행, 실패 0개, 선택적 전체 클라이언트 시험 2개 건너뜀 |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings` | 통과 |
| `tools/blueprint_counts.py`, `tools/blueprint_status.py`, `tools/ci/check_product_purpose.py`, `spec_check.py` | 통과. 엔진 단위·통합 시험 등록 274개, 문서 시험 등록 3개 |
| `ontology_check.py`, `tools/vocab_check.py`, `tools/validation_check.py`와 `--selftest` | 통과. 검증 자료 변이 40개 검출 |

첫 `tools/tests` 실행은 작업 트리 안으로 지정한 `TMPDIR` 때문에 임시 파일의 저장소 밖 격리를 검사하는 온톨로지 시험 3개가 실패했다. 표준 임시 디렉터리로 되돌린 뒤 해당 모듈 6개와 전체 재실행의 온톨로지 시험이 통과했다. 전체 재실행에서 시간 초과가 난 데몬 정적 검사는 `python3 -m unittest discover -s tools/tests -p test_daemon_static_checks.py -v`로 재검증했다.
