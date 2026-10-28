# Fix round 1 — 반복 감사 후 체크포인트 복구

기준 커밋: `7b7831b09d5e36cefc25dc4c16457fc6e0e4fc3c` + 이 작업 트리 변경.

검토 P1: 100건에서 `audit` 5회가 원장을 110건으로 키우면, 체크포인트 예약 전 읽기가 입장 Class B 한도 110을 넘어서 영구 잠금을 다시 만든다.

수정: `Session.open()`은 `purpose == "checkpoint"`에만 원장 상한 우회를 허용한다. 감사는 일반 읽기·쓰기 상한을 지키며, 한도에서 먼저 체크포인트를 실행하라는 오류로 거부된다. 입장·프로필·비용 한도는 올리지 않았다. 거부된 감사도 입장을 남겨 비용을 계상한다.

회귀:

- 로컬 원장: 90건 → 감사 5회 성공 → 100건 → 감사 6회 거부(원장 100건 유지, 입장 기록 유지) → 체크포인트 101·정산 102 → 일반 읽기 및 예약 후 전체 감사 재개.
- 루프백 S3 스텁: 배포된 입장 한도와 `initial-119.json`의 `verify`·`status` 프로필로 100건에서 감사 6회 거부. 거부는 원장 GET 전에 이루어지며 Class B 2회씩이다. 이후 체크포인트 예약 전 Class B는 102/110, 체크포인트 101·정산 102가 성공하고 일반 실행은 원장 GET 2회로 재개한다. 전체·작업 caps는 임시 시험 정책으로 격리했다.

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | 구현 변경 전 새 회귀 2개 모두 실패 |
| [after.log](after.log) | 구현 변경 후 같은 회귀 2개 모두 통과 |
| [budget-tests.log](budget-tests.log) | `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v`: 118개 통과, 종료 0 |
| [python-tests.log](python-tests.log) | `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v`: 1,221개 실행·실패 0·건너뜀 6, 종료 0 |
| [rust-tests.log](rust-tests.log) | `cargo test --all --locked`: 466개 통과·1개 무시, 실패 0, 종료 0 |
| [rust-lint.log](rust-lint.log) | `cargo clippy --all-targets -- -D warnings`: 종료 0 |
| [consistency-checks.log](consistency-checks.log) | 어휘·검증 자료·검증기 selftest·설계 수치·잠금 규칙·spec_check·데몬 dry_run·cargo fmt·git diff 검사 모두 종료 0 |

Python 건너뜀은 비공개 로컬 원본이 필요한 기존 검사 5개와 설치된 botocore에 해당하지 않는 구버전 검사 1개다. 새 회귀는 모두 실행했다.

전체 Python 결과와 소스·증거 해시는 [manifest.json](manifest.json)에 기록한다.

실제 R2·외부 서비스에 접근하지 않고 임시 로컬 저장소와 루프백 스텁만 사용했다. 자격 증명을 사용하거나 커밋·푸시·GitHub 호출을 하지 않았다. 이 검증은 보관 도구의 비용 통제 경계이며, 수집·화면·출시 완료 증거가 아니다.
