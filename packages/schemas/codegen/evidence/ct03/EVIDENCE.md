# T-CT-03 증거 색인 (`packages/schemas/codegen/evidence/ct03/`)

과제 **T-CT-03**: OpenAPI v1 초안(공개·개인·관제), 서버 타입 크레이트 `onjeon-api-types`, Rust·TS·Dart 생성 타입. 구역 contracts, 단계 S0. 리뷰어는 PR 본문이 아니라 대상 SHA에 커밋된 이 파일들을 읽는다. 각 로그의 첫 줄이 명령(`$ …`), 마지막 줄이 `exit code: N`이다. 로그 본문은 손으로 고치지 않았고 실행 머신의 작업 트리 절대 경로 한 곳만 `<repo>`로 바꿨다(`lint_fmt.log`).

## 1. 로그를 만든 트리

| 항목 | 값 |
|---|---|
| 과제 ID | T-CT-03 (fix round 2) |
| 작성 | 모델 역할: 구현자(작성 계열). 실행 경로: 감독자가 띄운 격리 작업 트리(worktree)에서 에이전트가 직접 명령 실행. 리뷰어는 별도 계열 |
| 부모 커밋(로그 생성 시 HEAD) | `7d61a403145c6fa12bba135c0116ec53e3b9eec3`(main 병합 포함, 어휘 1.6.0) + 이 라운드의 변경(커밋·푸시는 감독자) |
| `packages/schemas` 트리 sha256 (`codegen/evidence/` 제외) | `39c0c6e99d9bfccafcdaa42ed7798d0d3ff62432c385278af268511dd1cb111f` |
| 계산 명령 | `bash packages/schemas/codegen/tree_hash.sh` |
| 대상 SHA(PR head) | **감독자가 채운다.** 그 커밋에서 `tree_hash.sh`가 위 값을 내면 이 로그는 그 커밋의 코드에서 나온 것이다. 다르면 낡은 로그이므로 §3 명령을 다시 돌린다 |
| 실행 일시 | 2026-10-17 (VM 시계) |

## 2. 도구 버전

cargo/rustc 1.98.1, python3 3.13.5(`-I`), node v20.19.2, tsc 5.9.3(`TSC='node /tmp/tsc/tsc.js'`), Dart SDK 3.13.5(`PATH=/tmp/dart-sdk/bin:$PATH`; 두 도구는 VM 임시 설치).

## 3. 로그별 명령·결과

| 로그 | 명령 | 종료 | 결과 |
|---|---|---|---|
| `gen_and_build.log` | `gen.sh && cargo build -p onjeon-api-types` | 0 | 생성·빌드 |
| `gen_check.log` | `gen.sh --check` | 0 | 생성물 30개 최신 |
| `api_types_test.log` | `cargo test -p onjeon-api-types` 및 `--features skeleton` | 0 | 각 17개 통과(스켈레톤 피처 쪽에 피처 전용 시험 포함) |
| `lint_fmt.log` | `cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`, 스켈레톤 피처 clippy `-D warnings` | 0 | 경고 없음 |
| `python_tests.log` | `python3 -I -m unittest discover -s packages/schemas/codegen/tests -v` | 0 | 104개 OK(OpenAPI lint·캐시 헤더·스켈레톤 비노출·누출 정적 검사 포함) |
| `build_check.log` | `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 0 | Rust·TS·Dart 빌드, Dart는 기본 진입점 스켈레톤 사용 코드가 `skeletonOperations` 오류로 거부됨을 확인. `SKIPPED` 없음 |
| `cargo_test_all.log` | `cargo test --all` (CI와 같은 명령) | 0 | 전부 통과(`onjeon_contracts` 25개 포함) |

## 4. 수락 항목 대응

- 모든 2xx 응답 본문에 `release_id`: lint(`openapi_model.py`)와 `test_every_success_body_requires_release_id…`. 오류 본문(`ErrorResponse`, T-CT-01 계약)은 예외이며 `openapi/README.md`에 적었다. 이 해석은 유지보수자 확인이 필요하다.
- 개인·관제 `Cache-Control: private, no-store` 고정과 금지 지시어: `test_openapi.py`의 변이 시험.
- 스켈레톤 `x-onjeon-skeleton: true`, 기본 비활성, 비노출·누출 검사: `test_openapi.py`, `api_types_test.log`(피처 유무), `build_check.log`.
- PR 템플릿 A·Q·L·I·M·R: PR 본문에 적는다(감독자). 이 과제는 소비자 질문을 직접 해결하지 않는 계약 기반이다.

## 5. 누출 확인

`test_evidence.py`가 이 디렉터리의 경로·비밀값·모델 식별자 꼴·로그 완전성을 검사한다. 로그가 자기 자신을 담을 수 없으므로 최종 파일은 대상 SHA에서 다시 돌려 확인한다.
