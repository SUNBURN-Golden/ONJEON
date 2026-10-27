# Audit 2 — 데몬 모의 검증의 필수 시험 ID 대조가 한 방향뿐이라는 지적

기록일: 2026-10-27. 노드: `audit2-daemon-coverage-reverse`. 대상: T-OP-00 필수 시험 ID 33개(`tasks.json` T-OP-00 `required_test_ids`, `tools/daemon/mock_tasks.json` `t_op_00_required_test_ids`).
검증 기준 커밋: `991334c`(이 변경은 그 위의 미커밋 작업 트리).

## 발견

지적은 다음과 같다. `test_daemon_dry_run.py:86-87`은 구현한 시험 ID가 필수 목록 안에 있는지(implemented ⊆ required)만 본다. 그래서 33개 중 17개가 빠져도 시험이 실패하지 않는다.

기준 커밋에서 다시 확인한 결과는 지적과 일부 다르다.

- `Coverage.test_test_ids_are_the_ones_in_tasks_json`에는 T-OP-00 첫 커밋(1ee58d7)부터 반대 방향 검사가 있었다. 필수 목록에서 구현 목록을 뺀 차집합이 비어야 한다. [수정 전 기록](../../../tools/evidence/audit2-daemon-coverage-reverse/before.log) part 1에서 M41을 빼면 이 검사가 `restart-ttl-expired-no-resend`를 빠진 ID로 잡는다.
- 지금은 33개 모두 시나리오가 있다. 시나리오 49개 중 필수 ID를 가진 것이 33개다. "17개 미구현"은 [그록봇 인계 README §9](../proposals/설계검토_결과/그록봇_인계/README.md)의 2026-10-13 결과표에 남아 있던 문장이다. 그 표는 날짜 표시 없이 현재 상태처럼 읽혔다.
- 실제로 한 방향뿐인 곳은 도구였다. `dry_run.py --require-all`은 필수 ID가 실행됐는지만 보았다(required ⊆ ran). 기준 트리에서 [재현 스크립트](../../../tools/evidence/audit2-daemon-coverage-reverse/repro_coverage_reverse.py)를 돌리면(before.log part 2) 다음 세 경우 모두 종료 코드가 0이었다.
  - 필수 목록에 없는 ID를 가진 시나리오가 있을 때
  - 두 시나리오가 같은 ID를 쓸 때
  - 필수 목록에 같은 ID가 두 번 적혔을 때. 이때 요약은 "3개 중 실행 2개, 실행하지 않은 것 0개"였다.
- 단위 시험도 필수 목록 안의 중복은 잡지 못했다. 차집합은 집합으로 계산하므로 같은 ID가 두 번 적혀도 결과가 같다.

## 수정

- [dry_run.py](../../../tools/daemon/dry_run.py)에 `coverage(required, ran)`를 더했다. 이 함수는 두 방향을 한 번에 계산한다.
  - `not_run`: 필수 목록에 있는데 실행하지 않은 ID
  - `unlisted`: 실행했는데 필수 목록에 없는 ID
  - `repeated`: 두 시나리오가 같은 ID를 쓰거나 필수 목록에 두 번 적힌 ID

  STATIC과 시험 ID가 `-`인 시나리오는 세지 않는다.
- 요약에 "필수 목록에 없는 시험 ID n개"와 "두 번 이상 나온 시험 ID n개"를 ID와 함께 적는다. `--report` JSON에도 `unlisted`·`repeated`를 넣었다.
- `--require-all`은 세 목록 중 하나라도 비어 있지 않으면 1을 낸다. 그래서 이제 실행한 ID와 필수 목록이 정확히 같아야 0이다. `--require-all`이 없으면 이 목록은 보고만 하고 종료 코드를 바꾸지 않는다. 한 시나리오만 고르는 실행(`--scenario M30`)은 예전처럼 동작한다.
- [시험](../../../tools/tests/test_daemon_dry_run.py)의 `Coverage.test_test_ids_are_the_ones_in_tasks_json`은 세 개의 따로 된 단언 대신 다음 두 가지를 확인한다.
  - `coverage(...)`의 세 목록이 모두 비었다.
  - 도우미 없이 계산한 정렬 목록이 필수 목록과 같다.

  필수 ID 수 33도 고정했다. 보류로 남긴 ID는 없다. 그래서 지적이 제시한 두 해법 중 "같음을 단언"을 택했다.
- [데몬 README](../../../tools/daemon/README.md)에 `--require-all`의 뜻을 적었다. [인계 README §9](../proposals/설계검토_결과/그록봇_인계/README.md)의 결과표 아래에는 그 표가 2026-10-13 당시 결과이고, 지금은 33개가 모두 실행되며 무엇이 이를 확인하는지 적었다. 표의 내용은 기록이라 고치지 않았다.

전이표·사건·규칙 파일·시나리오 내용은 바꾸지 않았다. 검사 수(704건)도 그대로다.

## 회귀 증거

[`CoverageBothWays`](../../../tools/tests/test_daemon_dry_run.py)(4개)의 확인 내용은 다음과 같다.

- `coverage`: 정상 목록에서 세 목록이 비고, 다섯 변형이 각각 맞는 목록 하나에만 나온다. 변형은 하나 빠짐·목록 밖 ID·두 번 실행·목록에 두 번·ID를 `-`로 바꿈이다.
- 실제 시나리오 목록에서 필수 ID를 가진 시나리오 33개를 하나씩 빼면, 매번 그 ID 하나만 `not_run`에 나온다.
- CLI: M41·M44와 필수 목록 두 개짜리 임시 tasks 파일로 돌린다.
  - 정확히 같으면 `--require-all` 종료 0이다.
  - 빠짐·목록 밖·두 번 실행·목록에 두 번이면 각각 종료 1이고 해당 줄에 ID가 나온다. 이때 시나리오 검사 실패는 0건이다.
  - 같은 입력에 `--require-all`이 없으면 종료 0이다.
- `--report` JSON에 `not_run`·`unlisted`·`repeated`가 들어간다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -I tools/evidence/audit2-daemon-coverage-reverse/repro_coverage_reverse.py <트리>` | 수정 전: 기존 단위 시험은 빠진 ID를 잡는다. `--require-all`은 빠짐만 1이고 목록 밖·두 번 실행·목록에 두 번은 0이다. 수정 후: 정확히 같을 때만 0이고 나머지 네 경우는 모두 1이다 | [before.log](../../../tools/evidence/audit2-daemon-coverage-reverse/before.log), [focused.log](../../../tools/evidence/audit2-daemon-coverage-reverse/focused.log) |
| `python3 -m unittest tools.tests.test_daemon_dry_run.Coverage tools.tests.test_daemon_dry_run.CoverageBothWays -v` | 수정 전(기준 트리 + 새 시험 파일): 12개 중 실패 1·오류 36(하위 사례 포함). 오류는 `coverage`가 없어서 난 것이고, 실패는 `--require-all` 요약에 목록 밖 ID 줄이 없어서 났다. 수정 후 12개 통과 | 위 두 로그 |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 234개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario all --require-all` | 검사 704건·실패 0건·명세 공백 표시 0건. 실행하지 않은 것·목록 밖·두 번 나온 것 모두 0개, 종료 0 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py` | 59개 통과, 종료 0 | [runner-verify-unittest.log](../../../tools/evidence/audit2-daemon-coverage-reverse/runner-verify-unittest.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1044개 실행·통과, skip 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit2-daemon-coverage-reverse/python-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`·`check_product_purpose.py`·`blueprint_status.py`·`git diff --check` | 모두 종료 0(`spec_check.py` 기계 44/44·존재 72/72) | [consistency-checks.log](../../../tools/evidence/audit2-daemon-coverage-reverse/consistency-checks.log) |

skip 6개는 로컬 비공개 원본이 필요한 기존 검사 5개와, 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 새 시험은 skip하지 않았다. 데몬 보고서 두 개는 부모 커밋 991334c와 현재 소스 해시로 다시 만들었다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

## 남은 것

- T-OP-09 실제 실행기 도구의 대조(`test_runner_verify.py` `test_registry_covers_r1_to_r22_and_all_required_test_ids`)는 이미 집합 같음을 단언한다. 이 변경에서 바꾸지 않았다.
- `spec_check.py` G12는 필수 ID마다 그 ID를 가진 과제가 있는지만 본다. 이 검사는 설계 묶음의 존재 검사이고 시나리오 대조가 아니다. 그대로 두었다.

## 증명 범위

이 증거는 모의 데몬 도구가 실행한 시험 ID와 T-OP-00 필수 목록을 두 방향으로 대조한다는 것까지를 보인다. 각 시나리오가 그 ID의 요구를 충분히 시험하는지는 이 대조가 증명하지 않는다. 그것은 시나리오별 검사와 기존 리뷰의 일이다. 실제 실행기(T-OP-09)의 동작, 열린 명세 공백 G51~G57의 해결, 데몬 가동 승인도 주장하지 않는다. [09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이고 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 시험은 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.
