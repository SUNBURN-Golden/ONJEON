# Decision: the content hash covers `publication_state`, so moving a rule from candidate to released changes its

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-30 11:21 KST); reversible.

**Decision:** 의도된 동작으로 확정하고 유지한다. publication_state는 규칙 내용 해시에 포함한다. candidate→released 승격은 재검증·재해시하며, released 상태에서 최상위 release_id만 바꾸는 재출시는 같은 해시를 유지한다.

**Why:** rule.rs:569의 구현, 엔진 README:15, audit2-hash-semantic-normalization 결정은 최상위 release_id만 제외하도록 명시한다. 이 해시는 계산 논리만이 아니라 상태·근거를 포함한 규칙 내용을 식별하며 BLUEPRINT I2·I3의 추적·재검증 계약과 일치한다. 검증: 기존 content_hash_scope 바이너리 7개 시험 통과. 독립 Python SHA-256 계산으로 고정 fixture 해시 일치, 두 DSL 버전에서 세 publication_state의 해시 차이와 release_id만 변경할 때의 동일성을 확인했다. 읽기 전용 환경으로 새 Rust 빌드·회귀 테스트 추가는 하지 않았다. 이 증거는 해시 정책 판단에 한정하며 제품 출시 완료 증거를 대체하지 않는다.

**Options:** ['채택: publication_state 포함·최상위 release_id 제외라는 기존 계약 유지', '기각: publication_state도 제외해 승격 전후 해시를 동일하게 변경', '유보: 상태와 무관한 비교가 필요할 때 별도의 버전 있는 논리 해시 추가']

**Revisit if:** 승격 전후 동일 식별자를 요구하는 승인·캐시·중복 탐지 기능이 생기면 재검토한다. 기존 내용 해시는 보존하고 별도 논리 식별자나 후보·공개본 해시 연결을 설계한다. 해시 자체를 공개 승인 증거로 사용하지 않는다.
