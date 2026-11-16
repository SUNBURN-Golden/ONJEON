# Audit 6: 제품 목적 대응표와 필수 시험 과제 연결

2026-11-17 · 노드 `audit6-purpose-table-test-id-mapping`

BLUEPRINT §13·ADR-0019 아래 09의 P06·P15·P16·P17과 `tasks.json`을 대조했다. 작업 계약과 제품 완료 증거의 추적 정합성을 검증한다.

현재 기준 트리에는 Audit 3의 보완이 이미 있다. T-MB-04·T-AP-07은 `first-view-priority`와 `decisive-conditions-not-hidden`을 등록하고 있으며, T-AP-08도 `decisive-conditions-not-hidden`을 등록한다. 이를 삭제했을 때 다른 과제에 ID가 남아 있어도 실패하는 회귀 시험을 유지했다.

남아 있던 두 불일치를 수정했다.

| 행 | 불일치 | 수정 |
|---|---|---|
| P06 | 완료 증거의 `profile-historical-vs-service`는 T-KN-04에 있지만 구현 작업 칸에 그 과제가 없었다 | P06에 T-KN-04를 추가하고 서비스 적재기 담당을 명시했다. T-KN-01의 라이브러리 검사·T-KN-02의 픽스처 표식 검사와 서비스 적재기 거부 책임을 그대로 구분한다 |
| P17 | T-AP-09가 구현 작업에 있지만 `no-composite-score`가 필수 ID에 없었다 | T-AP-09의 ID·시험 설명·완료 기준을 추가하고 03 대응 행과 09 §6을 맞췄다. 공개·개인 응답의 점수·순위·추천 정답 부재와 결과별 이유·근거를 요구한다 |

`check_product_purpose.py`는 두 시험의 담당 과제 등록을 `PURPOSE-OWNER`로 검사하고, P06·P17에서 담당 과제를 빼면 `PURPOSE-ROW-OWNER`로 보고한다. 기존 아홉 G12 ID와 P01~P19 구조·참조 검사를 유지한다. `profile-historical-vs-service`는 G12 아홉 ID에 추가하지 않고 P06의 별도 필수 배정으로 검사한다.

회귀 시험은 독립된 배정표로 실제 JSON의 필수 ID·시험 설명과 03의 완료 기준을 확인한다. 각 담당 과제에서 ID를 제거하되 다른 과제·설명에 남기는 변이, P06·P17에서 담당 참조만 제거하는 변이를 거부한다. 기존 CI Python discovery에서 실행되며 워크플로 변경은 없다.

명령·실행 결과와 수정 전 두 실패는 [검증 증거](../../../tools/evidence/audit6-purpose-table-test-id-mapping/README.md)에 기록한다. 이는 작업 계약·정적 검사 finding의 증거이며 실제 UI 수락 시험·화면 캡처·소비자 이해도·P행 전체·첫 출시 완료 증거를 대신하지 않는다. 제품 완료 판정은 계속 09의 실제 완료 증거를 따른다.
