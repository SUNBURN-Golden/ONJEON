# Audit 1: 데몬 복구의 구조화된 만료 사건 읽기

기록일: 2026-10-26. 노드: `audit1-daemon-recovery-structured-events`.
검증 기준 커밋: `17e172b7845b79da7a4c9bf11aae128111aea63e`.

지적은 `recovery.py`가 `normal_expiry.path` 설명 문장에서 정규식으로 만료 사건을 추출한다는 것이다. 이 작업의 기준 커밋에는 그 추출이 이미 제거되어 있고 `events_by_state`를 읽고 있었다. 다만 G43에 구조화된 `events` 목록이 있어도 실제 만료 분류에는 사용하지 않았고, `core_contract.reads`는 설명 문장을 포함한 `state_integrity` 전체를 노출했다.

[복구 코어](../../../tools/daemon/core/recovery.py)는 상태별 매핑의 사건이 `state_integrity.normal_expiry.events` 목록에도 등록되어 있고 현재 상태의 전이 행이 있을 때만 정상 만료 사건으로 선택한다. 기존 `events_by_state`의 상태별 선택을 유지한다. 목록에서 사건을 제거하면 해당 사건의 정상 만료 분류가 비활성화되며 다른 상태의 사건은 유지된다. 필수 목록 자체가 없으면 계약 오류(`SpecGap`)로 거부한다. 설명 문장으로 대체하지 않는다.

[규칙의 읽기 목록](../proposals/설계검토_결과/daemon_rules.json)은 정상 만료의 `detect`·`events_by_state`·`events`와 기존 `corruption`을 명시한다. `normal_expiry.path`·`outbox`·`next_lease` 설명 문장은 코어 뷰에 포함하지 않는다. G43의 [구현 설명](../../../tools/daemon/spec_gaps.py)도 실제 읽기 동작에 맞췄다.

## 검증

[회귀 시험 `StructuredExpiryEvents`](../../../tools/tests/test_daemon_dry_run.py)은 다음을 확인한다.

- 읽기 목록의 명시적 `events` 등록과 정상 만료 설명 문장의 코어 뷰 제외.
- `path`를 다른 사건 이름이 든 문장으로 바꾸거나 삭제하고 목록 순서를 뒤집어도 `leased → queued(lease_expired)`, `building → returned(heartbeat_missed_twice)`로 정상 복구.
- 만료된 pending 봉투의 `void(expired)`, 봉투 재발송 없음, 세대 추가 발급 없음, 두 번째 재시작의 중복 전이 없음.
- 목록에서 각 사건을 제거했을 때 해당 상태의 정상 만료 분류만 비활성화됨. 목록 누락은 계약 오류.

| 명령 | 실행 결과·증거 |
|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.StructuredExpiryEvents -v` | 수정 전 4개 실행·실패 4건(하위 사례 포함, [before.log](../../../tools/evidence/audit1-daemon-recovery-structured-events/before.log)), 수정 후 4개 통과([focused.log](../../../tools/evidence/audit1-daemon-recovery-structured-events/focused.log)) |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 186개 통과·실패 0([unittest.log](../../../tools/daemon/reports/unittest.log)) |
| `python3 -m unittest discover -s tools/tests -v` | 856개 실행·실패 0·skip 6([python-tests.log](../../../tools/evidence/audit1-daemon-recovery-structured-events/python-tests.log)) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all` | 검사 664건·실패 0건·시나리오 내 명세 공백 표시 0건. 필수 시험 ID 33/33 실행([dry_run.log](../../../tools/daemon/reports/dry_run.log)) |
| `cargo test --all --offline` | 402개 통과·실패 0·ignored 1([rust-tests.log](../../../tools/evidence/audit1-daemon-recovery-structured-events/rust-tests.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과([doc-checks.log](../../../tools/evidence/audit1-daemon-recovery-structured-events/doc-checks.log)) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 9개 등록 정합성 통과(같은 로그) |
| `python3 tools/vocab_check.py`, `python3 tools/validation_check.py`, `python3 tools/validation_check.py --selftest` | 어휘·검증 자료 내부 정합성·변조 38종 검사 통과(같은 로그). 원본 재검증 아님 |

전체 Python 시험의 skip 6개는 로컬 원본 부재 5개와 설치된 botocore가 조건부 쓰기를 지원해 적용되지 않는 구버전 거부 시험 1개다. 새 회귀 시험은 skip하지 않았다. 데몬 보고서 두 개는 현재 소스 해시로 다시 생성했고 해당 해시 회귀 시험도 통과했다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

[경로 검사](../../../tools/evidence/audit1-daemon-recovery-structured-events/scope-check.json)로 변경 파일이 이 노드의 허용 경로 안에 있고 보호 경로가 기준 커밋과 동일함을 확인했다. `git diff --check`도 통과했다. commit·push·GitHub 호출은 수행하지 않았다.

## 증명 범위

이 증거는 모의 어댑터를 사용하는 데몬 복구와 규칙 읽기 계약의 감사 지적을 검증한다. 실제 프로세스·외부 서비스 복구를 증명하지 않는다. 열린 명세 공백 G51~G57의 해결이나 데몬 가동 승인을 주장하지 않는다.

[09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이고 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 모의 시험은 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않으며 제품 완성 판정도 아니다.
