# Audit 2 — 원본 관측 추가 메타데이터의 예약 키 거부

대상: `audit2-archive-extra-overrides-hash`, `tools/source_archive.py::put_observation`.
연결: Blueprint A1·Q7·L1·I6(근거 사슬의 원본 관측 기반)·M1, 09 제품 목적 대응표 P02·P03.

## 발견과 수정

관측 레코드 생성 뒤 `rec.update(extra)`를 실행하여 `--extra '{"sha256":"forged","object_key":"forged"}'`가 실제 바이트에서 계산한 해시·보관 키를 덮어쓸 수 있었다. 같은 방식으로 출처와 관측 이력도 바꿀 수 있었다.

추가 메타데이터는 JSON 객체만 받으며 `source_id`, `url`, `observed_at`, `sha256`, `bytes`, `content_type`, `object_key`는 예약 키로 거부한다. 기존 값과 같은 값을 넣어도 거부한다. `put_observation`에서 직접 호출을 검증하고, `add-observation`은 보관소 생성·입력 읽기·원본 쓰기 전에 같은 검증을 수행한다. CLI는 종료 코드 1과 예약 키 이름만 포함한 오류를 반환하며 traceback을 출력하지 않는다. 정상 추가 메타데이터, 중첩 객체의 동명 키, `extra` 생략과 빈 객체, 동일 관측의 재실행은 유지한다.

크롤러의 기존 시험 도우미는 `content_type`을 명시적 인수와 추가 메타데이터에 중복 전달했으므로 추가 메타데이터에서 제거했다. 손상 이력 복구 시험은 정상 레코드를 생성한 뒤 시험용 사본의 해시를 변조하여 계속 원자적 복구 거부를 검증한다. 크롤러의 실제 업로더는 이미 기본 필드를 분리하고 있어 변경하지 않았다.

## 회귀 증거

- [`test_source_archive.py`](../../../tools/tests/test_source_archive.py): 예약 키 7개 각각의 기존 값·위조 값 거부, 객체가 아닌 메타데이터 거부, 정상 메타데이터·중첩 키·입력 불변성, 생략·빈 객체와 재실행을 검사한다.
- [`test_source_archive_commands.py`](../../../tools/tests/test_source_archive_commands.py): 보관소를 열기 전 거부와 실제 CLI의 실패 코드·오류 문구·쓰기 없음, 변경된 입력을 포함한 실패 실행 뒤 기존 보관소의 모든 바이트 보존을 검사한다.
- [수정 전 회귀 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/before.log): 새 시험을 기존 구현에 실행했을 때 46개 시험 중 하위 사례 실패 27건·오류 16건으로 실패한다. 예약 키가 기록되거나 객체가 아닌 메타데이터가 허용되는 문제를 재현한다.
- [첫 전체 Python 실행 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/python-integration-first.log): 위 크롤러 시험 도우미의 기존 호출 7건이 새 예약 키 검증에서 거부된 기록이다. 도우미를 새 호출 계약에 맞춰 수정한 뒤 전체 시험을 다시 실행했다.

## 실행 결과

모두 이 작업 트리에서 실행했다. 합성 입력·임시 로컬 보관소를 사용하며 실제 R2 접근·자격 증명은 사용하지 않았다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 46개 통과, 종료 코드 0 | [보관소 회귀 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_crawler_*.py' -v` | 300개 통과, 종료 코드 0 | [크롤러 통합 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/crawler-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 958개 실행, 952개 통과·6개 건너뜀, 종료 코드 0 | [전체 Python 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/python-tests.log) |
| `cargo test --all --locked` | Rust 447개 통과·1개 무시, 내장 Python 39개·129개 통과, 종료 코드 0 | [Rust 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/rust-tests.log) |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked -- -D warnings` | 모두 종료 코드 0 | [형식·린트 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/rust-checks.log) |
| 어휘·검증 자료·검증기 selftest·제품 목적 연결·설계 명세 검사 | 모두 종료 코드 0 | [일관성 검사 로그](../../../tools/evidence/audit2-archive-extra-overrides-hash/consistency-checks.log) |

Python 건너뜀 6개는 로컬 원본 보관소가 필요한 기존 검사 5개와 설치된 botocore가 이미 조건부 PUT을 지원하여 해당하지 않는 구버전 검사 1개다. 신규 회귀 검사는 모두 실행했다.

이 증거는 원본 관측 도구의 무결성 검증에 한정한다. 실제 공시 확보율·R2 관측 목록 대조·화면·출시 완료 증거를 대신하지 않으며 P02·P03 또는 I6 전체를 완료 처리하지 않는다.
