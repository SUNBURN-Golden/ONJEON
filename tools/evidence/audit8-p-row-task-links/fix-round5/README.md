# Fix round 5: main 병합 충돌 해소 — 작업 연결과 결정 상태 열 유지

5차 수정의 요청은 진행 중인 `git merge`의 충돌을 해소하되 양쪽 의도를
모두 유지하는 것이다. 이 노드(`audit8-p-row-task-links`)는 09 대응표에
시험 담당 과제 연결과 P20을 추가했고, `origin/main`은
`audit8-decision-status-sync`·`audit8-decision-id-namespaces`로
`결정 상태(작업·범위)` 열과 결정 ID 구분을 추가했다.

| 충돌 파일 | 해소 |
|---|---|
| `docs/blueprint/DECISIONS.md` | 머리말 한 줄만 충돌했다. `Audit 8 완료 범위 P20 확장·결정 상태 동기화`로 양쪽 변경을 함께 남겼다. 본문의 BP-D-23(P20)·§1.2 ID 구분표·DEC 상태 표는 자동 병합된 양쪽 내용을 그대로 유지했다 |
| `docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md` | 1·3절 표가 충돌했다. 이 노드의 행 내용(작업·증거)을 기준으로 두고 main의 `결정 상태(작업·범위)` 열을 11번째 열로 삽입했다. main이 바꾼 P14 `축소·후속` 문구(`O16의 저장소 공개 범위·… 잔여`)와 결정 상태 안내 문단은 유지했다. P20 행도 같은 11열 형식으로 맞췄다 |

보존한 이 노드의 의도: P02의 T-DT-04·T-AP-04, P03의 T-WB-01, P08·P16의
T-MB-04, P18의 익명 열람 과제(T-AP-01·T-MB-01·T-MB-03)와 `entry_points`
증거, P20 개인정보 보호·복구 행. 보존한 main의 의도: 09의
`결정 상태(작업·범위)` 열, ID 구분표, DEC 상태 표, P14의 O16 잔여 조건.

`결정 상태` 칸은 손으로 채우지 않고 `python3 tools/decision_status.py --write`로
`tasks.json`·결정 원장에서 생성했다. 표의 구분선 열 수가 11열과 맞도록
정리했고, 열이 하나 늘어난 것에 맞춰 두 시험을 갱신했다.

| 시험 갱신 | 이유 |
|---|---|
| `tools/tests/test_decision_status.py` | 행 집합을 P01~P20으로 확장 |
| `tools/tests/test_product_purpose.py` | P20의 `축소·후속` 칸을 마지막 열(`[-1]`)로 읽도록 변경(결정 상태 열 삽입) |

## 재실행 결과

명령과 전체 출력은 [static-checks.log](static-checks.log),
[merge-tests.log](merge-tests.log), [python-tests.log](python-tests.log)에 있다.

| 실행 | 결과 |
|---|---|
| `python3 -I tools/decision_status.py` | 결정 색인·표 최신, 종료 0 |
| `python3 -I tools/ci/check_product_purpose.py` | 09 P01..P20 연결, 종료 0 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47, 존재 72/72, 전체 통과 |
| 관련 시험 45개(결정 상태·대응표·완료 범위·제품 목적) | 전부 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,809개 중 1,738개 통과, 71개 건너뜀, 실패·오류 0, 종료 0 |

이 기록은 병합 충돌 해소와 문서·도구 정합성 증거다. 실제 동의·삭제·복원·
누출·롤백 실행 기록이나 P20 완료 증거가 아니다.
