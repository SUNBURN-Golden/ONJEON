# Fix round 1: 로컬 Cargo 도구 선택

보고된 로컬 시험 실패는 Python 회귀가 아니라 그 뒤의 Cargo 실행에서 났다.
이 환경에는 Rust 1.98.1이 설치되어 있었지만 rustup 전역 기본 도구가 없어
`cargo`가 `rustup could not choose a version of cargo to run`으로 종료했다.
Python 회귀 자체는 `Ran 1787 tests ... OK (skipped=71)`로 통과했다.

저장소 코드 변경 없이 로컬 도구 선택만 고쳤다. `rustup default 1.98.1`로
설치된 도구를 기본으로 지정했고, [toolchain.log](toolchain.log)에 그 상태를
남겼다. CI는 이미 워크플로 환경 변수 `RUSTUP_TOOLCHAIN: "1.98.1"`로 같은
도구를 선택하므로 이번 수정은 로컬 실행 환경에만 해당한다.

| 실행(작업 트리 루트) | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests` | 1,787개 실행, 실패·오류 0, 71개 건너뜀, 종료 0: [python-tests.log](python-tests.log) |
| `cargo test --all --locked` | 537개 통과, 기존 1개 무시, 실패 0, 종료 0: [cargo-tests.log](cargo-tests.log) |
| `cargo test --locked --offline --manifest-path services/scenario-api/Cargo.toml` | 4개 통과, 종료 0 |
| `cargo test --locked --offline --manifest-path "docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml"` | 4개 통과, 종료 0 |

정적 검사도 다시 실행해 통과했다:
`python3 -I tools/ci/check_product_purpose.py`,
`python3 -I tools/ci/check_pr_body_traceability.py --selftest`,
`python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py`(기계 47/47,
존재 72/72), `python3 -I tools/release_readiness/progress.py`(P20 포함),
`python3 -I tools/release_readiness/check.py --json`(미완료이므로 예상 종료 1).

이 수정은 빌드 라운드의 표·도구 변경을 바꾸지 않는다. P행·과제 연결과 그
회귀 시험의 내용은 상위 [README](../README.md)에 기록한 그대로다.
