# Audit 2 — 원장 100건 상한 경계 수정

대상: `audit2-ledger-cap-off-by-one`, `tools/r2_budget.py::Ledger.read/append`.
연결: Blueprint A1·L1~L2·M1, ADR-0017, 09 제품 목적 대응표 P02·P03.

## 발견과 수정

`read`의 기존 `len(keys) > limit`는 원장이 정확히 100건일 때도 실행을 허용했다. 이후 예약·정산이 101·102번째 기록을 쓸 수 있었다. 이제 `>=`로 거부하고, `append`도 `count - base_seq >= limit`면 저장소 PUT 전에 중단한다. 체크포인트가 없으면 전체 기록 수, 있으면 해당 체크포인트 뒤의 기록 수가 기준이다. 정책 한도·정책 해시·기존 원장 내용은 바꾸지 않았다.

98건에서 시작하면 예약 99·정산 100까지 기록한다. 99건에서 시작하면 예약 100까지 쓰고 정산은 `settlement_failed: BudgetError`를 반환한다. 이때 미정산 예약은 전액 사용한 것으로 계속 계산하며 로컬 잠금은 해제한다. 체크포인트 명령도 예산 실행이므로 100건에 닿기 전에 여유를 두고 실행해야 한다(기존 운영 권고: 80건 초과 시). 100건에서의 새 예약 거부는 추가 원장 GET·PUT 전에 일어나지만, 세션의 선행 입장·마감 확인까지 요청이 없다는 뜻은 아니다.

감사 `read(full=True)`는 전체 이력 검증을 위해 읽기 상한을 우회한다. `audit_checkpoints`가 별도 `Ledger` 판독기를 사용하게 하여 전체 읽기의 상태 초기화가 실행 중 원장의 체크포인트 위치를 지우지 않도록 했다. 따라서 전체 이력이 100건을 넘어도 체크포인트 뒤에 여유가 있으면 감사 후 정상 정산할 수 있다. 쓰기 상한은 우회하지 않는다.

## 회귀 증거

- [`test_r2_budget.py`](../../../tools/tests/test_r2_budget.py)의 `LedgerRecordCap`: 99건 읽기·100번째 쓰기 허용, 100건 예약 거부, 101·102번째 직접 쓰기의 PUT 전 차단, 98·99건에서 시작한 세션 정산, 마지막 자리 경쟁 후 상한 재검사를 검증한다.
- [`test_r2_checkpoint.py`](../../../tools/tests/test_r2_checkpoint.py)의 `Reads`: 체크포인트 유무에 따른 정확히 100건의 읽기 거부, 순번 98 체크포인트 뒤 기록 197·198 허용과 199 거부, 전체 이력 감사와 감사 후 정산을 검증한다. 기존 픽스처는 쓰기 전에 최신 체크포인트 위치를 읽도록 고쳤다.
- [수정 전 로그](../../../tools/evidence/audit2-ledger-cap-off-by-one/before.log): `git show HEAD:tools/r2_budget.py`를 메모리에만 로드하여 새 경계 시험 6개를 실행했다. 2개 통과·4개 시험 실패(하위 사례 포함 실패 6개), 종료 1. 원장 101·102번째 PUT 허용과 마지막 자리 경쟁 후 초과 예약·정산을 재현했다.

## 검증 범위

임시 로컬 원장과 S3 스텁을 사용한다. 실제 R2에 접근하거나 자격 증명을 사용하지 않았다. 모두 이 작업 트리에서 실행했다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 96개 통과, 종료 0 | [예산·체크포인트 로그](../../../tools/evidence/audit2-ledger-cap-off-by-one/budget-tests.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 969개 실행, 963개 통과·6개 건너뜀, 종료 0 | [전체 Python 로그](../../../tools/evidence/audit2-ledger-cap-off-by-one/python-tests.log) |
| `cargo test --all --locked` | Rust 결과 합계 447개 통과·실패 0개·1개 무시, 종료 0 | [Rust 로그](../../../tools/evidence/audit2-ledger-cap-off-by-one/rust-tests.log) |
| 어휘·검증 자료·검증기 selftest·제품 목적 연결·설계 명세·온톨로지 전체 검사·`cargo fmt`·`cargo clippy`·`git diff --check` | 모두 종료 0 | [명령·결과 로그](../../../tools/evidence/audit2-ledger-cap-off-by-one/consistency-checks.log) |

첫 전체 Python 실행은 968개 중 환경 오류 2개·건너뜀 6개로 실패했다([초기 로그](../../../tools/evidence/audit2-ledger-cap-off-by-one/python-tests-initial.log)). 환경의 `CARGO_TARGET_DIR`가 공용 경로를 가리키는데 기존 온톨로지 시험은 실행 파일을 해당 크레이트의 `target/debug`에서 찾아 발생했다. 이 환경 변수만 해제하여 최종 코드를 전체 재실행했고 모두 통과했다. Python 건너뜀 6개는 비공개 로컬 원본이 필요한 기존 검사 5개와 조건부 PUT을 이미 지원하는 botocore에 해당하지 않는 구버전 검사 1개다. 새 회귀 시험은 모두 실행했다.

이 증거는 원본 보관 도구의 비용 통제 경계에 한정한다. 실제 공시 확보율·R2 관측 목록 대조·화면·출시 완료 증거를 대신하지 않으며 P02·P03을 완료 처리하지 않는다.
