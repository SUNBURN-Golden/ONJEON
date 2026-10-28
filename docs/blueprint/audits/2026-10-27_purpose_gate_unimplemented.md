# Audit 2: 제품 목적 관문(`purpose-rows-all-closed`) 미구현

기록일: 2026-10-27. 노드: `audit2-purpose-gate-unimplemented`. 결정: [audit2-purpose-gate-unimplemented](../../decisions/audit2-purpose-gate-unimplemented.md)(선택 D).
연결: [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) §6·§7, tasks.json T-OP-08.

## 발견과 현재 상태

감사 지적: P01~P19의 닫힘을 판정할 `purpose-rows-all-closed` 판정기, `tools/release_readiness/check.py`, 증거 디렉터리가 없고 spec_check G47은 문자열만 맞춘다. 09가 기계 검사 관문이 되도록 T-OP-08의 판정기를 지금 만들어야 하는가.

| 지적 | 작업 트리 대조 | 조치 |
|---|---|---|
| `tools/release_readiness/check.py`·`docs/release-readiness/evidence/`가 없음 | **맞다.** 둘 다 없다. 닫힌 행은 0/19이며 09 §7도 "완료 증거는 아직 없다"고 적는다 | 만들지 않는다. T-OP-08의 `allowed_paths`·`produces`이고, 선행 5개(T-OP-07·T-OP-00·T-OP-09·T-KN-14·T-CT-07)가 post_merge가 아니며, 과제 상태는 데몬 기록에만 있고 증거 등록부 형식도 정해지지 않았다. 지금 만들면 닫힘을 꾸미거나 항상 실패한다(결정 문서 선택 A·B 기각 사유) |
| G47이 문자열 존재만 봄 | **설계상 그렇다.** spec_check 요약이 G47을 "존재 검사"로 분류하고 보호된 설계 묶음 안에 있다 | 바꾸지 않는다(선택 C 기각). 대신 CI 정적 검사 `tools/ci/check_product_purpose.py`를 보강 |
| 09가 기계 검사되지 않음 | **일부만 맞다.** `check_product_purpose.py`(시험 14개, CI의 `tools/tests`에서 실행)가 이미 P01~P19 행·구현 과제 실재·§6 시험 ID 9개 등록을 검사했다. 하지만 세 가지 빈틈이 있었다 | 아래 규칙 3개 추가 |

보강 전 빈틈(아래 [before.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/before.log)에서 변이 11개 모두 종료 코드 0):

1. 시험 ID가 **아무 과제에나** 등록돼 있으면 통과했다. `purpose-rows-all-closed`를 T-OP-07로 옮기거나 `acquisition-reason-not-counted`를 T-OP-01로 옮겨도 통과했다.
2. 축소·후속 칸에 근거가 없거나 없는 결정을 인용해도 통과했다. 09 §6은 이 칸을 근거(결정 ID·정본)가 있을 때만 제외로 인정한다.
3. T-OP-08이 최종 관문에서 빠지거나 `--purpose … --evidence docs/release-readiness/evidence/` 판정 명령이 지워져도 통과했다. 이러면 닫힘 관문 자체가 소리 없이 사라질 수 있다.

## 추가한 규칙

| 규칙 | 검사 |
|---|---|
| PURPOSE-OWNER | §6이 정한 담당 과제 중 하나 이상이 각 시험 ID를 `required_test_ids`에 등록해야 한다. T-DT-04 `acquisition-reason-not-counted`, T-AP-04 `coverage-status-counts-acquired-only`, T-KN-08 `label-kinds-complete`, T-TW-05 `switch-diff-evidence-trace`·`multi-contract-relation-trace`, T-MB-03·T-MB-04·T-AP-07 중 하나에 `first-view-priority`·`decisive-conditions-not-hidden`·`no-composite-score`, T-OP-08 `purpose-rows-all-closed`. 담당 외 과제에 추가로 등록된 사본은 허용한다(현재 T-MB-02의 `decisive-conditions-not-hidden`) |
| PURPOSE-SCOPE | 축소·후속 칸이 `—`가 아니면 근거(`ADR-nnnn`, `DEC-*`, `D-nn`, `Onn`, `BLUEPRINT §n`)를 하나 이상 인용해야 하고, 인용한 근거가 모두 저장소에 있어야 한다. `ADR-nnnn`·`DEC-*`·`D-nn`은 `docs/decisions/`의 파일(`D-nn`은 `DEC-D-nn.md`), `Onn`은 `docs/blueprint/DECISIONS.md`의 행, `BLUEPRINT §n`은 `docs/BLUEPRINT.md`의 제목이다. 표에 축소·후속 열이 없으면 PURPOSE-ROWS로 실패한다 |
| PURPOSE-GATE | T-OP-08이 있고 `final_gate: true`이며 `required_test_ids`에 `purpose-rows-all-closed`가 있고, `tests`에 판정 명령이 정확히 있어야 한다. 명령은 `shlex.split`으로 토큰을 나눠 비교한다. 앞 세 토큰이 `python3`·`-I`·`tools/release_readiness/check.py`이고, 그 뒤에는 `--purpose docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md`, `--registry docs/blueprint/proposals/설계검토_결과/tasks.json`, `--evidence docs/release-readiness/evidence/` 세 쌍만 각각 한 번씩 와야 한다(순서는 자유). 접두·부분 문자열 일치는 인정하지 않으므로 `check.py.disabled`, `.md.bak`, `evidence/old/`, 추가 플래그, `\|\| true`·`;`·`#`·리다이렉트, 환경 변수 접두, 짝이 맞지 않는 따옴표·줄바꿈(LF/CR)은 모두 실패한다 |

§6 담당 표는 코드의 `TEST_OWNERS`에 있고 `test_owner_map_matches_section_six`가 09 §6 본문을 파싱해 일치를 확인한다. 현재 저장소의 축소·후속 칸 10개(P01·P02·P03·P06·P09·P11·P14·P17·P18·P19)는 모두 실재하는 근거를 인용한다(P18은 `BLUEPRINT §1`).

이 검사는 정적 연결 검사다. 행이 닫혔는지(구현 과제의 post_merge 상태, 완료 증거 로그)는 판정하지 않으며 출력 문구도 "0 rows proven closed"라고 적는다. 닫힘 판정은 계속 T-OP-08 `purpose-rows-all-closed`의 몫이다.

## 회귀 시험

[`tools/tests/test_product_purpose.py`](../../../tools/tests/test_product_purpose.py): 14개에서 24개로 늘었다. 기존 `test_required_id_on_any_task_passes`는 빈틈 1을 고정하던 시험이라 담당 과제로의 분산·담당 외 사본 허용 시험으로 바꿨다. 추가한 시험은 다음과 같다. 시험 ID 9개 각각을 담당 외 과제로 옮기면 PURPOSE-OWNER, 실제 tasks.json의 담당 등록, §6↔`TEST_OWNERS` 일치, T-OP-08 관문 약화 변이 6종(최종 관문 해제·키 삭제·명령 삭제·`--purpose` 누락·다른 증거 경로·다른 판정기)과 과제 삭제, 실제 T-OP-08 명령 형태와 유일한 final_gate, 근거 형식 5종의 통과와 근거 없음·없는 근거 인용 실패(줄 번호 포함), 실제 09 축소·후속 칸 10개의 근거 보유, 축소·후속 열 삭제. `--selftest`도 규칙마다 변이 하나 이상(8개, 판정기 이름 `check.py.disabled` 포함)과 정상 2개로 늘렸다.

2차 수정(설계 검토 지적): 1차의 PURPOSE-GATE는 판정기 경로를 접두로, `--purpose`·`--evidence`를 부분 문자열로만 맞춰서 실제 T-OP-08 명령을 `check.py.disabled`, `09_제품목적_대응표.md.bak`, `evidence/old/`로 바꿔도 통과했다([round1.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round1.log)에서 새 변이 5개 모두 종료 코드 0). 토큰 단위 정확 일치로 바꾸고 `--registry`도 요구한다. 추가한 시험: `test_gate_command_requires_exact_tokens`(통과 4종: 기본·옵션 순서 변경·공백·따옴표, 실패 25종: 위 세 변이와 등록부 `.bak`·`--registry` 누락·옵션 중복·추가 플래그·`|| true`·`&&`·`;`·`#`·리다이렉트·환경 변수 접두·줄바꿈(LF/CR)·`-I` 누락·`python`·`--purpose=` 형식·짝 없는 따옴표·문자열 아님, 통과·실패 모두 `check`에서도 확인하며 각 실패는 PURPOSE-GATE 하나), `test_real_gate_command_mutations_fail`(실제 tasks.json의 T-OP-08 명령을 메모리에서 7가지로 바꾸면 모두 PURPOSE-GATE).

## 직접 실행한 검증 증거

| 명령 | 결과·로그 |
|---|---|
| 감독기 1차 실행과 같은 조건(`runner/target` 없음)에서 `test_ontology_runner_io_error.py` | 오류 18개, 모두 `runner/target/debug/ontology-case-runner` 없음. 이 VM의 `CARGO_TARGET_DIR`가 공유 디렉터리를 가리켜 새 작업 트리에 실행기가 없었다. 이번 변경과 무관: [python-tests-initial.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/python-tests-initial.log) |
| `CARGO_TARGET_DIR=target cargo build --locked --offline` (온톨로지 실행기) | 종료 코드 0: [ontology-build.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/ontology-build.log) |
| [purpose_mutation.py](../../../tools/evidence/audit2-purpose-gate-unimplemented/purpose_mutation.py) + origin/main(538a8a7)의 `check_product_purpose.py` | 실제 tasks.json·09의 임시 사본에 변이 11개를 심어도 12회 모두 종료 코드 0: [before.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/before.log) |
| 같은 스크립트 + 1차 수정(9189600)의 검사기 | 처음 변이 6개는 잡지만 판정 명령 변이 5개(`check.py.disabled`·`.md.bak`·`evidence/old/`·`tasks.json.bak`·`\|\| true`)는 종료 코드 0: [round1.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round1.log) |
| 같은 스크립트 + 2차 수정한 검사기 | 변이 없는 사본은 종료 코드 0, 변이 11개는 모두 종료 코드 1이고 의도한 규칙이 행·과제·명령을 짚는다: [after.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/after.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 24개 통과: [product-purpose-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/product-purpose-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -v` | 종료 코드 0, 1,155개 실행·실패 0·건너뜀 30개. 건너뜀은 모두 이 VM의 환경 제약(boto3/botocore 미설치·구버전 25개, `ONJEON_ARCHIVE_RAW`·로컬 원본 보관소·pdftotext 필요 5개)이다: [python-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/python-tests.log) |
| `cargo test --all --offline` | 종료 코드 0, Rust 결과 합계 458개 통과·실패 0개·무시 1개: [rust-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/rust-tests.log) |
| 수치·결정 색인·어휘·검증 자료·제품 목적(본 검사·selftest)·명세 검사, `git diff --check` | `blueprint_counts.py`·`blueprint_status.py`·`vocab_check.py`·`validation_check.py`(본 검사·selftest)·`check_product_purpose.py`(본 검사·selftest)·`spec_check.py`(기계 44/44·존재 72/72)·`git diff --check` 모두 종료 코드 0: [consistency-checks.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/consistency-checks.log) |

## 3차 수정 검증 (2026-10-28)

설계 검토의 PURPOSE-SCOPE 지적을 재현했다. P18의 `BLUEPRINT §1`을 존재하지 않는 `BLUEPRINT §7.1.999`로 바꿔도 참조가 `§7.1`로 잘려 통과했다. 제목 검사에도 접두 일치가 있어 `### 8.1`만 있는 문서가 `§8`의 근거로 인정됐다. 참조의 점으로 구분된 숫자를 끝까지 읽고, 제목에서 추출한 전체 절 식별자와 정확히 비교하도록 고쳤다. 제목 번호 뒤의 마침표(`## 1.`)는 허용한다.

회귀 시험 두 개를 추가했다. 실제 09의 P18만 임시 사본에서 변이하는 시험은 PURPOSE-SCOPE 한 건과 P18·전체 참조·줄 번호를 확인한다. 별도 임시 정본 시험은 실재하는 1~4단계 절의 통과, 없는 하위 절·상위 절·비슷한 번호·제목 아닌 본문 참조의 거부를 확인한다. 실제 설계 문서는 변이하지 않았다.

| 명령 | 결과·로그 |
|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` (검사기 수정 전, 새 시험 포함) | 26개 실행, 실패 5건(임시 정본 변이 4건·실제 P18 변이 1건): [before-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round3/before-tests.log) |
| 같은 명령 (수정 후) | 26개 모두 통과: [product-purpose-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round3/product-purpose-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/docs/blueprint/proposals/온톨로지/검증/runner/target/debug/ontology-case-runner" python3 -I -m unittest discover -s tools/tests -v` | 종료 코드 0, 1,157개 실행·실패 0·건너뜀 30개(boto3/botocore 의존성 25개, 보관 원본·pdftotext 환경 5개). 작업 트리에 있는 온톨로지 실행기를 지정했다: [python-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round3/python-tests.log) |
| 제품 목적 본 검사·selftest, 결정 색인, 어휘, 검증 자료 본 검사·selftest, 명세 검사, `git diff --check` | 모두 종료 코드 0, 명세 기계 44/44·존재 72/72: [consistency-checks.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round3/consistency-checks.log) |

## 4차 수정 검증 (2026-10-28)

검토 대상 HEAD `0461281f33ddfa53ba95f7f027451dd48a94036f`의 증거 변이 스크립트는 P09의 예전 문구 전체를 찾았다. 병합 뒤에는 이 문구가 없어 네 번째 실행에서 `AssertionError`로 중단됐다. 해당 HEAD의 스크립트를 메모리에서 실행해 재현했다([before.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round4/before.log), 종료 코드 1). 기존 로그는 당시 실행 기록으로 유지하고, 현재 문서로 다시 실행한 증거는 `round4/`에 저장했다.

`purpose_mutation.py`의 범위 변이는 이제 행 ID와 해당 표의 `축소·후속` 열 제목으로 칸을 선택한다. P09·P19의 기존 문구에 의존하지 않고 선택한 칸만 바꾼다. 행 누락·중복 또는 근거 열 누락은 명시적으로 실패한다. `tools/tests/test_purpose_mutation.py`에 문구·열 위치 변경, 잘못된 표 거부, 실제 P09의 다른 칸 보존, 실제 검사기로 12회 전부 실행하는 회귀 시험 4개를 추가했다.

| 명령 | 결과·로그 |
|---|---|
| `python3 -I tools/evidence/audit2-purpose-gate-unimplemented/purpose_mutation.py tools/ci` | 12회 모두 실행. 정상 사본은 종료 코드 0, 변이 11개는 모두 종료 코드 1. P09는 PURPOSE-SCOPE의 근거 없음, P19는 없는 D-61로 실패하고 뒤의 관문 변이까지 실행됨: [after.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round4/after.log) |
| `python3 -I -m unittest discover -s tools/tests -p 'test_*purpose*.py' -v` | 기존 26개와 새 회귀 시험 4개, 총 30개 통과: [product-purpose-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round4/product-purpose-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/docs/blueprint/proposals/온톨로지/검증/runner/target/debug/ontology-case-runner" python3 -I -m unittest discover -s tools/tests -v` | 종료 코드 0, 1,173개 실행·실패 0·건너뜀 30개(boto3/botocore 의존성 25개, 보관 원본·pdftotext 환경 5개): [python-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round4/python-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --all --locked --offline` | 종료 코드 0, 458개 통과·실패 0·무시 1개: [rust-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round4/rust-tests.log) |
| 제품 목적 본 검사·selftest, 설계도 수치·결정 색인, 어휘, 검증 자료 본 검사·selftest, 명세 검사, `git diff --check` | 모두 종료 코드 0, 명세 기계 44/44·존재 72/72: [consistency-checks.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round4/consistency-checks.log) |

## 5차 수정: 시험 시간 초과 조사와 실행 상한 (2026-10-28)

감독기의 900초 시간 초과는 실패로 취급했다. 제공된 출력은 `validation_check.py --selftest`의 변이 38개 성공에서 끝나지만, 전체 실행 명령과 멈춘 시험 이름은 없다. 따라서 그 검사기가 멈췄다고 단정하지 않았다. 같은 자체 시험은 별도 실행에서 0.37초, 명세 검사는 0.30초에 통과했다. Python 전체 시험은 수정 전 1,173개가 95.548초에 통과했다([python-tests-before.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/python-tests-before.log)).

`unittest.TextTestResult`의 `startTest`·`stopTest`에 `time.monotonic()` 측정을 넣어 전체 시험을 다시 실행했다. [python-profile.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/python-profile.log)의 가장 느린 시험은 `test_daemon_dry_run.Cli.test_all_scenarios_exit_zero_and_print_expected_and_actual`(20.187초), `test_pass_rows_print_the_full_transition_columns`(17.954초), `Coverage.test_dry_run_reports_all_required_ids_run`(15.630초)였다. 전체 1,173개는 81.249초에 통과했고, 새 증거 하네스 시험은 0.495초였다. 공유 Cargo target으로도 Rust 전체 시험을 다시 실행해 통과했다([shared-target-rust.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/shared-target-rust.log)). 이 재실행에서는 900초 정지를 재현하지 못했으며 원래 시간 초과의 원인은 확정하지 않는다.

별도로 확인한 무기한 대기 경로는 `purpose_mutation.py`의 검사기 자식 실행과 이를 감싼 회귀 시험에 시간 제한이 없던 점이다. 이제 각 검사기는 기본 10초 제한(`--timeout`으로 변경 가능)을 가지며, 실행 전에 변이 이름을 즉시 출력한다. 시간 초과는 해당 이름과 제한을 출력하고 종료 코드 2로 끝난다. 정상·변이 판정 결과의 집계와 구별한다. 회귀 시험의 상위 실행에도 150초 제한을 뒀다. 이 변경은 다른 Python 시험이나 감독기 전체의 실행 시간을 제한하지 않는다.

600초 잠드는 가짜 검사기로 수정 전 무기한 대기를 재현했다. 이전 하네스는 외부 1초 제한에서 진행 출력 없이 중단됐고, 현재 하네스는 `--timeout=0.1`에서 0.137초 만에 첫 변이의 이름과 `TIMEOUT`을 출력하고 종료 코드 2를 반환했다([timeout-regression.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/timeout-regression.log)). 이 가짜 검사기 회귀 시험과 0·음수·NaN·무한대 제한값 거부 시험을 추가했다. 정상 하네스의 12회 실행과 변이 11개 거부도 계속 검사한다.

| 명령 | 결과·로그 |
|---|---|
| `python3 -I -m unittest discover -s tools/tests -p 'test_*purpose*.py' -v` | 32개 통과: [product-purpose-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/product-purpose-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/docs/blueprint/proposals/온톨로지/검증/runner/target/debug/ontology-case-runner" timeout 180s python3 -I -m unittest discover -s tools/tests -v` | 종료 코드 0, 1,175개 실행·실패 0·건너뜀 30개, 69.191초. 건너뜀은 앞선 실행과 같은 boto3/botocore 의존성 25개와 원본·pdftotext 환경 5개: [python-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/python-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target" timeout 180s cargo test --all --locked --offline` | 종료 코드 0, 458개 통과·실패 0·무시 1개: [rust-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/rust-tests.log) |
| 증거 하네스, 제품 목적 본 검사·selftest, 설계도 수치·결정 색인, 어휘, 검증 자료 본 검사·selftest, 명세 검사, `git diff --check`(각 명령 150초 제한) | 모두 종료 코드 0. 정상 사본 통과·변이 11개 거부, 명세 기계 44/44·존재 72/72: [consistency-checks.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/round5/consistency-checks.log) |

## 제품 목적과 한계

09가 "철저한 수집·관리, 지식·레이블링, 디지털 트윈, 소비자 화면"의 완료 기준을 각 담당 과제와 최종 관문에 묶어 두는지를, 작업이 더 들어오기 전에 CI에서 지키게 하는 변경이다. `tools/release_readiness/check.py`와 증거 등록부는 여전히 없다. P01~P19 중 닫힌 행은 0개이며, 이 검사를 통과했다고 어느 행이 구현되거나 닫힌 것은 아니다. 닫힘 판정은 T-OP-08이 선행을 마친 뒤 `purpose-rows-all-closed`로 한다. 다시 검토할 조건은 결정 문서의 "Revisit if"를 따른다. T-OP-08이 대기열에 오를 때, 데몬 과제 상태나 증거 등록부 형식이 저장소에 먼저 정해질 때, 운영자가 조기 닫힘 현황판을 요청할 때, 09에 행이나 시험 ID가 추가될 때다.
