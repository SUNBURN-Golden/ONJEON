# Decision: the audit goal says completion is judged by 09. But `tasks.json:2` says it is "채택된 정본이 아니다", and nei

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-09 14:38 KST); reversible.

**Decision:** 기존 ADR-0019의 한정 채택을 유지하고 이 지적은 이미 해소된 것으로 판정한다. 새 ADR이나 파일 수정은 불필요하다. BLUEPRINT를 단일 진입점으로, 09를 제품 완료 증거 기준으로, tasks.json을 작업 실행·개별 수락 계약으로 유지한다.

**Why:** 현재 tasks.json:2는 정본 미채택이 아니라 ADR-0019에 따른 한정 채택을 명시한다. BLUEPRINT §0.1·§9.5와 README에도 두 계약의 역할과 위계가 반영되어 있다. 직접 검증에서 test_pr_policy.py 23개 통과, check_product_purpose.py 통과, spec_check.py 기계 45/45·존재 72/72 통과, blueprint_status.py 통과를 확인했다. test_product_purpose.py 17개는 읽기 전용 환경의 임시 디렉터리 생성 제한으로 실행 오류가 발생해 통과 증거에서 제외한다. 이 판정은 문서 정합성에 한정하며 제품 출시 완료를 의미하지 않는다. 제품 완료에는 T-OP-08 purpose-rows-all-closed와 P01~P19의 실제 증거가 필요하다.

**Options:** ['기존 ADR-0019 채택과 반영 상태를 검증하여 지적 종료', '동일 내용을 새 ADR로 중복 채택', '제안 묶음 전체를 정본으로 승격', '09와 tasks.json의 채택 철회']

**Revisit if:** 완료 범위·증거 기준·작업 소스가 변경되거나 상위 계약과 충돌하면 재검토한다. 변경 시 ADR과 BLUEPRINT·09·tasks.json·결정 원장을 함께 동기화한다.
