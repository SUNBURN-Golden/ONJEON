# Audit 3 — 시험 실패 재임대의 가드 실패 정체 해소

대상: `audit3-daemon-failed-tests-stuck`, 개발 도구 T-OP-00·T-OP-09.
기준 커밋: `e1c5f14c0de0e428e46fcb975e412f909d9557ed` 위의 미커밋 작업 트리. 이 작업 트리의 커밋·푸시·GitHub 호출은 하지 않았다. 실행기 시험은 임시 로컬 저장소를 사용한다.

## 발견과 수정

`building → building / result_failed_tests`는 before_cond로 실패 횟수를 올린 뒤 3회 미만이면 같은 작성자에게 재임대한다. 가드가 거짓이면 적용할 행이 없었다. Audit 2의 대기 롤백은 봉투·횟수·사용량의 부분 커밋을 막았지만, 재전달이 없으면 과제는 heartbeat 만료까지 `building`에 남았다.

[규칙 데이터](../proposals/설계검토_결과/daemon_rules.json)의 재임대 행에 다음 fallback을 추가했다.

```json
"on_cond_fail": {
  "emit": "unmapped_condition",
  "args": {
    "original_event": "result_failed_tests",
    "reason": "retry_lease_guard_failed"
  }
}
```

[전이 엔진](../../../tools/daemon/core/transition_engine.py)은 가드 자체의 `emit_event` → 행의 `on_cond_fail` → 일반 `guard_wait` 순서로 처리한다. cond 안의 가드와 별도 `guard` 필드가 모두 같은 경로를 쓴다. 다른 후보 행이 적용되면 cond fallback은 실행하지 않는다.

- 실패 횟수가 이번 보고를 포함해 1·2회이고 가드가 실패하면 기존 `unmapped_condition`의 활성 임대 행이 즉시 `returned(R-03)`로 옮긴다. 임대는 revoked, 프로세스 종료·토큰·쓰기 및 보존 자격 회수·pending outbox 무효화는 기존 종료 규약을 쓴다. 새 임대·지시는 없다.
- 결과 수락·사용량·실패 횟수 +1·반송과 R-code는 같은 트랜잭션으로 커밋한다. 동일 세대에서 같은 결과를 다시 보내면 `envelope_duplicate_delivery`이며 횟수·반송을 반복하지 않는다. 복귀에는 `owner_resolved`가 필요하다.
- 3회째는 기존 `result_failed_tests → returned(R-06)` 행을 적용한다. 가드가 실패해도 R-03으로 덮지 않는다.
- `instruction_envelope_valid`가 `envelope_invalid`를 내는 경우 기존 R-13이 우선한다. 빌더가 없어 이 사건의 전제도 충족하지 못하면 R-03 fallback이다.
- fallback이 없는 행은 기존 대기 롤백을 유지한다. 기존 `GuardWaitRollsBack`은 이 일반 계약을 검증하도록 재임대 행의 fallback을 뺀 시험용 규칙을 사용한다. 실제 규칙의 즉시 반송은 새 `FailedTestsGuardFallback`과 M30이 검증한다.

R-03 목록과 04 공통 가드·전이표, 05 M30, 07 G48, [데몬 README](../../../tools/daemon/README.md)를 같은 동작으로 갱신했다. 새 R-code나 사건 종류는 만들지 않았다.

## 회귀와 실행 증거

[회귀 시험](../../../tools/tests/test_daemon_dry_run.py)의 `FailedTestsGuardFallback` 6개는 충돌·단일 작성자·동시 임대 수·잠금·사용량 슬롯·빌더 실패를 각각 1·2회째에 주입한다. 가상 시계를 진행하거나 heartbeat 만료·재전달을 기다리지 않고 즉시 반송됨을 확인한다. 현재 임대 종료·자격 회수·결과 수락·사용량·실패 횟수·재시작 후 중복 무시·재임대 없음도 검사한다. 3회째 R-06, 정상 재임대, R-13 우선, 별도 guard 필드와 fallback 제거 변이를 포함한다.

[수정 전 재현](../../../tools/evidence/audit3-daemon-failed-tests-stuck/before-tests.log)은 기준 커밋의 코어·규칙을 작업 트리 안의 임시 디렉터리에 추출하고 새 시험 파일만 넣어 실행했다. 6개 시험 중 하위 사례 포함 실패 13건·오류 1건, 종료 1이다. 오류는 기존 규칙에 `on_cond_fail` 키가 없어서이며, 실패는 즉시 반송이 없는 동작을 보여 준다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.FailedTestsGuardFallback tools.tests.test_daemon_dry_run.GuardWaitRollsBack -v` | 14개 통과 | [focused-tests.log](../../../tools/evidence/audit3-daemon-failed-tests-stuck/focused-tests.log) |
| `python3 -m unittest tools.tests.test_daemon_dry_run -v` | 267개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all` | 검사 692건·실패 0, 필수 ID 33/33 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v` | 59개 통과 | [runner-tests.log](../../../tools/evidence/audit3-daemon-failed-tests-stuck/runner-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1185개 실행, skip 6, 실패·오류 0 | [python-tests.log](../../../tools/evidence/audit3-daemon-failed-tests-stuck/python-tests.log) |
| `cargo test --all` | 결과 요약 합계 466 passed·0 failed·1 ignored | [cargo-tests.log](../../../tools/evidence/audit3-daemon-failed-tests-stuck/cargo-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`·제품목적 연결·BLUEPRINT 상태·`git diff --check` | 모두 종료 0 | [consistency-checks.log](../../../tools/evidence/audit3-daemon-failed-tests-stuck/consistency-checks.log) |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 20개 중 기존 실패 2개, 종료 1 | [ci-tests.log](../../../tools/evidence/audit3-daemon-failed-tests-stuck/ci-tests.log), [기준 커밋 재현](../../../tools/evidence/audit3-daemon-failed-tests-stuck/baseline-ci-check.log) |

전체 Python 시험 전 온톨로지 runner를 이 작업 트리의 `target`에 빌드했다([빌드 로그](../../../tools/evidence/audit3-daemon-failed-tests-stuck/ontology-build.log)). skip 6개는 비공개 원본이 필요한 기존 시험 5개와 현재 botocore에 적용되지 않는 구버전 시험 1개다. 새 시험은 skip하지 않았다. 데몬 보고서는 저장소 규약의 현재 소스 해시로 다시 생성했다.

추가 CI 검사 실패 2개(`RepoIsClean`의 실제 저장소 검사·격리 CLI 검사)는 `packages/ontology` → `onjeon-rules-engine` 의존성의 기존 `DEP-ZONE` 1건·`IMP-ZONE` 2건 때문이다. 기준 커밋의 검사기·계층 규칙·소스를 임시 디렉터리에 추출해 `check_deps.py`로 같은 세 위반을 재현했다. 이 노드는 해당 계층 의존성을 수정하지 않는다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

## 증명 범위

이 변경은 개발 도구의 상태 전이 정체와 회귀 검증이다. 실제 제공자·원격 서비스·제품 데이터 수집 성공이나 데몬 가동 승인을 뜻하지 않는다. [09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 T-OP-08 축 5의 운영 기록에만 연결된다. P01~P19의 실제 데이터·디지털 트윈·소비자 화면·출시 완료 증거를 대신하지 않는다. 기존 명세 공백 G47·G51~G57도 그대로다.
