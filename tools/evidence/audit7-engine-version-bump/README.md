# Audit 7 엔진 빌드 식별

엔진 0.2.0의 직렬화된 `engine_version`은 `0.2.0+snapshot-json-1`이다.
이 값은 엔진의 `ENGINE_VERSION`에 고정하며 접미사는 입력 스냅샷의 인코딩을 식별한다. Cargo 패키지 버전은 0.1.0이다.
[제품목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결되는 로컬 검증이다.

| 검증 대상 | 관찰 결과 |
|---|---|
| [rule-0.2 출력 골든](../../../packages/rules-engine/tests/snapshot_hash.rs) | 버전 변경 전에는 기대값과 실제 `0.1.0+snapshot-json-1`이 달라 실패했다. 변경 후에는 버전과 독립적으로 계산한 스냅샷 해시가 모두 일치했다. |
| [릴리스 매니페스트](../../../packages/schemas/codegen/tests/fixtures/ReleaseManifest.fixture.json) | [계약 시험](../../../packages/schemas/src/tests.rs)이 rule-0.1 규칙의 실제 직렬화 결과를 읽어 매니페스트의 엔진 버전과 대조했다. |
| [같은 릴리스의 결과 픽스처](../../../packages/schemas/codegen/tests/test_schemas.py) | 수정 라운드 1의 대조 시험을 `674703d`의 픽스처로 돌리면 `rel:20261001-1`인 시나리오 두 개와 단독 평가 결과 한 개에서 엔진 버전 불일치가 검출된다. 수정 후 세 결과 모두 매니페스트의 빌드 식별자와 일치하며 각 DSL 판도 매니페스트에 열거돼 있다. |
| [PostgreSQL 매니페스트 업그레이드](../../../infra/db/public/test.sh) | PostgreSQL 17.11의 02 스키마에 `0.1.0` 매니페스트를 고정했다. `0.2.0+snapshot-json-1` 삽입은 기존 제약에서 거부됐고 [03 마이그레이션](../../../infra/db/public/03_engine_version.sql) 적용 뒤 같은 INSERT가 통과했다. 기존 행을 다시 읽은 값은 `0.1.0`이었고 빈 접미사(`0.2.0+`)는 새 제약에서 거부됐다. |
| [엔진 크레이트의 unsafe 금지](../../../packages/rules-engine/src/lib.rs) | 임시 엔진 복사본 끝에 `#[allow(unsafe_code)] pub unsafe fn audit_probe() {}`를 추가하고 `cargo check --offline`을 실행했다. 컴파일러가 E0453과 unsafe 함수 선언 오류를 냈다. 같은 복사본에서 크레이트의 `forbid` 속성을 제거하면 빌드가 통과했다. |
| [규칙 ID 검증](../../../packages/rules-engine/tests/identity_evidence.rs) | 기존 검증 시험 7개가 통과했다. 두 로더·두 DSL·세 공개 상태에서 빈 문자열과 유니코드 공백을 거부하고, 내용이 있는 ID의 앞뒤 공백은 보존했다. |

## 수정 라운드 2 작업 트리 검증

루트, 시나리오 API, 온톨로지 runner의 `Cargo.lock`을 각각 `origin/main`과 대조해 세 파일 모두 바이트 단위로 일치함을 확인했다.
이 상태에서 기존 `env!("CARGO_PKG_VERSION")`으로 엔진 버전을 조합하면 출력 골든이 실제값 `0.1.0+snapshot-json-1`을 보고 실패했다.
엔진 버전을 독립 상수로 바꾼 뒤 같은 골든과 아래 시험을 실행했다.

| 명령 | 결과 |
|---|---|
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 536개 통과, 픽스처 재생성용 시험 1개 ignored |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline`, `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 각각 4개 통과 |
| `bash infra/db/public/test.sh` | PostgreSQL 17.11에서 새 설치와 02 → 03 업그레이드를 포함해 171개 통과 |
| `python3 -I -m unittest discover -s packages/schemas/codegen/tests` | 138개 실행, 실패 0, TypeScript·Dart 호환성 시험 2개 건너뜀 |
| `python3 -m unittest discover -s tools/tests -v` | 1,725개 실행, 실패 0, 6개 건너뜀 |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked --offline -- -D warnings`, `python3 -I tools/blueprint_counts.py` | 모두 통과 |
