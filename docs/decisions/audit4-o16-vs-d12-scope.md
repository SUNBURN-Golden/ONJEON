# Decision: DEC-D-12 allows showing source excerpts in the product. Does that also settle O16, which is about pu

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-09 15:31 KST); reversible.

**Decision:** DEC-D-12로 O16 전체가 해결되지는 않는다. 소비자 앱의 원문 표시만 허용되었으며, 공개 GitHub 저장소 docs/blueprint/validation/extracts/에 새 원문 발췌를 추가하는 일은 O16 잔여 결정 전까지 차단된다. 기존 발췌와 Git 이력은 유지한다.

**Why:** DEC-D-12.md:30–33은 새 발췌 추가를 명시적으로 승인하지 않는다. BLUEPRINT.md:408, DECISIONS.md:102, 09_제품목적_대응표.md의 P14도 일치한다. python3 -B -m unittest tools.tests.test_decision_records tools.tests.test_purpose_table_decision_sync tools.tests.test_decisions_ledger_sync -v 실행 결과 47개 모두 통과했으며, 앱 표시와 저장소 재배포를 구분하는 회귀 검사도 포함된다. 감사의 범위 혼동은 해소됐지만 O16은 부분 해결 상태다. 이번 판단은 기존 승인 범위 확인이며 새로운 법적 판단이나 공개 승인이 아니다. 표시 플래그 적용·게이트 등록·P14 제품 완료 증거는 별도로 충족해야 한다.

**Options:** ['DEC-D-12를 공개 저장소 재배포 승인으로 확대하여 O16 종료 — 기각', '앱 표시 허용과 저장소 공개를 구분하고 O16 잔여 관문 유지 — 채택', '기존 발췌 삭제 및 Git 이력 정리 — 기존 결정에 반하므로 기각']

**Revisit if:** 소유자가 공개 저장소의 새 발췌 공개 범위와 재배포 조건을 명시적으로 결정하거나 DEC-D-12를 변경할 때, 또는 관련 문서·회귀 검사에 불일치가 생길 때.
