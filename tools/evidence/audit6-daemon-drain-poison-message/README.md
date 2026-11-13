# audit6-daemon-drain-poison-message 실행 증거

2026-11-12 작성, 2026-11-13 재검증. [수정 기록](../../../docs/blueprint/audits/2026-11-12_daemon_drain_poison_message.md) ·
[실행기 시험](../../daemon/runner_verify/tests/test_runner_verify.py)(`DrainPoisonMessage`).
기준 커밋 `ee9331b3660d033b2dcf09df1e5344c081815497` 위 미커밋 변경이며,
[manifest.json](manifest.json)은 변경 소스·문서·시험·로그의 SHA-256을 기록한다.

| 증거 | 결과 |
|---|---|
| [prefix-reproduction.log](prefix-reproduction.log) | 수정 전 소스에서 `DrainPoisonMessage` 6개 시험 실행: FAILED(failures=3, errors=6). `PushFailed`가 드레인을 죽이고, 깨진 JSON이 받은편지함에 남고, 최상위 catch가 RV_RESULT 없이 traceback으로 끝나 finding이 재현된다 |
| [runner-adapter-tests.log](runner-adapter-tests.log) | 실제 실행기 시험 67개 통과(`DrainPoisonMessage` 6개 포함), 종료 0 |
| [poison-tests.log](poison-tests.log) | 독성 메시지 시험 6개 통과, 종료 0. Git 어댑터의 `subprocess.TimeoutExpired` 유형도 격리·후속 전달 검사에 포함 |
| [python-tests.log](python-tests.log) | 전체 Python 1,590개 실행, 실패·오류 0, 기존 skip 6개, 종료 0 |
| [r2-tests.log](r2-tests.log) | R2 예산·체크포인트·문서 회귀 146개 통과, 종료 0. admission deadline 거부·실행 시간 초과·정산 검사 포함 |
| [모의 시나리오](mock-scenarios.log) | 검사 695건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 종료 0 |
| [데몬 회귀](../../daemon/reports/unittest.log) | 296개 통과, 종료 0; `runner_verify/`는 소스 해시 대상이 아니라 로그 재생성 없음 |
| [static-checks.log](static-checks.log) | 공용 코어 정적 검사 13/13 통과, 종료 0 |
| [rust-tests.log](rust-tests.log) | 워크스페이스 514개 통과, 기존 ignored 1개, 종료 0 |
| [ontology-runner-tests.log](ontology-runner-tests.log) | 온톨로지 실행기 4개 통과, 종료 0 |
| [spec-check.log](spec-check.log) | 기계 검사 46/46·존재 검사 72/72 통과, 종료 0 |
| [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) | 어휘·검증 자료 일관성·변조 탐지 검사 통과, 종료 0 |
| [blueprint-status.log](blueprint-status.log), [blueprint-counts.log](blueprint-counts.log) | 결정 색인·등록 수 일치, 종료 0 |

핵심 회귀는 `DrainPoisonMessage`다. 다섯 가지 예외(`PushFailed`·`TimeoutError`·
`subprocess.TimeoutExpired`·`AttributeError`·`TypeError`) 각각에서 독성 파일 앞뒤의 정상 메시지가 전달되고
`daemon_done/`의 `ok:False` 기록·원본 보존을 검사한다. 깨진 JSON은 건너뛰기 대신
같은 격리를 받고, 가드 대기(`issue_lease.on_guard_wait`) 봉투는 여전히 받은편지함에
남아 다음 드레인에서 재전달된다. 실제 프로세스 시험은 실제 어댑터 위에서 같은
드레인 안의 세 독성 파일(`"envelope": "x"`의 `AttributeError`, 깨진 JSON의
`JSONDecodeError`, 미발급 자격 푸시의 `PushFailed`)을 격리하고 뒤의 첫 하트비트가
leased→building으로 수락되는 것을 본다. HTTP 시험은 잘못된 본문 두 건이 오류
응답을 받고 서버가 세 번째 정상 메시지를 수락하는 것을 본다.

기존 skip 6개는 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개,
설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 시험 1개다.

수정 1라운드(2026-11-13): 감독자의 로컬 재실행에서 1,590개 중 오류 1건
(`r2_budget.BudgetError: run time 170s exceeds limit 120s`)이 나왔다. 독성
메시지 전달 경로가 아닌 R2 예산 검사에서 발생했다.
`test_r2_budget.py`·`test_r2_checkpoint.py`의
`EndToEnd`는 실제 botocore HTTP를 로컬 스텁에 보내면서 실제 시계로 admission
한도(120초)를 재는데, 호스트 부하가 높으면 HTTP가 멈춰 한도를 넘긴다.
두 `EndToEnd`의 setUp에서 `mock.patch.object(b, "time", wraps=b.time)`로
r2_budget의 시계만 고정했다(`test_r2_checkpoint.py`가 이미 쓰던 방식).
botocore·서버 타임아웃은 실제 시계를 유지하고 요청·바이트 회계 단언은
그대로다. 마감(deadline) 동작은 시계를 명시적으로 진행시키는 전용 시험들이
계속 검증한다. 운영 코드와 예산 정책은 변경하지 않았다.
[r2-tests.log](r2-tests.log)는 두 모듈과 R2 문서 검사의 독립 재실행 기록이다.
이번 확인 중 이전 시도의 실행기 시험 프로세스가 같은 로그에 쓰고 있어
중복 실행을 중단한 뒤 실행기 전체 시험을 처음부터 다시 실행했다.
중단된 실행은 통과 증거로 세지 않는다.

그 전체 실행은 R10의 자격 발급 하위 프로세스가 300초 제한을 넘겨 실패했다
([runner-adapter-tests-first.log](runner-adapter-tests-first.log), 67개 중 실패 2개는
같은 R10 실패와 집계 검사다). [r10-recheck.log](r10-recheck.log)의 독립 실행은
검사 10개가 모두 PASS였다. 이후 다른 시험 실행과 겹치지 않게 전체 실행기
시험을 다시 실행했으며 최종 결과는 위 `runner-adapter-tests.log`에 남긴다.
시간 제한을 늘리거나 실패 검사를 생략하지 않았다.

재현(루트에서 Rust·잠긴 의존성 준비 후):

```sh
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify.DrainPoisonMessage -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v
python3 -m unittest tools/tests/test_daemon_dry_run.py
python3 -I tools/daemon/static_checks.py
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
python3 -m unittest discover -s tools/tests -v
python3 -m unittest discover -s tools/tests -p 'test_r2_*.py' -v
cargo test --all --locked --offline
cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I tools/blueprint_status.py
python3 -I tools/blueprint_counts.py
```

이번 작업에서 제품 저장소의 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
실행기 시험의 Git 원격은 표식이 붙은 임시 로컬 bare 저장소다.
이 증거는 09 §5의 개발 도구 보강이며 P01~P19의 완료 판정을 바꾸지 않는다.
