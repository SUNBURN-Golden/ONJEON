# Decision: `tasks.json:2` says it is not adopted canon, and BLUEPRINT never mentions `tasks.json` or 09. Should

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-17 17:36 KST); reversible.

**Decision:** 두 문서를 BLUEPRINT 하위의 구속력 있는 계약으로 한정 채택한 현행 결정을 유지한다. tasks.json은 작업 계획·개별 수락 기준, 09는 제품 완료 증거 기준이다. ADR-0019와 BLUEPRINT §9.5·§13에 이미 반영되어 있으므로 이 지적은 해결된 것으로 판정한다.

**Why:** 현재 tasks.json:2는 한정 채택을 명시하며 BLUEPRINT §0.1·§9.5·§13도 두 계약을 연결한다. 직접 검증에서 test_pr_policy.py 25개, check_product_purpose.py, spec_check.py 기계 46/46·존재 72/72, blueprint_status.py가 모두 통과했다. 제품 완료는 근거 있는 제외 외 P01~P19의 실제 증거와 T-OP-08 purpose-rows-all-closed로 판정한다. 이번 검증은 문서·명세 정합성 증거이며 제품 완료를 뜻하지 않는다. 제안 묶음 전체와 common_done_criteria는 채택 범위에 포함하지 않는다.

**Options:** ['현행 한정 채택 유지', '정본 미채택 상태로 되돌리기', '제안 묶음 전체를 정본으로 채택']

**Revisit if:** 사용자가 제품 범위·완료 기준을 변경하거나 상위 계약과의 충돌 또는 작업 소스 이전이 발생하면 새 ADR과 BLUEPRINT·두 계약을 함께 갱신한다.
