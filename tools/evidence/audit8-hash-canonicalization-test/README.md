# Audit 8 규칙 내용 해시의 키 순서 독립성

기본 `serde_json::Map`은 객체 키를 정렬하므로, 기존 순서 변경 시험에서는 로더가 해시를 계산하기 전에 두 입력의 차이가 사라졌다. 새 시험은 최상위 키와 배열 속 객체 키를 각각 재정렬한다. 두 로드 결과의 JSON 값은 같고 직렬화 바이트는 다른지 확인한 뒤 `rule_content_hash`를 비교한다. [회귀 시험](../../../packages/rules-engine/order-tests/tests/content_hash.rs).

루트 `Cargo.lock`은 이 작업의 허용 경로 밖이다. 별도 복사본에서 엔진의 개발 의존성에 기능을 직접 추가하자 기존 잠금 파일을 사용한 `cargo metadata --locked`가 갱신 필요 오류를 반환했다. 시험 워크스페이스의 개발 의존성에서 `serde_json/preserve_order`를 켜고 `indexmap`과 그 의존성을 별도 잠금 파일에 기록했다. 시험은 엔진과 같은 `serde_json`을 사용한다. Cargo 기능 트리에서 시험 워크스페이스의 기능 활성화와 루트 엔진 일반 의존성의 비활성 상태를 확인했다. [시험 워크스페이스](../../../packages/rules-engine/order-tests/Cargo.toml) · [CI 실행 단계](../../../.github/workflows/ci.yml).

## 로컬 검증

| 실행 | 결과 |
|---|---|
| `cargo test --manifest-path packages/rules-engine/order-tests/Cargo.toml --locked --offline --target-dir target/order-tests` | 2개 통과 |
| 임시 복사본에서 `canonicalize`가 입력 JSON을 그대로 반환하도록 변경 | 두 시험 모두 해시 비교에서 실패 |
| 임시 복사본에서 `canonicalize`가 최상위 키만 정렬하도록 변경 | 최상위 시험 통과, 배열 속 객체 시험은 해시 비교에서 실패 |
| 임시 복사본에서 정규화 원복 후 `preserve_order` 제거 | 두 시험 모두 로드된 JSON 바이트가 달라야 한다는 검사에서 실패 |
| `cargo test -p onjeon-rules-engine --locked --offline` | 단위·통합·문서 시험 272개 통과 |
| `cargo test --all --locked --offline` | Rust 시험 556개 통과, 기존 무시 1개. 내장 Python 시험 39개 통과, 코드 생성 시험 142개 실행 중 선택 시험 2개 건너뜀 |
| 시나리오 API와 온톨로지 실행기 `cargo test --locked --offline` | 각각 4개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | CI의 새 시험 명령과 `--locked` 사용을 검사하도록 갱신한 뒤 1,809개 실행, 실패 0개, 6개 건너뜀 |
| 루트 및 시험 워크스페이스의 `cargo fmt --check`, `cargo clippy --locked --offline --all-targets -- -D warnings` | 통과 |
| `blueprint_counts.py`, `workflow_check.py`, `check_product_purpose.py`, `spec_check.py` | 통과 |
| 데몬 실행기 시험 81개 | 78개 통과. 로컬 Claude CLI 프록시의 R6·R7과 집계 검사에서 3개 실패. R6·R7을 따로 재실행한 결과 두 시나리오의 실패 검사 0개, 미확인 10개 |

검증 범위는 BLUEPRINT I2와 P08·P14의 합성 규칙 해시다. 제품 완료 판정은 각 행에 명시된 실제 릴리스 시나리오와 화면에서 원문 좌표까지의 추적 증거를 따른다. [설계도 I2](../../../docs/BLUEPRINT.md#8-설계-불변식) · [제품 목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md).
