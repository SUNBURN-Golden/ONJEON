# Fix round 1 — deferred dispatch fencing (P1)

기준: `ed017d6a672cde82a67bc2ef2880287edb3afcb5` + 이 worktree의 미커밋 변경.
설명: [감리 기록의 fix round 1](../../../../docs/blueprint/audits/2026-10-28_daemon_fenced_write_dedupe.md#fix-round-1--커밋-후-임대-교체-경쟁-p1).

커밋 후 발송 전에 바뀐 임대를 재검사하고, 원격 호출이 끝날 때까지 저장소 변경과 같은 배타 잠금을 유지한다. 원격 쓰기는 계속 커밋 후 트랜잭션 밖에서 한다. `PushRemote`는 요청과 같은 임대의 활성 자격만 선택한다.

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | 추가 회귀 2개, 하위 사례 포함 실패 16건. 두 사건·두 저장소의 교체·종료·만료 경쟁 및 자격 선택 재현 |
| [after.log](after.log) | `FencedWriteDedup` 16개 통과. 기존 중복·롤백 사례, 발송 전 변경 거부, 발송 중 교체 대기, 별도 OS 프로세스의 FileStore 변경 대기, 자격 선택 |
| [runner-adapters.log](runner-adapters.log) | 실행기 `Adapters` 7개 통과. 파일 트랜잭션의 원자성·중첩 거부·중간 강제 종료 후 복구 포함 |
| [공용 unittest.log](../../../daemon/reports/unittest.log) | 데몬 시험 261개 통과, 현재 소스 해시 포함 |
| [공용 dry_run.log](../../../daemon/reports/dry_run.log) | 검사 704건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 현재 소스 해시 포함 |
| [python-tests.log](python-tests.log) | `unittest discover -s tools/tests -v`: 1,179개 실행, 실패·오류 0, skip 6, 종료 0 |
| [cargo-tests.log](cargo-tests.log) | `cargo test --all` 종료 0. 기존 `regenerate_declared_abox_fixture` 1개 ignored |
| [checks.log](checks.log) | 어휘·검증 자료·selftest·설계 묶음·BLUEPRINT 등록 수·결정 색인 6개 명령 모두 종료 0 |

Python skip 6개는 원본 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개, 설치된 botocore에 해당하지 않는 구버전 거부 시험 1개다. 새 회귀·데몬·실행기 어댑터 시험의 skip은 없다.

재현 명령(저장소 루트):

```sh
python3 -m unittest tools.tests.test_daemon_dry_run.FencedWriteDedup -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify.Adapters -v
python3 -m unittest tools/tests/test_daemon_dry_run.py -v
python3 -m unittest discover -s tools/tests -v
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
cargo test --all
```

새 경쟁·자격 시험의 Git 어댑터는 spy다. OS 프로세스 시험은 임시 JSON 상태 저장소만 변경한다. 실제 Git·GitHub 쓰기, 운영 자격·원격 접근, 전체 실제 실행기 시나리오는 실행하지 않았다. 이 증거는 개발 도구의 로컬 회귀 검증이며 상주 데몬 가동·출시 승인이 아니다.

잠금은 저장소 전체 범위이므로 원격 호출 동안 다른 저장소 변경도 기다린다. 커밋·원격 쓰기의 원자성, 미발송 intent 자동 복구, exactly-once 전달은 보장하지 않는다.
