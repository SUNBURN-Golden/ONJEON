# Audit 7 — 상태 저장소의 임시 파일 PID

`FileStore`의 임시 파일 이름은 `.state.json.<pid>.<id>.tmp`다. 시작 시 정리 코드가
인덱스 2의 `json`을 정수로 읽으려다 PID를 0으로 처리해, 살아 있는 프로세스의
파일도 삭제했다. 인덱스 3에서 PID를 읽도록 수정했다.
[저장소 어댑터](../../../tools/daemon/runner_verify/adapters.py).

| 회귀 시험 | 직접 실행 결과 |
|---|---|
| `test_store_preserves_a_live_writers_temp_file` | 수정 전에는 현재 프로세스 PID의 파일이 사라져 실패했다. 수정 후에는 새 `FileStore`가 시작해도 파일과 내용이 보존됐다. |
| `test_store_survives_a_kill_in_the_middle_of_a_write` | 쓰기 도중 `SIGKILL`로 종료한 자식 프로세스가 임시 파일 하나를 남겼다. 다음 시작에서 그 파일이 삭제됐고 이전에 커밋된 상태를 읽었다. |

두 시험은 `python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify.Adapters -v`로 재현한다.
[회귀 시험](../../../tools/daemon/runner_verify/tests/test_runner_verify.py).

## 프로젝트 검증

| 실행 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과. R18 강제 종료·복구 시나리오와 정적 검사 포함. |
| `python3 -m unittest discover -s tools/tests -v` | 1,764개 중 1,758개 통과, 기존 skip 6개. |
| `cargo test --all --locked --offline` | 537개 통과, 기존 ignored 1개. |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과. |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과. |
| 데몬 `dry_run.py --scenario all --require-all --quiet` | 검사 695건 통과, 필수 ID 33/33 실행. |
| 설계 묶음 `spec_check.py` | 기계 검사 47/47, 존재 검사 72/72 통과. |

초기 Cargo 실행에는 환경에 설정된 공유 빌드 캐시가 사용됐다. 표의 Rust 결과는
작업 트리 내부 빌드 경로에서 확인했다. Python 시험에는 시스템 기본 임시 경로를
사용했다. 작업 트리 내부 `TMPDIR`를 지정한 실행에서는 온톨로지의 저장소
외부 임시 파일 검증 3건이 실패했다. 기본 임시 경로에서 해당 모듈 6개 모두 통과했다.

검증 범위는 T-OP-09의 상태 저장소다.
[09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지).
