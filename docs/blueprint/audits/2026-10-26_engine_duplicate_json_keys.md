# Audit 2: 규칙 JSON의 중복 키 거부

기록일: 2026-10-26. 노드: `audit2-engine-duplicate-json-keys`.

**Fix round 1 상태: 미해결.** 아래 최초 검증은 엔진 문자열 로더만 입증한다.
실제 실행용 `packages/twin-runtime/src/input_stage.rs`의 `load_rule_artifact`는
일반 `serde_json::from_slice::<Value>` 다음 `Rule::from_json`을 호출하므로 중복 키를
여전히 마지막 값으로 읽고 실행·해시한다. 최초 설명은 이 호출자를 빠뜨렸다.

`Rule::from_json_str`가 JSON을 바로 `serde_json::Value`로 읽으면서 중복 키의 마지막 값만
보존하던 문제를 수정했다. `"amount":{"krw":1},"amount":{"krw":100000000}`은 이전에
1억 원 규칙으로 로드·해시되었지만, 이 문자열 API에서는 이제 검증·규칙 트리 생성·해시 전에 오류가 된다.

[로더](../../../packages/rules-engine/src/rule.rs)는 재귀적인 Serde deserializer로
객체마다 디코딩된 키의 중복을 검사한다. 최상위뿐 아니라 입력 선언, 식, 배열 안 객체,
연산 파라미터에도 적용한다. 같은 값의 반복과 `amount`/`\u0061mount`도 거부한다.
오류는 기존 `RuleError` 형식을 유지하며 경로 `$`, 중복 키 이름, JSON 행·열을 제공한다.
정상 JSON의 의미 검증·해시 알고리즘은 유지하고 새 의존성은 추가하지 않았다.

`Rule::from_json`은 이미 생성된 `serde_json::Value`를 받으므로 그 이전에 사라진 중복 키를
복구할 수 없다. 원문은 `from_json_str`로 읽도록 API 문서와 엔진 README에 명시했다.

## Fix round 1: 실행 경로와 허용 범위

엔진에 공개 바이트 파서 `parse_rule_json(&[u8]) -> Result<Value, serde_json::Error>`를
추가했다. 문자열 로더도 같은 파서를 사용한다. 런타임은 이 API로 전체 아티팩트를 먼저
파싱하고, `inputs_from_outside_dsl`을 제거한 다음 기존 `Rule::from_json`을 호출하면 된다.
메타데이터 자체·배열 안 선언·중첩 `duration`의 중복도 제거 전에 검사한다.
스키마 시험에서 원문을 일반 `Value`로 먼저 읽던 두 호출자도 `Rule::from_json_str`로 바꿨다.

사용자 허용 경로에는 `packages/twin-runtime/**`가 없다. 따라서 런타임 소스·시험 파일은
변경하지 않았다. 적용할 정확한 변경과 실행 경로의 시험 3개를
[runtime-loader.patch](../../../tools/evidence/audit2-engine-duplicate-json-keys-round1/runtime-loader.patch)에
준비했다. 이는 **미적용 패치**이며 현재 실행 경로의 수정 완료 증거가 아니다.
현재 상태의 재현 시험·실행 방법·새 로그는
[round 1 증거](../../../tools/evidence/audit2-engine-duplicate-json-keys-round1/README.md)에 기록한다.
허용 범위를 넓혀 이 패치를 적용하고 런타임 회귀 시험·전체 시험을 다시 통과해야 발견 사항을 닫을 수 있다.

## 검증

최초 수정에서 이 worktree의 rustc/cargo 1.98.1로 로컬 실행했다. 당시 로그는
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
