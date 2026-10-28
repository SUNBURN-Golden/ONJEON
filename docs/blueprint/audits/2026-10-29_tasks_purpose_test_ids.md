# Audit 3: 제품 목적 시험 ID의 과제별 누락

2026-10-29 · 노드 `audit3-tasks-purpose-test-ids`

09 §6은 세 UX 시험을 T-MB-03·T-MB-04·T-AP-07 각각에 배정했지만, `first-view-priority`는 T-MB-03에만 있었다. P16의 API·실제 사건 작업에도 `decisive-conditions-not-hidden` 등록이 빠져 있었다. 기존 검사기는 전체 과제에서 ID가 한 번이라도 나오면 통과해 이 누락을 검출하지 못했다.

| 필수 시험 ID | 이번에 등록을 보완한 과제 | 기준 |
|---|---|---|
| `first-view-priority` | T-MB-04, T-AP-07 | 09 §6·P15 |
| `decisive-conditions-not-hidden` | T-AP-07, T-AP-02, T-AP-08 | 09 §6·P16 |

`tasks.json`의 필수 ID·시험 설명·완료 기준과 03 작업명세의 대응 행을 함께 수정했다. 첫 뷰 시험 설명은 각 과제가 담당하는 화면에 한정한다. T-AP-02는 결과를 바꾸는 조건을 응답에서 제거한 변이를 거부하는 계약 시험, T-AP-07·T-AP-08은 해당 조건을 숨긴 화면 변이를 거부하는 시험을 요구한다. 09 §6은 P16의 추가 담당 과제를 명시한다.

`tools/ci/check_product_purpose.py`의 `PURPOSE-OWNER` 검사는 09 §6·P16이 지정한 아홉 ID의 과제 배정 18쌍을 검사한다. 다른 과제에 같은 ID가 남아 있거나 `tests`·`done_criteria`에 설명만 있어도 지정 과제의 `required_test_ids` 누락은 실패다. 지정 과제 자체가 없어도 실패한다. 기존 전체 ID·P01~P19 참조·행 구조 검사를 유지한다.

`tools/tests/test_product_purpose.py`는 기존 CI의 Python discovery로 실행된다. 18쌍 각각의 ID를 삭제하고 다른 과제에 남기는 변이, 아홉 ID 전체 누락, 각 목적 행의 잘못된 과제 참조, 지정 과제 삭제를 검사한다. 독립된 UX 배정표로 실제 JSON을 검사하고, 시험 설명 존재와 03의 필수 ID·완료 기준 일치도 확인한다. 워크플로 수정은 없다.

실행 로그와 명령·결과는 [검증 증거](../../../tools/evidence/audit3-tasks-purpose-test-ids/README.md)에 있다. 수정 전 검사 결과는 정확히 다섯 누락을 보고했다.

이 증거는 **작업 배정·명세·정적 검사의 회귀 검증**이다. 실제 화면의 첫 뷰 캡처, 조건 비은닉 UI 시험, 소비자 이해 시험을 실행했다는 뜻이 아니며 P15·P16 또는 출시 완료 증거를 대신하지 않는다. 제품 완료 판정은 계속 09의 완료 증거를 따른다.
