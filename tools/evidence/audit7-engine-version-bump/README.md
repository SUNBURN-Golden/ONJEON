# Audit 7 엔진 빌드 식별

엔진 0.2.0의 직렬화된 `engine_version`은 `0.2.0+snapshot-json-1`이다.
패키지 버전은 Cargo에서 읽고 접미사는 입력 스냅샷의 인코딩을 식별한다.
[제품목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결되는 로컬 검증이다.

| 검증 대상 | 관찰 결과 |
|---|---|
| [rule-0.2 출력 골든](../../../packages/rules-engine/tests/snapshot_hash.rs) | 버전 변경 전에는 기대값과 실제 `0.1.0+snapshot-json-1`이 달라 실패했다. 변경 후에는 버전과 독립적으로 계산한 스냅샷 해시가 모두 일치했다. |
| [릴리스 매니페스트](../../../packages/schemas/codegen/tests/fixtures/ReleaseManifest.fixture.json) | [계약 시험](../../../packages/schemas/src/tests.rs)이 rule-0.1 규칙의 실제 직렬화 결과를 읽어 매니페스트의 엔진 버전과 대조했다. |
| [PostgreSQL 매니페스트 저장](../../../infra/db/public/test.sh) | 수정 전에는 `+`에서 `release_manifest_engine_version_check` 위반이 발생했다. 수정 후 PostgreSQL 17.11 임시 DB에 전체 식별자를 삽입했고 제약 검사 166개가 통과했다. |
| [엔진 크레이트의 unsafe 금지](../../../packages/rules-engine/src/lib.rs) | 임시 엔진 복사본 끝에 `#[allow(unsafe_code)] pub unsafe fn audit_probe() {}`를 추가하고 `cargo check --offline`을 실행했다. 컴파일러가 E0453과 unsafe 함수 선언 오류를 냈다. 같은 복사본에서 크레이트의 `forbid` 속성을 제거하면 빌드가 통과했다. |
| [규칙 ID 검증](../../../packages/rules-engine/tests/identity_evidence.rs) | 기존 검증 시험 7개가 통과했다. 두 로더·두 DSL·세 공개 상태에서 빈 문자열과 유니코드 공백을 거부하고, 내용이 있는 ID의 앞뒤 공백은 보존했다. |

## 프로젝트 시험

루트 `Cargo.lock`은 이 노드의 수정 허용 경로 밖에 있고 엔진 버전이 0.1.0이다.
따라서 원본 작업 트리의 `cargo test --all --locked --offline`은 컴파일 전에 종료 코드 101을 반환했다.
작업 트리 내부의 검증용 복사본에서 `cargo update --offline -p onjeon-rules-engine`을 실행했고,
루트 잠금 파일의 차이가 해당 패키지의 버전 한 줄임을 확인했다.

| 실행 환경 | 명령 | 결과 |
|---|---|---|
| 한 줄을 갱신한 복사본 | `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 536개 통과, 1개 ignored |
| 같은 복사본 | `cargo clippy --all-targets --locked --offline -- -D warnings`, `python3 -I tools/blueprint_counts.py` | 모두 통과 |
| 원본 작업 트리의 독립 Cargo 작업 공간 | 시나리오 API와 온톨로지 runner의 `cargo test --locked --offline` | 각각 4개 통과 |
| 원본 작업 트리 | `python3 -m unittest discover -s tools/tests -v` | 1,725개 실행, 실패 0, 6개 건너뜀 |
| 원본 작업 트리 | `cargo fmt --all -- --check`, 제품 목적 검사, 설계 명세 검사, 온톨로지 사례 검사 | 모두 통과 |
