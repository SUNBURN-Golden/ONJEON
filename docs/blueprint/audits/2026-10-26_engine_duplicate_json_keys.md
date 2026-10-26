# Audit 2: 규칙 JSON의 중복 키 거부

기록일: 2026-10-26. 노드: `audit2-engine-duplicate-json-keys`.

`Rule::from_json_str`가 JSON을 바로 `serde_json::Value`로 읽으면서 중복 키의 마지막 값만
보존하던 문제를 수정했다. `"amount":{"krw":1},"amount":{"krw":100000000}`은 이전에
1억 원 규칙으로 로드·해시되었지만, 이제 검증·규칙 트리 생성·해시 전에 오류가 된다.

[로더](../../../packages/rules-engine/src/rule.rs)는 재귀적인 Serde deserializer로
객체마다 디코딩된 키의 중복을 검사한다. 최상위뿐 아니라 입력 선언, 식, 배열 안 객체,
연산 파라미터에도 적용한다. 같은 값의 반복과 `amount`/`\u0061mount`도 거부한다.
오류는 기존 `RuleError` 형식을 유지하며 경로 `$`, 중복 키 이름, JSON 행·열을 제공한다.
정상 JSON의 의미 검증·해시 알고리즘은 유지하고 새 의존성은 추가하지 않았다.

`Rule::from_json`은 이미 생성된 `serde_json::Value`를 받으므로 그 이전에 사라진 중복 키를
복구할 수 없다. 원문은 `from_json_str`로 읽도록 API 문서와 엔진 README에 명시했다.

## 검증

이 worktree에서 rustc/cargo 1.98.1로 로컬 실행했다. 로그는
[`packages/rules-engine/evidence/audit2-duplicate-json-keys/`](../../../packages/rules-engine/evidence/audit2-duplicate-json-keys/)에 있다.

| 명령 | 결과·증거 |
|---|---|
| 수정 전 `cargo test -p onjeon-rules-engine --test loader_and_arith loader_rejects_duplicate_json_keys_at_every_depth --offline` | 감사 예시가 `Ok(Rule)`로 수용되어 회귀 시험 실패. 마지막 금액 100000000과 내용 해시가 출력됨([before.log](../../../packages/rules-engine/evidence/audit2-duplicate-json-keys/before.log)) |
| 수정 후 `cargo test -p onjeon-rules-engine --test loader_and_arith --offline` | 13개 통과, 실패 0([loader.log](../../../packages/rules-engine/evidence/audit2-duplicate-json-keys/loader.log)) |
| `cargo test --all --offline` | Rust 단위·통합·문서 시험 414개 통과, 실패 0, 기존 ignored 1. 내부에서 실행한 Python 검사 39개·129개도 통과. 기존 골든 해시·trace·변이·건전성·실제 조항 시험 포함([workspace.log](../../../packages/rules-engine/evidence/audit2-duplicate-json-keys/workspace.log)) |
| `cargo fmt --all -- --check` | 통과, 진단 출력 없음([fmt.log](../../../packages/rules-engine/evidence/audit2-duplicate-json-keys/fmt.log)) |
| `cargo clippy --all-targets --offline -- -D warnings` | 통과([clippy.log](../../../packages/rules-engine/evidence/audit2-duplicate-json-keys/clippy.log)) |

[추가한 로더 시험 3개](../../../packages/rules-engine/tests/loader_and_arith.rs)는 다음을 확인한다.

- 두 DSL 버전에서 중복 키 9종(18조합)을 거부하고 키 이름·행·열을 보고한다.
- 별개 객체의 같은 키는 허용한다. 정상 원문의 JSON·내용 해시·평가 직렬화가 `from_json`과
  같고, 정수 양 끝값·한글 문자열·`null`·배열·불리언을 보존한다.
- 부동소수점·지수 표기·`u64::MAX` 금액의 의미 검증 거부와 잘못된 JSON·후행 데이터
  거부를 유지한다.

`python3 -I tools/blueprint_status.py`는 결정 원장 36개와 §11 색인의 일치를 확인했다.
`git diff --check`, 변경 문서의 로컬 링크 대상, 허용 경로와 보호 파일 불변 여부도 확인했다
([scope-check.log](../../../packages/rules-engine/evidence/audit2-duplicate-json-keys/scope-check.log)).
commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 증명 범위

BLUEPRINT의 A1·A2·A5, Q5·Q7, L6, I2·I3·I4·I5·I18, M0 엔진 기반 유지보수에 연결된다.
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08(가상 상황 계산)·P14(계산 근거 추적)를
지원하는 엔진 기반 수정 증거다. 시험은 `fixture_only` 규칙이며 실제 릴리스 상품 시나리오나
화면→원문 좌표 증거를 대체하지 않는다. P08·P14 또는 첫 출시 완료를 주장하지 않는다.
