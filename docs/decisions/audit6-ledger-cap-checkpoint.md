# Decision: the 100-record ledger cap with no checkpoint tool (O17) runs out after about 16 `sources.yml` dispat

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-15 20:15 KST); reversible.

**Decision:** 100건 상한을 유지하고 이미 구현된 체크포인트 도구를 채택한다. 신규 구현이나 상한 인상은 불필요하다. 지정 환경의 수동 운영에서 상한 도달 전에 체크포인트를 수행한다.

**Why:** 현재 HEAD 37a4e62에는 체크포인트 CLI와 100건 복구가 구현되어 있다. 상한은 최신 체크포인트 이후 기록에 적용되며 원본 이력과 누적 사용량은 보존한다. tools/evidence/audit4-ledger-cap-test/README.md와 Audit 6의 저장된 시험 로그는 98·99·100건 경계, 복구 후 꼬리 2건, 사용량 동등성, 실패 재시도를 검증한다. 이번 읽기 전용 환경에서는 문서·규칙 시험 11건이 통과했으나 전체 체크포인트 시험은 임시 디렉터리 생성 불가로 재검증하지 못했다. 따라서 도구 부재 지적은 기존 구현·증거로 해소하되 O17 전체 및 09 대응표 P02/P03의 완료로 확대하지 않는다. 실제 R2 실행·비용 한도 변경·배포는 이 결정에 포함하지 않는다.

**Options:** ['기존 tools/r2_budget.py checkpoint 활용 — 선택', '상한 인상 — 입장 읽기 예산과 충돌하며 누적 문제를 미룰 뿐이므로 기각', '체크포인트 신규 구현 — 기존 구현과 중복되므로 기각']

**Revisit if:** 쓰기 가능한 환경의 회귀 시험이 실패하거나, 체크포인트 크기·입장 요청·월별 입장 한도가 운영을 막거나, 자동 수집·동시성 확대가 필요해질 때 재검토한다.
