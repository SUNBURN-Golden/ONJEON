# Decision: most `DEC-*` records were made by the autoloop on the owner's behalf; only D-04 and D-12 are direct 

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-04 14:50 KST); reversible.

**Decision:** DEC는 기존 설계·위임 범위 안의 조건부 개발 기준과 결정 증거로 유효하다. 전부 ADR로 전환하거나 소유자 재승인을 받을 필요는 없다. 다만 상위 결정·게이트 조건·완료 기준을 변경하려면 ADR → BLUEPRINT §7 갱신과 관련 계약 동기화가 필요하다. 소유자 승인이 요구되는 사항은 별도 승인을 충족해야 하며, ADR 작성만으로 승인되지 않는다. 기존 게이트의 조건 충족과 등록은 게이트 정의 변경과 구분한다. DEC 존재·색인·자동 루프 완료만으로 게이트를 해제하지 않는다.

**Why:** BLUEPRINT §0.1은 DEC가 ADR을 대신하지 않는다고 명시하고, §10 규칙 3은 결정 변경에 ADR → §7을 요구한다. ADR-0019도 같은 경계를 유지한다. D-04·D-12의 직접 결정은 명시된 범위에서 존중하되 다른 관문까지 면제하지 않는다. D-02·O12는 사용자 확정이 아닌 잠정 개발 기준이다. 검증: test_decision_records·test_decisions_ledger_sync·test_purpose_table_decision_sync 39개, StartGateEnforcement·PrereqAndMergeGateCond 19개 통과. blueprint_status.py는 ADR/DEC 37개 색인 정상 확인. 별도 상태 갱신 시험 16개는 읽기 전용 환경의 임시 디렉터리 생성 제한으로 실행 오류였다. 이 증거는 권위 구분과 기존 게이트 동작을 확인하며, 소유자 승인이나 09 제품 완료 증거를 대신하지 않는다. 파일·게이트 변경은 수행하지 않았다.

**Options:** ['모든 DEC를 소유자 확정 및 게이트 해제 권한으로 인정: 기각', '모든 DEC에 ADR 전환 또는 소유자 재승인을 요구: 기각', '위임 범위의 개발 기준은 유지하고, 설계 변경·승인·증거·게이트 등록을 구분: 채택']

**Revisit if:** 소유자가 위임 범위나 기존 결정을 명시적으로 변경하거나, DEC가 상위 계약과 충돌하거나, 게이트 조건·완료 증거 기준을 변경하려 하거나, 자동 등록이 승인·필수 증거 확인을 우회하는 경로가 발견될 때.
