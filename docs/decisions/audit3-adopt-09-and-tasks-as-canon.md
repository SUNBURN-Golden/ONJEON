# Decision: 09_제품목적_대응표 and tasks.json serve as the completion bar and the daemon's task source. But they live u

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-29 08:05 KST); reversible.

**Decision:** 09와 tasks.json을 BLUEPRINT 하위의 완료·실행 계약으로 한정 채택한다. 새 ADR로 BLUEPRINT §0.1·§9·§13과 README·DECISIONS에 역할을 명시한다. 09는 제품 완료 증거 기준, tasks.json은 데몬 작업·개별 수락 기준으로 유지한다. 기존 경로는 유지하되 미채택 문구와 관련 회귀검사를 함께 갱신한다. 전체 제안 묶음·온톨로지·공통 PR 기준의 일괄 채택은 포함하지 않는다.

**Why:** DEC-BUNDLE-STATUS는 2026-10-13 사용자 결정으로 실행·완료 기준이 이미 채택됐음을 기록한다. 지적과 달리 README와 BLUEPRINT §4·§11도 09를 참조한다. 남은 결함은 문서 위계와 실행 계약의 명시적 통합이다. 기준 철회는 사용자 목적과 T-OP-08의 purpose-rows-all-closed를 훼손한다. 직접 검증에서 check_product_purpose.py 통과, spec_check.py 기계 45/45·존재 72/72 통과, test_pr_policy.py 19개 통과를 확인했다. 이는 현행 명세 정합성 증거이며 정본 채택 반영이나 제품 완료 증거는 아니다. 최초 응답은 결정만 반환했다. Fix round 1에서는 ADR-0019와 문서 위계·상태·회귀 시험을 실제 반영했다. 검증 결과는 [Audit 3 증거](../blueprint/audits/2026-10-29_adopt_09_and_tasks.md)를 따른다.

**Options:** ['두 파일의 역할만 ADR로 정식 채택', '현재의 실행 기준 채택·정본 미채택 상태 유지', '완료 기준과 데몬 작업 소스에서 제외', '제안 묶음 전체를 정본으로 채택']

**Revisit if:** 사용자가 완료 기준을 변경하거나, D-21 경로의 독립 리뷰에서 상위 정본과 충돌이 확인되거나, 작업 소스를 이전할 때 재검토한다. 실제 데이터·화면·출시 증거 없는 완료 판정은 계속 불허한다.
