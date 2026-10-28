# Fix round 2 — 실패한 체크포인트 뒤에도 복구 가능

기준 커밋: `c1ace43b804777f9de9903c0c24a62de353ba738` + 이 작업 트리 변경.

검토 P1: 체크포인트 PUT만 실패하면 예약·정산 두 건이 남아 100 → 102 → 104 → 106 → 108 → 110건이 된다. 쓰기를 복구해도 다음 체크포인트 실행은 예약 전 읽기 입장 한도 Class B 110에 막힌다.

수정: 체크포인트를 입장 한도 안에서 **예약 전에** 저장·확인한다. 검증한 기록·입장 목록을 재사용하고, 예산·남은 입장 몫 검사도 저장 전에 유지한다. `over_limit_ok`는 복구 읽기에만 적용하며 모든 `append()`는 상한을 지킨다. 실패는 입장만 남겨 원장을 키우지 않고, 성공은 체크포인트 100 → 예약 101 → 정산 102다. CLI는 입장 단계에서 저장한 결과를 출력하여 중복 체크포인트를 쓰지 않는다. 입장·프로필·전체/작업 caps·월별 입장 제한은 올리지 않았다.

회귀:

- 실제 botocore + 루프백 S3 스텁: 배포된 입장 한도와 `initial-119.json`의 `verify`·`status` 프로필, 격리된 전체/작업 caps로 100건에서 체크포인트 PUT만 다섯 번 실패. 매번 원장 100건 유지·예약 없음·입장 1~5건·잠금 해제·자료 접근 불가·입장 계량기 유지. 서버 요청/업로드 바이트를 계량기와 대조한다. 쓰기 복구 뒤 체크포인트·예약·정산·일반 실행·전체 감사 성공, 실패 입장 전액 계상과 요약/전체 사용량 동등성을 확인한다.
- 실제 CLI + 로컬 원장: 다섯 실패 뒤 성공, 실패의 ACTIVE/예약/잠금 정리, 성공 시 체크포인트 한 개·정산 102.
- 크기 검사 실패 다섯 번 뒤 복구, 체크포인트 저장 후 예약 경쟁의 재읽기·해시 연결·감사, 빈/이미 요약된 원장의 `nothing_new` 경로.
- 기존 99/100건·기존 체크포인트 뒤 100건 복구, 일반/감사 상한, 복구 플래그가 있어도 101번째 append 거부, 예산 caps 거부 회귀도 갱신·실행했다.

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | 구현 변경 전 새 S3 회귀 실패: 첫 실패만으로 102건이 되어 `102 != 100` |
| [after.log](after.log) | 위 새 회귀 5개 모두 통과, 건너뜀 없음 |
| [budget-tests.log](budget-tests.log) | `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v`: 123개 통과, 종료 0 |
| [python-tests.log](python-tests.log) | `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v`: 1,226개 실행·실패 0·건너뜀 6, 종료 0 |
| [rust-tests.log](rust-tests.log) | `cargo test --all --locked`: 466개 통과·1개 무시, 실패 0, 종료 0 |
| [rust-lint.log](rust-lint.log) | `cargo clippy --all-targets -- -D warnings`: 종료 0 |
| [consistency-checks.log](consistency-checks.log) | 어휘·검증 자료·검증기 selftest·설계 수치·잠금 규칙·spec_check·데몬 dry_run·cargo fmt·git diff 검사 모두 종료 0 |
| [manifest.json](manifest.json) | 결과·변경 소스/증거 SHA-256 |

Python 건너뜀은 비공개 로컬 원본이 필요한 기존 검사 5개와 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 새 회귀는 모두 실행했다.

실제 R2·외부 서비스·자격 증명에 접근하지 않고 임시 로컬 원장과 루프백 S3 스텁만 사용했다. 커밋·푸시·GitHub 호출은 하지 않았다. 월별 입장·비용 제한은 계속 적용한다. 이미 읽기 입장 한도를 넘은 과거의 비정상 원장을 복원했다는 증거는 아니다. 이 검증은 보관 도구의 비용 통제 경계이며 수집·화면·출시 완료 증거가 아니다.
