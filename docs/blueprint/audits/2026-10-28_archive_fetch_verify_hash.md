# Audit 3 — R2 복원 바이트와 객체 키의 SHA-256 대조

대상: `audit3-archive-fetch-verify-hash`, `tools/source_archive.py::cmd_fetch`.
연결: Blueprint A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 판정과 변경

R2에는 이 도구 밖에서의 덮어쓰기를 막는 버킷 쓰기 정책이 없으므로 해시 기반 객체 키만으로 내려받은 바이트를 신뢰할 수 없다. 이 작업의 시작 시점에는 [Audit 2](2026-10-26_archive_samples_verify_before_put.md)에서 추가한 복원 전 SHA-256 검사가 이미 있었다. 이번 작업은 해당 검사를 유지하고 R2 읽기 경로의 회귀 증거를 추가한다. 불일치 진단에는 표본 ID·기대 해시·실제 해시에 더해 요청한 객체 키도 기록한다.

`fetch`는 `samples.csv`의 SHA-256으로 `objects/sha256/<aa>/<bb>/<sha256>` 키를 만들고, `raw.get(key)`로 받은 바이트를 직접 해시한다. 키에 사용한 기대 해시와 다르면 stderr 진단과 종료 코드 1로 즉시 중단한다. 대상 디렉터리 생성·파일 쓰기는 검증 뒤에만 수행하므로 손상된 객체가 새 파일로 복원되거나 기존 파일을 덮어쓰지 않는다. 앞에서 검증·복원한 파일은 유지하고 이후 행은 읽지 않는다. 서버의 체크섬 메타데이터는 이 판정에 사용하지 않는다.

## 회귀 증거

[`test_source_archive_fetch_r2.py`](../../../tools/tests/test_source_archive_fetch_r2.py)는 실제 R2 분류의 `S3Store`와 `get` 구현을 사용한다. 합성 자격 증명으로 클라이언트를 만들고, botocore `Stubber`가 접두어를 포함한 정확한 버킷·키의 GET을 검사한다. 실제 R2 접근·원본·비밀키는 사용하지 않는다. 비용 입장·계량은 기존 예산 시험의 범위이며 이 시험에서는 모의 예산 세션을 사용한다.

- 체크섬 메타데이터가 없는 정상 바이트의 복원과 읽기 스트림 닫힘.
- 같은 길이의 변조 바이트 및 빈 바이트를 각각 거부. 체크섬 없음·기대 해시로 위조된 체크섬·변조 바이트에 맞는 체크섬의 세 경우와 대상 파일 없음·있음의 두 경우를 조합한 12개 하위 사례.
- 불일치의 종료 코드 1·성공 문구 없음·객체 키와 실제 해시 진단·기존 파일 보존·새 대상 디렉터리 미생성.
- 같은 키의 첫 GET은 정상이고 다음 GET은 변조된 경우, 앞의 검증된 파일을 보존하고 이후 행의 GET·디렉터리 생성을 중단.

메모리에서만 `cmd_fetch`의 해시 불일치 거부 분기를 제거한 [변조 검사](../../../tools/evidence/audit3-archive-fetch-verify-hash/hash-check-mutation.log)도 수행했다. 대체 바이트 12개 하위 사례가 실패하고, 중간 객체 시험은 금지된 이후 GET을 `UnStubbedResponseError`로 검출한다. 로그의 `FAILED (failures=12, errors=1)`은 의도한 변조 검출 결과이며 검출 확인 명령의 종료 코드는 0이다. 디스크의 구현은 바꾸지 않았다.

## 실행 결과

2026-10-28, 이 작업 트리에서 실행했다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_source_archive*.py' -v` | 52개 통과, 종료 0 | [보관소 회귀 로그](../../../tools/evidence/audit3-archive-fetch-verify-hash/archive-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,233개 실행, 실패 0·건너뜀 6, 종료 0 | [전체 Python 로그](../../../tools/evidence/audit3-archive-fetch-verify-hash/python-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과, 종료 0 | [설계·제품 목적 연결 검사](../../../tools/evidence/audit3-archive-fetch-verify-hash/spec-check.log) |
| `python3 tools/vocab_check.py` | 49축·270값 통과, 종료 0 | [어휘 검사](../../../tools/evidence/audit3-archive-fetch-verify-hash/vocabulary.log) |
| `python3 tools/validation_check.py` | 추출·메타데이터 내부 일관성 통과, 종료 0 | [일관성 검사](../../../tools/evidence/audit3-archive-fetch-verify-hash/validation.log) |

건너뜀은 비공개 로컬 원본이 필요한 기존 시험 5개와 설치된 botocore에 해당하지 않는 구버전 조건부 PUT 시험 1개다. 새 R2 복원 시험 3개와 하위 사례는 모두 실행했다.

이 증거는 복원 도구의 바이트 무결성 검증에 한정한다. 실제 R2 관측 목록 대조·공시 확보율·변경 재처리·소비자 화면·출시 완료 증거를 대체하지 않으며 P02·P03 전체를 완료 처리하지 않는다.
