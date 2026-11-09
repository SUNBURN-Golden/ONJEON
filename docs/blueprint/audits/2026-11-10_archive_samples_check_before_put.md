# Audit 5 — 표본 해시 검증 후 원본 저장

대상: `audit5-archive-samples-check-before-put`, `tools/source_archive.py::cmd_archive_samples`.
연결: Blueprint A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 판정과 변경

지적된 저장 순서 결함은 이 작업의 시작 코드에 이미
[Audit 2 수정](2026-10-26_archive_samples_verify_before_put.md)으로 해결돼 있었다.
캐시를 한 번 읽고 해당 바이트의 SHA-256을 `samples.csv`와 비교한 다음,
일치한 경우에만 같은 바이트를 `put_raw`에 전달한다. 불일치는
`hash_differs_from_samples_csv`·실제 해시·종료 코드 1로 보고하며 해당 행의
원본·관측·파생물 쓰기를 건너뛴다. 다음 정상 행은 계속 처리한다.
[Audit 4](2026-11-03_archive_verify_before_upload.md)의 R2 요청 경계 시험도 유지한다.

이번 변경은 실행 순서를 유지하고, 같은 바이트를 검증·저장해야 하는 이유를 코드
주석에 명시하며 두 회귀 시험과 재현 가능한 변이 검사를 추가한다.

## 추가 회귀 증거

[`test_source_archive_commands.py`](../../../tools/tests/test_source_archive_commands.py)의
합성 표본 CSV·캐시·실제 임시 `LocalStore`로 검사한다.

- `test_repaired_cache_archives_and_reruns_without_retaining_rejected_bytes`:
  불일치 시 원본·파생 보관소 디렉터리조차 생성하지 않는다. 캐시를 수정하면
  정상 원본·관측·파생물을 저장하고, 다시 변조하면 두 보관소의 모든 바이트를
  보존한다. 다시 수정하여 재실행하면 `already_present`이고 보관소는 동일하다.
  거부된 바이트의 객체는 어느 단계에서도 남지 않는다.
- `test_archive_uses_verified_snapshot_when_cache_changes_before_put`:
  해시 비교 다음, 저장 직전에 캐시를 다른 바이트로 교체하거나 삭제한다.
  두 경우 모두 이미 검증한 바이트만 저장하며 원본 해시·관측 해시·크기는 일치한다.
  교체된 바이트의 객체는 생성하지 않는다. 시점은 모의 `content_type_of` 호출로
  고정하여 타이밍에 의존하지 않는다.

[변이 검사](../../../tools/evidence/audit5-archive-samples-check-before-put/check_order_mutations.py)는
메모리에서만 ① 해시 비교를 `put_raw` 뒤로 이동하거나 ② 검증 뒤 캐시를 다시
읽어 저장하도록 바꾼다. 첫 변이는 기존 거부 시험 두 개와 새 복구 시험이 모두
검출하고, 두 번째는 새 바이트 보존 시험이 검출한다. 의도된 실패·오류 뒤 두 번의
`MUTATION REJECTED`와 종료 코드 0을 확인한다. 실행 코드는 디스크에서 바꾸지 않는다.

2026-11-10 이 작업 트리에서 실행한 명령·결과·원본 로그는
[검증 기록](../../../tools/evidence/audit5-archive-samples-check-before-put/README.md)에 남긴다.
이 증거는 로컬 보관 도구의 finding 종료 근거다. 실제 공시 확보율·R2 관측 대조·
변경 재처리·상품 트윈·소비자 화면·P02/P03 전체·첫 출시 완료를 뜻하지 않는다.
기존 보관 객체의 삭제·복구나 실제 R2 작업은 수행하지 않았다.

## Fix round 1: CI 시험 시계 고정

CI `42720338918`의 `600 != 601` 실패는 종료 시각만 모의한 시험에서 발생했다.
실수형 시작 시각에 601을 더한 뒤 다시 빼면 `600.9999999999999`가 될 수 있어,
정수 초로 측정하는 계기가 600을 반환했다. 같은 패턴의 정산 GET 소진 시험도
함께 재현했다. 두 시험 모두 세션 생성 전부터 시작 시각 100을 고정하고
정산 시각을 701로 진행한다. 601초 경과·정산 실패·예약 전액 유지·잠금 해제 등
기존 검증은 유지하며 운영 코드의 예산 계산은 바꾸지 않는다.

재현 로그와 호스트 시각별 검증, 보관 순서 변이 검사 및 전체 재시험 결과는
[round 1 검증 기록](../../../tools/evidence/audit5-archive-samples-check-before-put/fix-round1/README.md)에 남긴다.
