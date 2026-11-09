# Audit 5: 규칙 JSON 중복 키 거부

검증일: 2026-11-09. 노드: `audit5-engine-reject-duplicate-json-keys`.
BLUEPRINT A5, Q5·Q7, L6, I2·I3·I5·I18, M0 엔진 유지보수와
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견과 수정

기존 `Rule::from_json_str`은 일반 `serde_json::Value`로 역직렬화했다.
객체 중복 키가 마지막 값으로 덮어써져, `"amount":{"krw":1},"amount":{"krw":999}`와
`"amount":{"krw":1,"krw":999}` 모두 999원 규칙으로 로드됐다.
이미 만들어진 `Value`를 검사하는 것으로는 원래 중복을 찾을 수 없다.

[재귀 JSON 역직렬화기](../../../packages/rules-engine/src/strict_json.rs)는 각 객체의
키를 JSON 이스케이프 해독 후 비교하고, 이미 있는 키면 값을 덮어쓰기 전에 거부한다.
배열·중첩식·입력 선언·미선택 분기·연산 파라미터·평가에 쓰이지 않는 메타데이터에도
같은 검사를 적용한다. 동일 값의 중복도 거부한다. 객체가 다르면 같은 키를 쓸 수 있고,
유니코드 정규화는 하지 않는다. 숫자 표현·문자열·배열 순서를 비롯한 정상 값은 보존한다.
기존 JSON 문법·UTF-8·후행 입력·재귀 깊이 제한도 유지한다.

`Rule::from_json_str`이 이 역직렬화기를 사용한 뒤 기존 DSL 검증과 해시 계산을 수행한다.
중복 오류는 기존 JSON 문법 오류와 같은 `RuleError.path = "$"`이며,
메시지에 중복 키·행·열을 남긴다. 정상 규칙의 해시·trace·평가 결과는 바꾸지 않는다.
의존성·규칙 스키마·엔진 결과 버전·공유 fixture 변경은 없다.

원시 아티팩트 바이트를 처리할 호출자에게 `parse_rule_json(&[u8])`을 공개했다.
이 함수는 JSON 문법·중복 키만 검사하며 이후 `Rule::from_json`의 DSL 검증이 필요하다.
`Rule::from_json(&Value)` 자체는 중복 이력을 복원할 수 없으므로, 원시 JSON을 일반
serde로 먼저 파싱한 뒤 전달하는 호출자는 이 보호를 받지 않는다. 공개 API 문서와
엔진 README에 이 경계를 명시했다.

## 회귀 시험과 음성 대조

[duplicate_json_keys.rs](../../../packages/rules-engine/tests/duplicate_json_keys.rs)의
6개 시험은 원시 JSON 텍스트를 사용한다.

- rule-0.1·rule-0.2와 공개 상태 3종의 모든 최상위 키, 감리의 두 `amount`·`krw` 사례,
  같은 값과 반대 순서의 중복을 거부한다.
- 입력 이름·한글·제어 문자·빈 키와 `"krw"`/`"\u006brw"`처럼 해독 후 같은 키를 검사한다.
- 배열·미선택 `if` 가지·`then` 키·반올림 단위·날짜 파라미터·중첩 메타데이터를 검사한다.
- 별개 객체의 같은 키·구분되는 유니코드 형식·중복 JSON처럼 보이는 문자열을 허용하고,
  정상 소스·내용 해시·재로드·전체 평가 직렬화의 동일성을 확인한다.
- 정수 경계·유한 소수·null·bool·빈 배열/객체의 파싱 보존과 문법·깊이 제한을 확인한다.

[negative_control.py](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/negative_control.py)는
작업 트리 안의 임시 크레이트에서 같은 시험을 실행한다. 정상 파서로 6개가 통과하고,
파서만 일반 `serde_json::Value` 역직렬화로 바꾸면 중복 키 시험 4개가 실패하며 정상값·문법
대조 2개는 통과한다. 실제 소스는 수정하지 않는다.

## 직접 실행한 로컬 검증

Rust 1.98.1, 작업 트리 전용 `CARGO_TARGET_DIR="$PWD/target"`을 사용했다.
아래 증거는 로컬 실행이며 원격 CI 결과가 아니다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test duplicate_json_keys` | 6개 통과: [focused-engine.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/focused-engine.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 501개 통과, 기존 ignored 1개. 내부 Python 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/workspace.log) |
| `python3 -I packages/rules-engine/evidence/audit5-duplicate-json-keys/negative_control.py` | 정상 6개 통과, 마지막 키 우선 변이 4개 예상 실패: [요약](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/negative-control.log), [정상](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/control-fixed.log), [변이](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/control-last-wins.log) |
| `python3 -I tools/blueprint_counts.py --write` | 엔진 등록 수 236개·doctest 3개 갱신: [counts-write.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/counts-write.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,403개 실행, 실패 0, 기존 skip 6개: [python-tests.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/python-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 온톨로지 실행기 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/ontology-runner.log) |
| `cargo fmt --all -- --check` / `cargo clippy --all-targets --locked --offline -- -D warnings` | 통과: [fmt.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/clippy.log) |
| `python3 -I tools/blueprint_counts.py` / `python3 -I tools/blueprint_status.py` | 수치·결정 색인 일치: [counts.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/counts.log), [status.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/status.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 연결·필수 시험 정적 검사 통과: [product-purpose.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 45/45·존재 72/72 통과: [spec-check.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/spec-check.log) |

최종 허용 경로·보호 파일·문서 링크·공백 검사:
[scope.log](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/scope.log).

## 적용 범위와 후속 경로

`packages/twin-runtime/src/input_stage.rs`의 `load_rule_artifact`는 원시 규칙을 일반 serde로
먼저 파싱해 `Rule::from_json`으로 전달한다. 따라서 이 호출 경로에도 `parse_rule_json`을
적용해야 중복 덮어쓰기를 차단할 수 있다. `packages/twin-runtime/**`는 이 노드의 명시적
허용 경로에 없으므로 해당 파일과 시험은 변경하지 않았다. 범위 확대를 요청했으며,
검토 가능한 [후속 수정·시험 초안](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/twin-runtime-proposed.patch)을
보관한다. 초안은 적용·실행된 완료 증거가 아니다.

엔진 문자열 진입점의 중복 키 거부를 검증한 기반 증거다. P08·P14 전체, 실제 상품
릴리스 시나리오·소비자 화면·첫 출시 완료를 주장하지 않는다. 보호 문서·허용 경로 밖
파일의 최종 변경과 commit·push·GitHub 호출은 없다.
