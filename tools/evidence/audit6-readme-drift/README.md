# Audit 6: README 디렉터리·ADR·문서 위계 재검증

검증일: 2026-11-17. 노드: `audit6-readme-drift`.
기준 커밋: `182125bb4470902789a3366d6b649f8c0518b9c9` + 이 노드의 미커밋 변경.

## 발견과 수정

| 감리 지적 | 시작 시점 대조 | 조치 |
|---|---|---|
| ADR 목록이 0011까지만 있음 | [루트 README](../../../README.md)는 이미 0001~0019를 나열했다 | 기존 디렉터리 양방향 대조를 유지하고 0011 뒤를 자르는 변이 검출을 정규 시험에 추가 |
| `tools/`·`infra/r2/`·`data/registry/` 누락 | `infra/r2/`와 `data/registry/`는 이미 존재했으나 `tools/` 전체 행은 없었다(`tools/daemon/`만 안내) | `tools/` 행과 수집·보관·비용 검사·원장 정규화·시험 경로 링크를 추가하고 세 디렉터리 각각의 행 삭제를 검출 |
| 문서 우선순위가 BLUEPRINT §0.1과 충돌 | 이미 [BLUEPRINT §0.1](../../../docs/BLUEPRINT.md#01-문서-위계)로 위임하고 있었다 | 기존 검사를 유지하고 옛 우선순위로 교체하거나 현행 링크와 함께 삽입한 변이를 모두 검출 |

[회귀 시험](../../tests/test_readme_index.py)은 기존 CI의
`python3 -m unittest discover -s tools/tests -v`로 자동 실행된다.
새 `tools/` 행의 링크 대상 존재를 확인하고, `AuditFindingRegressions`는
README 문자열만 메모리에서 변조해 여섯 변이가 의도한 검사의 assertion
실패로 검출되는지 확인한다. 실제 README 파일은 변이하지 않는다.

## 직접 실행한 증거

| 증거 | 명령·결과 |
|---|---|
| [수정 전](before-tests.log) | 새 시험 추가 후 README 수정 전 집중 시험: 15건 중 3건 실패. 모두 `tools/` 행 부재를 보고 |
| [수정 후](focused-tests.log) | `python3 -m unittest discover -s tools/tests -p test_readme_index.py -v`: 15건 통과, 건너뜀 없음. 변이 6종 검출 포함 |
| [Python 전체](python-tests.log) | `python3 -m unittest discover -s tools/tests -v`: 1,665건 실행, 실패·오류 0, 기존 건너뜀 6건 |
| [결정 색인](blueprint-status.log) | `python3 -I tools/blueprint_status.py`: ADR·DEC 37개 정합 |
| [제품 목적 연결](purpose-check.log) | `python3 -I tools/ci/check_product_purpose.py`: P01~P19 작업 연결·필수 시험 ID 9개 정합(정적 검사) |
| [Rust 전체](rust-tests.log) | `cargo test --all --locked --offline`: 문서 시험 포함 532건 통과, 실패 0, 기존 ignored 1건 |
| [온톨로지 빌드](ontology-build.log)·[시험](ontology-tests.log) | `cargo build`·`cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline`: 빌드 성공, 시험 4건 통과 |
| [변경 범위](scope-check.log) | 허용 경로만 변경, 보호 문서 불변, `git diff --check`·이 문서의 로컬 링크 존재 검사 통과. README·시험 파일 SHA-256 기록 |

Rust 명령은 `RUSTUP_TOOLCHAIN=1.98.1`을 사용한다. `CARGO_TARGET_DIR`는
이 작업 트리의 `target/workspace`(루트 Rust 시험)와 `target/ontology`
(온톨로지 실행기 및 Python 시험)로 지정했다. Python 전체 시험에는
`ONJEON_ONTOLOGY_RUNNER`로 이 작업 트리에서 빌드한 실행기를 전달한다.

Python 건너뜀 6건은 원본 보관 경로 미설정 2건, 로컬 보관소·pdftotext가
필요한 재현 시험 3건, 설치된 botocore가 조건부 쓰기를 지원해 해당하지
않는 구버전 거부 시험 1건이다. README 시험에는 건너뜀이 없다.
Rust ignored 1건은 기존 `regenerate_declared_abox_fixture` 재생성 시험이다.

이 증거는 README finding의 문서 정합성·회귀 검증에 한정된다.
[09_제품목적_대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의
실제 공시 수집·상품/계약 트윈·소비자 화면·P01~P19 및 첫 출시 완료를
증명하지 않으며 완료 상태를 변경하지 않는다.

## 수정 라운드 1: 공유 target의 stale 시험 바이너리 (소스 변경 없음)

감독자 재실행이 `CARGO_TARGET_DIR=/workspace/onjeon-run/shared-target`에서
`onjeon-rules-engine --test fixture_supplements` 2건 실패를 보고했다.
이 작업 트리의 소스는 HEAD에서 변경되지 않았고(`git status --porcelain -- packages/` 비어 있음),
앞 라운드의 Rust 전체 시험은 작업 트리 전용 target에서 532건 통과했다.

진단(메모리 `shared-cargo-target-stale-artifacts`의 삭제된 작업 트리 변형):

- 재현: `cargo test -p onjeon-rules-engine --test fixture_supplements --locked --offline`
  → `Finished in 0.02s`(재컴파일 없음), 두 시험이 `NotFound`로 실패.
- 원인: 공유 target의 `fixture_supplements-5c73c7add3657f0c` 바이너리에
  `env!("CARGO_MANIFEST_DIR")`로 **삭제된** 작업 트리
  `/workspace/onjeon-run/wt/_review_2807300_45732361` 경로가 박혀 있었다
  (`strings`로 확인, 해당 디렉터리 부재). 동일 소스 ⇒ 신선한 fingerprint라
  cargo가 재컴파일하지 않았다. 코드 결함이 아니라 환경 문제다.

조치(동시 빌드 없음 확인 후 공유 target 수리):

1. `ps aux | grep -E 'cargo|rustc'` → 실행 중인 빌드 없음.
2. 8개 워크스페이스 패키지 전체 `cargo clean -p` (부분 clean은 불충분했던 전례).
3. `RUSTUP_TOOLCHAIN=1.98.1 cargo test --all --locked --offline --no-fail-fast`
   → **532건 통과, 실패 0**, exit 0 ([rust-tests-fix1.log](rust-tests-fix1.log)).
   재빌드된 바이너리는 이제 이 작업 트리(`audit6-readme-drift`) 경로를 담는다.
4. 온톨로지 실행기 `cargo test --manifest-path …/runner/Cargo.toml --locked --offline`
   (target/ontology) → 4건 통과 ([ontology-tests-fix1.log](ontology-tests-fix1.log)).
5. `ONJEON_ONTOLOGY_RUNNER=…/target/ontology/debug/ontology-case-runner
   python3 -m unittest discover -s tools/tests -v` → **1,665건 실행, OK(건너뜀 6)**,
   exit 0 ([python-tests-fix1.log](python-tests-fix1.log)). README 회귀·변이 검출 포함.

이 라운드에서는 소스·문서를 바꾸지 않았다. README finding 수정(앞 라운드)은
그대로 유효하며, 실패는 공유 target 수리로 해소됐다.
