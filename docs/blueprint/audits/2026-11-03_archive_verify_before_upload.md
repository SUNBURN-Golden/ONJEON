# Audit 4 — 표본 해시 비교와 R2 업로드 순서

대상: `audit4-archive-verify-before-upload`, `tools/source_archive.py::cmd_archive_samples`.
연결: Blueprint A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 판정과 변경

감리 지적은 캐시 바이트를 영구 보관한 다음 `samples.csv`의 해시와 비교하면
불일치 바이트가 삭제할 수 없는 원본 객체로 남는다는 것이다. 작업 시작 시점에
[Audit 2 수정](2026-10-26_archive_samples_verify_before_put.md)이 이미 반영돼 있었다.
현재 구현은 `body = p.read_bytes()` → `sha256_bytes(body)` → CSV 해시 비교 →
일치한 경우에만 `put_raw` 순서다. 해시 불일치는 실제 해시와
`hash_differs_from_samples_csv`를 보고하고 해당 행의 원본·관측·파생 쓰기를 건너뛴다.
다음 정상 행은 계속 처리하되 명령 전체는 종료 코드 1을 반환한다.

이번 변경은 기존 실행 코드를 유지하고, 영구 업로드 경계의 회귀 시험과 재현 가능한
변이 검사를 추가한다. 이미 보관된 잘못된 객체의 삭제·복구는 수행하지 않는다.

## 회귀 증거

[`test_source_archive_upload_r2.py`](../../../tools/tests/test_source_archive_upload_r2.py)는
실제 R2 분류의 `S3Store`를 사용하고 botocore `Stubber`로 요청을 검사한다.
자격 증명과 문서는 합성이며 네트워크를 사용하지 않는다. 비용 입장·계량은 기존
예산 시험의 범위이며 여기서는 모의 예산 세션을 사용한다.

- 변경 파일·같은 길이의 변조 파일·빈 파일의 해시 불일치를 각각 거부한다.
  파생 입력이 있어도 원본·파생 클라이언트의 빈 응답 큐에서 HEAD·GET·PUT 요청이
  하나도 발생하지 않는다. 종료 코드 1·표본 ID·실제 해시·불일치 상태를 검사한다.
- 불일치 행 다음 정상 행만 원본과 관측으로 저장한다. 버킷·접두어·객체 키·본문·
  MIME·SHA-256 체크섬·`IfNoneMatch="*"`가 정확한 요청만 허용한다.
  정상 행만 재실행하면 HEAD로 기존 체크섬을 확인하여 추가 PUT 없이
  `already_present`·종료 코드 0을 반환한다.
- 기존 로컬 시험은 정상 파생 명세·재실행, 기존 보관소 바이트 보존·`put_raw` 미호출,
  경로 거부·혼합 행·저장 충돌·복원 무결성도 계속 검사한다.

[변이 검사 스크립트](../../../tools/evidence/audit4-archive-verify-before-upload/check_upload_order_mutation.py)는
메모리에서만 해시 비교를 `put_raw` 뒤로 옮겨 원래 지적을 재현한다. 새 시험 두 개가
금지된 원본 요청을 검출한다. [변이 로그](../../../tools/evidence/audit4-archive-verify-before-upload/upload-order-mutation.log)의
`FAILED (failures=1, errors=4)`는 의도한 검출이며, 스크립트는 두 시험의 검출과
건너뜀 없음을 확인한 뒤 `MUTATION REJECTED`·종료 코드 0을 반환한다.
디스크의 실행 코드를 수정하지 않는다.

## 실행 결과

2026-11-03, 이 작업 트리에서 README의 Rust 1.98.1 경로 한정 재정의를 적용하고
실행했다. 결과와 명령은 [검증 기록](../../../tools/evidence/audit4-archive-verify-before-upload/README.md)에 있다.

이 증거는 보관 도구의 업로드 전 바이트 무결성에 한정한다. 실제 공시 확보율·R2
관측 목록 대조·변경 재처리·소비자 화면·출시 완료 증거를 대신하지 않으며,
P02·P03 전체를 완료 처리하지 않는다.
