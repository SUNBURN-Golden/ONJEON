# 데몬 모의 작업 도구 (T-OP-00, dry_run)

`daemon_rules.json`을 데이터로 읽어 05 §5의 M1~M44를 공용 전이·검증 코어(`core/`)로 실행하고, 시나리오마다 기대 전이와 실제 전이를 나란히 보여 준다. 개발 도구다. 출시 완성품의 일부가 아니고(09 §5), 완료가 가동 승인이 아니다.

```sh
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json \
  --tasks tools/daemon/mock_tasks.json --scenario all [--report <경로>.json] [--quiet] [--require-all]
python3 -m unittest tools/tests/test_daemon_dry_run.py
python3 -I tools/daemon/static_checks.py
python3 -m unittest tools/tests/test_daemon_static_checks.py -v
```

`--scenario`는 `all`, M 번호(`M41`), 또는 필수 시험 ID(`restart-ttl-expired-no-resend`)를 받는다. 하나라도 기대와 다르거나 시나리오가 예외로 멈추면 종료 코드는 1이다. 실행 기록과 보고서는 `reports/`에 있다. `reports/dry_run.log`가 보고서이고, 통과한 검사도 기대·실제 열(전이 열 포함)을 줄이지 않고 다 적는다. JSON이 필요하면 `--report`로 만든다. `--require-all`을 주면 실행한 시험 ID가 T-OP-00 필수 시험 ID 33개(`mock_tasks.json` `t_op_00_required_test_ids`)와 정확히 같아야 종료 코드 0이다. 빠진 ID(실행하지 않은 시험 ID), 목록에 없는 ID(필수 목록에 없는 시험 ID), 두 번 이상 나온 ID(두 시나리오가 같은 ID를 쓰거나 목록에 두 번 적힌 것)를 요약에 적고, 하나라도 있으면 1이다(`dry_run.coverage`, audit2-daemon-coverage-reverse). STATIC과 시험 ID가 `-`인 시나리오는 세지 않는다.

검사가 0개인 시나리오는 실패한다(`--require-all` 없이도 적용). 설계 검사 `spec_check.py`의 G12b는 정본 `tasks.json`의 T-OP-00 필수 ID와 두 소스의 등록 목록·함수 정의·모의 목록을 대조하며 누락·미등록·중복·읽기 오류를 거부한다. 함수 존재는 실행 성공 증명이 아니므로 CI `design-specs`에서도 `--scenario all --require-all`을 실행한다. `Coverage`는 정본 33개와 실제 실행·unittest 연결을 검증하고, `CoverageBothWays`·`test_daemon_required_test_coverage.py`는 각 ID 삭제·함수 삭제·빈 함수 변이를 검사한다. [Audit 3 증거](../evidence/audit3-daemon-required-test-coverage/README.md).

설계 묶음의 `검증/실행로그_dry_run.txt`는 현재 전체 실행의 `--quiet` 출력이며 전체 기대·실제 값은 `reports/dry_run.log`에 있다. `Coverage.test_dry_run_reports_all_required_ids_run`이 이 요약 로그를 현재 실행 출력과 대조한다. STATIC의 검사 수는 정적 검사 13개와 설명 키 변조·삭제 비교 2개를 합친 15개다.

## 구성

| 경로 | 내용 |
|---|---|
| `core/` | 공용 코어. 표준 라이브러리만 쓰고, 바깥 세계는 `core/ports.py`의 어댑터 인터페이스로만 만난다. 모의 분기 문자열이 없다(정적 검사). 실제 실행기(T-OP-09)는 어댑터만 바꿔 같은 코어를 부른다 |
| `core/rules.py` | `core_contract.reads`로 만든 규칙 뷰. 설명 키(`when` 문장·`note`·`_*`)는 버린다. 읽기 목록 밖의 값은 `OUTSIDE_READS` 네 개뿐이고 모두 명세 공백 G51로 보고한다 |
| `core/transition_engine.py` | `transitions[]`의 `cond`·`guard`·`side_effects`·`return_code`·`on_cond_fail`, `noop_rules`, 가드 `on_fail` |
| `core/gate_evaluator.py` | 구조화 술어 평가, `result_scope_valid`의 변경 경로 정규화·허용/금지 범위 검사, PR 본문 필드의 `has_fields` 검사 |
| `core/effects.py` | 부수 효과 id별 처리. 어떤 id를 어떤 순서·인자로 실행할지는 데이터다 |
| `core/lease.py` | `issue_lease`(세대를 바꾸는 유일한 곳), 임대 잠금, `lease_guards`, outbox 발송·재발송(sent 표시는 compare-and-set) |
| `core/fencing.py`, `core/envelope_validator.py` | `accept_envelope`, `fenced_write`, `validate_instruction`, 지시 봉투 작성, 수신 측 검증 |
| `core/handoff.py`, `core/recovery.py` | 인계 단계와 실패 처리, 재시작 복구, 정상 만료, 상태 손상 |
| `core/secret_scan.py` | 비밀값 패턴의 세 검사 지점. 일치한 문자열은 기록하지 않는다 |
| `core/observation.py` | CI·PR·리뷰·감리·병합 관측·결정 기록·선행 과제. 아래 "관측 계층" 참고 |
| `mock_adapters.py`, `mock_env.py` | 가상 시계, 메모리 저장소, 모의 빌더(수신 측 검증, `real_data_allowed`에 따른 단계 실행), 모의 Git(트리 OID 모델), 모의 리뷰어. 네트워크·CLI·실제 저장소·모델 호출 없음 |
| `mock_tasks.json` | 시험 전용 fixture(`origin=fixture`, `fixture_only=true`). 모의 과제(T-MOCK-*)와 모의 빌더(이름·실행기·계열). 규칙의 수치(ttl_s·heartbeat_s·max_attempts 등)는 두지 않는다(G01). 과제 `limits`(max_wall_s·max_retries)는 확정되지 않은 초안 기본값을 따라 쓴 fixture 값이고 제품 값이 아니다(G47) |
| `scenarios.py`, `scenarios_flow.py`, `bench.py` | M26·M28~M30·M33~M44(임대·봉투·재시작·인계)와 M1~M25·M27·M31·M32(큐에서 병합 관측·정기 감리까지, 중단·권한) |
| `static_checks.py` | 병합 API·네트워크·CLI·벽시계·스케줄러·두 번째 해시·모델 식별자·비용 상한이 없음, 세대 대입은 `issue_lease` 안에서만 |
| `spec_gaps.py` | 명세 공백 목록과 코어가 택한 해석 |

정상 만료는 `state_integrity.normal_expiry.events_by_state`의 상태별 사건이 구조화된 `events` 목록과 현재 상태의 전이 행에 모두 있을 때 선택한다. `core_contract.reads`는 정상 만료의 `detect`·`events_by_state`·`events`를 명시하며 설명 문장(`path`·`outbox`·`next_lease`)은 코어 뷰에 넣지 않는다. [Audit 1 수정·검증 증거](../../docs/blueprint/audits/2026-10-26_daemon_recovery_structured_events.md).

`* → returned`(`unmapped_condition`) 두 행은 cond `task_state.state not_in [done, cancelled]`로 종료 상태(나가는 행이 없는 두 상태)를 뺀다. 그 상태의 표에 없는 사건(다시 전달된 `pr_merged_observed`·병합 관측 등)은 `noop_rules`가 `event_after_terminal_state`로 기록만 하므로 done 과제가 반송되어 후속 과제를 막지 않는다(`TerminalStatesIgnoreUnmapped`, M19). [Audit 2 수정·검증 증거](../../docs/blueprint/audits/2026-10-27_daemon_wildcard_from_terminal.md).

`merged → audit_queued`와 `merged → done`(`impl_counter_incremented`)은 cond `event.docs_only != true` / `== true`로 배타다. 관측 계층은 docs-only 판정(변경 경로가 모두 `docs/**` 또는 라벨 `docs-only`)을 사건의 `docs_only`로 넘길 뿐이고 목적지는 행의 cond가 고른다. 값이 없으면 구현 PR로 세어 감리를 거친다. 호출자가 목적지를 지정하는 경로(`to`)는 없앴다(`DocsOnlyLandingCond`, M23). [Audit 2 수정·검증 증거](../../docs/blueprint/audits/2026-10-27_daemon_docs_pr_never_done.md).

`handle_event`(봉투 없이 들어오는 사건의 입구)는 `core_contract.operations.handle_event`를 읽는다. `routes`의 사건은 검사 연산으로 보내고(`fence_violation`→accept_envelope, `push_requested`·`pr_update_requested`→fenced_write, `daemon_restart`→재시작 복구), `without_envelope` 허용 목록의 사건만 전이표에 닿는다. 그 밖의 이름(`result_*`·`switch_signal`·`first_heartbeat`·`heartbeat`, 코어가 스스로 내는 `envelope_invalid`·`unmapped_condition`·`state_corrupted`, 모르는 이름)은 `envelope_rejected_invalid`(R-13)로 기록만 하고 상태·임대는 그대로다. 봉투 사건은 `submit_envelope`(accept_envelope의 임대·토큰·중복·만료 검사)로만 들어온다. 목록이 사건 목록 밖의 이름을 담거나 routes와 겹치면 코어가 시작하지 않는다(`HandleEventFencing`, M17). [Audit 2 수정·검증 증거](../../docs/blueprint/audits/2026-10-27_daemon_handle_event_fencing.md).

`result_*` 사건을 `without_envelope`나 `routes`에 등록한 규칙도 시작 시 `SpecGap`으로 거부한다. 결과 보고는 `submit_envelope(task_id, "result", envelope)`를 통해서만 처리하며, 완전한 결과 봉투를 일반 사건의 payload에 넣어도 거부한다. 임대 없는 building 과제의 상태 보존·정상 봉투 수락·같은 봉투의 중복 거부와 규칙 변이를 `HandleEventFencing`에서 검사한다. [Audit 3 보강·검증 증거](../../docs/blueprint/audits/2026-10-28_daemon_handle_event_envelope_bypass.md).

결과 봉투의 범위와 PR 본문은 `accept_envelope.checks_in_order`의 `result_scope`·`pr_body_fields`가 강제한다. 기존 필수 필드·임대·중복·만료 검사 뒤, 비밀값 검사(`preserve_manifest.secret_patterns.scan[result_envelope].after_check = current_lease_rules`)를 먼저 실행한다. 그 뒤 `gate_evaluator.paths_within_scope`가 `touched_paths` 목록의 각 경로를 정규화하고 허용·금지 경로와 정본 승인 예외를 검사한다. 자료형이 잘못된 목록도 R-01로 반송하고 PR 기록을 만들지 않는다. `pr_opened` 결과에는 `pr_body` 사전이 필요하다. 필수 키는 규칙의 `pr_body_required_fields`(`task_id`, `authors`, `target_sha`, `test_log_ref`)이며 값은 공백 아닌 문자열 또는 그러한 문자열의 비어 있지 않은 목록이다. 누락·빈 값·다른 자료형은 R-09 `envelope_rejected_invalid`로 기록하고 상태·임대·inbox_seen을 유지하므로 같은 작성자가 같은 봉투 ID로 보완할 수 있다. 비밀값 패턴도 함께 있으면 R-10이 우선하여 임대를 폐기하며 봉투를 inbox_seen에 넣지 않는다. 옛 임대·만료·중복·필수 필드 오류의 기존 우선순위는 유지한다. after_check가 누락되거나 검사 ID를 유일하게 가리키지 않으면 시작을 거부한다. `building → pr_open`의 `cond`도 범위·본문 검사를 다시 평가한다. 모의 빌더와 실행기 검증용 어댑터는 이 필드 사전을 합성하며, 코어는 실제 Git 호스트의 PR 본문 조회·인증을 하지 않는다. [Audit 3 수정·검증 증거](../../docs/blueprint/audits/2026-10-28_daemon_gate_touched_paths.md).

`fenced_write`(`push_requested`·`pr_update_requested`)도 `inbox_seen`을 검사한다. 필수 식별자 → 임대 일치 → 중복 → 활성·만료 → 데몬 경유 순서이며, 키는 `accept_envelope.idempotency_key_fields`의 기존 signal 종류를 쓴다. 검사 통과 뒤 처리 키·`execute_write` intent·전이 기록을 같은 트랜잭션으로 커밋하고 원격 호출은 그 뒤 트랜잭션 밖에서 실행한다. 발송 시 `store.dispatch_guard()`로 저장소 변경과 같은 배타 잠금을 잡고, 이미 소비한 중복 검사만 빼고 다시 검사한 뒤 원격 호출이 반환할 때까지 잠금을 유지한다. 그 전에 임대가 교체·종료·만료되었으면 R-11로 거부하며 원격 호출은 없다. 잠금은 원격 호출 동안 다른 저장소 변경도 기다리게 하며, 원격 어댑터가 저장소를 중첩 변경할 수는 없다. `PushRemote`는 요청의 `lease_id`와 일치하는 활성 자격만 사용한다. 원격 호출이 정상 반환하면 잠금을 풀고 별도 트랜잭션으로 `execute_write` 효과 기록을 남긴다. 롤백·커밋 실패에서는 원격 쓰기가 없고 같은 요청으로 재시도할 수 있다. 커밋 후 중단·원격 오류·완료 기록 실패에서는 처리 키가 남아 같은 요청을 다시 실행하지 않는다. 원격 성공 여부 대조·미발송 intent의 자동 복구나 exactly-once 전달은 구현하지 않았다(`FencedWriteDedup`). [Audit 3 수정·검증 증거](../../docs/blueprint/audits/2026-10-28_daemon_fenced_write_dedupe.md).

outbox 발송(`resend_outbox`)은 검사 트랜잭션 → 발송(트랜잭션 밖) → 표시 트랜잭션 순서다. 표시는 `core_contract.operations.resend_outbox.mark_sent`의 compare-and-set이다. 표시 트랜잭션에서 `checks[compare_and_set]`(`pending`)을 다시 평가해 참일 때만 `set`(status `sent`, sent_at `clock.now`)을 쓴다. 발송 중 만료·취소 뒤 재시작·손상으로 void된 행이나 다른 발송이 먼저 sent로 표시한 행은 그대로 두고, 진단 `outbox_not_pending_at_mark`와 결과 `not_marked`만 남긴다. 이미 나간 봉투의 임대는 끝났으므로 그 봉투로 온 보고는 R-11로 막힌다. 모의 발송기의 `during_send`(한 번만 실행되는 훅)가 발송과 표시 사이의 경쟁을 만든다. `mark_sent`가 없는 검사 id를 가리키거나, `set`에 status가 없거나, `on_conflict.writes`가 비어 있지 않으면 코어가 시작하지 않는다(`SendMarkCompareAndSet`, M41). [Audit 2 수정·검증 증거](../../docs/blueprint/audits/2026-10-27_daemon_envelope_sent_after_void.md).

시험 실패 재임대(`building → building`, `result_failed_tests`)는 결과를 센 뒤 3회 미만이고 가드가 거짓이면 행의 `on_cond_fail`로 `unmapped_condition → returned(R-03)`를 즉시 실행한다. 현재 임대를 revoked로 끝내고 프로세스·토큰·쓰기 자격을 회수한다. 결과 봉투·사용량·실패 카운터는 한 번 커밋되며 새 임대·지시는 없다. 재전달은 같은 세대의 duplicate이고, 복귀에는 `owner_resolved`가 필요하다. 3회째는 기존 R-06 행이 선택된다. 가드 자체의 `emit_event`(`instruction_envelope_valid` → `envelope_invalid`, R-13)는 행의 fallback보다 우선한다. [Audit 3 수정·검증 증거](../../docs/blueprint/audits/2026-10-28_daemon_failed_tests_stuck.md).

행에 `on_cond_fail`이 없고 거짓인 가드가 전부 `wait`이면 전이 엔진은 결과에 `guard_wait`를 단다. `engine._txn`은 그 사건의 트랜잭션 전체를 버린다(`core_contract.operations.issue_lease.on_guard_wait`, `transaction: rollback`). 카운터·`inbox_seen`·가드 평가가 만든 다음 세대 사용량 슬롯·결과 사용량(`usage_retry` 포함)은 남지 않는다. `keep_diagnostics`(`guard_failed`·`cond_not_met`)와 `guard_wait_rolled_back` 진단만 새 트랜잭션에 쓴다. 결과는 `accepted: false`, `reason: guard_wait`다. 실제 실행기의 파일 큐(`runner_verify/daemon_main.py` drain)는 이런 봉투를 inbox에 남겨 다음 drain에서 다시 넣는다. 계약에 rollback이나 필수 이름이 없으면 코어가 시작하지 않는다(`GuardWaitRollsBack`, M30). [Audit 2 트랜잭션 수정·검증 증거](../../docs/blueprint/audits/2026-10-27_daemon_guard_fail_partial_commit.md).

## 관측 계층(명세 공백 G51~G55)

PR 이후 전이(전이표 43~85행)는 대부분 `cond`가 없다. `blocked→queued`(prereqs_satisfied)는 선행 과제와 시작 관문을 모두 `cond`로 코어가 평가한다: `prereq_tasks_in(post_merge_states) == true`(`core/observation.py`의 같은 함수, 읽기 목록 밖 `post_merge_states`는 `Rules.outside()`로만)와 `task.decision_gates.start subset_of task_state.decisions_recorded`. 관측 계층은 선행 과제가 찼을 때만 사건을 내며, 기록되지 않은 start 결정이 있거나 start가 목록이 아니면(null·누락) 과제는 `blocked`에 남고 `cond_not_met` 진단에 그 게이트가 남는다. 사건을 직접 넣어도 같다(`StartGateEnforcement`, [audit1-start-gates-enforcement](../../docs/decisions/audit1-start-gates-enforcement.md); 선행 과제 쪽은 `PrereqAndMergeGateCond`). 병합 관문도 merge_wait로 들어가는 행(review_approved·audit_pending → merge_wait의 ready·decision_pending, merge_wait 사유 갱신)의 `cond` `task.decision_gates.merge subset_of` / `not_subset_of task_state.decisions_recorded`다. 관측 계층이 사건을 고르고 행의 cond가 같은 관문을 다시 본다(audit2-spec-check-reads-prose-when). 어떤 사건을 낼지 정하는 규칙은 `when` 문장, `audit_triggers.immediate_rules[].rule`, `record_separation.merge_observation_fields._rule` 같은 문장이거나 읽기 목록 밖에 있다. 코어가 문장을 읽지 않으므로 `core/observation.py`가 04 §2.2·§4·§5의 규칙을 코드로 적용한다. 행이 하는 일은 여전히 전이표가 정한다. 이 해석은 모두 `spec_gaps.py`의 G51~G55에 적었고, 설계 담당이 구조화 필드로 옮기면 이 모듈을 그 필드를 읽도록 바꾼다.

## 현재 결과

- 필수 시험 ID 33개 전부와 M1~M44(M10a·M10b·M18a·M18b 포함)를 실행한다. 검사 수·실패 수는 `reports/dry_run.log`의 요약을 본다.
- G29~G50: 코어가 새 필드를 읽는다(`spec_gaps.py`의 `core_reads`). G47만 일부다. 기본값이 든 `envelopes.instruction.limits`를 `core_contract.reads`에 넣는 일은 `daemon_rules.json` 변경이라 이 과제의 허용 경로 밖이다. 코어는 과제 정의의 limits를 쓴다.
- 문장에서 꺼낸 토큰은 0종이다(`Rules.token_log`).
- 새 명세 공백 G51~G57 중 G54는 범위·본문 검사와 실패 처리를 구조화 술어로 연결해 일부 해소했다. 경로 패턴의 해석은 여전히 `gate_evaluator`에 명시돼 있다. 나머지 공백은 열려 있다.

## 정적 검사 실행과 범위

`python3 -I tools/daemon/static_checks.py`는 13개 정적 검사를 실제로 실행하고 각 결과와 위반 위치를 출력한다. 기본 규칙·모의 과제 경로는 스크립트 위치를 기준으로 정하므로 다른 작업 디렉터리에서도 실행할 수 있다. `--rules <경로>`·`--tasks <경로>`로 입력을 바꾼다. 종료 코드는 모두 통과하면 0, 위반이면 1, 입력 읽기·JSON·소스 구문 등 검사 완료 오류면 2다.

네트워크·동적 코드 검사에는 `__builtins__` 접근, 금지 멤버의 리터럴 `getattr` 조회, `from os import system as s` 같은 별칭 가져오기, `os.exec*`·`os.spawn*`·`posix_spawn*` 등 프로세스 실행 함수 참조, `ctypes`·`_ctypes`·`posix`·`nt` 가져오기가 포함된다. `re.compile`·일반 데이터·포트 객체의 `getattr`는 허용한다. 루프 검사는 AST 리터럴 조건이 참인 `while True:`·`while 1:` 등을 거부하며 주석·문자열 속 루프 예시는 실행문으로 보지 않는다. 기존 스케줄러 패턴 검사도 유지한다.

패턴 검사의 자체 제외는 이 검사기의 정확한 경로에만 적용한다. 하위 디렉터리를 포함해 다른 `static_checks.py`는 검사한다. `runner_verify/`의 기존 별도 검사 경계는 유지한다. 이 검사는 Python 샌드박스가 아니며, 계산해서 만든 속성명·일반 변수 흐름·입력에 의존하는 무한 루프까지 증명하지 않는다. [Audit 3 수정·회귀 실행 증거](../evidence/audit3-daemon-static-check-bypasses/README.md)를 참조한다.

## 증거 기록(reports/)

`reports/dry_run.log`(보고서)와 `reports/unittest.log`(시험 실행)의 머리말은 `generated from parent commit <sha> + tree hash of tools/daemon sources`로 시작한다. 로그는 커밋 전에 만들므로 로그 자신이 들어갈 커밋의 SHA를 적을 수 없다. 그래서 부모 커밋(이 변경을 얹은 바로 앞 커밋)과, 그 위에 얹은 소스의 내용 해시를 적는다. PR head는 부모 커밋에 이 변경 커밋 하나를 더한 것과 정확히 같다. main을 병합하는 커밋에 들어갈 로그는 둘째 부모를 `merge input main commit <sha>` 둘째 줄로 적는다. 해시는 `tools/daemon/`(`reports/`·`runner_verify/`·`__pycache__` 제외)과 `tools/tests/test_daemon_dry_run.py`의 파일 내용으로 만들고, 같은 소스면 같은 값이 나온다. 저장소 루트에서 다시 계산한다.

```sh
{ find tools/daemon -path tools/daemon/reports -prune -o -path tools/daemon/runner_verify -prune -o -path '*/__pycache__' -prune -o -type f -print; \
  echo tools/tests/test_daemon_dry_run.py; } | LC_ALL=C sort | xargs sha256sum | sha256sum
```

`Cli.test_evidence_logs_name_the_parent_commit_and_source_hash`가 두 로그의 해시가 현재 소스와 맞는지 확인한다. 소스를 고치면 로그를 다시 만들어야 한다.

## 이 모의 검증이 증명하지 않는 것

실제 프로세스·파일 시스템(잠금·rename·fsync)·Git·원격 푸시·네트워크·CLI·모델 호출, 다중 프로세스 경쟁(스레드와 잠금으로만 시험), 실제 제공자 청구와 사용량 기록의 대조. 모의 Git의 트리 해시는 모델이다. 이것들은 T-OP-09(실제 실행기)에서 확인한다.
