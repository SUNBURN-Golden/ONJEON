# Audit 3 — 결과 봉투의 변경 경로·PR 본문 관문

기록일: 2026-10-28. 노드: `audit3-daemon-gate-touched-paths`.
최초 검증 기준: `e1c5f14c0de0e428e46fcb975e412f909d9557ed` 위의 미커밋 작업 트리. 수정 1차 기준은 아래 별도 기록을 따른다.
관련: BLUEPRINT §11 개발 도구, 04 자동개발명세 R-01·R-09, T-OP-00 M8·M32.

## 확인과 수정

기준 트리에는 `observation.result_event`의 R-01 검사가 이미 있었다. 따라서 보통의 범위 밖 파일을 바꾼 결과는 이미 반송됐다. 다만 검사와 실패 처리가 구조화 조건에 연결돼 있지 않았고, `touched_paths=False`, `0`, `""`, `{}` 같은 값은 `or []`를 거쳐 변경 없음으로 통과했다. PR 본문의 `task_id, authors, target_sha, test_log_ref` 조건은 `when` 설명뿐이었으며, 본문이 없어도 `building → pr_open`으로 전이했다.

[gate_evaluator.py](../../../tools/daemon/core/gate_evaluator.py)의 `paths_within_scope`로 경로 검사 구현을 모았다. `result_scope_valid` 함수 술어를 평가 문맥에 등록하고 [규칙 파일](../proposals/설계검토_결과/daemon_rules.json)의 `accept_envelope.checks_in_order`에 `result_scope`와 `pr_body_fields`를 추가했다. 필수 필드·임대 일치·중복·활성/만료·현재 임대 규칙 검사 다음에 평가한다. `building → pr_open`의 `cond`도 두 검사를 다시 평가하고, `result_out_of_scope` 행은 범위 위반 조건을 검사한다. 자연어 `when`은 읽지 않는다.

- R-01: `touched_paths`가 목록이어야 한다. 각 경로의 정규화, 정확한 파일 또는 `<dir>/**` 허용, 금지 경로 우선, 승인된 정본 파일의 기존 예외를 유지한다. 목록·경로·허용/금지 설정의 잘못된 자료형도 닫힌 쪽으로 판정한다. 위반 시 `returned(R-01)`으로 전이하고 임대를 종료하며 PR 기록을 만들지 않는다. `failed_tests` 등 다른 결과 상태에도 적용한다.
- R-09: `pr_opened`는 `pr_body` 사전이 필요하다. `pr_body_required_fields`에 있는 필드의 값이 공백 아닌 문자열 또는 그런 문자열의 비어 있지 않은 목록이어야 한다. `has_fields` 술어가 이를 검사한다. 실패하면 R-09 `envelope_rejected_invalid`를 기록하고 상태·임대·inbox_seen을 유지한다. 같은 작성자가 같은 봉투 ID로 보완하여 제출할 수 있다.
- 모의 빌더·실행기 검증용 stand-in·harness는 정상 PR 결과에 합성 본문 필드를 넣는다. 명시적으로 잘못된 `pr_body`를 전달하면 자동으로 보완하지 않는다. 코어가 기본 본문을 만들거나 누락을 통과시키지는 않는다.

G54의 범위·본문 검사와 실패 처리는 구조화 조건으로 연결했다. G54에서 경로 패턴 해석의 데이터화까지 요구했던 부분은 `spec_gaps.py`에 일부 해소로 남겨 구분한다. 이 노드가 지적한 결과 수락·PR 전이의 검사 누락은 아래 회귀 시험으로 닫았다.

## 시험과 증거

[ResultGates](../../../tools/tests/test_daemon_dry_run.py)의 회귀 시험 15개는 범위 밖·혼합·금지·위험 경로, 목록 자료형, 허용 설정 자료형, 경로 정규화와 정확한 파일 허용, 필수 본문 필드별 누락·빈 값·자료형, 재제출·중복, 다른 결과 상태, R-01 우선, 옛 임대 R-11 우선, 필수 필드 목록 변이, 수락 검사 제거 시 전이 조건의 재검사를 확인한다. 기존 정본 승인 예외 시험과 설명 문장 제거·교체 불변성 시험도 유지했다.

새 시험 중 최초 12개를 수정 전에 실행한 [before.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/before.log)는 본문 검사·잘못된 변경 목록 거부에서 실패하고, 아직 없는 구조화 필드의 변이 시험에서 예외가 났다. 정상적인 범위 밖 경로의 기존 반송 시험은 이미 통과했다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.ResultGates -v` | 15개 통과 | [focused.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/focused.log) |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py -v` | 최초 276개 통과, 수정 1차 281개 통과로 보고서 갱신 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all` | 검사 704건 통과, 필수 시험 ID 33개 누락·목록 밖·중복 없음 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1194개 실행, 실패·오류 0, 기존 skip 6 | [python-tests.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/python-tests.log) |
| `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` | 59개 통과 | [runner-tests.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/runner-tests.log) |
| `cargo test --all` | 466개 통과, 기존 ignore 1, 실패 0 | [cargo-tests.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/cargo-tests.log) |
| 어휘·검증 자료·검증기 selftest·설계 명세·제품 목적 대응표 검사 | 모두 종료 0 | [vocabulary.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/vocabulary.log), [validation.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/validation.log), [validation-selftest.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/validation-selftest.log), [spec-check.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/spec-check.log), [product-purpose.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/product-purpose.log) |
| `python3 -I -m unittest discover -s tools/ci/tests` | 20개 중 기존 의존성 검사 실패 2개, 나머지 통과 | [ci-tests.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/ci-tests.log), [기준 커밋 대조](../../../tools/evidence/audit3-daemon-gate-touched-paths/ci-baseline.log) |

추가 CI 검사 실패는 `packages/ontology/Cargo.toml`의 `knowledge → twin` 의존 1건과 같은 패키지 시험의 엔진 import 2건이다. 읽기 전용 Git 객체로 기준 커밋의 입력을 읽어 동일 검사기를 실행했고, 현재 결과와 정확히 같은 위반 3건임을 대조했다. 이 노드에서 의존성 규칙이나 온톨로지를 바꾸지 않았다.

Python skip 6개는 비공개 원본이 필요한 기존 시험 5개와 설치된 botocore에 해당하지 않는 구버전 시험 1개다. 새 회귀 시험에는 skip이 없다. 온톨로지 시험 실행기는 이 작업 트리의 `target`에 빌드했다([ontology-build.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/ontology-build.log)). 데몬 보고서 두 개는 기준 커밋과 현재 데몬 소스·시험의 SHA-256으로 재생성했다. 검증은 로컬 실행 결과다.

## 수정 1차 — R-10 우선순위 복원

기준: `847596e8641de2546fe7bfb37e159a0d370fd900` 위의 미커밋 작업 트리. 리뷰 P1은 유효한 현재 임대의 결과에서 비밀값 패턴과 범위·본문 오류가 함께 있으면 새 R-01·R-09 검사가 `_secret_check()`보다 먼저 반환하여 R-10 즉시 중단을 우회한다는 지적이었다. 합성 패턴을 `test_log_ref`에 넣은 [수정 전 재현](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/before.log)은 회귀 시험 2개에서 조합 5건 실패를 확인했다.

`preserve_manifest.secret_patterns.scan[result_envelope].after_check = current_lease_rules`를 추가하고 `fencing.accept`가 그 검사의 성공 직후 비밀값 검사를 실행하도록 옮겼다. 구조화 필드로 순서를 지정하며 설명 문장은 읽지 않는다. 필수 필드·임대 일치·중복·활성/만료·현재 임대 규칙은 먼저 검사하고, 범위·본문 검사는 R-10 검사 뒤에 둔다. 검사 기준 ID가 없거나 중복되면 시작 시 `SpecGap`으로 거부하여 검사가 조용히 생략되지 않게 한다.

추가 시험 5개는 정상 현재 임대의 `pr_opened`·`failed_tests`에서 범위 위반·본문 누락·두 오류 동시 발생과 합성 비밀값을 조합한다. R-10 `building → returned`, 임대 `revoked`, 프로세스 종료·쓰기 자격·토큰 폐기, inbox_seen 불변, PR 기록 없음, 저장소·저널에 일치 원문 없음까지 확인한다. 옛 임대·만료·중복·필수 필드 오류는 기존 R-11·중복·R-13 처리를 유지한다. 순서 필드 변이와 누락·잘못된 ID·중복 ID의 시작 거부도 검사한다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.ResultGates -v` | 20개 통과 | [round1/focused.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/focused.log) |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py -v` | 281개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all` | 704건 통과, 필수 ID 33개 누락·목록 밖·중복 없음 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1199개 실행, 실패·오류 0, 기존 skip 6 | [round1/python-tests.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/python-tests.log) |
| `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` | 59개 통과 | [round1/runner-tests.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/runner-tests.log) |
| `cargo test --all` | 466개 통과, 기존 ignore 1, 실패 0 | [round1/cargo-tests.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/cargo-tests.log) |
| 어휘·검증 자료·검증기 selftest·설계 명세·제품 목적 대응표 검사 | 모두 종료 0 | [vocabulary.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/vocabulary.log), [validation.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/validation.log), [validation-selftest.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/validation-selftest.log), [spec-check.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/spec-check.log), [product-purpose.log](../../../tools/evidence/audit3-daemon-gate-touched-paths/round1/product-purpose.log) |

데몬 보고서의 부모 커밋·소스 해시는 이 수정 1차 기준으로 갱신했다. 최초 시험의 `focused.log` 등은 최초 증거로 남긴다. 새 회귀 시험의 skip은 없으며 Python의 기존 skip 6개와 Rust의 기존 ignore 1개는 위 최초 검증과 같다. `git diff --check`와 변경 파일의 허용 경로 대조도 통과했다.

## 증명 범위

결과 봉투가 주장하는 변경 경로·PR 본문 필드의 코어 검사를 증명한다. 실제 Git diff와 PR 본문을 Git 호스트에서 조회·인증하는 기능은 구현하지 않았으며, 검증 어댑터의 본문 필드는 합성이다. 실행기 시험 통과도 기존 PASS/UNCONFIRMED 수락 기준을 따르며 운영 환경 검증 완료를 뜻하지 않는다.

[09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 이 결과는 개발 도구·T-OP-08 축 5 운영 기록이다. P01~P19의 실제 공시 데이터·트윈·소비자 화면·첫 출시 완료 증거를 대체하지 않는다.
