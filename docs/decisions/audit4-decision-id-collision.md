# Decision: public-price direction BP-D-08 and criteria gate D-08 use separate namespaces

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-04 15:05 KST); reversible.

**Decision:** 확정 방향 원장의 Dxx 네임스페이스를 BP-D-xx로 변경한다. 공개 가격 결정은 BP-D-08, 판단 기준 적용 게이트는 D-08 및 DEC-D-08.md를 유지한다. 저장소에는 이미 적용되어 있어 추가 개명 없이 기존 해결을 채택한다.

**Why:** [결정 원장 §1·§1.1](../blueprint/DECISIONS.md#11-이전-id-대응표)과 [Audit 3 결정](audit3-dec-id-collision.md)에 개명 및 이전 ID 대응표가 있다. BP-D-08은 공개 가격 수집·표시·비교 방향이고, [DEC-D-08](DEC-D-08.md)은 판단 기준 적용 조건을 기록한다. tasks.json의 D-08은 T-KN-14 release에만 연결된다. 결정 내용·승인·게이트 상태를 바꾸지 않는 가역적 식별자 정리다.

**Options:** ['원장 전체를 BP-D-xx로 개명 — 채택', '실행 게이트와 DEC 파일명 개명 — 실행 참조 마이그레이션 부담으로 기각', '공개 가격 결정만 개명하거나 하이픈 차이만 설명 — 다른 번호의 혼동이 남아 기각']

**Validation:** Fix round 1에서 이 기록의 이전 원장 표기를 현행 참조로 정정했다. 현행 문서 참조 검사 대상에서는 이전 표기를 원장 §1.1 대응표에서만 허용한다. 검사 대상 밖인 `docs/research`의 역사적 표기는 원장 §1.1의 대응표로 해석한다. Audit 3에서 작성한 기존 회귀시험은 BP-D-08의 공개 가격 의미와 D-08의 작업 게이트·DEC 파일명 보존을 포함한다. [Fix round 1 시험 증거](../../tools/evidence/audit4-decision-id-collision/fix-round1/README.md)와 [Fix round 2 재검증·PR 본문 수정 인계](../../tools/evidence/audit4-decision-id-collision/fix-round2/README.md)를 참조한다.

**Revisit if:** 이전 원장 ID를 기계 식별자로 사용하는 외부 소비자가 발견되거나, 원장과 실행 게이트의 통합 ID 체계를 도입할 때.

**Fix round 3:** CI 41804857097도 노드 ID가 없는 PR 본문으로 실패했다. 네임스페이스 결정은 유지하며 [본문 교체안·재검증 증거](../../tools/evidence/audit4-decision-id-collision/fix-round3/README.md)를 제공한다. 감독자가 PR 본문을 적용하고 새 pull-request 실행을 시작해야 한다. 로컬 파일 변경만으로 원격 PR 본문이나 실패한 실행이 갱신되지는 않는다.
