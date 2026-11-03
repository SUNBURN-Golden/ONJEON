# Audit 4: 엔진 README 시험 표 누락 재검증

기록일: 2026-11-04. 노드: `audit4-engine-readme-test-table`.
연결: BLUEPRINT A1·A2·A5, Q7, L6, I6, M1 기반, [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08·P14.

작업 시작 시 [엔진 README](../../../packages/rules-engine/README.md)의 `## 테스트` 표에는 `real_clauses`·`vocabulary`가 모두 있었다. [Audit 3 기록](2026-10-29_engine_readme_test_table.md)과 마찬가지로 두 행의 누락은 이미 수정된 상태였으며, 이번 작업에서 새로 추가했다고 주장하지 않는다.

기존 `readme_test_table` 시험은 표 첫 열과 `tests/*.rs` 파일을 양방향 대조하며, 두 행의 개별 삭제·개명도 검출한다. 이번에는 같은 README 문자열에서 **두 행을 동시에 삭제**하는 음성 대조를 보강했다. 누락 집합이 정확히 `real_clauses`·`vocabulary`이고 낡은 이름은 없는지 확인한다. 파일을 변경하지 않고 메모리에서 검사한다. README의 시험 설명과 이 증거 링크도 갱신했다. 시험 함수 등록 수와 엔진 동작은 바꾸지 않았다.

저장소 루트에서 Rust `1.98.1`과 이 작업 트리 전용 `CARGO_TARGET_DIR="$PWD/target"`를 사용했다.

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test readme_test_table --test real_clauses --test vocabulary` | 종료 0, 표 검사 5개·실제 조항 11개·어휘 9개, 총 25개 통과. [focused.log](../../../packages/rules-engine/evidence/audit4-engine-readme-test-table/focused.log) |
| `cargo test --all --locked --offline` | 종료 0, 단위·통합·문서 시험 495개 통과, 실패 0, 기존 ignored 1개(`regenerate_declared_abox_fixture`). [workspace.log](../../../packages/rules-engine/evidence/audit4-engine-readme-test-table/workspace.log) |
| `cargo fmt --all -- --check` | 종료 0. [fmt.log](../../../packages/rules-engine/evidence/audit4-engine-readme-test-table/fmt.log) |
| `python3 -I tools/blueprint_counts.py` | 종료 0, 기존 등록 수와 일치. [blueprint-counts.log](../../../packages/rules-engine/evidence/audit4-engine-readme-test-table/blueprint-counts.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 종료 0, P01~P19 작업 연결과 G12 시험 ID 정적 정합성 통과. [product-purpose.log](../../../packages/rules-engine/evidence/audit4-engine-readme-test-table/product-purpose.log) |

`git diff --check`와 README·이 감사 기록의 로컬 링크 존재 검사도 통과했다.

`real_clauses`는 실제 조항 기반 `fixture_only` 사례 105개의 정확한 수와 규칙별 사례 보유 등을, `vocabulary`는 정본 어휘·DSL 버전 제한과 합성·실제 조항 기반 규칙의 시험 전용 상태를 확인한다. 이 기록은 README 표 정합성과 P08·P14 엔진 기반 회귀 증거다. 실제 상품 릴리스·전 상품 수집·소비자 화면·첫 출시 완료 증거를 대체하지 않는다.
