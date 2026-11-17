# audit6-prose-test-coverage-guard 검증 증거

2026-11-17. 모든 명령은 이 작업 트리 루트에서 실행했다. 커밋·푸시·GitHub 호출·외부
제공자 호출은 없다. A1~A6·Q1~Q7·L0~L9·I6·M1~M5의 작업 완료 검증 장치이며
실제 제품 기능이나 출시 완료를 주장하지 않는다.

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_task_test_coverage.py -v` | 15개 통과, [focused-tests.log](focused-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 20개 통과, [purpose-tests.log](purpose-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,697개·실패 0·기존 skip 6, [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 종료 코드 0, [rust-tests.log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 종료 코드 0, [ontology-tests.log](ontology-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47·존재 72/72, [spec-check.log](spec-check.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` | 종료 코드 0, [daemon-tests.log](daemon-tests.log); 기존 모의 GAP은 제품 완료 증거 아님 |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/check_missing_task_suites.py` | 62과제 확인: 필수 ID가 있는 27과제 등록 부재를 모두 종료 코드 1로 거부, 35과제는 빈 목록 명시, [missing-suites.log](missing-suites.log) |
| `python3 -I tools/validation_check.py --selftest` | 변이 40개 모두 의도한 이유로 검출, [validation-selftest.log](validation-selftest.log) |
| `python3 -I tools/ci/check_bootstrap.py` | 종료 코드 0·기존 advisory 6개, [bootstrap-default.log](bootstrap-default.log) |
| `python3 -I tools/ci/check_bootstrap.py --strict-paths` | 종료 코드 1·기존 경로 finding 6개, [bootstrap-check.log](bootstrap-check.log); HEAD의 tasks.json과 rule·message를 대조해 동일함을 확인, [bootstrap-baseline.log](bootstrap-baseline.log) |

새 회귀 시험은 과제 62개마다 명령·완료 조건·작성 경로 삭제를 거부하며, 과제별
모든 필수 ID 제거도 거부한다. 실행 시험에서는 등록·함수 삭제, 알 수 없는 ID,
중복·재사용·동적 목록·실행 중 목록 변경, 실패·오류·skip·expectedFailure·0건 실행,
빈 assertion, 모듈·클래스 준비 skip, 다른 과제의 등록 빌리기를 검사했다.
양성 사례는 임시 디렉터리의 실제 unittest 2개를 전부 실행하고 통과한다.

첫 전체 Python 실행의 [initial-python-tests.log](initial-python-tests.log)는 10개 실패를 기록한다.
T-UX-01 시험 경로 추가에 따른 기존 경로 기대값 1개, 03 완료 기준 표 동기화 누락 8개,
빈 필수 목록에 남은 등록도 거부하도록 강화한 실행기의 이전 기대값 1개다.
경로 기대값을 정확한 두 경로로 갱신하고, 표를 JSON과 동기화하고, 이전 기대값을
등록이 남은 경우 실패·등록이 없는 빈 목록만 명시적 통과로 고친 뒤 전체 재실행했다.
기존 사용자 확정·수락 수치·결정 관문은 그대로 검사한다.

필수 ID가 있는 제품 과제 27개의 실제 등록·제품 시험 구현은 각 과제의 산출물이다.
이 노드에서는 그 시험이나 제품 증거를 만들었다고 보고하지 않는다. 감독 실행기가
`시험 …` 문구를 건너뛰어도 새 필수 명령을 실행하면 구현 부재가 실패로 드러난다.

## Fix round 1: origin/main(7dc1241, PR #550) 병합 — 양쪽 의도 모두 유지

병합 충돌은 세 파일이었다. `tasks.json`의 123개 헝크는 모두 같은 모양으로,
HEAD는 `tools/task_tests/<과제 ID>/**`를, main(audit6-evidence-path-for-all-tasks)은
`docs/release-readiness/evidence/<과제 ID>/**`를 같은 allowed_paths·conflict_paths
목록 끝에 추가한 것이다. 두 항목을 모두 남겼다(T-OP-08의 allowed_paths는 기존
집계 권한이 증거 경로를 이미 덮어 자동 병합됐다). `03_작업명세.md`의 두 헝크는
§6 과제 표(61행)와 §7 산출물·완료 기준 표(62행)로, 기준(7abea57) 대비 칸 단위
비교에서 양쪽이 서로 다른 칸만 고친 것을 확인하고 칸별 병합했다: HEAD의 시험
명령·완료 기준·필수 시험 ID 칸과 main의 수정 허용 경로·산출물 칸을 모두 유지한다.
`test_audit5_confirm_agent_made_decisions.py`의 T-UX-01 경로 기대값은 세 권한
(사전 등록·시험 등록·증거) 모두를 검사하도록 갱신했고 수락 수치·결정 관문
검사는 그대로다. 해소 절차·필드별 대조는
[conflict-resolution.log](merge-main-round1/conflict-resolution.log),
양쪽 의도 존재 확인은 [merge-intents.log](merge-main-round1/merge-intents.log)에 있다.
커밋은 하지 않았고 병합은 감독이 커밋할 수 있도록 스테이지했다.

병합 후 재실행(모두 이 작업 트리 루트에서):

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_task_test_coverage.py -v` | 15개 통과, [coverage-tests.log](merge-main-round1/coverage-tests.log) |
| `python3 -m unittest discover -s tools/tests -p test_evidence_paths.py -v` | 5개 통과(main 회귀), [evidence-paths.log](merge-main-round1/evidence-paths.log) |
| `python3 -m unittest discover -s tools/tests -p test_audit5_confirm_agent_made_decisions.py -v` | 22개 통과, [decision-regressions.log](merge-main-round1/decision-regressions.log) |
| `python3 -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 20개 통과, [product-purpose-tests.log](merge-main-round1/product-purpose-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47·존재 72/72(G12c 포함), [spec-check.log](merge-main-round1/spec-check.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,702개·실패 0·기존 skip 6, [python-tests.log](merge-main-round1/python-tests.log) |
| `cargo test --all --locked --offline` | 532 통과·1 ignored, [cargo-tests.log](merge-main-round1/cargo-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 통과, [ontology-tests.log](merge-main-round1/ontology-tests.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` | 종료 코드 0, [daemon-tests.log](merge-main-round1/daemon-tests.log); 기존 모의 GAP은 제품 완료 증거 아님 |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/check_missing_task_suites.py` | 필수 ID 27과제 등록 부재 전부 종료 코드 1 거부, [missing-suites.log](merge-main-round1/missing-suites.log) |
| `python3 -I tools/validation_check.py --selftest` | 변이 40개 모두 의도한 이유로 검출, [validation-selftest.log](merge-main-round1/validation-selftest.log) |
| `python3 -I tools/ci/check_bootstrap.py` | 종료 코드 0·기존 advisory 6개, [bootstrap-default.log](merge-main-round1/bootstrap-default.log) |
| `python3 -I tools/ci/check_bootstrap.py --strict-paths` | 종료 코드 1·기존 경로 finding 6개(병합 전과 동일), [bootstrap-check.log](merge-main-round1/bootstrap-check.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 종료 코드 0, [product-purpose.log](merge-main-round1/product-purpose.log) |
| `python3 -I tools/release_readiness/check.py --registry docs/blueprint/proposals/설계검토_결과/tasks.json --evidence docs/release-readiness/evidence/ --json` | 예상 종료 코드 1: 목적 행 19·기능 64 모두 open, [release-readiness.log](merge-main-round1/release-readiness.log) |

Python 전체 실행 수는 병합 전 1,697개에서 main의 증거 경로 회귀 5개가 더해져
1,702개다. skip 6개는 병합 전과 같은 환경 의존 skip이다. §7 완료 기준 칸은
64과제 전부 tasks.json의 done_criteria와 동기화됐고, 필수 시험 ID 칸도 일치한다.
이 로그들은 병합 정합성 증거이며 실제 데이터 확보·제품 시험 수행·출시 완료를
주장하지 않는다. 커밋·푸시·GitHub 호출·비밀값·프로덕션 접근은 없었다.

## Fix round 2: 픽스처 assertion이 빈 필수 ID 시험을 통과시키던 결함 수정

리뷰 지적: `RequiredResult.startTest()`가 `setUp()` 이전부터 assertion을 세고
`addSuccess()`가 시험 전체 수명주기의 assertion을 인정해서, 공유 픽스처의
assertion 하나가 `pass` 본문인 필수 ID 시험을 통과시켰다. 22380d2에서 재현 확인
(단일 필수 ID, `setUp`의 `self.assertTrue(True)`, 본문 `pass` → 종료 코드 0).
수정은 등록된 시험 메서드 실행 중에만 assertion을 집계한다: 메서드 래퍼가
집계 플래그를 켜고 끝나면 끄며, `setUp`·`tearDown`·`addCleanup` 콜백의
assertion은 집계하지 않는다. `tools/task_tests/README.md`와 감리 문서에 이
조건을 명시했다.

새 회귀 시험 3개(`tools/tests/test_task_test_coverage.py`):

- `test_fixture_assertions_cannot_pass_empty_required_methods`: setUp만·
  tearDown만·둘 다·cleanup만 assertion이 있고 두 본문이 `pass`이면 종료 코드 1
  (실패 메시지 확인). 리뷰의 단일 ID 재현도 포함한다.
- `test_fixture_assertions_cannot_mask_one_empty_method_of_two`: 실제 assertion
  메서드 하나와 빈 메서드 하나가 섞이고 setUp이 assertion을 해도 종료 코드 1.
- `test_real_method_assertions_pass_alongside_fixture_assertions`: 픽스처
  assertion과 실제 메서드 assertion 병존, 도우미 메서드·subTest assertion은
  종료 코드 0(양성 대조).

증명 스크립트 2개: `repro_fixture_assertions.py`는 주어진 트리의 실행기로 빈
메서드 거부 6건과 양성 2건의 종료 코드를 검사한다.
`check_regressions_detect_prefix.py`는 수정 전 실행기(22380d2)를 임시 트리에
놓고 새 회귀 3개를 실행해, 거부 회귀 2개는 실패하고 양성 대조는 통과함을
검사한다(회귀가 실제 결함을 잡음을 증명).

재실행(모두 이 작업 트리 루트에서):

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_task_test_coverage.py -v` | 18개 통과, [coverage-tests.log](fix-round2/coverage-tests.log) |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round2/repro_fixture_assertions.py "$PWD"` | 거부 6건·양성 2건 모두 의도한 종료 코드, [repro-fixture-assertions.log](fix-round2/repro-fixture-assertions.log) |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round2/check_regressions_detect_prefix.py "$PWD"` | 수정 전 실행기에서 거부 회귀 2개 실패·양성 통과, [regressions-vs-prefix.log](fix-round2/regressions-vs-prefix.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,705개·실패 0·기존 skip 6, [python-tests.log](fix-round2/python-tests.log) |
| `cargo test --all --locked --offline` | 532 통과·1 ignored, [cargo-tests.log](fix-round2/cargo-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 통과, [ontology-tests.log](fix-round2/ontology-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47·존재 72/72(G12c 포함), [spec-check.log](fix-round2/spec-check.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` | 종료 코드 0, [daemon-tests.log](fix-round2/daemon-tests.log); 기존 모의 GAP은 제품 완료 증거 아님 |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/check_missing_task_suites.py` | 필수 ID 27과제 등록 부재 전부 종료 코드 1 거부, 35과제 빈 목록 명시, [missing-suites.log](fix-round2/missing-suites.log) |
| `python3 -I tools/validation_check.py --selftest` | 변이 40개 모두 의도한 이유로 검출, [validation-selftest.log](fix-round2/validation-selftest.log) |

Python 전체 실행 수는 round 1의 1,702개에 새 회귀 3개가 더해져 1,705개다.
skip 6개는 같은 환경 의존 skip이다. Rust 코드는 변경하지 않았고 두 Cargo 실행은
round 1과 같은 결과다. tasks.json·완료 기준 표는 변경하지 않았다. 이 수정은
검사 장치의 결함 수정이며 제품 시험 구현·실제 데이터 확보·출시 완료를 주장하지
않는다. 커밋·푸시·GitHub 호출·비밀값·프로덕션 접근은 없었다.

## Fix round 3: 별칭 메서드가 필수 ID 재사용 검사를 우회하던 결함 수정

리뷰 지적: 실행기가 대상 문자열만 비교해서, 서로 다른 두 대상이 별칭
(`test_second = test_first`)으로 같은 메서드를 가리켜도 통과했다. 3b109a4에서
재현 확인(별칭 4종 모두 `required=2, ran=2, coverage=PASS`, 종료 코드 0):
[repro-before-fix.log](fix-round3/repro-before-fix.log). 수정은 스위트 구성 전에
각 대상의 해석된 함수를 동일성으로 비교해 같은 구현의 재사용을 거부한다
(`tools/task_test_coverage.py`). 클래스 안 별칭·생성 후 대입·다른 클래스로의
별칭·상속이 모두 거부되고, 이름이 같아도 구현이 다르면 통과한다.
`tools/task_tests/README.md`와 감리 문서에 이 조건을 명시했다.

새 회귀 시험 2개(`tools/tests/test_task_test_coverage.py`):

- `test_method_aliases_cannot_share_one_implementation`: 별칭 4종(리뷰의
  클래스 안 별칭 재현 포함)이 종료 코드 1이고 `reuses the test implementation`
  메시지를 내며, `run_task`는 ValueError를 일으킨다.
- `test_distinct_implementations_with_same_method_name_pass`: 두 클래스의 같은
  이름 메서드가 서로 다른 구현이면 종료 코드 0(양성 대조, 이름 기반 과잉 거부 방지).

증명 스크립트 2개: `repro_method_alias.py`는 주어진 트리의 실행기로 별칭 4종
거부와 양성 2건의 종료 코드를 검사한다
([repro-after-fix.log](fix-round3/repro-after-fix.log)).
`check_regressions_detect_prefix.py`는 수정 전 실행기(3b109a4)를 임시 트리에
놓고 새 회귀 2개를 실행해, 거부 회귀는 실패하고 양성 대조는 통과함을 검사한다
([regressions-vs-prefix.log](fix-round3/regressions-vs-prefix.log)).

재실행(모두 이 작업 트리 루트에서):

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_task_test_coverage.py -v` | 20개 통과, [coverage-tests.log](fix-round3/coverage-tests.log) |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round3/repro_method_alias.py "$PWD"` | 거부 4건·양성 2건 모두 의도한 종료 코드, [repro-after-fix.log](fix-round3/repro-after-fix.log) |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round3/check_regressions_detect_prefix.py "$PWD"` | 수정 전 실행기에서 거부 회귀 실패·양성 통과, [regressions-vs-prefix.log](fix-round3/regressions-vs-prefix.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,707개·실패 0·기존 skip 6, [python-tests.log](fix-round3/python-tests.log) |
| `cargo test --all --locked --offline` | 532 통과·1 ignored, [cargo-tests.log](fix-round3/cargo-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 통과, [ontology-tests.log](fix-round3/ontology-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47·존재 72/72(G12c 포함), [spec-check.log](fix-round3/spec-check.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` | 종료 코드 0, [daemon-tests.log](fix-round3/daemon-tests.log); 기존 모의 GAP은 제품 완료 증거 아님 |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/check_missing_task_suites.py` | 필수 ID 27과제 등록 부재 전부 종료 코드 1 거부, 35과제 빈 목록 명시, [missing-suites.log](fix-round3/missing-suites.log) |
| `python3 -I tools/validation_check.py --selftest` | 변이 40개 모두 의도한 이유로 검출, [validation-selftest.log](fix-round3/validation-selftest.log) |

Python 전체 실행 수는 round 2의 1,705개에 새 회귀 2개가 더해져 1,707개다.
skip 6개는 같은 환경 의존 skip이다. Rust 코드는 변경하지 않았고 두 Cargo 실행은
round 2와 같은 결과다. tasks.json·완료 기준 표는 변경하지 않았다. 이 수정은
검사 장치의 결함 수정이며 제품 시험 구현·실제 데이터 확보·출시 완료를 주장하지
않는다. 커밋·푸시·GitHub 호출·비밀값·프로덕션 접근은 없었다.

## Fix round 4: 공유 Cargo 타깃의 삭제된 작업 트리 바이너리 수리 (소스 무변경)

감독 실행에서 `onjeon-api-types` 시험 10개가 실패했고, 오류는 이 작업 트리가
아닌 `/workspace/onjeon-run/wt/audit6-stop-daemon-investment/…` 경로의
`gen.py` 부재(NotFound)와 unittest 발견 ImportError를 가리켰다. 진단
([stale-target-diagnosis.log](fix-round4/stale-target-diagnosis.log)):

- `audit6-stop-daemon-investment` 작업 트리는 이미 삭제됐다(`wt/` 목록에 없음).
- 공유 타깃(`CARGO_TARGET_DIR=/workspace/onjeon-run/shared-target`)의 시험
  바이너리 `onjeon_api_types-7c4a02dd950953e7`에 그 삭제된 작업 트리의 절대
  경로가 컴파일 시점에 박혀 있다(`strings`로 확인). 이 시험들은 컴파일 시점
  경로에서 저장소 루트를 찾기 때문에 삭제된 경로에서는 파일을 열 수 없다.
- cargo는 지문이 신선하다고 판단해 재컴파일 없이 바이너리를 재사용했다
  (`Finished in 0.04s`). 이 작업 트리에서도 같은 10개 실패를 재현했다
  ([repro-stale-binary.log](fix-round4/repro-stale-binary.log), 종료 코드 101).
- 이 작업 트리의 Rust 소스(`packages/`·`services/`)는 HEAD 대비 무변경이다.
  실패는 환경 결함이며 코드 결함이 아니다.
- 실행 중인 cargo/rustc 프로세스가 없어 공유 타깃을 수리할 수 있었다.

수리: 워크스페이스 8개 패키지 전부 `cargo clean -p`
(onjeon-rules-engine·onjeon-contracts·onjeon-api-types·onjeon-ontology·
onjeon-twin-runtime·onjeon-ai-gateway·onjeon-collect·onjeon-criteria,
합계 1,422 파일·약 1,622MiB, [cargo-clean.log](fix-round4/cargo-clean.log))
후 이 작업 트리에서 전체 재빌드·실행했다. 재빌드된 바이너리에는 이 작업 트리
경로가 박히며 `onjeon-api-types` 17개 시험이 통과한다(재실행 확인).

재실행(모두 이 작업 트리 루트에서):

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_task_test_coverage.py -v` | 20개 통과, [coverage-tests.log](fix-round4/coverage-tests.log) |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round3/repro_method_alias.py "$PWD"` | 거부 4건·양성 2건 모두 의도한 종료 코드, [repro-method-alias.log](fix-round4/repro-method-alias.log) |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/fix-round3/check_regressions_detect_prefix.py "$PWD"` | 수정 전 실행기에서 거부 회귀 실패·양성 통과, [regressions-vs-prefix.log](fix-round4/regressions-vs-prefix.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,707개·실패 0·기존 skip 6, [python-tests.log](fix-round4/python-tests.log) |
| `cargo test --all --locked --offline --no-fail-fast` | 532 통과·1 ignored·종료 코드 0, [cargo-tests.log](fix-round4/cargo-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4 통과, [ontology-tests.log](fix-round4/ontology-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47·존재 72/72(G12c 포함), [spec-check.log](fix-round4/spec-check.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` | 종료 코드 0, [daemon-tests.log](fix-round4/daemon-tests.log); 기존 모의 GAP은 제품 완료 증거 아님 |
| `python3 -I tools/evidence/audit6-prose-test-coverage-guard/check_missing_task_suites.py` | 필수 ID 27과제 등록 부재 전부 종료 코드 1 거부, 35과제 빈 목록 명시·round 3 로그와 바이트 단위 동일, [missing-suites.log](fix-round4/missing-suites.log) |
| `python3 -I tools/validation_check.py --selftest` | 변이 40개 모두 의도한 이유로 검출, [validation-selftest.log](fix-round4/validation-selftest.log) |

소스·tasks.json·완료 기준 표·문서 기준은 변경하지 않았다. round 3의 별칭 차단
수정은 그대로이며 그 회귀·증명 스크립트도 같은 결과로 통과한다. 이 라운드는
검증 장치의 환경 수리이며 제품 시험 구현·실제 데이터 확보·출시 완료를 주장하지
않는다. 커밋·푸시·GitHub 호출·비밀값·프로덕션 접근은 없었다.
