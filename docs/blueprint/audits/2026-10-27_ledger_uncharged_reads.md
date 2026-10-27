# Audit 2 — GET 실제 바이트와 원장 읽기 계량

대상: `audit2-ledger-uncharged-reads`, `tools/source_archive.py::S3Store.get`, `tools/r2_budget.py::Session.open/Meter.charge_get_bytes`.
연결: Blueprint A1·L1~L2·M1, ADR-0017, 09 제품 목적 대응표 P02·P03.

## 발견과 수정

기존 GET은 응답의 `ContentLength or 0`을 본문 읽기 전에 집계했다. 길이가 없거나 작게 표시되면 실제 읽은 바이트가 빠지고, 길이가 크게 표시되거나 읽기가 실패하면 읽지 않은 바이트까지 집계했다. 원장 저장소는 `start`가 `ACTIVE`를 설정하기 전에 생성되어 `meter=None`을 유지했다. HTTP 요청 횟수는 이벤트 훅으로 집계됐지만 원장·체크포인트 GET 본문은 내려받기 사용량에서 빠졌다.

이제 `S3Store.get`은 최대 64 KiB씩 읽고 반환된 바이트 길이를 집계한다. `ContentLength`는 집계 근거로 쓰지 않는다. 각 읽기는 남은 한도 + 1바이트 이하이며, EOF 확인에 필요한 추가 1바이트도 사용량에 포함하고 초과 시 즉시 중단한다. 계량기는 이미 읽은 바이트를 오류 뒤에도 유지한다. 성공·한도 초과·읽기 오류 모두 응답 스트림을 닫는다. 한도를 이미 초과한 계량기로는 본문을 더 읽지 않는다.

`Session.open`은 기본 생성한 원장과 주입받은 S3 원장 모두에 세션 계량기를 명시적으로 연결한다. 예약 전 읽기는 입장 한도로, 예약 뒤 읽기는 실행 한도로 같은 카운터에 쌓인다. `finish`가 `ACTIVE`를 비운 뒤 정산용 꼬리를 읽어도 연결된 계량기로 집계한다. 정책·한도·정책 해시와 기존 원장은 바꾸지 않았다.

이 값은 GET 본문 스트림이 반환한 바이트이며 소켓 계량값이 아니다. HTTP 파서가 내부에서 읽은 뒤 예외와 함께 반환하지 않은 바이트, LIST·오류 응답 본문은 측정하지 않는다. 정산은 기존처럼 예약 이하로 기록한다. 내려받기 한도를 초과하여 정산 꼬리 읽기도 실패하면 미정산 예약 전액이 유지된다. 운영 설명은 [BUDGET.md §3·§5](../../../infra/r2/BUDGET.md)에 반영했다.

## 회귀 증거

- [GetBytes·MeterChecks](../../../tools/tests/test_r2_budget.py): 헤더 누락·0·과소·과대 표기, 여러 청크, 짧은 읽기, 빈 본문, 정확한 한도, 초과 시 1바이트만 추가로 읽고 집계, 이미 초과한 한도에서 추가 읽기 거부, 읽기 오류·botocore 길이 불일치 오류 전 반환된 바이트 유지, 성공·실패 시 스트림 닫기를 검증한다.
- 같은 파일의 `EndToEnd`: 실제 botocore와 루프백 S3 스텁으로 원장·체크포인트의 예약 전 GET, 보관소 GET, `finish` 이후 꼬리 GET의 본문 크기 합계를 정산·요약의 `get_bytes`와 정확히 대조한다. 기본·주입 원장을 모두 검사한다. 입장 내려받기 한도가 부족하면 입장 기록만 남고 새 예약 없이 중단하며 로컬 잠금이 해제되는지도 검증한다.
- [수정 전 재현 로그](../../../tools/evidence/audit2-ledger-uncharged-reads/before.log): HEAD의 두 구현 파일을 별도 Python 프로세스의 메모리에만 로드해 신규 시험 3개를 실행했다. 헤더 의존 집계·읽기 상한 부재·원장 계량기 누락으로 실패했다(하위 사례 포함 실패 9개·오류 2개, 종료 1). 작업 트리의 구현 파일은 되돌리지 않았다.

## 검증 범위

모든 시험은 이 작업 트리의 임시 파일·모의 스트림·루프백 S3 스텁으로 실행했다. 실제 R2나 실제 자격 증명을 사용하지 않았다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 107개 통과, 종료 0 | [예산·체크포인트](../../../tools/evidence/audit2-ledger-uncharged-reads/budget-tests.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 980개 실행, 974개 통과·6개 건너뜀, 종료 0 | [전체 Python](../../../tools/evidence/audit2-ledger-uncharged-reads/python-tests.log) |
| `cargo test --all --locked` | 447개 통과·실패 0개·1개 무시, 종료 0 | [전체 Rust](../../../tools/evidence/audit2-ledger-uncharged-reads/rust-tests.log) |
| 어휘·검증 자료·검증기 selftest·제품 목적 연결·설계 명세·`cargo fmt`·`cargo clippy` | 모두 종료 0 | [정합성 검사](../../../tools/evidence/audit2-ledger-uncharged-reads/consistency-checks.log) |
| 온톨로지 runner 빌드·전체 검사 | 모두 종료 0 | [온톨로지](../../../tools/evidence/audit2-ledger-uncharged-reads/ontology-checks.log) |
| `git diff --check`·변경 경로 검사·구현/시험 SHA-256 기록 | 종료 0 | [최종 검사](../../../tools/evidence/audit2-ledger-uncharged-reads/final-checks.log) |

전체 Python 시험은 기존 온톨로지 시험이 실행 파일을 해당 크레이트의 `target/debug`에서 찾으므로 외부 `CARGO_TARGET_DIR`만 해제해 실행했다. 건너뜀 6개는 로컬 비공개 원본이 필요한 기존 검사 5개와 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 신규 회귀 시험 11개는 모두 실행·통과했다.

이 증거는 원본 보관 도구의 비용 통제 수정에 한정한다. 실제 공시 확보율·R2 관측 목록 대조·변경 재처리·소비자 화면·출시 완료 증거를 대신하지 않으며 P02·P03을 완료 처리하지 않는다.
