# Audit 3 — 원장 상한 영구 잠금 해소

대상: `audit3-r2-ledger-cap-lockout`, `tools/r2_budget.py::Ledger.read/append`, `reserve`, `Session`, `_cli`.
연결: Blueprint A1·L1~L2·M1, ADR-0017, 09 제품 목적 대응표 P02·P03.

## 현재 수정 — Fix round 2

**검토 P1.** 앞 수정은 `checkpoint` 세션의 쓰기 상한을 무조건 우회했다. 체크포인트 PUT만 실패해도 예약·정산 두 건은 남아 100 → 102 → 104 → 106 → 108 → 110건이 됐다. 저장소가 복구되어도 다음 실행은 예약 전 Class B 입장 한도 110에 막혀 영구 잠금이 다시 생겼다.

**수정.** `over_limit_ok`는 복구 읽기에만 적용한다. `append()`의 상한은 모든 세션에 적용한다. 체크포인트 실행은 입장 → 원장 검증·전체/작업 예산·남은 입장 몫 검사 → 체크포인트 저장·확인 → 예약 → 정산 순서다. 예약 전 원장·입장 읽기 결과를 재사용하여 체크포인트를 저장하고 새 체크포인트를 읽어 확인한다. 그때까지 계량기는 입장 한도를 유지하며 자료 접근도 허용하지 않는다. CLI는 이때 저장한 결과를 출력하며 두 번째 체크포인트를 쓰지 않는다.

100건의 성공 경로는 체크포인트 100 → 예약 101 → 정산 102다. 뒤따르는 기록은 두 건이다. 체크포인트 PUT·크기 검사·확인 읽기가 실패하면 예약이 없으므로 정산도 없다. 실패한 입장은 계속 전액 계상된다. 실패 반복은 뒤받침을 키우지 않으며 저장소가 복구되면 같은 읽기 비용으로 복구를 재시도한다. 입장·프로필·전체/작업 caps·월별 입장 제한은 올리거나 우회하지 않았다.

100건에서 예약 완료까지 요청은 Class A 7·Class B 103(기존 체크포인트가 있으면 B 104)으로 배포 입장 한도 A 8·B 110 안이다. 쓰기 직전에도 기존 상한을 지키므로 복구 플래그가 있어도 체크포인트 없는 101번째 쓰기는 거부된다. 예약 경쟁에서 지면 새 체크포인트 기준으로 다시 읽고 한도를 재검사한다.

## 회귀와 증거

[`test_r2_checkpoint.py`](../../../tools/tests/test_r2_checkpoint.py)의 새 회귀 다섯 개:

- `EndToEnd.test_failed_checkpoint_retries_do_not_grow_backlog_or_block_recovery`: 루프백 S3의 실제 botocore 요청, 배포 입장 한도와 `initial-119.json`의 `verify`·`status` 프로필을 사용한다. 100건에서 체크포인트 PUT만 다섯 번 실패시켜도 원장은 매번 100건이고 입장만 1~5건 남는다. 서버의 실제 요청·업로드 바이트를 계량기와 대조하고 한도 안임을 확인한다. 쓰기 복구 뒤 체크포인트·예약·정산·일반 실행·전체 감사를 확인하며, 실패 입장 다섯 건이 전액 계상되고 요약/전체 원장의 사용량이 같은지도 확인한다. 시험의 전체·작업 caps는 격리했다.
- `Lockout.test_checkpoint_cli_failure_retries_and_success_write_once`: 실제 CLI·세션·로컬 원장으로 다섯 실패 뒤 성공, 실패 시 예약 없음·ACTIVE 없음·잠금 해제, 성공 시 체크포인트 한 번만 저장·정산 102를 확인한다.
- `Lockout.test_failed_checkpoint_size_check_keeps_backlog_and_reservation_unchanged`: 크기 검사 실패 다섯 번도 뒤받침을 늘리지 않으며 검사 복구 뒤 성공한다.
- `Lockout.test_checkpoint_reservation_race_rereads_from_the_new_base`: 체크포인트 저장 뒤 예약 경쟁을 주입해 새 기준점으로 다시 읽고 체크포인트 연결·전체 감사를 통과한다.
- `Lockout.test_checkpoint_session_on_empty_or_already_summarised_ledger`: 빈 원장·이미 요약된 원장의 `nothing_new` 뒤 예약·정산도 정상이다.

기존 회귀도 현재 순서로 갱신했다: 99/100건·기존 체크포인트 뒤 100건 복구, 일반 세션/반복 감사의 상한 준수, 복구 플래그가 있는 `append()`의 상한 강제, 전체/작업 예산 거부 유지. [`test_r2_budget.py`](../../../tools/tests/test_r2_budget.py)의 `LedgerRecordCap`은 읽기 전용 `tail()` 뒤 일반 `append()`가 101번째 PUT을 보내지 않음을 계속 확인한다.

최신 실행 결과와 소스/증거 해시: [fix-round2 증거](../../../tools/evidence/audit3-ledger-cap-lockout/fix-round2/README.md).

## 앞선 발견과 수정 이력

- 최초 발견: 실행마다 예약·정산 두 건이 쌓여 약 50회 뒤 100건 읽기 상한에 걸렸고, 복구 명령도 같은 상한에 막혔다. 처음에는 복구와 감사 세션 모두 상한을 우회했다([초기 증거](../../../tools/evidence/audit3-ledger-cap-lockout/README.md)).
- Fix round 1: 반복 감사가 뒤받침을 키우는 경로를 막기 위해 우회를 체크포인트 세션으로 한정했다([당시 증거](../../../tools/evidence/audit3-ledger-cap-lockout/fix-round1/README.md)). 이번 수정은 체크포인트 실패 반복에도 같은 불변식을 적용한다.
- 거부된 실행의 입장 기록은 의도된 회계다. 읽기 전에 남기며 정산되지 않으면 입장 한도 전액이 사용량에 잡힌다. 거부·복구 실패 반복도 무료 요청이 되지 않는다(`infra/r2/BUDGET.md` §4). 이를 삭제하지 않는다.

## 검증 범위

이 작업 트리의 임시 로컬 원장과 루프백 S3 스텁만 사용했다. 실제 R2·외부 서비스·자격 증명을 사용하거나 커밋·푸시·GitHub 호출을 하지 않았다. 월별 입장·비용 한도 소진은 여전히 정당한 거부다. 이미 입장 읽기 한도를 넘은 과거의 비정상 원장을 복원했다는 증거는 아니다.

이 증거는 보관 도구의 비용 통제 경계에 한정하며 실제 공시 확보율·R2 관측 대조·화면·출시 완료 증거를 대신하지 않는다. P02·P03을 완료 처리하지 않는다.
