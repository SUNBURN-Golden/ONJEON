# Decision: the content hash includes `publication_state`, so moving a rule from candidate to released changes i

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-14 21:06 KST); reversible.

**Decision:** 기존 rule_content_hash 계약을 유지한다: publication_state와 근거를 포함하고 최상위 release_id만 제외한다. 후보 승인을 공개본 승인으로 자동 간주하지 않는다. 최종 승인 기록은 released 상태의 해시와 release_id에 결부하고 후보 해시와의 연결을 보존해야 한다.

**Why:** rule.rs:589, README, Audit 2·3 결정과 BLUEPRINT I2·I3는 계산 의미만이 아니라 로드한 규칙 내용을 식별하도록 정한다. 독립 Python 검증에서 고정 규칙 해시 8개 일치, 두 DSL 버전의 상태 변경 시 해시 변경·release_id 변경 시 동일성·근거 및 계산식 변경 탐지를 확인했다. 저장된 Rust content_hash_scope 로그도 7개 통과다. 다만 읽기 전용 환경에서 Rust 재실행이나 승인 흐름 수정은 하지 않았다. finding 전체의 완료 판정에는 최종 승인 해시와 결과 해시 일치, 오래된 후보 승인 및 승인 후 변조 거부를 검증하는 통합 증거가 필요하다. 이번 정책 결정만으로 09 대응표 P06·P08·P14 완료를 선언하지 않는다.

**Options:** ['채택: 내용 해시 유지, 최종 공개본 해시에 승인 연결', '기각: publication_state 제외로 기존 내용 식별 계약 변경', '유보: 상태와 독립적인 비교용 해시를 별도로 도입']

**Revisit if:** 승격 전후 동일 식별자가 필요한 기능이 구체화되면 별도의 버전 있는 비교용 해시를 검토한다. 기존 해시의 의미를 조용히 변경하지 않는다.
