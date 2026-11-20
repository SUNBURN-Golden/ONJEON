# Decision: `BLUEPRINT.md`, `README.md`, the ADRs and `PRINCIPLES.md` never mention `09_제품목적_대응표` or `tasks.json

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-20 19:24 KST); reversible.

**Decision:** Audit 8의 정본 누락 지적은 해결된 것으로 판정한다. ADR-0019가 이미 09_제품목적_대응표를 첫 출시의 완료 증거 기준으로, tasks.json을 작업별 실행·수락 계약으로 한정 채택했고 ADR-0020이 이를 재확인했다. 작업별 병합은 통합 브랜치 이력에서 확인한 뒤 tools/release_readiness/merged_tasks.json에 작업 ID와 병합 커밋의 전체 SHA를 기록한다. T-OP-08은 docs/release-readiness/evidence/readiness.json의 task_states와 수락 증거로 출시 준비 상태를 판정한다.

**Why:** 커밋 dcdb72c에서 docs/BLUEPRINT.md:25, README.md:38, 제안 묶음 README가 두 계약의 지위를 명시한다. docs/PRINCIPLES.md:9는 구현 기준을 BLUEPRINT에 위임한다. 따라서 빌더는 보호된 proposals/를 수정할 필요 없이 자기 작업의 증거를 docs/release-readiness/evidence/<작업 ID>/에 남길 수 있다. test_pr_policy와 test_audit7_task_bundle_adr의 31개 시험 및 check_product_purpose.py가 통과했다. 병합 원장의 20개 ID·SHA는 Git 1차 부모 병합 이력과 모두 일치했다. 전체 64개 작업 중 20개가 병합됐고, 완료 증거로 닫힌 제품 목적은 19개 중 0개다.

**Options:** ['기존 ADR-0019·0020과 병합 원장을 유지한다 (채택).', '새 D-21 ADR로 두 파일을 다시 채택하고 proposals/ 밖으로 옮긴다.', 'tasks.json에 작업별 병합 상태를 추가한다.']

**Revisit if:** 제품 완료 기준이나 두 계약의 권한·범위가 바뀌면 D-21 경로의 새 ADR로 검토한다. 후속 병합에서 원장과 Git 이력이 어긋나면 통합 브랜치의 병합 커밋을 확인해 원장을 정정한다.
