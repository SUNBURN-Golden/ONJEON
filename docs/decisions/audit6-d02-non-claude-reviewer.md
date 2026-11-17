# Decision: cross-family review (D-02) can't be registered until non-Claude model access is confirmed. That bloc

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-17 22:25 KST); reversible.

**Decision:** OpenAI API를 비-Claude 승인 계열 X로 선택한다. 첫 검증 후보는 gpt-6-astra이며 실제 응답으로 확인한 모델 ID만 review_policy.json에 고정한다. 접근 검증을 다음 실행 우선 작업으로 지정하고, 2026-11-18 18:00 KST를 증거 확보 상태 점검 시점으로 정한다. 이는 접근 확보 보장이 아니다. 사용자 측 접근·비용 승인과 월 한도·보존/학습 조건 확인 후, services/ai-gateway 실제 API 경로의 최소 호출 성공·JSON Schema 적합성·모델 식별·지연·비용·확인 시각·호스트 해시를 05 §2 형식으로 남긴 뒤에만 D-02를 등록한다. T-OP-03 발송은 그 이후다. T-KN-06 모의 구현과 S1(a)는 계속한다. 작성=Claude, 승인=OpenAI, 제3계열 검증 전 레드팀=OpenAI의 다른 모델/프롬프트와 degraded 기록을 유지한다. 이번 결정은 가역적 제공자 선정·순서 결정이며 지출·키 발급·production 실행을 승인하지 않는다.

**Why:** docs/decisions/audit5-non-claude-ai-provider.md에 이미 같은 제공자 우선순위가 있다. 그러나 services/ai-gateway/README.md는 실제 제공자 어댑터 부재를 명시하고, docs/vm_check/2026-10-16/summary.json에는 실제 호출 성공 증거가 없다. 이번에 test_audit5_non_claude_ai_provider.py 25개 시험을 실행해 모두 통과했지만 이는 정책·근거 정합성 검증이다. 실제 접근 차단 해소 증거가 아니므로 finding은 아직 실행상 미해결이다. 공식 문서는 JSON Schema 출력 지원을 확인해 주지만 해당 계정의 접근을 증명하지 않는다([OpenAI Docs](https://developers.openai.com/api/docs/guides/structured-outputs)). D-02 등록 뒤에도 실제 2계열 ReviewDecision·hold 실행·S1(b) 화면 숫자→원문 좌표 증거를 확보해야 하며, P02·P04·P06·P14는 09 대응표의 각 완료 증거로 별도 판정한다.

**Options:** ['채택: Audit 5의 OpenAI 우선 결정을 유지하고 실제 API 접근 증거 확보를 다음 실행 단계로 둔다.', '보류: xAI Grok은 동일한 API 검증을 통과하면 제3계열 또는 대체 후보로 검토한다.', '기각: Codex CLI 리뷰나 현재 대화를 API 접근 증거로 인정하고 D-02를 즉시 등록한다.', '기각: 동일 Claude 계열을 독립 계열로 세거나 모의 시험으로 S1(b)를 통과 처리한다.']

**Revisit if:** 점검 시점까지 접근 증거가 없으면 부족한 조건·담당·다음 확인일을 기록하고 D-02 차단을 유지한다. OpenAI 접근, 모델 식별, Schema 출력, 보존/학습 조건 또는 월 한도 조건을 충족하지 못하면 검증된 대체 제공자를 재선정한다. T-OP-03 실측에서 품질·비용·지연이 부적합하거나 제3계열 접근이 확인되면 구성을 재검토한다.
