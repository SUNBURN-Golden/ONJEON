# Audit 2 — 표본 보관 전·복원 쓰기 전 SHA-256 검증

대상: `audit2-archive-samples-verify-before-put`, `tools/source_archive.py::cmd_archive_samples`·`cmd_fetch`.
연결: Blueprint A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 발견과 수정

`archive-samples`는 `put_raw`로 원본을 영구 보관한 뒤 `samples.csv`의 SHA-256과 비교했다. 따라서 실패한 표본도 보관소에 남았고, 기존 시험도 이 동작을 기대했다.

캐시에서 읽은 바이트의 SHA-256을 먼저 계산하여 표본 목록과 대조한다. 불일치하면 기존 `hash_differs_from_samples_csv` 결과·실제 해시·종료 코드 1을 유지하면서 해당 행의 원본·관측·파생물 쓰기를 모두 건너뛴다. 다른 정상 행은 계속 처리한다. 일치한 바이트만 기존 `put_raw`·관측·파생물 경로로 전달하므로 동일 바이트의 재실행과 충돌 거부는 유지한다. 이미 잘못 보관된 객체를 삭제하거나 복구하지는 않는다.

`fetch`는 해시 기반 키로 내려받은 바이트의 SHA-256을 `samples.csv`와 대조한 뒤 대상 디렉터리·파일을 쓴다. 불일치하면 표본 ID·기대 해시·실제 해시를 stderr에 기록하고 종료 코드 1로 중단한다. 해당 파일을 새로 만들거나 기존 파일을 덮어쓰지 않고, 뒤의 표본도 복원하지 않으며 성공 문구를 출력하지 않는다. 앞에서 검증을 통과하여 복원한 파일은 유지한다. 두 명령에서 표본 CSV 파일도 명시적으로 닫는다.

## 회귀 증거

[`test_source_archive_commands.py`](../../../tools/tests/test_source_archive_commands.py)는 다음을 검사한다.

- 불일치한 원본과 파생 입력이 있어도 원본·관측·파생 보관소에 쓰기가 없음.
- 기존 보관소의 모든 바이트가 보존되고 `put_raw`를 호출하지 않음.
- 경로 오류·누락·해시 불일치 행 뒤의 정상 행은 새 객체와 관측으로 보관됨.
- 손상된 보관 객체의 복원은 CLI 종료 코드 1·오류 해시를 반환하며, 대상이 없거나 이미 있는 두 경우 모두 대상 바이트를 쓰지 않음.
- 복원 실패 뒤의 표본을 처리하지 않음.
- 기존 정상 복원, 정상 보관·파생물 재실행, 경로 제한, 충돌 거부 회귀 시험도 유지.

[수정 전 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/before.log)는 같은 49개 시험 중 실패 6건으로 쓰기 순서·복원 검증 누락을 재현한다(복원 대상 존재 여부 하위 사례 포함). [수정 후 보관소 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/archive-tests.log)는 49개 모두 통과한다.

## 실행 결과

이 작업 트리에서 합성 입력·임시 로컬 보관소로 실행했다. 실제 공시 원본·R2 접근·자격 증명은 사용하지 않았다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 49개 통과, 종료 코드 0 | [보관소 회귀 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 961개 실행, 955개 통과·6개 건너뜀, 종료 코드 0 | [전체 Python 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/python-tests.log) |
| `cargo test --all --locked` | Rust 447개 통과·1개 무시, 내장 Python 39개·129개 통과, 종료 코드 0 | [Rust 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/rust-tests.log) |
| `cargo fmt --all -- --check` | 종료 코드 0 | [형식 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/rust-format.log) |
| `cargo clippy --all-targets --locked -- -D warnings` | 종료 코드 0 | [린트 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/rust-lint.log) |
| `python3 tools/vocab_check.py` | 종료 코드 0 | [어휘 검사 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/vocabulary.log) |
| `python3 tools/validation_check.py` | 종료 코드 0 | [내부 일관성 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/validation.log) |
| `python3 tools/validation_check.py --selftest` | 변조 38종 검출, 종료 코드 0 | [selftest 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/validation-selftest.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과, 종료 코드 0 | [설계·제품 목적 연결 검사 로그](../../../tools/evidence/audit2-archive-samples-verify-before-put/spec-check.log) |

Python 건너뜀 6개는 비공개 로컬 원본 보관소가 필요한 기존 검사 5개와 설치된 botocore가 이미 조건부 PUT을 지원하여 해당하지 않는 구버전 검사 1개다. 신규 회귀 시험은 모두 실행했다.

이 증거는 원본 보관·복원 도구의 로컬 무결성에 한정한다. 실제 공시 확보율·R2 관측 목록 대조·변경 재처리·화면·출시 완료 증거를 대신하지 않으며 P02·P03 전체를 완료 처리하지 않는다.
