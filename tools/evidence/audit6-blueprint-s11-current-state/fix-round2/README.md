# audit6-blueprint-s11-current-state 수정 2차 실행 증거

노드: `audit6-blueprint-s11-current-state`.
기록일: 2026-11-17 KST(대조 기준일 2026-11-16 UTC).
대상: [감리 기록 수정 2차](../../../../docs/blueprint/audits/2026-11-16_blueprint_s11_current_state.md).

검토 finding: 수정 1차 이후 로컬 시험에서 `onjeon-contracts` 13개 실패와
codegen ImportError가 보고됐다. 실패 로그의 경로가 이 작업 트리가 아니라
`/workspace/onjeon-run/wt/audit6-blueprint-s12-decisions-sync/`를 가리켰다.

## 진단: 코드 결함이 아닌 공용 target 잔존 바이너리

- 이 작업 트리의 Rust 소스는 HEAD와 동일하다(`git diff`에 Rust 소스 변경 없음).
- 환경의 공용 `CARGO_TARGET_DIR`은 `/workspace/onjeon-run/shared-target`인데,
  거기에는 이미 삭제된 다른 작업 트리(`audit6-blueprint-s12-decisions-sync`)에서
  컴파일된 시험 바이너리가 남아 있었다. 해당 작업 트리 디렉터리는 현재 존재하지
  않는다.
- `packages/schemas` 시험은 저장소 루트를 컴파일 시점 절대 경로
  (`env!("CARGO_MANIFEST_DIR")`, `src/tests.rs`·`src/events.rs`)로 푼다.
  삭제된 작업 트리 경로가 박힌 바이너리는 `codegen/gen.py`·`codegen/tests` 등을
  읽지 못해 NotFound/ImportError로 실패한다.
- Cargo는 지문이 신선하다고 판단해 재컴파일 없이 그 바이너리를 실행했다.
  재현: `cargo test -p onjeon-contracts --lib --locked --offline` →
  `Finished … in 0.03s`, 41 통과·13 실패, 종료 101
  ([shared-target-repro.log](shared-target-repro.log)). 보고된 실패와 동일하다.

소스는 바꾸지 않았다. 검증은 두 경로로 수행했다.

1. **작업 트리 전용 target**(`CARGO_TARGET_DIR="$PWD/target"`): 수정 1차와
   같은 결정적 재실행. 명령 자체는 README와 같다.
2. **공용 target 정리·재빌드**: 동시 실행이 없는 것을 확인한 뒤 작업 공간
   크레이트 8개를 `cargo clean -p`로 제거하고 이 작업 트리에서 재빌드했다.
   처음에 `onjeon-contracts`·`onjeon-api-types`만 정리했을 때는
   `onjeon-rules-engine`의 `fixture_supplements` 바이너리도 같은 잔존
   상태라 2개가 더 실패했다([first-attempt 로그](shared-target-repair-first-attempt.log)).
   크레이트 8개 전체 정리 후 재실행은 532개 통과·무시 1개, 종료 0이며
   삭제된 작업 트리 경로 참조가 없다([shared-target-repair.log](shared-target-repair.log)).

## 명령과 결과

저장소 루트에서 실행했다. 로그는 로컬 실행의 표준 출력·오류이며 수락 결과는
명령의 종료 코드와 함께 아래에 기록한다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `cargo test -p onjeon-contracts --lib --locked --offline` (공용 target, 재현) | 재컴파일 없이 41 통과·13 실패, 종료 101. 삭제된 작업 트리 경로 참조 3건 | [shared-target-repro.log](shared-target-repro.log) |
| `cargo clean -p onjeon-contracts -p onjeon-api-types` 후 `cargo test --all --locked --offline` (공용 target) | rules-engine 잔존 바이너리 2개 실패 추가 확인, 종료 101 | [shared-target-repair-first-attempt.log](shared-target-repair-first-attempt.log) |
| 작업 공간 크레이트 8개 `cargo clean -p` 후 `cargo test --all --locked --offline --no-fail-fast` (공용 target) | 8개 재컴파일, 532개 통과·기존 무시 1개, 실패 0, 종료 0 | [shared-target-repair.log](shared-target-repair.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --all --locked --offline` | 532개 통과, 기존 무시 1개, 실패 0, 종료 0 | [rust-tests.log](rust-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo build --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 빌드 성공, 종료 0 | [ontology-build.log](ontology-build.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 4개 통과, 종료 0 | [ontology-tests.log](ontology-tests.log) |
| 온톨로지 실행기 build·test (공용 target, README 명령) | 빌드 성공·4개 통과, 종료 0 | [build](ontology-build-shared.log), [test](ontology-tests-shared.log) |
| `python3 -m unittest discover -s tools/tests -v` (README 명령) | 1,665개, 실패·오류 0, 기존 건너뜀 6개, 종료 0 | [python-tests.log](python-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_blueprint_current_state.py -v` | 9개 통과, 종료 0 | [focused.log](focused.log) |
| `python3 -I -m unittest discover -s tools/tests -p 'test_blueprint*.py' -v` | 73개 통과, 종료 0 | [blueprint-tests.log](blueprint-tests.log) |
| `python3 -I tools/blueprint_counts.py` | 엔진 등록 266 + doctest 3, 실제 조항 7, 변조 40, 어휘 49 일치, 종료 0 | [counts.log](counts.log) |
| `python3 -I tools/blueprint_status.py` | ADR·DEC 37개 색인 일치, 종료 0 | [status.log](status.log) |
| `python3 -I tools/vocab_check.py` | 종료 0 | [vocabulary.log](vocabulary.log) |
| `python3 -I tools/validation_check.py` | 종료 0 | [validation.log](validation.log) |
| `python3 -I tools/validation_check.py --selftest` | 변조 40종 통과, 종료 0 | [tamper-tests.log](tamper-tests.log) |
| `python3 -I tools/registry_check.py` | 종료 0 | [registry-check.log](registry-check.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 46/46·존재 72/72 통과, 종료 0 | [spec-check.log](spec-check.log) |
| `python3 -I tools/release_readiness/check.py --json` | P행 19·기능 64 모두 open, closed/excluded=0. **종료 1(제품 미완료)** | [readiness.json](readiness.json), [종료 코드](readiness-exit.log) |
| 허용 경로·보호 파일·링크·공백 검사 | 허용 경로만 변경, 보호 파일 불변, 링크·공백 정상 | [scope.log](scope.log) |

## 해석과 범위

수정 2차에서 소스·시험 코드는 바꾸지 않았고, 감리 기록에 진단·재검증 절만
추가했다. 문서 finding(§11 근거 수)의 정정과 회귀 시험 2개는 수정 1차
그대로이며 집중 9개·관련 73개가 다시 통과했다. 건너뜀 6개는 초회·수정 1차와
같은 조건부 건너뜀(비공개 원본 미설정 2, 로컬 보관본·추출기 조건 미충족 3,
구버전 SDK 분기 1)이고 새 회귀 검사에는 건너뜀이 없다. 무시 1개는 기존
온톨로지 픽스처 시험이다.

공용 target 정리는 빌드 산출물만 제거·재빌드한 것이며 다른 작업 트리의
소스는 건드리지 않았다. 공용 target은 이후 다른 작업 트리의 동시 실행이
다시 덮어쓸 수 있다. 같은 실패가 재현되면 실패 로그의 다른 작업 트리 경로로
진단하고 전용 target으로 재실행한다.

출시 판정기 결과의 종료 1은 정본 등록부의 완료 증거가 없다는 관측이며
이 문서 finding의 실패가 아니다. 실제 공시·상품/계약 트윈·소비자 화면·
P01~P19 전체·T-OP-08 완료·출시 승인을 선언하지 않는다.
보호 파일 변경·commit·push·GitHub 호출·비밀값 조회·실제 R2/AI 제공자/
프로덕션 접근은 수행하지 않았다. 로그는 행 끝 공백과 파일 끝 빈 줄만 정리했다.
