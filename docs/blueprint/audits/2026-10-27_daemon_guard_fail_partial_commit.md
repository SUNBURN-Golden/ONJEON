# Audit 2 — 가드가 거짓인 재임대 사건이 일부만 커밋되던 트랜잭션

기록일: 2026-10-27. 노드: `audit2-daemon-guard-fail-partial-commit`. 시험 ID: `lease-guards-all-paths`(T-OP-00, 05 M30).
검증 기준 커밋: `3ba1d80fd9450be6235d72337ec9d81ffa5e7873`(이 변경은 그 위의 미커밋 작업 트리).

## 발견

재임대 행(`building → building`, `result_failed_tests`)은 결과 봉투 하나를 한 트랜잭션에서 처리한다. 처리 순서는 다음과 같다.

1. `accept_envelope` 검사를 한다.
2. `inbox_seen`에 표시한다.
3. 결과의 사용량을 기록한다.
4. before_cond `increment_counter`(`consecutive_failed_tests`)를 실행한다.
5. cond의 `lease_guards all_pass`를 평가한다. 이 평가가 `usage_slot_ready`를 보면서 다음 세대 사용량 슬롯을 만든다([사용량 모듈](../../../tools/daemon/core/usage.py) `UsageView.slot`, 감사 당시 `usage.py:34-47`).

가드가 거짓이면 행은 적용되지 않는다. 그 가드의 `on_fail`은 `wait`이므로 진단만 남겨야 한다. 그런데 트랜잭션은 그대로 커밋되었다. 카운터 +1, `seen` 표시, 결과 사용량, 빈 다음 세대 슬롯이 모두 남았다. 그래서 가드가 풀린 뒤 빌더가 같은 봉투를 다시 보내도 `envelope_duplicate_delivery`가 되었다. 과제는 임대 TTL이 끝날 때까지 `building`에 머물렀다. `queued → leased`·`ci_failed`·`changes_requested`의 `lease_granted`에서도 가드가 거짓이면 빈 슬롯이 커밋되었다.

[수정 전 재현](../../../tools/evidence/audit2-daemon-guard-fail-partial-commit/before.log): 기준 커밋을 임시 디렉터리에 풀고 새 시험 파일과 M30 검사를 더한 `scenarios.py`만 넣었다. 코어와 규칙 파일은 바꾸지 않았다.

- `GuardWaitRollsBack`: 8개 시험이 모두 실패했다. 하위 사례를 포함해 실패 8건·오류 8건이고 종료 코드는 1이다. 오류 8건은 새 데이터 키(`issue_lease.on_guard_wait`)가 없어서 났다. 실패 8건이 지적 그 자체다.
- M30: 검사 199건 중 27건이 실패했다.
  - 재임대 경로에서는 여섯 가지 wait 주입(충돌·단일 작성자·동시 임대 수·잠금·슬롯·빌더) 모두에서 store가 바뀌었다.
  - 같은 봉투의 재전달로는 재임대가 나지 않았다.
  - 다른 세 발급 경로(queued·ci_failed·changes_requested)에서는 빈 슬롯이 남았다.
- [재현 스크립트](../../../tools/evidence/audit2-daemon-guard-fail-partial-commit/repro_guard_wait_partial_commit.py)의 결과(같은 로그 끝):
  - 거절 직후: `consecutive_failed_tests=1`, `seen=2`, 사용량 `[(1, …, 3), (2, None, None)]`.
  - 재전달: `envelope_duplicate_delivery`, 세대 1 그대로.

## 수정

- [규칙 파일](../proposals/설계검토_결과/daemon_rules.json)에 `core_contract.operations.issue_lease.on_guard_wait`를 더했다. `core_contract.*`는 이미 읽기 목록에 있다.
  - `transaction: rollback`: 그 사건의 트랜잭션 전체를 버린다.
  - `keep_diagnostics: [guard_failed, cond_not_met]`: 버린 트랜잭션의 진단 중 이것만 새 트랜잭션에 다시 쓴다.
  - `diagnostic: guard_wait_rolled_back`: 사건·거짓인 가드·봉투 id를 담는 진단 하나를 더한다.
  - `result: guard_wait`: 호출자에게 주는 결과의 reason이다. `accepted`·`applied`는 거짓이고 전이는 없다.
- [전이 엔진](../../../tools/daemon/core/transition_engine.py) `_guard_on_fail`은 거짓인 가드의 `on_fail`이 사건을 하나도 내지 않으면 결과에 `guard_wait`를 단다. `emit_event`(`envelope_invalid`, G48)는 전이이므로 그대로 커밋한다.
- [accept_envelope](../../../tools/daemon/core/fencing.py)는 그 표시와 봉투 id를 결과에 넘긴다.
- [엔진](../../../tools/daemon/core/engine.py) `_txn`은 표시를 보면 store 트랜잭션 안에서 예외를 던져 트랜잭션을 버린다. 그 뒤 새 트랜잭션에 `keep_diagnostics`와 `guard_wait_rolled_back`만 쓴다. 다음 것들이 모두 남지 않는다.
  - 카운터
  - `inbox_seen`
  - 다음 세대 슬롯
  - 결과 사용량. 사용량 쓰기가 실패한 경우의 `usage_retry`와 그 경고 진단도 포함한다.
- 코어가 시작할 때 [임대 모듈](../../../tools/daemon/core/lease.py) `check_guard_wait`가 계약을 확인한다. `transaction`이 rollback이 아니거나, `keep_diagnostics`가 목록이 아니거나, 진단·결과 이름이 없으면 `SpecGap`으로 멈춘다.
- 임대 잠금(G45)은 원래대로 자기 트랜잭션에서 잡고 푼다.
- 봉투가 보지 않은 것으로 남으므로, 가드가 풀린 뒤 같은 봉투의 재전달은 처음 받는 것처럼 처리된다(재임대, 세대 +1, `consecutive_failed_tests` 1). 그 뒤의 재전달은 세대가 바뀌었으므로 late(R-11)다(G40 순서).
- 실제 실행기 도구의 파일 큐([`daemon_main.op_drain`](../../../tools/daemon/runner_verify/daemon_main.py))는 결과가 `guard_wait`인 봉투를 `daemon_done`으로 옮기지 않는다. 그 봉투는 inbox에 남아 다음 drain에서 다시 들어간다.

같은 내용을 [04 임대 발급 공통 가드 행](../proposals/설계검토_결과/04_자동개발명세.md), [05 M30](../proposals/설계검토_결과/05_VM실행준비.md), [07 G48 행](../proposals/설계검토_결과/07_수정대응표.md), [데몬 README](../../../tools/daemon/README.md)에 적었다. 전이표·사건 목록·noop 목록·가드 목록은 바뀌지 않았다.

## 회귀 증거

[`GuardWaitRollsBack`](../../../tools/tests/test_daemon_dry_run.py)(8개)는 다음을 확인한다.

- 데이터: `on_guard_wait`의 값이 위와 같다.
- 재임대 행의 여섯 가지 wait 주입:
  - 저널·임대 잠금 밖의 store가 거절 전과 같다.
  - 카운터 0, `inbox_seen` 1건(첫 하트비트), 세대 1, 임대 active, 상태 building이다.
  - 사용량 행은 세대 1의 슬롯 하나뿐이고 calls는 없다.
  - 결과는 `accepted: false`, `reason: guard_wait`다.
  - 저널에는 진단 `cond_not_met`, `guard_wait_rolled_back` 둘만 남는다. 거짓인 가드 id와 봉투 id가 맞다.
- 같은 봉투의 재전달:
  - 가드가 풀리면 `retry_failed_tests` 재임대가 난다. 세대 2, 발송 2건, 카운터 1이다.
  - 사용량은 세대 1에 calls 3이 기록되고 세대 2 슬롯이 생긴다.
  - 그 뒤의 재전달은 R-11이다.
- 사용량 쓰기 실패가 겹쳐도 `usage_retry`와 그 경고가 남지 않는다.
- `queued`의 `lease_granted`도 store가 그대로이고 슬롯이 없으며, 잠금은 풀려 있다.
- 대조: `instruction_envelope_valid`의 `envelope_invalid`는 전이다. returned R-13이 커밋되고 봉투는 seen이며 rollback 진단은 없다.
- 변이: `keep_diagnostics`를 비우면 `guard_wait_rolled_back`만 남는다.
- 계약 위반 다섯 경우(commit, 목록 아님, 진단 없음, 결과 없음, 누락)에서는 코어가 시작하지 않는다.

dry_run M30(lease-guards-all-paths)에 검사 35건을 더했다. store 불변 검사가 29건, 재임대 카운터 검사가 6건이다(보고서 전체 669 → 704건).

- wait 주입이 있는 다섯 발급 경로(queued·재임대·ci_failed·changes_requested·paused 복귀)에서 저널·임대 잠금 밖 store가 불변이고 저널에는 진단만 남는다.
- 재임대 경로의 재시도는 이제 같은 봉투의 재전달이다. 주입을 풀면 그 재전달로 세대 +1이 되고 카운터는 1이다. 기존 검사 '주입을 풀면 발급되고 토큰(세대)이 +1'도 이 재전달로 확인한다. 수정 전에는 이 검사 6건이 duplicate 때문에 실패했다.
- 인계 경로(`switch`가 인계 단계를 커밋하는 경로)는 store 불변 검사에서 뺐다.

[`DrainGuardWait`](../../../tools/daemon/runner_verify/tests/test_runner_verify.py)는 drain이 `guard_wait` 봉투를 inbox에 남기고 받은 봉투만 옮기는지 본다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.GuardWaitRollsBack -v` | 수정 전 8개 실패(하위 사례 포함 실패 8·오류 8, 종료 1), 수정 후 8개 통과 | [before.log](../../../tools/evidence/audit2-daemon-guard-fail-partial-commit/before.log), [focused.log](../../../tools/evidence/audit2-daemon-guard-fail-partial-commit/focused.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario M30 --quiet` | 수정 전 199건 중 27건 실패, 수정 후 199건 통과 | 위 두 로그 |
| `python3 -I tools/evidence/audit2-daemon-guard-fail-partial-commit/repro_guard_wait_partial_commit.py` | 수정 전 거절 뒤 카운터 1·seen 2·빈 세대 2 슬롯, 재전달 duplicate. 수정 후 거절 뒤 카운터 0·seen 1·슬롯 없음, 재전달로 세대 2·카운터 1 | 위 두 로그의 끝 |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 230개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario all --require-all` | 검사 704건·실패 0건·명세 공백 표시 0건 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` | 59개 통과(실제 프로세스·git을 쓰는 T-OP-09 도구, 새 `DrainGuardWait` 포함), 종료 0 | [runner-verify-unittest.log](../../../tools/evidence/audit2-daemon-guard-fail-partial-commit/runner-verify-unittest.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1040개 실행·통과, skip 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit2-daemon-guard-fail-partial-commit/python-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`·`check_product_purpose.py`·`blueprint_status.py`·`git diff --check` | 모두 종료 0(`spec_check.py` 기계 44/44·존재 72/72) | [consistency-checks.log](../../../tools/evidence/audit2-daemon-guard-fail-partial-commit/consistency-checks.log) |

skip 6개는 로컬 비공개 원본이 필요한 기존 검사 5개와, 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 새 시험은 skip하지 않았다. 전체 Python 시험 전에 온톨로지 runner를 작업 트리 안(`CARGO_TARGET_DIR=target`)에 빌드했다. Rust 파일은 바꾸지 않아 `cargo test`는 다시 돌리지 않았다. 데몬 보고서 두 개는 기준 커밋과 현재 소스 해시로 다시 만들었다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

## 남은 것

- rollback은 사건을 처리한 입구(`handle_event`·`submit_envelope`)의 트랜잭션 단위다. 인계 경로의 `preserved`는 자기 트랜잭션에서 처리되므로 그 트랜잭션만 버려진다. 앞서 커밋된 인계 단계(보존 커밋·푸시)는 그대로이고, 그래야 한다.
- 다른 사건이 낸 사건(`on_cond_fail`·`emit_event`의 연쇄) 안에서 가드가 wait이면 바깥 사건은 커밋된다. 지금 전이표에는 그런 연쇄로 발급 행에 닿는 경로가 없다.
- 실제 빌더 쪽의 재전달 주기(같은 봉투를 언제 다시 보내는지)는 정해져 있지 않다. 이 변경은 코어가 봉투를 받지 않았다고 답하고, 파일 큐는 봉투를 남겨 둔다는 데까지다. 아무도 다시 보내지 않으면 임대는 예전처럼 TTL에서 끝난다. 실제 경로의 확인은 T-OP-09의 일이다.

## 증명 범위

이 증거는 모의 어댑터를 쓰는 데몬 코어와 규칙 데이터의 트랜잭션 경계를 검증한다. 여기에 실제 실행기 도구의 drain 분기 단위 시험 하나가 더해진다. 실제 프로세스·파일 큐의 재전달 경로 전체나 실제 실행기(T-OP-09)의 동작은 증명하지 않는다. 열린 명세 공백 G51~G57의 해결이나 데몬 가동 승인도 주장하지 않는다. [09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이고 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 시험은 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.
