# Audit 7 엔진 빌드 식별

엔진 0.2.0의 직렬화된 `engine_version`은 `0.2.0+snapshot-json-1`이다.
`ENGINE_VERSION`은 결과와 릴리스 매니페스트에 기록되는 평가기 버전으로, 입력 스냅샷 인코딩 접미사 `+snapshot-json-1`을 포함하며 Cargo 패키지 버전과 독립적으로 관리한다(아래 수정 라운드 4 참고).
[제품목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결되는 로컬 검증이다.

| 검증 대상 | 관찰 결과 |
|---|---|
| [rule-0.2 출력 골든](../../../packages/rules-engine/tests/snapshot_hash.rs) | 버전 변경 전에는 기대값과 실제 `0.1.0+snapshot-json-1`이 달라 실패했다. 변경 후에는 버전과 독립적으로 계산한 스냅샷 해시가 모두 일치했다. `engine_version_golden` 시험이 상수 전체를 리터럴로 고정하고, 직렬화 출력 골든도 같은 문자열을 고정한다. |
| [릴리스 매니페스트](../../../packages/schemas/codegen/tests/fixtures/ReleaseManifest.fixture.json) | [계약 시험](../../../packages/schemas/src/tests.rs)이 rule-0.1 규칙의 실제 직렬화 결과를 읽어 매니페스트의 엔진 버전과 대조했다. |
| [같은 릴리스의 결과 픽스처](../../../packages/schemas/codegen/tests/test_schemas.py) | 수정 라운드 1의 대조 시험을 `674703d`의 픽스처로 돌리면 `rel:20261001-1`인 시나리오 두 개와 단독 평가 결과 한 개에서 엔진 버전 불일치가 검출된다. 수정 후 세 결과 모두 매니페스트의 빌드 식별자와 일치하며 각 DSL 판도 매니페스트에 열거돼 있다. |
| [PostgreSQL 매니페스트 업그레이드](../../../infra/db/public/test.sh) | PostgreSQL 17.11의 02 스키마에 `0.1.0` 매니페스트를 고정했다. `0.2.0+snapshot-json-1` 삽입은 기존 제약에서 거부됐고 [03 마이그레이션](../../../infra/db/public/03_engine_version.sql) 적용 뒤 같은 INSERT가 통과했다. 기존 행을 다시 읽은 값은 `0.1.0`이었고 빈 접미사(`0.2.0+`)는 새 제약에서 거부됐다. |
| [엔진 크레이트의 unsafe 금지](../../../packages/rules-engine/src/lib.rs) | 임시 엔진 복사본 끝에 `#[allow(unsafe_code)] pub unsafe fn audit_probe() {}`를 추가하고 `cargo check --offline`을 실행했다. 컴파일러가 E0453과 unsafe 함수 선언 오류를 냈다. 같은 복사본에서 크레이트의 `forbid` 속성을 제거하면 빌드가 통과했다. 수정 라운드 4에서 같은 절차를 다시 실행해 두 결과를 재확인했다. |
| [규칙 ID 검증](../../../packages/rules-engine/tests/identity_evidence.rs) | 기존 검증 시험 7개가 통과했다. 두 로더·두 DSL·세 공개 상태에서 빈 문자열과 유니코드 공백을 거부하고, 내용이 있는 ID의 앞뒤 공백은 보존했다. |

## 수정 라운드 4: 빌드 식별과 잠금 파일 경로 제약

수정 라운드 3은 [크레이트 버전](../../../packages/rules-engine/Cargo.toml)을 `0.2.0`으로 올리고 [루트 잠금 파일](../../../Cargo.lock)을 함께 갱신했으나, 루트 `Cargo.lock`은 이 노드의 허용 경로 밖이라 차단됐다.
루트 워크스페이스는 `packages/rules-engine`을 구성원으로 포함하고 CI는 `cargo test --all --locked`로 잠금 파일 일치를 검사한다. 패키지 버전을 `0.2.0`으로 올린 상태에서 루트 잠금 파일을 기본(`0.1.0`)으로 되돌리고 `cargo metadata --locked --offline`을 실행하면 종료 코드 101과 `cannot update the lock file … because --locked was passed` 오류가 난다. 즉 패키지 버전 인상은 루트 잠금 파일 재작성을 강제하므로 허용 경로 안에서는 수행할 수 없다.

[추적 비밀 검사](../../check_tracked_secrets.py)가 허용 경로 밖의 `.gitignore` 대신 허용 경로 안의 수단으로 같은 결과를 보장한 선례를 따라, 이 노드는 결과와 매니페스트에 실제로 기록되는 빌드 식별자를 올린다.

- Cargo 패키지 버전은 `0.1.0`으로 유지하고, [루트](../../../Cargo.lock)·[시나리오 API](../../../services/scenario-api/Cargo.lock)·[온톨로지 runner](../../../docs/blueprint/proposals/온톨로지/검증/runner/Cargo.lock) 잠금 파일도 모두 `0.1.0`으로 일치시킨다. 이 노드의 누적 변경 사항(시작 커밋 대비)에 루트 잠금 파일은 포함되지 않는다.
- [`ENGINE_VERSION`](../../../packages/rules-engine/src/lib.rs)은 하드코딩한 `0.2.0+snapshot-json-1`로, 모든 평가 결과와 릴리스 매니페스트가 이 값을 기록한다. 감사 지적의 대상(결과·매니페스트가 빌드를 구분하지 못함)은 이 값이다.
- 골든 고정: `engine_version_golden`이 상수를 리터럴과 대조한다. 변이 검증으로 복사본의 상수를 `0.1.0+snapshot-json-1`으로 낮추면 이 시험이 실패함(`left: "0.1.0+snapshot-json-1"`, `right: "0.2.0+snapshot-json-1"`)을 확인했다. 직렬화 출력 골든의 문자열 고정도 함께 통과한다.
- Cargo 패키지 버전 자체를 `0.2.0`으로 올리려면 루트 `Cargo.lock`을 허용 경로에 추가해야 한다(잠금 파일에서 `onjeon-rules-engine` 항목의 버전 한 줄 갱신).

| 명령 | 결과 |
|---|---|
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 537개 통과(문서 시험 3개 포함), 실패 0, 픽스처 재생성용 시험 1개 ignored |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline`, `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 각각 4개 통과 |
| `bash infra/db/public/test.sh` | PostgreSQL 17.11에서 새 설치와 02 → 03 업그레이드를 포함해 171개 통과 |
| `python3 -I -m unittest discover -s packages/schemas/codegen/tests` | 138개 실행, 실패 0, TypeScript·Dart 호환성 시험 2개 건너뜀 |
| `ONJEON_ONTOLOGY_RUNNER=…/debug/ontology-case-runner python3 -m unittest discover -s tools/tests` | 1,725개 실행, 실패 0, 6개 건너뜀 |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked --offline -- -D warnings`, `python3 -I tools/blueprint_counts.py` | 모두 통과(엔진 시험 270개, 문서 시험 3개) |
