# Audit 3 — fenced_write 중복 방지와 커밋 후 원격 쓰기

기록일: 2026-10-28. 노드: `audit3-daemon-fenced-write-dedupe`.
기준 커밋: `835dba23f33e8fa871514f89512d2fcd16bc921a` + 이 노드의 미커밋 변경.
범위: T-OP-00 개발 도구, F08·M17(`late-write-fenced`). BLUEPRINT §11의 개발 도구 보강이며 [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 출시 완성품 제외 항목이다. P01~P19의 실제 데이터·트윈·화면·출시 완료 증거를 대신하지 않는다.

## 발견과 수정 전 증거

`fencing.fenced_write`는 임대·만료·데몬 경유만 확인하고 `inbox_seen`을 조회하거나 표시하지 않았다. 같은 `envelope_id`로 `push_requested` 또는 `pr_update_requested`를 다시 보내면 `remote.execute`를 다시 호출했다. `effects.h_execute_write`가 저장소 트랜잭션 안에서 원격 쓰기를 실행하므로, 그 뒤 전이 기록이나 커밋이 실패해도 외부 쓰기는 남았다.

[수정 전 로그](../../../tools/evidence/audit3-daemon-fenced-write-dedupe/before.log)는 기존 구현에 초기 회귀 시험 9개를 먼저 추가한 결과다. 9개 중 8개가 실패했다(하위 사례 포함 실패 28건·오류 2건, 종료 1). 서로 다른 ID의 정상 요청은 양성 대조로 통과했다. 특히 전이 기록 실패·커밋 실패 시험은 저장소가 롤백되어도 원격 쓰기 1건이 남는 문제를 재현했다.

## 구현 계약

- [규칙](../proposals/설계검토_결과/daemon_rules.json)의 `operations.fenced_write.checks`를 필수 식별자 → 임대 일치 → 중복 → 활성·만료 → 데몬 경유 순서로 확장했다. 식별자 누락은 R-13, 현재 세대의 중복은 `envelope_duplicate_delivery`, 이전 임대는 기존처럼 R-11이다. 이전 세대 판정은 중복보다 먼저, 현재 세대 중복 판정은 만료보다 먼저다.
- [fencing.py](../../../tools/daemon/core/fencing.py)는 `accept_envelope.idempotency_key_fields`와 기존 `envelope_kind=signal`을 사용해 중복을 조회한다. 검사 통과 뒤 키와 최초 관측 시각·세대, 원격 쓰기 intent, 자기 상태로의 전이 기록을 한 트랜잭션에 저장한다. 실패한 요청은 키를 소비하지 않는다.
- [effects.py](../../../tools/daemon/core/effects.py)는 원격 쓰기를 실행하는 대신 요청 사본을 커밋 후 작업으로 준비한다. [engine.py](../../../tools/daemon/core/engine.py)의 `_after_commit`이 저장소 트랜잭션을 벗어난 뒤 `remote.execute`를 호출한다. 원격 호출이 정상 반환하면 `execute_write` 효과 기록을 별도 트랜잭션에 쓴다. intent를 원격 완료 기록으로 취급하지 않는다.
- 롤백·커밋 실패에서는 원격 호출과 처리 키가 모두 없으므로 같은 요청으로 재시도할 수 있다. 커밋 후 중단·원격 오류·완료 기록 실패에서는 키를 유지해 같은 요청을 다시 실행하지 않는다.

## 회귀 검증

[`FencedWriteDedup`](../../../tools/tests/test_daemon_dry_run.py)의 12개 시험은 두 사건 모두에 적용한다.

- 재전달·코어 재생성 후 재전달은 원격 쓰기 1회, 중복 noop, 새 전이 없음. 서로 다른 ID는 각각 실행한다.
- 필수 식별자 네 개의 누락·null은 R-13이고 임대·상태·처리 키를 바꾸지 않는다.
- 원격 어댑터는 처리 키와 전이가 이미 커밋된 상태를 관측하고, 실행 중 저장소 트랜잭션이 없다.
- 전이 효과 실패·커밋 실패 시 원격 호출 0회·저장소 전체 롤백, 같은 요청의 정상 재시도.
- 동시 요청 8개는 원격 호출 1회와 중복 noop 7건.
- 이전 임대는 중복보다 먼저 R-11, 현재 세대 중복은 만료 뒤에도 중복, 처음 보는 만료 요청은 R-11.
- 원격 쓰기 후 예외, 커밋 직후 발송 전 중단, 완료 기록 실패에도 처리 키를 유지한다.
- 실제 `FileStore`의 파일 잠금·rename 커밋을 사용해 원격 호출 중 새 트랜잭션을 열 수 있고, 코어를 재생성해도 중복이 차단됨을 확인한다. 원격 어댑터는 모의이며 Git 쓰기는 하지 않는다.

실행 결과와 재현 명령은 [증거 안내](../../../tools/evidence/audit3-daemon-fenced-write-dedupe/README.md), [수정 후 로그](../../../tools/evidence/audit3-daemon-fenced-write-dedupe/after.log), [전체 데몬 시험](../../../tools/daemon/reports/unittest.log), [모의 시나리오](../../../tools/daemon/reports/dry_run.log)에 남긴다. 데몬 보고서의 소스 해시는 README에 명시한 절차로 갱신했다.

| 실행 | 결과 |
|---|---|
| 신규 회귀 `FencedWriteDedup` | 12개 통과 |
| 전체 데몬 시험 | 257개 통과, 종료 0 |
| 전체 모의 시나리오 `--require-all` | 검사 704건 통과, 필수 ID 33/33, 누락·미등록·중복 0 |
| 전체 Python `unittest discover -s tools/tests -v` | 1,175개 실행, 실패·오류 0, skip 6, 종료 0 |
| `cargo test --all` | 종료 0. 기존 `regenerate_declared_abox_fixture` 1개 ignored |
| 어휘·검증 자료·selftest·설계 묶음·BLUEPRINT 등록 수·결정 색인 | 모두 통과. 설계 묶음 기계 검사 44/44·존재 검사 72/72 |

Python skip 6개는 원본 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해서 해당하지 않는 구버전 거부 시험 1개다. 새 회귀와 데몬 시험의 skip은 없다. 전체 Python 로그는 [여기](../../../tools/evidence/audit3-daemon-fenced-write-dedupe/python-tests.log), 나머지 도구 출력은 [여기](../../../tools/evidence/audit3-daemon-fenced-write-dedupe/checks.log)에 있다.

## 한계

저장소 커밋과 원격 쓰기를 하나의 원자 작업으로 만들지는 않는다. 커밋 후 발송 전에 중단되면 미발송 intent가 남고, 발송 뒤 응답이나 완료 기록이 실패하면 원격 성공 여부가 불명확할 수 있다. 이 구현은 같은 키의 자동 재실행을 막으며 원격 결과 대조·자동 복구·exactly-once 전달을 보장하지 않는다. 실제 Git·GitHub·운영 원격 요청은 수행하지 않았고, 상주 데몬 가동·실데이터 접근·첫 출시 관문을 승인하지 않는다.
