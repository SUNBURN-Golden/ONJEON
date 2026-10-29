# Decision: DEC-D-04 (keep the R2 token) contradicts BLUEPRINT §12 l.337 ("no further collection until the token

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-29 10:23 KST); reversible.

**Decision:** 현재 저장소에서는 이미 반영 완료된 지적으로 판정한다. BLUEPRINT §12와 DECISIONS.md를 추가 수정하지 않고, 기존 정정 근거와 회귀 검사 통과로 문서 불일치 finding을 종료한다.

**Why:** BLUEPRINT §12:393과 DECISIONS.md O13은 토큰 미폐기를 반영하면서 재사용·출력 금지와 실제 R2 접근 차단을 유지한다. §12:397과 O16은 앱 원문 표시 허용을 반영하고 공개 저장소의 새 발췌·기타 재배포 조건만 잔여로 남긴다. 기존 근거는 docs/blueprint/audits/2026-10-27_blueprint_open_decisions_stale.md에 있다. 이번 검증에서 test_o13_ruling.py 13개, test_decision_records.py 13개 및 blueprint_status.py가 모두 통과했다. 이는 문서 정합성 판정이며 자격증명 변경·법적 판단·표시 플래그 활성화나 09 제품 완료 판정은 아니다.

**Options:** ['현재 문서의 반영 상태를 검증하고 종료 — 채택', '동일 내용을 다시 수정 — 이미 반영되어 불필요', 'D-04 접근 관문 해제와 O16 전체 종료 — 소유자 결정 범위를 넘으므로 기각']

**Revisit if:** 소유자가 토큰·접근 자격 또는 원문 표시 결정을 변경하거나, 실제 R2 접근·표시 플래그 활성화·공개 저장소 발췌 추가를 추진하거나, 관련 회귀 검사가 실패할 때.
