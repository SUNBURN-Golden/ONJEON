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
1차의 [후속 수정·시험 초안](../../../packages/rules-engine/evidence/audit5-duplicate-json-keys/twin-runtime-proposed.patch)은
적용·실행된 완료 증거가 아니다. 2차에서는 아래와 같이 수정안을 별도 복사본에 적용해
실행했지만, 실제 런타임 소스의 허용 경로 확대 승인은 아직 받지 못했다.

## 수정 2차: 런타임 수정안 검증과 남은 차단

리뷰의 차단 사항을 재현했다. 실제 `load_rule_artifact`는 여전히 일반 serde를 사용하며,
엔진 단독 시험 통과로 이 경로의 해결을 주장할 수 없다. 요청의 허용 경로 목록에는
`packages/twin-runtime/**`가 없으므로, 두 런타임 파일의 수정 허용 여부를 질문했다.
승인 전에는 실제 소스와 시험 파일을 변경하지 않았다.

[runtime.patch](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/runtime.patch)는
`src/input_stage.rs`에서 원시 바이트를 `parse_rule_json`으로 검사한 뒤 선언을 분리하고,
`tests/input_stage.rs`에 회귀 시험 3개를 추가하는 검토 가능한 수정안이다.
최상위 `amount`, 중첩 `krw`, 두 키의 이스케이프 표기, 선언 키 자체·이스케이프 선언 키,
선언 배열의 `name`, 선언 내부 `duration.value` 중복의 8개 원시 JSON을 검사한다.
같은 8개를 연결된 `evaluate_request`에 전달해 중복 오류·엔진 호출 0회·결과 부재를
확인한다. 정상 아티팩트의 source·해시·평가와 선언 생략/null/빈 배열도 대조한다.

[check_runtime_patch.py](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/check_runtime_patch.py)는
허용 경로 `tools/evidence/` 아래 임시 런타임 복사본에서 실제 엔진·온톨로지 의존성을
사용해 수정 전후를 실행하고 패치를 생성한다. 임시 크레이트에만 오프라인 lockfile을
생성하며 저장소 lockfile은 바꾸지 않는다. 실제 런타임 파일에는 쓰지 않는다.

| 직접 재실행한 명령 | 결과·증거 |
|---|---|
| `python3 -I tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/check_runtime_patch.py` | 수정 전: 중복 거부 시험 2개 예상 실패·대조 2개 통과. 수정 후: 4개 통과. [요약](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/runtime-control.log), [수정 전](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/runtime-unfixed.log), [수정 후](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/runtime-fixed.log) |
| 같은 스크립트의 임시 런타임 전체 `cargo test --locked --offline` | 53개 통과·기존 ignored 1개: [runtime-full.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/runtime-full.log). 실제 런타임 소스에 적용한 결과가 아니다 |
| `CARGO_TARGET_DIR="$PWD/target" ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | 실제 작업 트리의 기존 Rust 시험 503개 통과·기존 ignored 1개: [workspace-before.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/workspace-before.log). 수정안의 새 런타임 시험은 이 명령에 포함되지 않는다 |

`git apply --check tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round2/runtime.patch`도
통과했다. 이 증거는 적용 준비와 재현 검증이며 차단 해소가 아니다. 두 런타임 파일을
허용받아 패치를 실제 적용한 뒤 작업 공간 시험을 다시 실행해야 한다.

## 수정 3차: 공유 Cargo 빌드 디렉터리로 인한 검사 실패

보고된 `duplicate_json_keys.rs:2`의 `E0432`를 재현했다. 이 작업 트리의
`src/lib.rs`는 이미 `parse_rule_json`을 공개 재수출한다. 상속된
`CARGO_TARGET_DIR=/workspace/onjeon-run/shared-target`으로 Clippy를 실행하면
API를 찾지 못하지만, 이 작업 트리의 `target/`으로 실행하면 같은 소스가 통과한다.
공유 디렉터리를 정리하거나 다른 작업 트리의 소스는 변경하지 않았다.

[with_worktree_target.py](../../../tools/ci/with_worktree_target.py)는 명령과 자식 프로세스의
`CARGO_TARGET_DIR`을 이 작업 트리의 `target/`으로 고정하고 저장소 루트에서 실행한다.
인자와 종료 코드를 보존하며, Python 시험이 내부에서 실행하는 Cargo에도 적용된다.
루트 README의 로컬 시험 절차에도 같은 환경 변수 설정을 추가했다.
[새 시험 3개](../../../tools/tests/test_worktree_target.py)는 공유 경로를 상속한 외부 작업
디렉터리에서 실행해 자식까지의 환경 격리·공유 파일 보존·인자와 실패 코드 전달·명령
누락 실패를 확인한다. 이 도우미를 거치지 않는 명령에는 환경 설정이 적용되지 않는다.

추가 실행에서 기존 `negative_control.py`가 이전 실행의 마지막 키 우선 변이 빌드를
정상 파서 대조에 재사용하는 실패도 발견했다. 복사본의 과거 소스 수정 시각과 재사용
빌드 디렉터리의 조합이 원인이므로, 임시 크레이트별 독립 `target/`을 사용하도록 고쳤다.
두 번 연속 실행해 각각 정상 6개 통과·변이 4개 예상 실패·대조 2개 통과를 확인했다.

아래 명령은 `python3 -I tools/ci/with_worktree_target.py`로 감싸 직접 실행했다.
3차 실행은 엔진 로드 동작이나 공개 API를 바꾸지 않으며, 2차의 런타임 허용 경로 제한도
해소하지 않는다.

| 명령 | 결과·증거 |
|---|---|
| `cargo fmt --all -- --check` | 통과: [fmt.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/fmt.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 보고된 빌드 실패 없이 통과: [clippy.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/clippy.log) |
| 같은 Clippy 명령에 `--target-dir target/audit5-round3-clean` 추가 | 별도 새 빌드에서도 모든 대상 통과: [clippy-clean.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/clippy-clean.log) |
| `python3 -m unittest discover -s tools/tests -v` | 새 격리 시험 3개 포함 1,406개 실행·실패 0·기존 skip 6개: [python-tests.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/python-tests.log) |
| `cargo test -p onjeon-rules-engine --locked --offline --test duplicate_json_keys` | 6개 통과: [duplicate-keys.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/duplicate-keys.log) |
| `cargo test --all --locked --offline` | Rust 503개 통과·기존 ignored 1개: [workspace.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/workspace.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts --locked --offline rule_02 -- --nocapture` | rule-0.2 왕복 시험 통과: [rule-02.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/rule-02.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과: [ontology-runner.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/ontology-runner.log) |
| `python3 -I packages/rules-engine/evidence/audit5-duplicate-json-keys/negative_control.py` (연속 2회) | 모두 의도한 결과: [1회](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/negative-control.log), [2회](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/negative-control-repeat.log) |
| `python3 -I tools/blueprint_counts.py` / `python3 -I tools/blueprint_status.py` | 수치·결정 색인 일치: [counts.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/counts.log), [status.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/status.log) |
| `python3 -I tools/ci/check_product_purpose.py` / `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 통과: [product-purpose.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/product-purpose.log), [spec-check.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/spec-check.log) |

최종 경로·보호 파일·문서 링크·공백 검사는
[scope.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round3/scope.log)를 따른다.

엔진 문자열 진입점의 중복 키 거부를 검증한 기반 증거다. P08·P14 전체, 실제 상품
릴리스 시나리오·소비자 화면·첫 출시 완료를 주장하지 않는다. 보호 문서·허용 경로 밖
파일의 최종 변경과 commit·push·GitHub 호출은 없다.


## 수정 4차: 기본 CI 명령에도 작업 트리 격리 적용

3차의 도우미는 명시적으로 감싼 명령만 보호했다. 따라서 상속된 공유 target을
그대로 쓰는 로컬 검사에서는 같은 `E0432`가 다시 발생할 수 있었다. 공개 재수출은
이미 존재하며, 엔진 소스의 API 누락으로 진단하거나 중복 키 시험을 제거하지 않았다.

이번에는 [ci.yml](../../../.github/workflows/ci.yml)의 워크플로 환경에
`CARGO_TARGET_DIR: ${{ github.workspace }}/target`을 추가했다. 기본 `cargo clippy`,
`cargo test`와 Python이 실행하는 Cargo에 함께 적용된다. 온톨로지 실행기의 명시적
`--target-dir`은 기존처럼 해당 실행기의 별도 빌드 경로를 선택한다. 로컬 외부 검사도
루트 README의 `export CARGO_TARGET_DIR="$PWD/target"` 또는 격리 도우미를 적용해야 한다.
저장소 파일만으로 외부 검사 프로세스의 상속 환경을 바꾸지는 못한다.

[격리 시험](../../../tools/tests/test_worktree_target.py)에 실제 엔진 복사본을 쓰는 회귀
시험을 추가했다. 첫 복사본에서 루트 `parse_rule_json` 재수출만 제거한 라이브러리를
빌드하고, 같은 target을 쓰는 두 번째 복사본의 오래된 소스 시각으로 `E0432`를 재현한다.
이후 같은 공개 API·중복 키 시험을 격리 도우미와 CI 환경 설정으로 각각 컴파일한다.
임시 복사본과 공유 캐시 대조는 모두 이 작업 트리의 `target/` 안에서 생성·삭제한다.
외부 공유 캐시를 청소하거나 다른 작업 트리를 변경하지 않는다. 별도 시험은 CI의
워크플로 환경에 격리 설정이 실제로 존재하는지도 확인한다.

[공개 파서 문서 시험](../../../packages/rules-engine/src/rule.rs)의 예제는 크레이트
루트에서 `parse_rule_json`을 가져와 감리의 `amount`·`krw` 중복 두 건을 거부하고,
정상 단일 키 값은 유지하는지 실행한다. BLUEPRINT의 현재 문서 시험 등록 수를
3개에서 4개로 갱신했다. 파서·평가 의미와 기존 원시 JSON 회귀 시험 6개는 유지한다.


다음은 Rust 1.98.1에서 `CARGO_TARGET_DIR="$PWD/target"`과
`ONJ_REQUIRE_RULE_02=1`을 설정하고 직접 재실행한 로컬 결과다. 원격 CI 실행 결과는 아니다.

| 명령 | 결과·증거 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_worktree_target.py -v` | 실제 stale API 대조 포함 5개 통과: [worktree-target.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/worktree-target.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,408개 실행·실패 0·기존 skip 6개: [python-tests.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/python-tests.log) |
| `cargo clippy --all-targets --locked --offline -- -D warnings` | 모든 대상 통과, `E0432` 없음: [clippy.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/clippy.log) |
| `cargo test --all --locked --offline` | Rust 504개 통과·기존 ignored 1개. 중복 키 회귀 6개와 공개 API 문서 시험 포함: [workspace.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/workspace.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과: [ontology-runner.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/ontology-runner.log) |
| `python3 -I packages/rules-engine/evidence/audit5-duplicate-json-keys/negative_control.py` | 정상 6개 통과·last-wins 변이 4개 예상 실패·대조 2개 통과: [negative-control.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/negative-control.log) |
| `cargo fmt --all -- --check` | 통과: [fmt.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/fmt.log) |
| `python3 -I tools/blueprint_counts.py` / `python3 -I tools/blueprint_status.py` | 수치·결정 색인 일치: [counts.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/counts.log), [status.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/status.log) |
| `python3 -I tools/ci/check_product_purpose.py` / `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 통과: [product-purpose.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/product-purpose.log), [spec-check.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/spec-check.log) |

허용 경로·보호 파일·문서 링크·공백 검사:
[scope.log](../../../tools/evidence/audit5-engine-reject-duplicate-json-keys/fix-round4/scope.log).
이번 수정은 보고된 빌드 실패를 다룬다. 위 2차의 실제 런타임 소스 허용 경로 제한은
계속 적용되며, 런타임 패치를 실제 적용했다고 주장하지 않는다.
