# Audit 2 — 봉투 없이 전이표에 닿던 `handle_event`

기록일: 2026-10-27. 노드: `audit2-daemon-handle-event-fencing`. 시험 ID: `late-write-fenced`(T-OP-00, 05 M17).
검증 기준 커밋: `0b78c4d7560bb29adf7c099af57b2712be4aa4ce`(이 변경은 그 위의 미커밋 작업 트리).

## 발견

[엔진](../../../tools/daemon/core/engine.py)의 `handle_event`는 봉투·요청 없이 들어오는 사건의 입구다. `daemon_restart`·`fence_violation`·`push_requested`·`pr_update_requested` 네 이름만 따로 보내고, 나머지는 이름을 보지 않고 [전이 엔진](../../../tools/daemon/core/transition_engine.py)에 넘겼다. 그래서 `accept_envelope`로만 와야 하는 사건(`result_*`·`switch_signal`·`first_heartbeat`·`heartbeat`)이 봉투 없이 들어오면 임대·토큰·중복·만료 검사(`accept_envelope.checks_in_order`)를 건너뛰었다. `building → pr_open`(`result_pr_opened`) 행은 cond가 없어서, 임대 없이 이름만으로 PR 상태로 옮겨지고 현재 임대가 `completed`로 끝났다.

[수정 전 재현](../../../tools/evidence/audit2-daemon-handle-event-fencing/before.log): 기준 커밋을 임시 디렉터리에 풀고 새 시험 파일만 바꿔 넣어 실행했다. 8개 중 7개 시험이 실패했다(하위 사례를 포함해 실패 13건·오류 7건, 종료 1). 양성 대조(`test_the_envelope_path_still_applies`)는 기준 커밋에서도 통과한다. 오류 7건은 새 데이터 키(`operations.handle_event`)가 없어서 난 것이고, 동작 실패 13건이 지적 그 자체다. 같은 로그 끝의 [재현 스크립트](../../../tools/evidence/audit2-daemon-handle-event-fencing/repro_bare_events.py) 출력은 `building`인 과제에 봉투 없이 사건을 넣은 결과다.

- `result_pr_opened`: `building → pr_open`, 임대 `completed`.
- `result_failed_tests`: `building → building` 재임대.
- `heartbeat`: 토큰 없이 임대 갱신(`last_heartbeat_at` 이동).
- 사건 목록에 없는 이름: `unmapped_condition`으로 `building → returned`, 임대 `revoked`.
- 시험에서는 `result_out_of_scope`·`result_verdict_requested`·`result_wip_preserved`·`unmapped_condition`도 반송을 일으켰다. `first_heartbeat`·`switch_signal`은 행의 cond가 봉투 필드를 읽으므로 봉투 없이는 cond가 맞지 않아 아무 기록도 남지 않았다. 페이로드에 현재 임대의 id·세대·토큰을 넣어도 마찬가지였다. 막힌 것은 우연히 cond 때문이었고, 거부 기록(R-13)도 없었다.

## 수정

- [규칙 파일](../proposals/설계검토_결과/daemon_rules.json) `core_contract.operations.handle_event`를 더했다. `core_contract.*`는 이미 읽기 목록에 있다.
  - `routes`: `daemon_restart → restart_recovery`, `fence_violation → accept_envelope`, `push_requested`·`pr_update_requested → fenced_write`. 이전 코드의 분기를 데이터로 옮겼다.
  - `without_envelope`: 봉투 없이 전이표에 닿아도 되는 사건 41개의 허용 목록이다. 선행·배정·임대 발급(가드가 막는다), 시계 사건(행의 cond가 `clock.now`를 읽는다), CI·리뷰·감리·병합·결정 관측, 담당자 조치, 인계 단계의 결과, 인계 중 비밀값 검출이 들어간다.
  - `on_reject`: noop `envelope_rejected_invalid`, `R-13`, 사유 `envelope_required`. 필수 필드가 모두 없는 봉투(`accept_envelope.on_fail.required_missing`)와 같이 기록만 하고 상태·임대는 바꾸지 않는다. `return_codes[R-13].when`에 이 경우를 적었다.
- [엔진](../../../tools/daemon/core/engine.py) `handle_event`는 위 데이터로 가른다. 목록 밖의 이름(봉투 사건, 코어가 스스로 내는 `envelope_invalid`·`unmapped_condition`·`state_corrupted`, 모르는 이름)은 [펜싱 모듈](../../../tools/daemon/core/fencing.py) `reject_without_envelope`로 간다. 봉투 사건은 `submit_envelope`로만 들어온다. 코어는 시작할 때 목록을 확인한다. 목록과 routes가 사건 목록 안에 있는지, 둘이 겹치지 않는지, routes가 아는 연산만 가리키는지 보고, 어긋나면 `SpecGap`으로 멈춘다.
- 코어 안의 호출자(인계 단계 `handoff.py`)와 모의·실제 실행기 도구(`mock_env`, `runner_verify/daemon_main.py`, `runner_verify/harness.py`)가 보내는 이름은 모두 목록이나 routes 안에 있다. 바꾼 호출자는 없다.

같은 내용을 [04 §7·§8](../proposals/설계검토_결과/04_자동개발명세.md), [05 M17·§5a 입력 사건](../proposals/설계검토_결과/05_VM실행준비.md), [07 F08 행](../proposals/설계검토_결과/07_수정대응표.md), [데몬 README](../../../tools/daemon/README.md)에 적었다. 사건 수(`events` 52개·`noop_events` 17개)와 전이 행은 바뀌지 않았다.

## 회귀 증거

[`HandleEventFencing`](../../../tools/tests/test_daemon_dry_run.py)(8개)는 다음을 확인한다.

- 구조: routes·on_reject 값이 위와 같다. 허용 목록은 중복이 없고, `events` 안에 있으며, routes와 겹치지 않는다.
- 봉투 사건 제외: 다음 사건은 허용 목록에 없다. `result_<status>`(`envelopes.result.status_values` 전부), `switch_signal`·`first_heartbeat`·`heartbeat`, cond가 `envelope.`·`signal.`·`report.`·`request.` 필드를 읽는 행의 사건(전이표에서 계산), 코어가 내는 세 사건, noop 사건.
- 코어 자신의 호출: `handoff.py`가 `handle_event`로 내는 사건이 모두 목록에 있다.
- 동작: `building` 과제에 봉투 없이 12개 이름을 넣었다. 봉투 사건 8개(`events`에 있는 `result_*` 5개, `switch_signal`, `first_heartbeat`, noop 사건 `heartbeat`), 코어 내부 사건 3개, 모르는 이름 1개다. 각각 `envelope_rejected_invalid`(R-13) 기록 하나만 남고 전이는 0건이다. `task_state`·`lease_record`·세대·outbox·inbox_seen·handoff_record도 그대로다.
- 페이로드의 임대 필드는 봉투가 아니다: 현재 임대의 id·세대·토큰을 넣은 `first_heartbeat`(leased)와 `result_pr_opened`(building)도 거부된다.
- 양성 대조: 같은 `pr_opened` 결과를 `submit_envelope`로 내면 `building → pr_open`이다. 목록에 있는 `owner_stop`은 전이표에 닿는다.
- 변이 시험: `result_pr_opened`를 목록에 넣으면 봉투 없는 사건이 다시 `building → pr_open`을 만든다. 지적이 그대로 재현된다.
- 계약 위반: 목록에 모르는 이름이 있거나, routes 사건이 목록에도 있거나, routes가 모르는 연산을 가리키면 코어가 시작하지 않는다.

dry_run 보고서의 M17(late-write-fenced)에 검사 하나를 더했다. 임대 B로 바뀐 뒤 봉투 없이 넣은 `result_pr_opened`·`switch_signal`이 R-13 noop 두 건만 남기고, 전이 0·상태·임대 B가 그대로인지 본다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.HandleEventFencing -v` | 수정 전 7개 실패(하위 사례 포함 실패 13·오류 7, 종료 1), 수정 후 8개 통과 | [before.log](../../../tools/evidence/audit2-daemon-handle-event-fencing/before.log), [focused.log](../../../tools/evidence/audit2-daemon-handle-event-fencing/focused.log) |
| `python3 -I tools/evidence/audit2-daemon-handle-event-fencing/repro_bare_events.py` | 수정 전 `pr_open`·재임대·임대 갱신·반송, 수정 후 다섯 이름 모두 R-13 noop·`building`·임대 `active` | 위 두 로그의 끝 |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 215개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario all --require-all` | 검사 667건·실패 0건·명세 공백 표시 0건 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1025개 실행·통과, skip 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit2-daemon-handle-event-fencing/python-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`(기계 44/44·존재 72/72)·`check_product_purpose.py`·`blueprint_status.py`·`git diff --check` | 모두 종료 0 | [consistency-checks.log](../../../tools/evidence/audit2-daemon-handle-event-fencing/consistency-checks.log) |

전체 Python 시험 전에 온톨로지 runner를 작업 트리 안(`CARGO_TARGET_DIR=target`)에 빌드했다. skip 6개는 로컬 비공개 원본이 필요한 기존 검사 5개와, 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 새 시험은 skip하지 않았다. Rust 파일은 바꾸지 않아 `cargo test`는 다시 돌리지 않았다. 실제 실행기 검증 도구(`tools/daemon/runner_verify`, T-OP-09)도 돌리지 않았다. 그 도구가 `handle_event`로 보내는 이름(`push_requested`·`pr_update_requested`와 `builder_available`·`owner_*`·`recovery_decision`)은 모두 routes나 허용 목록 안에 있다. 데몬 보고서 두 개는 기준 커밋과 현재 소스 해시로 다시 만들었다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

## 남은 것

- 허용 목록의 사건은 여전히 출처를 증명하지 않는다. 예를 들어 `owner_stop`이나 CI 관측을 누가 냈는지는 이 입구가 확인하지 않는다. 이 노드는 봉투로 와야 할 사건이 봉투 검사를 건너뛰는 길만 막았다. 관측·담당자 사건의 출처 인증은 실제 실행기(T-OP-09)와 운영 설정의 일이다.
- `secret_detected`는 인계 단계가 `handle_event`로 내므로 목록에 있다. 밖에서 넣으면 과제를 반송한다(닫힌 쪽으로 실패).

## 증명 범위

이 증거는 모의 어댑터를 쓰는 데몬 코어와 규칙 데이터의 사건 입구만 검증한다. 실제 프로세스·파일 큐·HTTP 입구나 실제 실행기(T-OP-09)의 동작은 증명하지 않는다. 열린 명세 공백 G51~G57의 해결이나 데몬 가동 승인도 주장하지 않는다. [09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이고 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 시험은 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.
