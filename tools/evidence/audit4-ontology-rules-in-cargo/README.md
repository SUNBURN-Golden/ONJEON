# Audit 4 온톨로지 원본 규칙 검증 증거

2026-11-03, 현재 작업 트리에서 로컬 실행. [수정 범위와 한계](../../../docs/blueprint/audits/2026-11-03_ontology_rules_in_cargo.md), [원본 내용 해시](../../../docs/blueprint/proposals/온톨로지/rule_content_hashes.json).

두 원본 JSON의 내용과 A-box의 동결 릴리스는 수정하지 않았다. 원본 파일명과 엔진 내용 해시 고정, Cargo 직접 로드·경계·미확인·동일 버전 변경 검출, runner 메타데이터 보존, CI·Python 빌드의 잠금 파일 사용을 검증한다. 실제 상품 릴리스·소비자 화면·P08·P14 전체·첫 출시 완료 증거는 아니다.

저장소 루트에서 사용한 환경:

```sh
export RUSTUP_TOOLCHAIN=1.98.1
export CARGO_TARGET_DIR="$PWD/target"
export ONJEON_ONTOLOGY_RUNNER="$PWD/target/ontology-runner/debug/ontology-case-runner"
```

검증 명령과 결과:

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,342 실행, 실패 0, 건너뜀 6, `OK (skipped=6)` | [python-tools.log](python-tools.log) |
| `cargo test --all --locked --offline` | 495 통과, 0 실패, 기존 doctest 1 무시 | [cargo-workspace.log](cargo-workspace.log) |
| `CARGO_TARGET_DIR="$PWD/target/ontology-runner" cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 통과, 0 실패. 새 시험에서 두 원본 × 세 지급 상태의 6행 대조 | 이 세션의 Cargo 실행 결과 |
| `CARGO_TARGET_DIR="$PWD/target/ontology-runner" cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 종료 0, Python 검사에 사용한 runner 빌드 | 이 세션의 Cargo 실행 결과 |
| `cargo clippy --locked --offline --all-targets -- -D warnings` | 종료 0 | [clippy-workspace.log](clippy-workspace.log) |
| `CARGO_TARGET_DIR="$PWD/target/ontology-runner" cargo clippy --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline --all-targets -- -D warnings` | 종료 0 | [clippy-runner.log](clippy-runner.log) |
| `cargo fmt --all -- --check` 및 runner의 `cargo fmt --manifest-path … -- --check` | 둘 다 종료 0 | 이 세션의 실행 결과 |
| `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py "$ONJEON_ONTOLOGY_RUNNER"` | 질문 11/11, 제약 자체 시험 15/15, 릴리스·문서 모델 25/25, 금액 표시·비교 10/10, 종료 0 | [ontology-check.log](ontology-check.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45, 존재 검사 72/72, 종료 0 | [spec-check.log](spec-check.log) |
| `python3 -I tools/blueprint_counts.py` | 엔진 시험 230, doctest 3, 실제 조항 규칙 7, 변조 시험 40, 어휘 축 49, 종료 0 | 이 세션의 실행 결과 |

엔진 전체 등록 수 230은 이 작업에서 추가한 `ontology_rules` 4개를 포함한다. 전체 워크스페이스 495건과는 집계 범위가 다르다. runner는 별도 Cargo 작업 공간이다. runner 출력의 릴리스·스키마 필드와 CI runner 빌드의 `--locked`는 작업 시작 시 이미 있었으며 회귀 시험으로 확인했다.

기계 판독용 결과와 주요 소스·원본 규칙·로그의 SHA-256은 [checks-summary.json](checks-summary.json)에 고정한다. `base_commit`은 작업 시작 기준 커밋이며 이 변경을 커밋하거나 푸시하지 않았다. 모든 변경·새 파일은 이 노드의 허용 경로에 있고 금지 파일은 수정하지 않았다.
