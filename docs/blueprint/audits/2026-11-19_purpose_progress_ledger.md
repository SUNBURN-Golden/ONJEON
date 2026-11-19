# Audit 7 — 제품 목적 진척 보고

기준 커밋 `5f02e505f0483626b79b701caac95507add612ef`에서 P01~P19는
**0/19 닫힘**, 전체 과제는 **20/64 병합**이다. Audit 7 착수 설명의
3건은 이 체크아웃의 병합 이력과 차이가 있다. `git log --first-parent --merges`의
과제 브랜치 ID를 `tasks.json`과 대조해 20개 고유 ID와 병합 SHA를 확인했다.
전체 과제 집계에는 개발 도구 T-OP-00·T-OP-09도 포함한다.
[병합 목록](../../../tools/release_readiness/merged_tasks.json).

`python3 -I tools/release_readiness/progress.py`의 로컬 실행은 P01~P19를
모두 표시하고 종료 코드 0을 반환했다. P02는 연결 과제 6개 중 T-DT-01·T-DT-02가
병합됐고 과제별 파일 0/6, 등록부 파일 0/0, 상태 Open이다. 현행
`readiness.json`으로 증거 판정기를 실행하면 P행 19개와 기능 64개가
열려 있고 종료 코드는 1이다. T-OP-08은 [09 §6](../proposals/설계검토_결과/09_제품목적_대응표.md#6-최종-관문과의-연결)의
완료 증거를 검토한다.

## 검증

| 명령·검증 대상 | 결과 |
|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_purpose_progress.py -v` | 8개 통과. 부분 병합·19개 행 분모, 등록 전 과제 파일, 행 증거 파일·수락 로그, 유효하지 않은 입력, CI 요약 기록을 검사했다 |
| CI 보고 단계의 셸 본문 | 현재 입력에서는 종료 0과 보고 표, 합성 입력에서 병합 목록을 제거하면 종료 2와 진단을 요약 파일에 기록했다. 워크플로의 `continue-on-error: true`를 시험에서 확인했다 |
| 제품 목적 정적 검사와 증거 판정기 회귀 시험 | 각각 20개와 17개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,725개 실행, 실패 0, 기존 건너뜀 6개 |
| `cargo test --all --locked --offline` 및 독립 Cargo 작업 공간 | workspace 536개 통과·기존 무시 1개. 시나리오 API와 온톨로지 실행기 각각 4개 통과 |
| CI 검사기와 설계 계약 검사 | CI 검사기 회귀 시험 21개 통과. 설계 계약의 기계 검사 47/47, 존재 검사 72/72 통과 |

보고서 사용법과 병합 목록 갱신 절차는 [도구 안내](../../../tools/release_readiness/README.md#product-purpose-progress)에 있다.
