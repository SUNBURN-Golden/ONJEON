# Audit 1: detect의 pdfplumber 필수 검사 제거

2026-10-22 | 노드 `audit1-detect-drop-pdfplumber-requirement`

`tools/verify_sources.py`의 공통 진입점이 `pdfplumber` 없는 환경에서 `detect`까지 종료 코드 2로 중단했다. PDF 인용 재추출에 필요한 모듈 검사를 `reproduce` 분기에만 적용했다. 공통 `pdftotext` 필수 검사는 이번 수정 범위 밖으로 유지한다.

회귀 시험 `tools/tests/test_verify_sources.py::CliDependencies`는 `sys.modules`에 `pdfplumber=None`을 넣어 설치 여부와 무관하게 모듈 부재를 재현한다. 수정 전에는 detect의 세 경우 모두 기대한 0/0/1 대신 2를 반환해 실패했고, 수정 후에는 통과했다.

- `detect`: 동일 바이트·변경 바이트·다운로드 실패 각각의 종료 코드, JSON 보고서, 다운로드 파일과 해시를 확인한다. 보고서의 `tools.pdfplumber`는 `null`이다.
- `reproduce`: 모듈이 없으면 처리·예산 세션 진입 전에 안내와 종료 코드 2를 반환하고, 모듈이 있으면 처리기로 진행한다.
- 출처 응답은 시험용 바이트와 모의 오류다. 실제 보험사 출처나 비공개 보관본을 검증한 기록은 아니다.

| 실행 명령 | 결과 |
|---|---|
| `python3 -m unittest tools.tests.test_verify_sources -v` | 28건: 25건 통과, 보관 원본이 필요한 3건 건너뜀 |
| `python3 -m unittest discover -s tools/tests -v` | 308건: 299건 통과, 6건 건너뜀, 3건 환경 오류 |
| `cargo test --all --offline` | 문서 시험 포함 84건 통과 |
| `python3 tools/vocab_check.py` | 통과: 33축, 177값 |
| `python3 tools/validation_check.py` | 내부 일관성 통과(원본 재검증 아님) |
| `python3 tools/validation_check.py --selftest` | 변조 38종을 각각 의도한 이유로 검출 |

전체 Python 시험의 오류 3건은 `test_r2_budget.EndToEnd`의 모든 시험이다. `setUp`에서 로컬 S3 모의 서버의 `ThreadingHTTPServer(("127.0.0.1", 0), Handler)`가 소켓 생성 중 샌드박스의 `PermissionError: [Errno 1] Operation not permitted`로 중단했다. 전체 시험 통과로 집계하지 않는다. 건너뛴 6건은 보관 원본 환경 변수 미설정 5건과 최신 botocore에서 적용되지 않는 구버전 전용 시험 1건이다.

이 기록은 해당 감사 결함의 수정 증거다. 제품 목적 대응표 P01~P19나 출시 관문의 완료를 뜻하지 않는다.
