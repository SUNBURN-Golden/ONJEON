# Audit 8 엔진 빌드 식별자

평가 결과의 `engine_version`은 `ENGINE_VERSION`의 `0.2.0+snapshot-json-1`이다. `rule-0.2` 연산자, 정적 타입 검사, 가지 오류 처리가 들어간 엔진은 이 값으로 식별된다. 릴리스 매니페스트 픽스처도 같은 식별자를 기록한다. [엔진 상수](../../../packages/rules-engine/src/lib.rs) · [Audit 7 변경 기록](../audit7-engine-version-bump/README.md).

I18 골든은 합성 사례와 실제 조항 기반 106개 사례의 전체 직렬화 결과에서 이 값을 리터럴로 검사한다. 반복 평가·규칙 재로딩·중첩 키 순서 변경 후에도 전체 바이트가 일치해야 한다. 스냅샷 골든은 `rule-0.2` 결과의 식별자와 독립적으로 계산한 스냅샷 해시를 검사한다. 공유 계약 시험은 직렬화된 엔진 결과와 릴리스 매니페스트 픽스처의 식별자를 대조한다. [I18 골든](../../../packages/rules-engine/tests/golden.rs) · [스냅샷 골든](../../../packages/rules-engine/tests/snapshot_hash.rs) · [공유 계약 시험](../../../packages/schemas/src/tests.rs).

로컬 복사본에서 평가 결과의 대입식을 `concat!(env!("CARGO_PKG_VERSION"), "+snapshot-json-1")`로 바꾸었다. 합성 사례 `t01_before_start`와 실제 조항 사례 `f01_under_cap`에서 각각 `0.1.0+snapshot-json-1`이 나와 두 I18 골든이 실패했다. 원래 대입식에서는 두 시험이 모두 통과했다.

Cargo 패키지 버전은 `0.1.0`이다. 복사본에서 패키지 선언만 `0.2.0`으로 올리면 `cargo metadata --locked --offline --format-version 1`이 종료 코드 101과 `cannot update the lock file … because --locked was passed`를 반환한다. 패키지 버전을 올리려면 이 노드의 허용 경로 밖에 있는 루트 `Cargo.lock`과 두 개의 별도 잠금 파일을 함께 갱신해야 한다.

## 로컬 재실행 결과

| 명령 | 결과 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test golden --test snapshot_hash` | 15개 통과 |
| `cargo test --all --locked --offline` | Rust 557개 통과, 기존 무시 1개 |
| 시나리오 API·온톨로지 실행기 `cargo test --locked --offline` | 각각 4개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,809개 실행, 실패 0개, 6개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `python3 -I -m unittest discover -s packages/schemas/codegen/tests` | 142개 실행, 실패 0개, 선택적 전체 클라이언트 시험 2개 건너뜀 |
| `cargo fmt --all -- --check`, `cargo clippy --locked --offline --all-targets -- -D warnings`, `python3 -I tools/blueprint_counts.py` | 통과 |
| `python3 -I tools/ci/check_product_purpose.py`, `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 통과 |

검증 범위는 I18과 P08·P14의 로컬 엔진 동작이다. [설계도 I18](../../../docs/BLUEPRINT.md#8-설계-불변식) · [제품 목적 대응표 P08·P14](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md#3-디지털-트윈-상품-구성과-실제-개인-계약의-차이-계산과-근거-추적).
