# Audit 6 — 원본 저장 전 비교·복원 전 검증

대상: `audit6-archive-verify-before-put`, `tools/source_archive.py`의
`cmd_archive_samples`·`cmd_fetch`.
연결: Blueprint A1·Q7·L1·I6·M1, 09 제품 목적 대응표 P02·P03.

보고된 두 결함은 이 작업 트리의 기준 코드에서 이미 수정되어 있다.
`cmd_archive_samples`는 캐시를 한 번 읽고 `samples.csv`와 SHA-256을 비교한 뒤
같은 바이트를 `put_raw`에 넘긴다. 불일치 행은 원본·관측·파생물 쓰기를 건너뛰고
종료 코드 1로 보고한다. `cmd_fetch`는 `raw.get`이 반환한 바이트를 직접 해시하고,
불일치면 복원 디렉터리 생성·파일 쓰기 전에 종료 코드 1을 반환한다.
전체 복원이 성공한 경우에만 `restored originals`를 출력한다. 기존 구현은 유지했다.

이번에 추가한
[`test_cli_rejects_bad_cache_and_corrupt_store_through_archive_restore_lifecycle`](../../../tools/tests/test_source_archive_commands.py)는
실제 CLI 파싱·실행·반환 경로와 임시 `LocalStore`를 함께 사용한다.
같은 길이의 잘못된 캐시 거부(저장소 미생성) → 캐시 수정·재시도 성공 →
캐시 재변조 거부(기존 원본·관측 바이트 보존) → 정상 복원 → 저장소 객체의
외부 변조를 재현한다. 변조 후 복원은 기존 정상 파일을 보존하고 삭제된 파일도
재생성하지 않으며, 실패 해시를 진단하고 성공 문구를 출력하지 않는다.

[`check_mutations.py`](../../../tools/evidence/audit6-archive-verify-before-put/check_mutations.py)는
저장·복원 함수 각각의 해시 검사를 제거하거나 쓰기 뒤로 이동하는 네 변이를
메모리에서만 만든다. 새 CLI 시험이 네 경우 모두 assertion 실패로 검출해야 통과하며,
건너뛰기·무관한 실행 오류는 검출 성공으로 세지 않는다.

명령·결과는 [실행 증거](../../../tools/evidence/audit6-archive-verify-before-put/README.md)에 기록한다.
기존 R2 스텁 시험도 재실행해 불일치 업로드 요청 없음, 체크섬 메타데이터 위조·누락,
정상 빈 객체, 중간 복원 실패·후속 GET 중단 및 예산 실패 반환 경로를 확인한다.
합성 바이트·임시 파일·모의 R2 응답의 로컬 회귀 증거이며 실제 공시 확보율,
R2 관측 목록 대조, 트윈·소비자 화면, P02/P03 전체·첫 출시 완료 증거를 대신하지 않는다.
