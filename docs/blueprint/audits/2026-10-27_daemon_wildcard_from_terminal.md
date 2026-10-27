# Audit 2 — 종료 상태에 걸리던 `unmapped_condition` 와일드카드 행

기록일: 2026-10-27. 노드: `audit2-daemon-wildcard-from-terminal`.
검증 기준 커밋: `4672d186069745880fdbdfc3da290909187f229f`(이 변경은 그 위의 미커밋 작업 트리).

## 발견

`daemon_rules.json`의 `* → returned`(`unmapped_condition`) 두 행(G37)은 cond가 `lease_record.status`뿐이었다. `from: "*"`라서 종료 상태 `done`·`cancelled`에도 걸렸고, [전이 엔진](../../../tools/daemon/core/transition_engine.py)은 `*` 행을 모든 상태의 후보로 고른다(`try_event`·`apply_event`). 그래서 `done` 과제에 병합 관측이 다시 오면(멱등 키가 다른 재전달, `pr_merged_observed` 직접 입력, 병합된 head의 CI 결과, 모르는 관측 종류) 행이 없는 사건이 `unmapped_condition`이 되어 `done → returned`(R-03)로 옮겼다. `returned`는 `post_merge_states`가 아니므로 그 과제를 선행으로 둔 후속 과제가 `blocked`에 남았다. `cancelled` 과제도 같은 경로로 `returned`가 되어 `owner_resolved`로 다시 큐에 들어갈 수 있었다.

[수정 전 재현](../../../tools/evidence/audit2-daemon-wildcard-from-terminal/before.log): 기준 커밋을 임시 디렉터리에 풀고 새 시험 파일만 바꿔 넣어 실행했다. 5개 중 3개 시험(구조·`done`·`cancelled`)이 실패했고, 하위 사례를 포함한 실패는 10건이다. 수정 전에는 `('done', 'returned', 'unmapped_condition')`·R-03이 기록됐다. `done` 시험은 T-MOCK-BASIC의 다섯 재전달이 모두 반송된 뒤 후속 과제 검사(`'blocked' != 'queued'`)에서 멈췄다. 종료가 아닌 상태 시험과 변이 시험은 기존 동작을 확인하는 시험이라 기준 커밋에서도 통과한다.

## 수정

[규칙 파일](../proposals/설계검토_결과/daemon_rules.json)을 바꿨다. 코어 코드는 바꾸지 않았다. 행이 하는 일은 여전히 데이터가 정한다.

- `* → returned unmapped_condition` 두 행의 `cond`에 `task_state.state not_in [done, cancelled]`를 더했다. 이 두 상태는 자기 상태에서 나가는 전이 행이 없는 유일한 상태이고, 시험이 그 사실을 전이표에서 계산해 목록과 맞춰 본다.
- `noop_rules`에 `unmapped_condition` 규칙(`task_state.state in [done, cancelled]`)을 더했다. `noop_events`에는 `event_after_terminal_state`를 더했다. 종료 상태에서 표에 없는 사건은 진단만 남기고 사라지지 않는다. 계약 기록인 `noop_record`로 남는다. 상태·임대·R 코드는 바뀌지 않는다.
- `concurrency.lease_end.conditional_rows`의 `end_lease_when`·`complement_row_cond`는 두 행의 cond를 그대로 옮겨 적는다(시험이 같음을 확인).
- 종료가 아닌 상태의 동작은 그대로다. 예를 들어 `audit_queued`·`merged_invalid_approval`·`queued`·`leased`는 계속 반송된다(R-03, 활성 임대면 `end_lease`).

같은 내용을 [04 §2.2 전이표](../proposals/설계검토_결과/04_자동개발명세.md)의 `* → returned` 행과 `noop_events` 수(16→17), [07 G37 행](../proposals/설계검토_결과/07_수정대응표.md), [spec_gaps G37](../../../tools/daemon/spec_gaps.py), [데몬 README](../../../tools/daemon/README.md)에 적었다.

범위 밖으로 남긴 것: 다른 와일드카드 행인 `* → returned state_corrupted`(상태 손상 탐지)와 `* → cancelled owner_cancelled`(담당자 취소)는 이 지적의 대상이 아니다. 둘은 사람·무결성 검사가 일으키는 사건이라 재전달 관측과 성격이 다르며, 바꾸지 않았다. 종료 상태 과제에 `head_sha` 관측이 오면 관측 계층이 옛 결과 무효(R-04) 기록을 남기는 동작도 상태를 바꾸지 않으므로 그대로 두었다.

## 회귀 증거

[`TerminalStatesIgnoreUnmapped`](../../../tools/tests/test_daemon_dry_run.py)(5개)는 다음을 확인한다.

- 구조: 나가는 행이 없는 상태 = `{done, cancelled}` = 두 와일드카드 행의 `not_in` 목록 = noop 규칙의 `in` 목록이다. noop 이름이 `noop_events`에 있다. `conditional_rows`가 행의 cond와 같다.
- `done`(정기 감리 통과 경로 `audit_queued → done`과 docs-only 경로 `merged → done`): 머지 커밋 없는 재관측, 다른 머지 커밋의 재관측, `pr_merged_observed` 직접 입력, 병합 head의 CI 실패, 모르는 관측 종류 다섯 가지 모두 전이 0·반송 기록 0·`record_r_code`/`end_lease` 0이다. `event_after_terminal_state` noop이 남는다. 그 뒤 후속 과제(T-MOCK-SUCC)가 `queued`가 되고 임대된다.
- `cancelled`: `owner_stop`·`lease_granted`·`pr_merged_observed`가 noop만 남기고 임대 세대가 늘지 않는다.
- 종료가 아닌 상태(`audit_queued`)의 같은 사건은 여전히 `returned`(R-03)다.
- 변이 시험: 상태 술어와 noop 규칙을 지우면 `done → returned`(R-03)가 다시 나오고 후속 과제가 `blocked`에 남는다. 지적이 그대로 재현된다.

dry_run 보고서의 M19(post-merge-prereq)에 "선행 done 뒤 다시 전달된 병합 관측은 기록만" 검사를 더했다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.TerminalStatesIgnoreUnmapped -v` | 수정 전 3개 시험 실패·하위 사례 포함 10건(종료 1), 수정 후 5개 통과 | [before.log](../../../tools/evidence/audit2-daemon-wildcard-from-terminal/before.log), [focused.log](../../../tools/evidence/audit2-daemon-wildcard-from-terminal/focused.log) |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 201개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario all --require-all` | 검사 665건·실패 0건·명세 공백 표시 0건 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1011개 실행·통과, skip 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit2-daemon-wildcard-from-terminal/python-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`(기계 44/44·존재 72/72)·`check_product_purpose.py`·`blueprint_status.py`·`git diff --check` | 모두 종료 0 | [consistency-checks.log](../../../tools/evidence/audit2-daemon-wildcard-from-terminal/consistency-checks.log) |

전체 Python 시험 전에 온톨로지 runner를 작업 트리 안(`CARGO_TARGET_DIR=target`)에 빌드했다. skip 6개는 로컬 비공개 원본이 필요한 기존 검사 5개와, 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 새 시험은 skip하지 않았다. Rust 파일은 바꾸지 않아 `cargo test`는 다시 돌리지 않았다. 데몬 보고서 두 개는 기준 커밋과 현재 소스 해시로 다시 만들었다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

## 증명 범위

이 증거는 모의 어댑터를 쓰는 데몬 코어와 규칙 데이터의 전이 결함만 검증한다. 실제 GitHub 웹훅 재전달이나 실제 실행기(T-OP-09)의 동작은 증명하지 않는다. 열린 명세 공백 G51~G57의 해결이나 데몬 가동 승인도 주장하지 않는다. [09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이고 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 시험은 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.
