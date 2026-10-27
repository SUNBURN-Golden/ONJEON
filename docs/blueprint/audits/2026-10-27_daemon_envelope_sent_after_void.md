# Audit 2 — 발송 중 void된 outbox 행이 sent가 되던 표시

기록일: 2026-10-27. 노드: `audit2-daemon-envelope-sent-after-void`. 시험 ID: `restart-ttl-expired-no-resend`(T-OP-00, 05 M41).
검증 기준 커밋: `49aa3d7d79f2a7d78b26f949940889930012a8ed`(이 변경은 그 위의 미커밋 작업 트리).

## 발견

[임대 모듈](../../../tools/daemon/core/lease.py)의 `resend_outbox`는 세 단계다. 먼저 한 트랜잭션에서 `core_contract.operations.resend_outbox.checks`(pending·임대 일치·취소/폐기 아님·만료 아님·상태)를 평가한다. 다음으로 트랜잭션 밖에서 봉투를 보낸다. 마지막으로 새 트랜잭션에서 행을 `sent`로 표시한다. 지적된 줄(감사 당시 `lease.py:184-191`, 지금은 표시 트랜잭션)은 행을 다시 보지 않고 `status = "sent"`, `sent_at = now`를 썼다. 발송 중에 다른 사건이 그 행을 `void`로 바꾸어도 `sent`로 덮였고, `void_reason`은 그대로 남았다. 규칙의 `on_pass`도 "outbox.status = sent, sent_at = now"라는 문장뿐이었다.

[수정 전 재현](../../../tools/evidence/audit2-daemon-envelope-sent-after-void/before.log): 기준 커밋을 임시 디렉터리에 풀고, 새 시험 파일과 모의 발송기의 훅(`during_send`)만 넣었다. 코어는 바꾸지 않았다. 7개 중 5개 시험이 실패했다(하위 사례를 포함해 실패 4건·오류 7건, 종료 1). 오류 7건은 새 데이터 키(`resend_outbox.mark_sent`)가 없어서 났다. 동작 실패 4건이 지적 그 자체다. 양성 대조 두 개는 기준 커밋에서도 통과한다(방해 없는 발송은 sent, 나간 봉투의 보고는 R-11). 같은 로그 끝의 [재현 스크립트](../../../tools/evidence/audit2-daemon-envelope-sent-after-void/repro_void_then_sent.py)는 발송과 표시 사이에 사건 하나를 끼워 넣는다.

- 만료(`tick`, `leased → queued`): 행 `void(expired)`가 `sent`로 바뀌고 `void_reason=expired`가 남는다.
- 취소 뒤 다른 데몬 인스턴스의 재시작: 재시작의 재발송 검사가 행을 `void(revoked)`로 둔다. 옛 인스턴스의 표시가 그것을 `sent`로 덮는다.
- 손상(outbox 세대 불일치) 뒤 재시작, 시험만: `void(corrupt)`가 `sent`가 된다.
- 두 번째 발송(`sender_retry`)이 먼저 표시한 경우: 첫 발송의 표시가 `sent_at`을 덮어쓰고 `send_envelope` 부수 효과가 두 번 기록된다.

## 수정

- [규칙 파일](../proposals/설계검토_결과/daemon_rules.json) `core_contract.operations.resend_outbox.mark_sent`를 더했다. `core_contract.*`는 이미 읽기 목록에 있다.
  - `compare_and_set: "pending"`: 표시 트랜잭션에서 다시 평가할 `checks[]`의 id다. 그 검사는 `outbox.status == pending`이다.
  - `set: {status: sent, sent_at: clock.now}`: 검사가 참일 때 쓰는 값이다.
  - `on_conflict: {writes: [], diagnostic: outbox_not_pending_at_mark, result: not_marked}`: 거짓이면 행에 아무것도 쓰지 않는다. 진단과 결과 레코드만 남긴다.
  - `on_pass`의 두 번째 문장에 compare-and-set을 적었다. 설명 키 `_rule`은 코어 뷰에 들어가지 않는다.
- [임대 모듈](../../../tools/daemon/core/lease.py) `_mark_sent`가 위 데이터대로 표시한다. `send_envelope` 부수 효과와 `sent` 결과 레코드는 실제로 표시했을 때만 남는다. `check_mark_sent`는 코어가 시작할 때([엔진](../../../tools/daemon/core/engine.py)) 계약을 확인한다. `compare_and_set`이 검사 id 하나를 가리키는지, `set`에 status가 있는지, `on_conflict`의 writes가 비어 있고 진단·결과 이름이 있는지 본다. 어긋나면 `SpecGap`으로 멈춘다.
- [모의 발송기](../../../tools/daemon/mock_adapters.py)에 `during_send`를 더했다. 발송 직후, 표시 전에 한 번만 도는 훅이다. 시험과 dry_run이 이것으로 경쟁을 만든다. 운영 코어에는 바뀐 것이 없다.

같은 내용을 [04 재시작 복원 행](../proposals/설계검토_결과/04_자동개발명세.md), [05 M41](../proposals/설계검토_결과/05_VM실행준비.md), [07 G06·G07 행](../proposals/설계검토_결과/07_수정대응표.md), [데몬 README](../../../tools/daemon/README.md)에 적었다. 전이표·사건 목록·noop 목록은 바뀌지 않았다.

이미 나간 봉투는 되돌릴 수 없다. 그 봉투의 임대는 끝났으므로 빌더가 그것으로 보내는 것은 막힌다. 만료된 봉투는 수신 측 검증에서 `lease_invalid`가 되고, 취소로 폐기된 임대의 `first_heartbeat`는 accept_envelope에서 막힌다. 둘 다 `late_envelope_rejected`(R-11)이며 전이는 0건이다. 시험이 이것도 확인한다.

## 회귀 증거

[`SendMarkCompareAndSet`](../../../tools/tests/test_daemon_dry_run.py)(7개)는 다음을 확인한다.

- 데이터: `mark_sent`의 값이 위와 같다. `compare_and_set`이 가리키는 검사는 `outbox.status == pending`(fail_key `not_pending`)이다.
- void는 void로 남는다(만료·취소 뒤 재시작·손상 뒤 재시작). 행은 `void`이고 사유는 각각 `expired`·`revoked`·`corrupt`, `sent_at`은 없다. 발송은 1번, `send_envelope` 부수 효과는 0건, 결과는 `not_marked`, 진단은 `outbox_not_pending_at_mark`다.
- 나간 봉투는 막힌다: 만료·취소 두 경우 모두 빌더 실행 뒤 R-11 noop 하나만 남고 전이는 0건, 상태는 `queued`·`cancelled` 그대로다.
- 두 번째 발송: `sender_retry`가 먼저 표시한 `sent_at`이 유지된다. `send_envelope` 부수 효과는 그 발송 하나뿐이고 결과는 `sent`, `not_marked` 순서다.
- 양성 대조: 방해 없는 발송은 `sent`, `sent_at = now`이고 부수 효과가 1건이다.
- 변이 시험: `compare_and_set`을 `lease_match`로 바꾸면 만료 뒤에도 그 검사는 참이다. 그러면 `void(expired)` 행이 다시 `sent`가 된다. 지적이 그대로 재현된다.
- 계약 위반: 없는 검사 id, status 없는 `set`, writes가 있는 `on_conflict`, 진단 없는 `on_conflict`, `mark_sent` 누락. 다섯 경우 모두 코어가 시작하지 않는다.

dry_run 보고서의 M41(restart-ttl-expired-no-resend)에 검사 두 개를 더했다. 발송과 표시 사이에 만료되면 행이 `void(expired)`로 남는지 본다. 그 봉투에 대해 빌더가 `lease_invalid`만 보내고 R-11·상태 `queued`인지도 본다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.SendMarkCompareAndSet -v` | 수정 전 5개 실패(하위 사례 포함 실패 4·오류 7, 종료 1), 수정 후 7개 통과 | [before.log](../../../tools/evidence/audit2-daemon-envelope-sent-after-void/before.log), [focused.log](../../../tools/evidence/audit2-daemon-envelope-sent-after-void/focused.log) |
| `python3 -I tools/evidence/audit2-daemon-envelope-sent-after-void/repro_void_then_sent.py` | 수정 전 만료·취소 행이 `sent`(void_reason 남음), 두 번째 발송의 sent_at 덮어씀. 수정 후 `void` 유지, sent_at `start+1` 유지 | 위 두 로그의 끝 |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 222개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario all --require-all` | 검사 669건·실패 0건·명세 공백 표시 0건 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` | 58개 통과(실제 프로세스·git을 쓰는 T-OP-09 도구, 같은 코어의 `_mark_sent` 경로를 거친다), 종료 0 | [runner-verify-unittest.log](../../../tools/evidence/audit2-daemon-envelope-sent-after-void/runner-verify-unittest.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1032개 실행·통과, skip 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit2-daemon-envelope-sent-after-void/python-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`·`check_product_purpose.py`·`blueprint_status.py`·`git diff --check` | 모두 종료 0(`spec_check.py` 기계 44/44·존재 72/72) | [consistency-checks.log](../../../tools/evidence/audit2-daemon-envelope-sent-after-void/consistency-checks.log) |

skip 6개는 로컬 비공개 원본이 필요한 기존 검사 5개와, 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 새 시험은 skip하지 않았다. 전체 Python 시험 전에 온톨로지 runner를 작업 트리 안(`CARGO_TARGET_DIR=target`)에 빌드했다. Rust 파일은 바꾸지 않아 `cargo test`는 다시 돌리지 않았다. 데몬 보고서 두 개는 기준 커밋과 현재 소스 해시로 다시 만들었다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

## 남은 것

- compare-and-set은 행 상태만 본다. 취소는 그 자체로 outbox를 void하지 않는다(M42: 재발송 검사가 `revoked`로 void한다). 그래서 발송 중에 취소만 일어나고 재발송 검사가 아직 돌지 않았다면 행은 아직 `pending`이고, 실제로 나간 봉투이므로 `sent`로 표시된다. 그 봉투로 온 보고는 임대가 `revoked`라 R-11로 막힌다. `owner_cancelled` 전이가 pending을 바로 void하지 않는 것은 기존 전이표의 동작이다(M42). 이 노드는 바꾸지 않았다.
- 실제 저장소(파일 잠금·rename)에서 두 트랜잭션 사이의 경쟁은 모의 저장소로만 시험했다. 실제 동시성은 T-OP-09가 확인할 일이다.

## 증명 범위

이 증거는 모의 어댑터를 쓰는 데몬 코어와 규칙 데이터의 outbox 표시만 검증한다. 실제 프로세스·파일 큐·전달 경로나 실제 실행기(T-OP-09)의 동작은 증명하지 않는다. 열린 명세 공백 G51~G57의 해결이나 데몬 가동 승인도 주장하지 않는다. [09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이고 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 시험은 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.
