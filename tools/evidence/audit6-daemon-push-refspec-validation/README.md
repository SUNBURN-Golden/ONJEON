# audit6-daemon-push-refspec-validation 실행 증거

2026-11-11. [수정 기록](../../../docs/blueprint/audits/2026-11-11_daemon_push_refspec_validation.md) ·
[모의 코어 회귀](../../tests/test_daemon_dry_run.py) ·
[실제 git 원격 회귀](../../daemon/runner_verify/tests/test_runner_verify.py).
기준 커밋 `1f0ef65e06485e23551878d30ff783248db28602` 위 미커밋 변경이다.

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | 수정 전 구현(HEAD)에 회귀 시험 추가 실행: 모의 코어 10개 실패 46·오류 1, 실제 git 원격 3개 실패 18·오류 2, 종료 1 |
| [after.log](after.log) | 수정 후 회귀 13개(모의 코어·어댑터 10 + 실제 git 원격 3) 통과, 종료 0 |
| [모의 시나리오](../../daemon/reports/dry_run.log) | 검사 692건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 종료 0 |
| [데몬 회귀](../../daemon/reports/unittest.log) | 299개 통과, 종료 0; 현재 소스 내용 해시 기록 |
| [python-tests.log](python-tests.log) | 전체 Python 1,567개 실행, 실패·오류 0, 기존 skip 6, 종료 0 |
| [rust-tests.log](rust-tests.log) | 워크스페이스 `cargo +1.98.1 test --all --locked --offline`: 514개 통과, 기존 fixture 재생성 1개 ignored, 실패 0, 종료 0 |
| [ontology-runner-tests.log](ontology-runner-tests.log) | 온톨로지 실행기 `cargo test --locked --offline`: 4개 통과, 종료 0 |

재현 명령(저장소 루트):

```sh
# before.log: 구현만 HEAD로 되돌리고(시험은 유지) 아래 두 실행의 출력
python3 -m unittest tools.tests.test_daemon_dry_run.PushRefspecFencing \
  tools.tests.test_daemon_dry_run.PushRefspecAdapter -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify.PushRefspecGit -v
# after.log: 위 두 명령을 수정 후에 다시 실행
python3 -m unittest discover -s tools/tests -v                       # python-tests.log
cargo +1.98.1 test --all --locked --offline                           # rust-tests.log
cargo +1.98.1 test --locked --offline \
  --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml  # ontology-runner-tests.log
```

`daemon_rules.json`은 HEAD와 구조 대조해 `fenced_write.checks[push_refspec]`·`on_fail.invalid_refspec`·
`_note` 설명 외에 변함이 없음을 확인한 뒤 [o13 픽스처](../../tests/fixtures/o13_unchanged_gates.json)의
파일 해시를 갱신했다. before.log의 `--receive-pack` 등 위험 모양은 모두 합성 값이며 실제 원격·자격증명이 아니다.

전체 runner_verify 시험(`python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py`,
63개)은 이 노드와 무관한 기존 실패 1건이 있다: `ScenarioAggregates.test_no_secret_or_raw_output_in_the_results`가
시나리오 증거 `handoff_timeline_ns`의 `"revoke_token": <나노초 시각>`을 일반 `token` 대입 패턴으로 오탐한다.
HEAD를 그대로 내보낸 트리에서 같은 실패를 확인했다(이 노드 변경 전 상태). 이 노드가 손대지 않은
비밀값 패턴·시나리오 증거 영역이므로 별도 후속 노드 몫으로 남긴다.

수정 1차(2026-11-12): 로컬 시험 실패는 이 작업 트리에 rustup 재정의가 없어서 cargo가 도구 체인을
고르지 못한 환경 문제였다(구현 변경 없음). 저장소 루트 README의 절차대로
`rustup override set --path "$PWD" 1.98.1`을 등록하고 전체 관문을 다시 실행했다:
Python 1,567개 통과(skip 6), `cargo test --all --locked --offline` 514개 통과(ignored 1),
온톨로지 실행기 4개 통과, `cargo fmt --check`·`clippy -D warnings`·비밀값 검사·vocab·validation·
blueprint_counts·spec_check(46/46·72/72)·ontology_check·모의 시나리오 692건(필수 ID 33/33) 모두 종료 0.
아래 python-tests.log·rust-tests.log·ontology-runner-tests.log는 이 재실행 결과로 갱신했다.
runner_verify의 기존 실패 1건은 HEAD 내보내기 트리에서 같은 단건 시험으로 다시 확인했다.
`tools/verify_sources.py`의 ResourceWarning은 수정 전부터 있던 것으로(시험 실패 아님) 이 노드 범위 밖이다.
