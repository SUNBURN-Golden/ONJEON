# Audit 4 — samples.csv 해시·출처 URL 검증

대상: `audit4-samples-csv-validation`. BLUEPRINT Q7·L1 및 [제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P02·P03의 원본·출처 관리에 연결한다. 로컬 도구의 회귀 증거이며 실제 공시 확보율·R2 관측 대조·소비자 화면·첫 출시 완료를 뜻하지 않는다.

## 확인한 결함과 수정

작업 시작 HEAD에는 로컬 보관소 경로 이탈 방어와 같은 출처 리다이렉트 제한이 이미 있었다. 따라서 `file://` 보관소 밖 읽기와 HTTPS→HTTP 이동은 해당 방어에서도 거부된다. 다만 `samples.csv`의 `sha256`·`url` 형식 검사가 없고, `object_key`는 임의 문자열을 키로 만들며, 최초 HTTP 출처는 허용했다. FTP·file 최초 출처는 기존 `source_origin`에서도 거부됐다. 감리 지적 중 이미 적용된 방어와 이번에 추가한 검사를 구별한다.

- `source_metadata.py`가 SHA-256 64자리 ASCII 16진수(대소문자 허용), 호스트·유효 포트가 있고 자격증명·공백·제어문자·역슬래시가 없는 HTTPS 출처 URL을 검사한다. 잘못된 값을 정규화하거나 잘라서 수용하지 않는다.
- `validation_check.check`가 표본마다 두 검사를 실행하며 필드별 오류를 낸다. 인코딩 문서가 없거나 같은 잘못된 해시를 인코딩에 복사해도 형식 검사를 우회할 수 없다.
- `source_archive.object_key`도 해시를 검사한다. 내부 일관성 검사를 먼저 실행하지 않아도 복원·보관 검증·재현의 저장소 조회 전에 `UnsafeStoreKey`로 거부한다. 기존 로컬 키 경로 방어도 유지한다.
- `verify_sources.source_origin`은 같은 HTTPS 검사를 사용한다. 최초 HTTP·FTP·file 출처는 opener 생성 전에 거부한다. 301·302·303·307·308의 HTTPS→HTTP 이동은 다음 요청 전에 차단하고 중간 본문은 읽지 않는다. 같은 출처의 HTTPS 상대 이동·기본 포트는 허용한다. 보관소 인수 `--raw file://…`는 계속 지원한다.

## 회귀와 증거

새 메타데이터 회귀 시험을 HEAD의 검사 코드에 적용하면 두 시험의 23개 하위 사례가 실패하고 오류는 0건이다([baseline-tests.log](../../../tools/evidence/audit4-samples-csv-validation/baseline-tests.log)). 원본 코드는 메모리에 불러와 검사했으며 작업 파일을 되돌리지 않았다.

[`test_samples_csv_validation.py`](../../../tools/tests/test_samples_csv_validation.py)는 잘못된 길이·문자·개행·절대 경로·상대 경로·빈 값·누락 값, 비HTTPS·호스트 누락·자격증명·잘못된 포트·공백·제어문자 등을 검사한다. 저장소 모의 객체의 `get`·`exists`·`list` 호출이 모두 0회이고 출력 디렉터리가 비어 있는지도 확인한다. 정상 14개 표본과 대소문자 16진수·HTTPS 기본/사용자 지정 포트·IPv6 URL도 검사한다.

[`test_verify_sources_fetch.py`](../../../tools/tests/test_verify_sources_fetch.py)는 실제 루프백 HTTPS 서버와 임시 보관소로 정상 수집·리다이렉트·최종 URL 기록 및 비HTTPS 최초 요청·다운그레이드의 실패를 검사한다. 인증서는 실행 중 임시 생성하고 해당 시험 클라이언트만 신뢰한다. 제품의 TLS 검증은 유지한다. 모든 리다이렉트 코드에 대한 거부·응답 닫힘·다음 요청 없음, 기존 바이트 보존·잘못된 응답의 보관 거부도 검사한다. 보험사·R2 접근은 하지 않는다.

`validation_check.py --selftest`에는 해시 경로 이탈·HTTP URL 변조를 추가했다(38→40종). BLUEPRINT §11의 생성 수와 검증 자료 안내도 갱신한다.

## 실행 결과

기준 HEAD: `f64e0e7dcbfe5817d47b3621e6b36b40f57f2dbf`. 명령·종료 코드·수정 소스 SHA-256은 [run-summary.json](../../../tools/evidence/audit4-samples-csv-validation/run-summary.json)에 기록했다. Cargo 출력 위치와 Python의 `ONJEON_ONTOLOGY_RUNNER`는 작업 트리 내부 경로를 명시한다.

| 실행 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_samples_csv_validation.py -v` | 종료 0, 4개 통과 | [메타데이터 회귀](../../../tools/evidence/audit4-samples-csv-validation/metadata-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 종료 0, 60개 중 57 통과·3 건너뜀 | [수집·재현 회귀](../../../tools/evidence/audit4-samples-csv-validation/verify-sources-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` (로컬 실행 파일 지정) | 종료 0, 1,334개 중 1,328 통과·6 건너뜀 | [전체 Python](../../../tools/evidence/audit4-samples-csv-validation/python-tools.log) |
| `cargo test --all --locked --offline` | 종료 0, Rust 478 통과·1 무시(문서 시험 포함) | [전체 Rust](../../../tools/evidence/audit4-samples-csv-validation/rust-tests.log) |
| 별도 온톨로지 실행기 `cargo test --locked --offline` | 종료 0, 3개 통과 | [실행기 시험](../../../tools/evidence/audit4-samples-csv-validation/ontology-runner-tests.log) |
| `validation_check.py` 및 `--selftest` | 종료 0, 정상 표본과 변조 40종 확인 | [검사](../../../tools/evidence/audit4-samples-csv-validation/validation.log), [변조 시험](../../../tools/evidence/audit4-samples-csv-validation/validation-selftest.log) |
| 어휘·BLUEPRINT 수/결정 인덱스·워크플로·설계 묶음·온톨로지 검사, `cargo fmt`·`cargo clippy` | 모두 종료 0 | [명령별 결과](../../../tools/evidence/audit4-samples-csv-validation/checks-summary.json) |

첫 전체 Python 실행은 설정한 온톨로지 실행 파일 경로와 환경의 기본 Cargo 출력 위치가 달라 20개 오류로 실패했다([초기 로그](../../../tools/evidence/audit4-samples-csv-validation/python-tools-initial.log)). 같은 이유로 온톨로지 검사도 처음에는 실행 파일을 찾지 못했다. 작업 트리 내부 출력 위치를 명시해 다시 빌드하고 전체 Python과 온톨로지 검사를 다시 실행해 위의 종료 0을 확인했다. 초기 실패를 통과로 계산하지 않았다.

비공개 보관 원본 등이 필요한 시험의 건너뜀과 Rust의 기존 무시 시험은 그대로 기록한다. 이 노드는 공시·R2에 접근하지 않았고 과거 원본 관측·확보 상태를 갱신하지 않았다.
