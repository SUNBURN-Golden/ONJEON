# Audit 2 — spec_check.py가 코어가 읽지 않는 `when` 문장으로 전이를 판정한다는 지적

기록일: 2026-10-27. 노드: `audit2-spec-check-reads-prose-when`. 대상: [spec_check.py](../proposals/설계검토_결과/검증/spec_check.py)의 G5b·G5c·G6b·G22·G33·G35·G42·G44와 [daemon_rules.json](../proposals/설계검토_결과/daemon_rules.json)의 전이 행.
검증 기준 커밋: `685dab5`(이 변경은 그 위의 미커밋 작업 트리).

## 발견

지적: G5b/G5c/G6b/G22/G33/G35/G44는 전이 행의 `when` 문장에서 단어를 찾는다. 데몬 코어는 `when`을 읽지 않는다(`_cond_note`, `core/rules.py`가 뷰에서 뺀다). 그래서 G22는 코어가 탈 수 없는 행에서도 통과한다. G35/G42는 `to == leased`인 행만 보아서 임대를 발급하는 다른 행을 빠뜨린다.

기준 커밋에서 다시 확인한 결과는 다음과 같다.

- 일곱 검사가 모두 `when` 문자열을 검색했다(G5b `"decision_gates.start" in when`, G5c `"decision_gates.merge" in when`, G6b `"post_merge_states" in when`, G22 `"docs_only" in when`, G33 `"current" in when`, G35 `"lease_guards" in when` 또는 guard, G44 `"preserve_succeeded"`/`"recovery_decision" in when`). G42도 `issue_lease`를 `when` 문장에서 찾았다.
- 지금 규칙 파일의 merged→done 행에는 cond `event.docs_only == true`가 있다(audit2-daemon-docs-pr-never-done). 다만 G22는 그 cond를 보지 않았다. [before_after.log](../../../tools/evidence/audit2-spec-check-reads-prose-when/before_after.log)에서 이 cond를 지우면 옛 G22는 그대로 통과한다. 형제 행의 cond를 지워도 통과한다. 이 경우 cond 없는 형제 행이 언제나 먼저 이기므로 코어는 done 행을 탈 수 없다. 반대로 모든 `when`을 비우면, 코어 동작은 같은데도 옛 G22는 실패한다.
- 검사가 문장만 보았기 때문에 숨은 규칙 두 가지는 cond에 없었다. 코어가 직접 사건을 받으면 이 두 규칙은 적용되지 않았다.
  - **선행 과제 충족**(blocked→queued, `post_merge_states`): `core/observation.py`만 코드로 확인했다. `prereqs_satisfied`를 직접 넣으면 선행이 끝나지 않아도 queued로 갔다.
  - **병합 관문**(`decision_gates.merge`): 관측 계층이 `audit_not_required`·`audit_pass`와 `decision_pending` 중 어느 사건을 낼지 고를 때만 보았다. 결정이 기록되지 않았어도 `audit_not_required`를 직접 넣으면 merge_wait(ready)로 갔다.
- 임대를 발급하는 행은 여섯 개다(`issue_lease` 부수 효과 기준). queued→leased, handoff→leased, paused_no_builder→leased, building→building(result_failed_tests), ci_failed→building, changes_requested→building이다. 옛 G35/G42는 `to == leased`인 앞의 세 행만 보았다. 지금 여섯 행 모두에 `guard: lease_guards`와 `issue_lease`가 있으므로 실제 결함은 없었다. 다만 뒤의 세 행에서 guard나 issue_lease를 빼도 옛 검사는 통과했다.

## 수정

**spec_check.py**: 전이 판정에는 이제 cond·guard·side_effects만 쓴다. `when`은 읽지 않는다. 머리말의 계약도 이에 맞게 고쳤다. `run(repo, T=None, D=None)`은 시험에서 바꾼 규칙을 받을 수 있다.

| 검사 | 이제 보는 것 |
|---|---|
| G5b | blocked→queued의 모든 행에 cond `task.decision_gates.start subset_of task_state.decisions_recorded`가 있다. cond에 병합 관문이나 `prereq_decisions`는 없다 |
| G5c | review_approved·audit_pending→merge_wait 행과 merge_wait 사유 갱신 행(리뷰어·감리 담당 부재로 기다리는 행은 뺀다)마다 cond `task.decision_gates.merge`가 `subset_of` 또는 `not_subset_of`로 하나 있다. 두 방향이 모두 있어야 한다 |
| G6b | blocked→queued 행에 cond `prereq_tasks_in(post_merge_states) == true`가 있다. 어떤 술어도 `merged`와의 같음을 보지 않는다 |
| G22 | merged→done 행에 cond `event.docs_only == true`가 있다. 같은 사건의 다른 행(merged·`*`)은 모두 `!= true`다. `events_in.payloads`의 그 사건이 `docs_only`를 싣는다 |
| G33 | fence·late·stale_lease 사건으로 상태를 바꾸는 행의 cond가 사건 쪽 `lease_id`·`lease_generation`을 `lease_record`와 `==`로 비교한다 |
| G35 | 임대를 발급하는 행 전부(`issue_lease` 부수 효과, to leased, 사건 lease_granted)에 `guard: lease_guards`나 cond `lease_guards all_pass true`가 있다. 코어는 둘 중 어느 쪽이 있어도 가드를 돌린다(`transition_engine.apply_event`) |
| G42 | 같은 행들이 `side_effects`에 `issue_lease`를 갖는다. 그 사유는 `concurrency.lease_issue.reasons`와 일대일이다(코어가 `(from, reason)`으로 행을 찾는다). `issue_lease` 밖의 부수 효과는 `lease_generation`을 건드리지 않는다 |
| G44 | handoff→leased 행에 cond `handoff_record.preservation_state == remote_pushed`가 있다. 복구 결정 뒤에도 보존이 성공해야 이 값이 된다 |

G7a의 쓰이지 않던 `when` 단어 인자도 뺐다. 파일을 연 뒤 닫지 않던 `load`·`read`·tbox 읽기는 `with`로 바꿨다.

**규칙 파일**: 숨은 두 규칙을 코어가 읽는 cond로 옮겼다.

- blocked→queued(`prereqs_satisfied`)의 cond 앞에 `prereq_tasks_in(post_merge_states) == true`를 넣었다.
- review_approved→merge_wait(`audit_not_required` / `decision_pending`), audit_pending→merge_wait(`audit_pass` / `decision_pending`), merge_wait→merge_wait(`decision_recorded`)에 cond를 넣었다. 형태는 `task.decision_gates.merge subset_of` / `not_subset_of task_state.decisions_recorded`다.
- `_cond_note`와 [04 §2](../proposals/설계검토_결과/04_자동개발명세.md) 전이표 네 행을 같이 고쳤다.

**코어**: `core/observation.py`에 `prereq_tasks_in(core, d, task_id, path)`를 더했다.

- 선행 과제가 모두 등록되어 있고, 그 상태가 `Rules.outside(path)` 목록 안에 있어야 참이다.
- `post_merge_states`는 읽기 목록 밖 값(OUTSIDE_READS, G51)이다. 그래서 이 함수는 관측 계층에 둔다(정적 검사 "읽기 목록 밖 값은 관측 계층의 Rules.outside()로만").
- `engine.ctx`는 이 함수를 cond 함수 `prereq_tasks_in(...)`로 노출한다. `_prereqs`도 같은 함수로 사건을 낼지 정하므로, 선행을 기다리는 과제에는 진단이 남지 않는다.
- 병합 관문 사건은 지금처럼 관측 계층이 고른다. 행의 cond가 같은 관문을 한 번 더 확인한다.
- [spec_gaps.py](../../../tools/daemon/spec_gaps.py) G51의 문구와 [데몬 README](../../../tools/daemon/README.md)도 맞게 고쳤다. G51의 나머지(PR 이후 다른 전이의 cond, 읽기 목록 밖 값)는 열린 채로 둔다.

## 회귀 증거

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -I tools/evidence/audit2-spec-check-reads-prose-when/mutations.py <기준 spec_check.py> <새 spec_check.py>` | 같은 규칙 변형 12개를 넣었다. 옛 검사는 cond·guard·issue_lease를 지운 10개를 모두 통과시키고, `when`만 비운 경우에 G22를 실패시킨다. 새 검사는 정확히 그 반대로 판정한다 | [before_after.log](../../../tools/evidence/audit2-spec-check-reads-prose-when/before_after.log) |
| `python3 -m unittest tools/tests/test_spec_check_cond.py -v` | 21개 통과. 묶음 그대로 통과, `when`을 모두 비워도 대상 검사 8개 통과, cond만 지우면 실패, G35/G42는 building으로 가는 세 행도 본다, 사유 중복·누락, `issue_lease` 밖의 세대 변경 | [spec-check.log](../../../tools/evidence/audit2-spec-check-reads-prose-when/spec-check.log) |
| `python3 -I …/검증/spec_check.py` | 기계 44/44·존재 72/72, 종료 0 | 같은 로그 |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 243개 통과. 새 `PrereqAndMergeGateCond`(9개): 선행이 안 끝났거나 등록되지 않은 과제는 직접 사건으로도 blocked, `post_merge_states` 각 상태에서 열림, 병합 관문 미기록이면 ready 사건 거부·decision_pending 적용, 기록되면 반대, 사유 갱신도 관문을 본다. cond를 지우면 다시 뚫린다 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario all --require-all` | 검사 704건·실패 0건·명세 공백 표시 0건, 종료 0(시나리오 결과는 같다) | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` | 59개 통과 | [runner-verify-unittest.log](../../../tools/evidence/audit2-spec-check-reads-prose-when/runner-verify-unittest.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1074개 통과, skip 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit2-spec-check-reads-prose-when/python-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`·`check_product_purpose.py`·`blueprint_status.py`·`git diff --check` | 모두 종료 0 | [consistency-checks.log](../../../tools/evidence/audit2-spec-check-reads-prose-when/consistency-checks.log) |

## 증명하지 않는 것

- spec_check은 여전히 명세의 구조만 본다. 코어가 cond를 실제로 그렇게 평가하는지는 dry_run과 `test_daemon_dry_run.py`가 확인한다. 실제 실행기는 T-OP-09다.
- G5c가 보는 행 집합은 "review_approved·audit_pending에서 merge_wait로 가는 행과 merge_wait 사유 갱신 행 중 부재 대기가 아닌 것"이다. 사유 이름(`merge_wait_reason`)은 아직 규칙 파일에 필드가 없다(G51·G55). 그래서 어느 사건이 ready인지는 사건 이름으로만 가른다.
- merge_wait→merged(`pr_merged_observed`)의 유효 병합 판정은 아직 코드에 있다(`observation.py`, G51). 이 노드의 범위 밖이다.
- [검증/실행로그_spec_check.txt](../proposals/설계검토_결과/검증/실행로그_spec_check.txt)는 설계 묶음 제출 때의 기록이라 다시 쓰지 않았다. 검사 이름이 바뀐 지금의 실행 결과는 spec-check.log에 있다.
