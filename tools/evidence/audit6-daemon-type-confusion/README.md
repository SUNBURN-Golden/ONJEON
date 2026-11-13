# audit6-daemon-type-confusion 실행 증거

2026-11-13. 기준 커밋 `a51a495a6eb2a8518825e1f7951ea915aa10a088` 위 미커밋 변경.
[감리 기록](../../../docs/blueprint/audits/2026-11-13_daemon_type_confusion.md) ·
[회귀 시험](../../tests/test_daemon_dry_run.py).

`true`·`1.0`이 정수 `1`과 같은 임대로 인정되면서 서로 다른 처리 키를 만드는 결함을 수정했다.
필수 정수 식별자는 정확한 `int`, 문자열 식별자는 공백 아닌 `str`로 검사한다.
술어 `==`·`!=`도 자료형을 구분한다. 정상 키 형식은 그대로 유지한다.
기존 push·PR 갱신 공용 `envelope_id` 기반 중복 방지는 내용·사건 종류 변경과 파일 저장소 재시작까지 검증했다.

## 실행 기록

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | 최종 신규 회귀 9개를 기준 커밋의 구현으로 실행: 하위 사례 포함 실패 250건, 오류 0, 종료 1 |
| [after.log](after.log) | 신규 회귀 9개 + 기존 결과 관문 회귀 20개, 총 29개 통과, 종료 0 |
| [전체 Python](python-tests.log) | 1,609개 실행, 실패·오류 0, 기존 skip 6개, 종료 0 |
| [공용 데몬 회귀](../../daemon/reports/unittest.log) | 315개 통과, 종료 0; 최종 소스 해시 기록 |
| [실행기 전체 시험](runner-tests.log) | 80개 통과, 종료 0 |
| [Rust 워크스페이스](rust-tests.log) | 515개 통과, 기존 ignored 1개, 종료 0 |
| [온톨로지 실행기](ontology-runner-tests.log) | 4개 통과, 종료 0 |
| [공용 모의 시나리오](../../daemon/reports/dry_run.log) | 검사 695건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 종료 0 |
| [정적 검사](static-checks.log) | 13/13 통과, 종료 0 |
| [명세 검사](spec-check.log) | 기계 46/46·존재 72/72 통과, 종료 0 |
| [비밀값](secrets-check.log)·[어휘](vocabulary.log)·[검증 자료](validation.log)·[selftest](validation-selftest.log) | 모두 종료 0 |
| [BLUEPRINT 상태](blueprint-status.log)·[등록 수](blueprint-counts.log) | 모두 종료 0 |

기존 skip 6개는 원본 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개,
현재 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다.
신규 회귀·데몬·실행기 시험의 skip은 없다.

## 시험 입력 정리와 재실행

[첫 데몬 실행](daemon-tests-first.log)은 315개 중 기존 회귀 2개가 실패했다.
두 시험은 오래된 `fencing_token`을 문자열 `"stale"`로 만들고 R-11을 기대했다.
엄격한 타입 검증에서는 문자열이 R-13으로 먼저 거부되므로, 두 시험의 토큰을
현재 토큰보다 1 작은 정수로 바꿨다. 오래된 **정수** 토큰의 R-11과 비밀값·범위·본문 검사보다
임대 검사가 앞서는 동작은 그대로 검사한다. 문자열 토큰의 R-13 거부는 신규 회귀가 검사한다.
당시 진행 중이던 전체 Python 실행은 같은 옛 시험 입력을 이미 읽은 상태여서 중단했다
([중단 로그](python-tests-interrupted.log), 성공 증거로 세지 않음).
구현을 완화하거나 실패 검사를 생략하지 않았으며, 수정 후 두 전체 시험을 다시 실행해 모두 통과했다.

## 재현

저장소 루트 README의 Rust·잠긴 의존성 준비를 마친 뒤 실행한다.

```sh
python3 -m unittest tools.tests.test_daemon_dry_run.EnvelopeIdentityTypes tools.tests.test_daemon_dry_run.FencedWriteIdentityTypes -v
python3 -m unittest tools.tests.test_daemon_dry_run -v
python3 -m unittest discover -s tools/tests -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
python3 -I tools/daemon/static_checks.py
cargo test --all --locked --offline
cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/check_tracked_secrets.py
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I tools/blueprint_status.py
python3 -I tools/blueprint_counts.py
```

`before.log`는 새 시험은 유지하고 수정한 코어 파일 3개만 `git show HEAD:<경로>`의 내용으로
일시 교체하여 생성한 뒤, `finally`에서 작업 소스를 복원했다. 공용 데몬 보고서의 머리말은
`tools/daemon/README.md`의 절차에 따라 부모 커밋과 최종 소스 내용 해시를 기록한다.

실행기 시험의 원격은 임시 로컬 bare 저장소이며 GitHub·운영 원격·실제 제공자를 호출하지 않는다.
이 작업 트리를 커밋·푸시하지 않았다. [09 §5](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의
개발 도구 검증이며 P01~P19의 실제 데이터·트윈·소비자 화면·출시 완료를 선언하지 않는다.
