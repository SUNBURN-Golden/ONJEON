# Audit 3 — `handle_event` 결과 봉투 우회 방지

기록일: 2026-10-28. 노드: `audit3-daemon-handle-event-envelope-bypass`.
검증 기준 커밋: `3676595f4ef7c1efc142efe1804ff47951ad15f3` 위의 미커밋 작업 트리.
관련: T-OP-00 `late-write-fenced`(M17), BLUEPRINT §11 개발 도구.

## 확인과 수정

지적은 `handle_event({"event": "result_pr_opened", ...})`가 봉투 검증 없이 `building → pr_open`을 만드는 경로다. 현재 기준 트리에는 [Audit 2 허용 목록 수정](2026-10-27_daemon_handle_event_fencing.md)이 이미 있어, 기본 규칙의 일반 결과 사건은 R-13 `envelope_rejected_invalid`로 거부된다. 다만 `without_envelope`에 `result_pr_opened`를 추가하면 우회가 다시 열렸으며, 기존 변이 시험도 이 전이를 허용했다.

[엔진](../../../tools/daemon/core/engine.py)의 초기화 검증을 보강했다. `core_contract.operations.handle_event`의 `without_envelope` 또는 `routes`에 `result_*` 이름을 등록하면 `SpecGap("operations.handle_event: result events require submit_envelope")`으로 시작을 거부한다. 결과 사건은 `submit_envelope(task_id, "result", envelope)`의 임대·세대·토큰·중복·만료 검사를 거친 뒤에만 전이표에 도달한다. 상태 전이표와 기본 허용 목록은 바꾸지 않았다.

## 회귀 시험과 증거

[HandleEventFencing](../../../tools/tests/test_daemon_dry_run.py)의 기존 8개 시험을 10개로 보강했다.

- 기존의 우회 재개 변이 시험을 시작 거부 시험으로 교체했다. 등록된 결과 사건 5개 각각에 대해 허용 목록과 세 가지 route(`restart_recovery`, `accept_envelope`, `fenced_write`)를 변이한다. 20가지 모두 초기화 시 거부된다.
- 임대가 전혀 없는 `building` 과제에서도 결과 사건 5개가 전이를 만들지 않고 R-13 noop만 남긴다. 과제 상태·임대·세대·outbox·inbox_seen·인계 기록은 유지된다.
- 현재 임대의 완전한 결과 봉투를 일반 사건 payload에 넣어도 거부한다. 같은 봉투를 정상 `submit_envelope`로 제출하면 한 번만 `building → pr_open`으로 전이하고, 재전달은 `envelope_duplicate_delivery`이며 과제 기록은 그대로다.
- 기존 허용 목록·일반 사건·인계 내부 호출·봉투 사건 거부 시험을 유지했다.

새 시험만 먼저 적용한 [수정 전 실행](../../../tools/evidence/audit3-daemon-handle-event-envelope-bypass/before.log)은 10개 시험 중 설정 변이의 하위 사례 20건에서 실패했다. 일반 사건 거부와 정상 봉투 경로는 이미 통과했다. 초기화 검증을 추가한 뒤 같은 시험은 모두 통과했다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.HandleEventFencing -v` | 10개 통과 | [focused.log](../../../tools/evidence/audit3-daemon-handle-event-envelope-bypass/focused.log) |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 245개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all` | 검사 704건, 실패 0건, 필수 시험 ID 누락·목록 밖·중복 없음 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1163개 실행, 실패·오류 0, 기존 skip 6 | [python-tests.log](../../../tools/evidence/audit3-daemon-handle-event-envelope-bypass/python-tests.log) |
| `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` | 59개 통과 | [runner-tests.log](../../../tools/evidence/audit3-daemon-handle-event-envelope-bypass/runner-tests.log) |
| 어휘·검증 자료·검증기 selftest·설계 명세·제품 목적 대응표·BLUEPRINT 결정 기록 대조 | 모두 종료 0 | [consistency-checks.log](../../../tools/evidence/audit3-daemon-handle-event-envelope-bypass/consistency-checks.log) |

데몬 보고서 두 개는 위 기준 커밋과 현재 데몬 소스·시험 파일의 SHA-256으로 재생성했다. 전체 Python 시험의 온톨로지 의존성은 작업 트리의 `target`에 빌드했다([ontology-build.log](../../../tools/evidence/audit3-daemon-handle-event-envelope-bypass/ontology-build.log)).

skip 6개는 로컬 비공개 원본이 필요한 기존 시험 5개와 설치된 botocore에 해당하지 않는 구버전 시험 1개다. 새 회귀 시험은 skip하지 않았다. 실행기 시험의 통과는 기존 PASS/UNCONFIRMED 수락 기준을 따르며 모든 운영 환경 검증 완료를 뜻하지 않는다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다. 최종 `git diff --check`도 종료 0이다.

## 증명 범위

결과 사건의 일반 입구 차단과 잘못된 규칙의 시작 거부를 검증한다. 관측·담당자 사건의 출처 인증, 실제 제공자 실행, 상주 데몬 가동 승인을 증명하지 않는다. Rust 소스는 변경하지 않았다.

[09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이며 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 증거는 P01~P19의 실제 공시 데이터·트윈·소비자 화면·출시 완료 증거를 대체하지 않는다.
