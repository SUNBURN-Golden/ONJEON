# DEC-D-15: 뷰모델 근거 종류·적용 확인

상태: 선택안 기록·감리 대기(2026-11-18), 사용자 확정 아님, 병합 미승인.

| 필드 | 내용 |
|---|---|
| decision_id | `DEC-D-15` |
| proposer | Codex, Audit 6 누락 관문 보완 요청에 따른 가역 작업 계약 정리 |
| scope | T-CT-03, T-CT-08, T-MB-01의 merge 관문 |
| approval | 미승인. 이 기록 생성은 `decisions_recorded` 등록이 아니다 |

06 §3.4의 선택안을 감리 입력으로 유지한다. amounts[].source 계약과 evidence_kind={terms, summary, disclosure, user_input}, applicability={applies, not_applies, unverified}를 구분한다. 큰 금액은 source=scenario: 그리고 evidence_kind=terms인 경우만 표시한다. summary+unverified는 근거 영역에만 둔다. 필수화·어휘 승격은 T-CT-08의 별도 canon_change 절차다.

기존 [06 검토 선택안](../blueprint/proposals/설계검토_결과/06_검토사항_점검.md)과 [03 §5](../blueprint/proposals/설계검토_결과/03_작업명세.md)의 감리 전 병합 대기를 작업 ID로 구체화했다. 새 상위 정책을 확정하지 않는다. 선택안을 버리고 의존성을 삭제하는 안은 기존 차단 조건을 약화하므로 채택하지 않는다.

등록 조건: 공통 뷰모델 선택안(필수 축·어휘·큰 금액과 요약서 표시 경계)의 대상 SHA에 고정된 독립 설계 감리 결과를 이 기록에 연결한 뒤 D-15를 별도로 등록한다. 감리 주체·대상 SHA·결과·증거 링크가 없는 현재는 등록하지 않는다. 공통 설계 선택의 감리는 T-CT-03 병합 전에 수행할 수 있으며 후행 T-CT-08·T-MB-01 구현 완료를 선행 조건으로 요구하지 않는다. 등록 후에도 각 과제의 필수 축 거부·생성 타입·화면 표시 시험과 해당 PR의 리뷰·감리를 따로 통과해야 한다. 공통 선택안 승인은 세 PR의 구현 승인이나 병합 지시가 아니다.

작성·로컬 시험은 이 merge 관문이 막지 않는다. 선행 과제·정본 변경 승인·독립 리뷰·사용자 병합 지시는 그대로 적용한다. 기존 병합을 소급 승인하지 않는다. 선택안·작업 범위가 바뀌거나 감리 증거가 확보되면 재검토한다.
