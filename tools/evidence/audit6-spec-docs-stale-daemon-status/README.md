# Audit 6 설계 문서의 데몬 상태 정정 증거

노드: `audit6-spec-docs-stale-daemon-status` · 실행일: 2026-11-17 KST.

설계검토 묶음의 README·02 구현계약·05 VM 실행 준비·06 점검표·그록봇 인계
README에서 T-OP-00·T-OP-09의 미구현 표기를 정정했다. 공용 모의 코어와 실제
실행기 검증 도구는 구현돼 있다. 상주 데몬·가동 승인·첫 출시 완료와 구분한다.

R2 인계 순서는 `daemon_rules.json`과 같은
`stop → isolate → confirm_quiescent → preserve → revoke_token → issue_next_lease`다.
가동 전 점검표의 실행기 범위는 R1~R22다. 과제 수는 지적 당시의 63개가 아니라
현재 `tasks.json`의 고유 ID **64개**에 맞췄다. 03 작업명세에 기록된 T-CT-08
추가 이력과 일치하며, 이번 변경에서 과제를 추가하거나 계약을 바꾸지 않았다.

기존 [2026-10-16 실행 보고서](../../../docs/vm_check/2026-10-16/RESULTS.md)의
PASS 17·PARTIAL 5·FAIL 0과 R6·R7·R9·R11·R21의 한계를 유지한다. 이 기록은
이번 노드가 실제 VM·벤더 CLI·운영 보호 브랜치·단기 자격을 재검증했다는 뜻이 아니다.
제품 완료는 계속 [09 제품 목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 증거로 판정한다.

## 검증

저장소 루트에서 실행했다. 회귀 검사는 하드코딩한 목표 개수 대신 현재 tasks의
고유 ID, 규칙의 인계 순서, R 시나리오 표와 기존 JSON 보고서에 문서를 대조한다.
구현 경로·보고서 링크와 PARTIAL·가동/출시 한계도 검사한다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_spec_docs_daemon_status.py -v` (문서 수정 전) | 5개 검사에서 11개 실패·하위 검사 실패로 기존 지적 검출 | [before.log](before.log) |
| 같은 명령 (수정 후) | 5개 통과, 종료 0 | [focused.log](focused.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,677개 실행·실패/오류 0·기존 건너뜀 6개, 종료 0 | [python-tests.log](python-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 46/46·존재 72/72 통과, 종료 0 | [spec-check.log](spec-check.log) |
| `python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet` | 필수 ID 33/33 실행, 검사 695건·실패 0, 종료 0 | [dry-run.log](dry-run.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --all --locked --offline` | 532개 통과·기존 무시 1개, 종료 0 | [rust-tests.log](rust-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml` | 4개 통과, 종료 0 | [ontology-tests.log](ontology-tests.log) |
| 허용 경로·보호 파일 제외·추가한 로컬 링크·공백 검사 | 통과 | [scope.log](scope.log) |

전체 Python 시험의 건너뜀 6개는 비공개 원본 미설정·로컬 보관본/추출기 조건과
구버전 botocore 전용 시험의 기존 환경 조건이다. 새 회귀 시험은 전부 실행했다.
최종 문서와 회귀 검사의 보고서 확인 두 항목은 집중 시험 5개로도 다시 확인했다.
로그는 행 끝 공백과 파일 끝 빈 줄만 정리했다.

허용 경로의 문서·회귀 시험·실행 증거만 변경했다. 보호 경로 변경, 저장소
commit/push, GitHub 호출, 비밀값 조회, 외부 수집·배포·운영 변경은 하지 않았다.
