# Decision: DEC-D-02/04/07/12/16 reuse the IDs D02/D04/D07/D12/D16 in DECISIONS.md, which mean unrelated things 

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-29 08:32 KST); reversible.

**Decision:** docs/blueprint/DECISIONS.md §1의 D01~D19를 BP-D-01~BP-D-19로 개명한다. DEC-D-xx 파일명과 작업 게이트 D-xx는 유지한다. 원장 참조를 함께 갱신하고 구→신 ID 대응표를 남긴다. 결정 내용·승인 상태·게이트 등록은 변경하지 않는다.

**Why:** 원장의 D16은 R2 전환이고 DEC-D-16은 사용자 이해도 시험이다. 지적된 5개 D-xx 모두 tasks.json의 실제 게이트에서 사용된다. 문서 원장 쪽을 개명하면 실행 식별자를 보존하면서 혼동을 제거한다. 검증: test_decision_records.py 13개 통과, 제안한 19개 ID의 유일성과 작업 게이트와의 비중복 확인. 현재 읽기 전용 환경이므로 변경은 미적용이다. finding 완료는 참조 갱신·누락 검사·회귀시험 및 BLUEPRINT §11 색인 갱신 증거가 남은 뒤 판정한다.

**Options:** ['원장의 Dxx 전체에 BP-D- 접두어 적용 — 채택', 'DEC-D-xx와 작업 게이트 D-xx 개명 — 실행 명세·상태 참조의 마이그레이션 부담으로 기각', '하이픈 차이만 설명하거나 지적된 5개만 개명 — 동일한 혼동이 남아 기각']

**Revisit if:** Dxx를 기계 식별자로 사용하는 외부 소비자가 발견되거나 결정 ID 통합 체계를 도입할 때 마이그레이션 범위를 재검토한다.
