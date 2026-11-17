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
