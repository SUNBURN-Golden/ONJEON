# audit3-r2-ledger-cap-lockout 실행 증거

최신 수정·검증은 [fix-round2/README.md](fix-round2/README.md)를 참조한다. 실패한 체크포인트가 뒤받침을 키우지 않도록 체크포인트 저장을 예약 앞으로 옮기고 모든 쓰기에 상한을 적용했다. 아래 로그·해시·개수는 초기 수정 당시의 이력이며, 감사의 상한 우회는 fix round 1에서 제거했다.

기준 커밋 `568c298f413c59e5b84718fe8fc70f45269de635` + 이 노드의 미커밋 변경. [감리 수정 기록](../../../docs/blueprint/audits/2026-10-28_ledger_cap_lockout.md)과 회귀 시험([test_r2_checkpoint.py](../../tests/test_r2_checkpoint.py) `Lockout`, [test_r2_budget.py](../../tests/test_r2_budget.py) `LedgerRecordCap`)을 참조한다. 수정 범위는 원본 보관 도구의 비용 통제이며 P01~P19 출시 완료 증거가 아니다.

| 증거 | 실행·결과 |
|---|---|
| [before.log](before.log) | HEAD 구현을 메모리에만 로드(`git show HEAD:tools/r2_budget.py`)해 실행. 100건 원장에서 `write_checkpoint`와 일반 세션 모두 `>= 100` 거부(영구 잠금 재현). 신규 회귀 10개 중 8개 오류(`purpose`·`over_limit_ok` 부재), `tail`/`append` 대조 통과, S3 스텁 시험은 격리 Python의 boto3 부재로 건너뜀. 종료 1 |
| [after.log](after.log) | 같은 절차를 현재 코드로 실행. 일반 원장·일반 세션은 계속 거부, `purpose="checkpoint"` 세션은 예약 101·체크포인트 101·정산 102, 다음 읽기 `base_seq 101`·기록 `[102]`. 신규 회귀 10개 모두 통과, 종료 0 |
| [budget-tests.log](budget-tests.log) | `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v`: 117개 통과, 종료 0 |
| [python-tests.log](python-tests.log) | `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v`: 1,220개 실행, 실패·오류 0, 건너뜀 6, 종료 0 |
| [rust-tests.log](rust-tests.log) | `cargo test --all --locked`: 합계 466개 통과·실패 0·1개 무시, 종료 0 |
| [rust-lint.log](rust-lint.log) | `cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`: 모두 종료 0 |
| [consistency-checks.log](consistency-checks.log) | `vocab_check`·`validation_check`·selftest(변조 38)·`blueprint_counts`·`r2_budget.py lock-rules`·`git diff --check`·설계 묶음 `spec_check`(45/45·72/72)·데몬 `dry_run --scenario all --require-all` 모두 종료 0. 추가 `tools/ci/tests` 20개 중 2개는 기존 DEP-ZONE 의존성 위반으로 실패(관련 4개 파일 모두 HEAD와 동일 — 기준선 문제) |
| [manifest.json](manifest.json) | 변경 소스·신규 회귀 시험 해시와 실행 결과 |

Python 건너뜀 6개는 비공개 로컬 원본이 필요한 기존 검사 5개와 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 검사 1개다. 신규 회귀 시험의 건너뜀은 없다.

재현:

```sh
python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v
python3 -m unittest discover -s tools/tests -v
python3 tools/vocab_check.py && python3 tools/validation_check.py --selftest
python3 -I tools/blueprint_counts.py && python3 -I tools/r2_budget.py lock-rules
cargo test --all --locked
```

임시 로컬 원장과 루프백 S3 스텁으로만 실행했다. 실제 R2·자격 증명·커밋·푸시·GitHub 호출은 없다.
