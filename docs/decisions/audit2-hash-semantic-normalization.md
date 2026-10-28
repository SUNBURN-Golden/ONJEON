# Decision: equivalent spellings (`"amt"` vs `{"input":"amt"}`, `"0.5"` vs `"0.50"`) hash differently. Should th

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-10-28 09:20 KST); reversible.

**Decision:** 기존 rule_content_hash는 유지한다. 검증된 원본 JSON 값의 객체 키를 재귀 정렬하고 최상위 release_id만 제외해 해시하며, 파싱된 AST의 의미 정규화 해시로 교체하지 않는다. 동등한 표기의 해시 차이는 명시된 내용 식별 계약으로 수용한다.

**Why:** BLUEPRINT I2·I3와 제품목적 P08·P14는 규칙 내용 식별과 재현·근거 추적을 요구한다. packages/rules-engine/README.md:14와 tests/content_hash_scope.rs는 같은 지급 결과라도 표기·기본값·근거 배열 변경을 구별하도록 명시한다. 또한 parse_rate는 0.5와 0.50을 각각 5/10과 50/100으로 보존하므로 AST 직렬화만으로 의미 정규화되지 않는다. 검증: 기존 content_hash_scope 바이너리 7개 시험 재실행 통과, Python 독립 계산으로 입력 별칭·요율 표기 4종의 해시 차이와 고정 fixture 해시 일치 확인. 저장된 focused.log에도 관련 시험 11개 통과 기록이 있다. 읽기 전용 환경이므로 새 빌드·파일 수정은 하지 않았다. 이는 해시 정책 판단의 근거이며 첫 출시 완료 증거를 대체하지 않는다.

**Options:** ['채택: 현재 내용 해시와 기존 감사·재현 기록의 호환성을 유지한다.', '기각: 정규화된 AST로 기존 해시를 교체한다. 규칙 인코딩 변경의 식별력이 줄고 기존 해시 계약이 변경된다.', '필요 시 재검토: 별도 버전이 있는 semantic_hash를 추가해 중복 탐지에 사용한다.']

**Revisit if:** 실제 소비 기능이나 중복 탐지에 의미 동등성 식별이 필요해지면 재검토한다. 별도 semantic_hash의 정규화 범위·버전, 요율 기약분수화, 기본값·타입·연산 순서·근거 보존 및 회귀 시험을 먼저 정의하고 기존 내용 해시를 보존한다.
