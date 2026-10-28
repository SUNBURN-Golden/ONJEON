# audit3-daemon-static-check-bypasses 실행 증거

기준 커밋 `285b9edf1dd60b80b9a7414a46d94d46ab83ecab` + 이 노드의 미커밋 변경. [감리 수정 기록](../../../docs/blueprint/audits/2026-10-28_daemon_static_check_bypasses.md)과 [회귀 시험](../../tests/test_daemon_static_checks.py)을 참조한다. 수정 범위는 T-OP-00 개발 도구이며 P01~P19 출시 완료 증거가 아니다.

| 증거 | 실행·결과 |
|---|---|
| [before.log](before.log) | 기존 검사기에 신규 회귀 16개 실행. 하위 사례 포함 실패 124건·오류 17건, 종료 1. 기존 루프 검사에 경로 인자가 없는 오류도 포함 |
| [after.log](after.log) | 같은 회귀 16개 모두 통과, 종료 0 |
| [python-tests.log](python-tests.log) | `python3 -m unittest discover -s tools/tests -v`: 1,201개, 실패·오류 0, skip 6, 종료 0 |
| [전체 데몬 시험](../../daemon/reports/unittest.log) | `python3 -m unittest tools/tests/test_daemon_dry_run.py -v`: 267개 모두 통과, 종료 0 |
| [전체 모의 시나리오](../../daemon/reports/dry_run.log) | `dry_run.py --scenario all --require-all`: 검사 692건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 종료 0 |
| [runner-verify-tests.log](runner-verify-tests.log) | 기존 별도 검사 경계 회귀: `python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py -v`, 59개 통과, 종료 0 |
| [rust-tests.log](rust-tests.log) | `cargo test --all`, 종료 0. 기존 fixture 재생성 시험 1개 ignored |
| [checks.log](checks.log) | 어휘·검증 자료·변조 selftest·설계 묶음·BLUEPRINT 결정 색인·정적 CLI 통과. CLI는 실제 13개 검사 실행. 추가 `tools/ci/tests` 20개 중 기존 의존성 관련 2개 실패 |
| [blueprint-counts.log](blueprint-counts.log) | `python3 -I tools/blueprint_counts.py`, 종료 0 |
| [baseline-dependencies.log](baseline-dependencies.log) | 위 의존성 위반 3건의 규칙·소스 네 파일이 HEAD와 동일함을 바이트·SHA-256으로 대조. `check_deps.py` 종료 1 재현 |
| [manifest.json](manifest.json) | 변경 소스·신규 회귀 시험 해시와 실행 결과 |

회귀는 builtins 매핑·속성·별칭, 금지 멤버의 리터럴 `getattr`, `os`의 프로세스 실행 함수 23종 참조·가져오기·별칭, 네이티브 실행 모듈, 상대 가져오기, 참 리터럴 루프를 검사한다. 다른 위치의 `static_checks.py`와 동명 `runner_verify/`가 검사 제외를 상속하지 않는지도 확인한다. 정상 데이터·`re.compile`·일반 객체 `getattr`·입력 의존 루프를 양성 대조로 둔다. CLI 시험은 격리 Python·다른 cwd·복사 소스의 주입 위반·입력/소스 오류를 포함하며 위험한 주입 소스를 실행하지 않는다.

Python skip 6개는 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다. 신규 회귀·전체 데몬·별도 실행기 시험의 skip은 없다.

추가 CI 실패는 `packages/ontology/Cargo.toml`, `packages/ontology/tests/common/mod.rs`, `packages/ontology/tests/fixture_origin/main.rs`의 knowledge→twin 의존성·가져오기를 `infra/ci/deps.json`이 거부하는 기존 문제다. 이 노드는 해당 정책·파일을 변경하지 않는다. 전체 검사 통과로 보고하지 않는다.

재현:

```sh
python3 -m unittest tools/tests/test_daemon_static_checks.py -v
python3 -I tools/daemon/static_checks.py
python3 -m unittest tools/tests/test_daemon_dry_run.py -v
python3 -m unittest discover -s tools/tests -v
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py -v
cargo test --all
python3 -m unittest discover -s tools/ci/tests -v
```

데몬 공용 보고서의 현재 소스 해시는 `137dff4091ec8316d317e53d40ac0feeeddf599cd16184693de3e67d231b7457`이다. [도구 README의 해시 절차](../../daemon/README.md#증거-기록reports)와 기존 `Cli.test_evidence_logs_name_the_parent_commit_and_source_hash`로 대조했다. 신규 시험 파일의 개별 해시는 manifest에 추가했다.

작업 저장소에 커밋·푸시하거나 GitHub·실제 제공자를 호출하지 않았다. 기존 실행기 시험의 Git 쓰기는 임시 로컬 시험 저장소에 한정되고 제공자 검증은 로컬 프록시·더미 자격을 쓴다. 정적 검사는 Python 샌드박스나 계산된 속성명·일반 데이터 흐름·입력 의존 무한 루프에 대한 완전한 증명이 아니다.


후속 병합: gate-touched-paths 노드의 수정 3차에서 공용 데몬 보고서를 두 노드가 합쳐진 소스로 재생성했다. 위 267개 시험·소스 해시는 이 노드 단독 검증 당시 기록이다. 현재 공용 보고서의 출처와 양쪽 회귀 시험 실행 결과는 [병합 검증 기록](../../../docs/blueprint/audits/2026-10-28_daemon_gate_touched_paths.md#수정-3차--main-정적-검사-보강과-병합)과 [round3 증거](../audit3-daemon-gate-touched-paths/round3/)를 참조한다.
