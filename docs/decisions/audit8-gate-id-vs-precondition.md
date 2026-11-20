# Decision: the daemon opens a gate once a decision id is registered, but several DEC files say the precondition

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-20 21:21 KST); reversible.

**Decision:** 아니요. 결정 ID는 정책 기록으로 보존한다. `real_data`와 `merge`는 해당 작업·행위에 적용되는 선행조건의 증거와 DEC가 요구하는 승인을 모두 확인한 뒤에만 연다. 증거가 없거나 일부만 충족되면 `real_data_allowed=false` 또는 `merge_wait(decision_pending)`을 유지한다. 그동안 합성·모의 작업과 별도 게이트가 없는 병합은 계속할 수 있다.

**Why:** 관련 회귀시험 23개가 통과했다. 별도로 현재 tasks.json의 게이트를 모의 데몬에 넣고 증거 없이 ID만 등록했다. D-17은 T-PS-01·02·03, D-02는 T-KN-06·T-OP-02의 다음 임대에서 real_data_allowed를 false에서 true로 바꿨다. O14는 T-OP-04를 decision_pending에서 ready로 바꿨다. 이는 daemon_rules.json의 ID 부분집합 판정과 일치한다. 그러나 D-17에는 제공자의 학습 미사용·보존·처리 지역 확인, 별도 동의와 백업 보존·삭제 안내가 필요하다. D-02에는 비-Claude 계열의 실제 API 호출·모델 식별 및 제공자 조건 확인이, O14에는 잠금 범위·기간 등 미정값 확정과 소유자의 적용 승인이 필요하다. O17은 T-DT-05의 별도 release 게이트이므로 O14 병합만으로 예약·대량 수집을 켤 수 없다. 이번 가역적 정책 결정과 재현으로 우회를 확인했으며, 코드상 차단은 미구현이다.

**Options:** ['ID 등록 즉시 해제 — DEC가 명시한 미충족 조건을 건너뛰므로 기각.', '담당자가 증거를 확인할 때까지 ID 등록을 미룸 — 현행 데몬의 임시 운영 통제로 채택.', '결정 기록과 조건 충족을 구분하고, 작업·게이트별 증거로 해제를 판정 — 최종 방식으로 채택.']

**Revisit if:** 각 DEC의 증거와 필수 승인이 확보되면 해당 게이트만 재판정한다. 구현상 finding은 ID만 등록한 경우, 증거가 일부인 경우, 다른 작업의 증거를 쓴 경우가 모두 차단되고 유효한 증거가 갖춰진 해당 게이트만 열리는 회귀시험이 통과할 때 닫는다. 첫 출시 완료는 09_제품목적_대응표의 완료 증거로 별도 판정한다.
