# Audit 5 — fetch 복원 전 SHA-256 검사 재검증

대상: `audit5-archive-fetch-verify-hash`, `tools/source_archive.py::cmd_fetch`.
연결: Blueprint A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

## 판정

보고된 무검증 복원은 이 작업 트리의 기준 코드에서 이미 해결되어 있다.
[Audit 2](2026-10-26_archive_samples_verify_before_put.md)에서 추가하고
[Audit 3](2026-10-28_archive_fetch_verify_hash.md)에서 R2 경로로 검증한 구현을 유지한다.
`cmd_fetch`는 `samples.csv`의 해시로 조회할 키를 구성하고 `raw.get(key)`의
반환 바이트를 직접 SHA-256으로 계산한다. 기대값과 다르면 종료 코드 1과
표본 ID·객체 키·기대/실제 해시를 출력하고, 대상 디렉터리 생성·파일 쓰기 전에 중단한다.
R2 객체 키와 서버 체크섬 메타데이터를 무결성 증명으로 신뢰하지 않는다.

## 추가 회귀 검증

[`test_source_archive_fetch_r2.py`](../../../tools/tests/test_source_archive_fetch_r2.py)에
실제 `S3Store.get`과 botocore `Stubber`를 사용하는 세 시험을 추가했다.

- 정상 복원 후 같은 키가 같은 길이의 변조 바이트로 바뀌고 서버 체크섬은 원래 값인
  경우에도 재실행마다 바이트를 다시 해시한다. 실패를 반환하고 마지막 정상 복원본을 보존한다.
- 실제 CLI 인수 파싱 → `run` → `cmd_fetch` → `with_budget` 반환 경로에서
  불일치의 종료 코드 1과 예산 정산의 `exit_1`을 확인한다. 성공 문구·복원 디렉터리는 없다.
  예산 시작·정산은 모의 호출이며 실제 원장·계량 검증을 대신하지 않는다.
- 빈 바이트의 해시가 표본 목록과 일치하면 길이 0의 정상 파일로 복원한다.
  기존 빈 변조 객체 거부 시험과 함께 바이트 길이만으로 판정하지 않는지 확인한다.

기존 시험은 서버 체크섬 없음·기대값으로 위조·변조 바이트와 일치하는 경우의 변조 거부,
기존 파일 보존·새 경로 미생성, 중간 행 실패 시 후속 GET 중단과 앞선 정상 파일 보존을 유지한다.

[`check_fetch_mutations.py`](../../../tools/evidence/audit5-archive-fetch-verify-hash/check_fetch_mutations.py)는
메모리에서만 해시 검사 분기를 제거하거나 파일 쓰기 뒤로 옮긴다. 두 변이 모두 선택한
네 회귀 시험 각각이 검출해야 성공한다. 실제 모듈 전역을 사용하므로 임시 표본·모의 저장소·
CLI 패치가 변이에도 적용된다. 디스크의 운영 코드는 변경하지 않는다.

## 실행 증거와 한계

2026-11-10 이 작업 트리에서 실행한 명령·결과·로그는
[증거 안내](../../../tools/evidence/audit5-archive-fetch-verify-hash/README.md)에 기록한다.
R2 시험은 합성 문서·합성 자격 증명과 모의 GET을 사용한다.
이 증거는 로컬 보관 도구의 회귀 검증이며 실제 R2 관측 목록 대조·공시 확보율·변경 재처리·
소비자 화면·출시 완료 증거를 대체하지 않는다. P02·P03 전체를 완료 처리하지 않는다.
