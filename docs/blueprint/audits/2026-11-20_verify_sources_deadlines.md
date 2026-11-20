# Audit 7 다운로드·재현 시간 제한

`audit7-verify-sources-untrusted-fetch`의 작업 시작점 `7a3d51e`에서는 최초 URL·리다이렉트·최종 URL에 HTTPS와 등록 호스트를 이미 요구했다. 다운로드 작업 프로세스도 같은 URL 검사를 거친다. 보관본 재현은 로컬 `file://` 보관소를 지원한다.

- `detect`는 출처마다 작업 프로세스 하나에 최대 120초를 준다. DNS 조회, 연결, 리다이렉트, 본문 수신, 재시도와 대기가 이 시간을 공유한다. 개별 소켓 타임아웃은 30초다. 총 시간 초과 시 프로세스를 종료하고 해당 출처를 `fetch_failed`와 `deadline_exceeded`로 기록한다. 이 경로는 본문을 반환하기 전에 끝나므로 다운로드 캐시·원본·관측을 쓰지 않는다.
- `reproduce`는 `pdftotext`의 페이지 발췌와 파생물 재생성, `pdftoppm`, `tesseract`를 명령당 120초로 제한한다. 버전 확인은 명령당 10초다. 재현 중 명령이 시간 초과하면 표본 ID와 도구를 `tool_timeout`으로 표준 오류에 출력하고 종료 코드 1을 반환한다. 검사 완료 후 보고서의 선택적 버전 조회가 시간 초과하면 해당 버전을 `null`로 기록한다.
- 보관본의 작업 복사본은 재현 범위가 끝날 때, OCR 이미지는 해당 페이지 처리가 끝날 때 제거한다. 정상 완료와 예외에 동일한 정리 범위를 적용한다.

## 회귀 증거

- 루프백 HTTPS 서버에서 응답 헤더가 늦는 리다이렉트 연쇄와 바이트가 계속 도착하는 본문을 같은 총 제한으로 중단했다. 재시도 대기 중에도 제한을 적용하며, 시간이 초과된 출처의 다운로드·보관 경로는 생성되지 않는다. 부모와 작업 프로세스의 비HTTPS·미등록 URL 거부와 정상 HTTPS 보존을 검증했다. [다운로드 시험](../../../tools/tests/test_verify_sources_fetch.py).
- 두 `pdftotext` 페이지 모드와 전체 PDF 재생성, 래스터화·OCR·버전 조회의 시간 제한을 검증했다. OCR 성공·실패·시간 초과, 보관본 재현 종료·부분 다운로드 실패 뒤 임시 파일 정리를 확인했다. [재현 시험](../../../tools/tests/test_reproduce_paths.py).
- 작업 프로세스의 `timeout=`만 메모리에서 제거하면 응답 헤더·본문 수신·재시도 대기 회귀 시험 3건이 모두 단언에 실패한다. HTTPS·호스트·리다이렉트 검사를 제거하는 기존 변이도 시험 단언이 잡아낸다. [URL 정책 변이 시험](../../../tools/evidence/audit6-verify-sources-url-allowlist/check_mutations.py).

| 시험 | 로컬 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 70건 통과, 보관본 통합 시험 3건 건너뜀 |
| `test_reproduce_paths.py` 및 `test_samples_csv_validation.py` 단위 시험 | 31건 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,740건 통과, 보관본 5건과 구버전 botocore 대상 시험 1건 건너뜀 |
| `python3 -I -m unittest discover -s tools/ci/tests` | 21건 통과 |
| `cargo test --all --locked --offline` | 537건 통과, 1건 제외 |
| 시나리오 API와 온톨로지 실행기의 `cargo test --locked --offline` | 각 4건 통과 |

첫 전체 Python 실행은 작업 트리 안에 `TMPDIR`를 지정해 온톨로지의 임시 파일 위치 시험 3건에 실패했다. 시스템 기본 임시 경로로 바꾼 뒤 전체 시험을 다시 실행했다.

이 기록은 [제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P02·P03의 로컬 도구 증거다. 실제 공시 수집·R2 대조와 첫 출시 완료는 대응표의 해당 증거를 따른다.
