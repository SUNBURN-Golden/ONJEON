# Decision: blueprint ledger IDs use the BP-D namespace

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-29 08:32 KST); reversible. Applied in fix round 1 on 2026-10-29.

**Decision:** `docs/blueprint/DECISIONS.md` §1의 19개 확정 방향을 `BP-D-01`~`BP-D-19`로 개명했다. `DEC-D-xx.md` 파일명과 작업 게이트 `D-xx`는 유지한다. 원장·ADR·DEC 본문·설계 제안·R2 문서 참조를 갱신했고 [구→신 ID 대응표](../blueprint/DECISIONS.md#11-이전-id-대응표)를 남겼다. 결정 내용·승인 상태·게이트 등록은 변경하지 않는다.

**Why:** 원장의 BP-D-16은 R2 전환이고 DEC-D-16은 사용자 이해도 시험이다. 지적된 5개 D-xx 모두 tasks.json의 실제 게이트에서 사용된다. 문서 원장 쪽을 개명하면 실행 식별자를 보존하면서 혼동을 제거한다.

**Validation:** [회귀시험과 실행 증거](../../tools/evidence/audit3-dec-id-collision/fix-round1/README.md). 19개 원장 ID·대응표의 유일성과 완전성, 허용 범위 문서의 이전 참조 부재·신규 참조 유효성, 지적된 5개 결정의 의미와 실제 작업 게이트·DEC 파일명 보존을 검사한다. BLUEPRINT §11의 상태·관문을 검토하고 결정 색인·내용 해시를 갱신했다. 과거 실행 로그·diff와 수정 범위 밖의 조사 자료는 원형을 보존하며 원장 §1.1의 대응표로 해석한다.

**Options:** 원장 전체에 BP-D- 접두어 적용을 채택했다. DEC와 작업 게이트 개명은 실행 명세·상태 참조의 마이그레이션 부담으로 기각했다. 하이픈 차이 설명이나 지적된 5개만 개명하는 안은 같은 혼동이 남으므로 기각했다.

**Revisit if:** 이전 원장 표기를 기계 식별자로 사용하는 외부 소비자가 발견되거나 결정 ID 통합 체계를 도입할 때 마이그레이션 범위를 재검토한다.
