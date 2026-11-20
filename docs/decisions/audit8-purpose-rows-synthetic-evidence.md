# Decision: `09:11` says synthetic passes are not evidence, yet `09:33` closes P07 on a "합성 PDF 기원 스냅샷" and P06 

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-20 20:54 KST); reversible.

**Decision:** 합성 자료만으로 완료할 수 있는 행은 P01~P19 중 0개다. P06의 historical_fixture 21/21은 회귀 시험으로 기록하고, 행을 닫으려면 D-02 관문 뒤 실제 이종 2계열의 ReviewDecision, 서비스 제약·픽스처 거부 결과, 보류 시 엔진 호출 0회 기록을 확인한다. P07의 합성 PDF E2E는 유지하되, D-17 조건 충족 후 사용이 승인된 실제 계약에서 확인한 판·가입 담보·금액이 스냅샷과 계약 상세 화면까지 일치하고 모호한 매핑은 해당 결론만 보류하는지 검증해야 닫는다. 각 완료 증거에 environment(실행 환경)와 origin(무엇을 실제로 관찰했는지 추적할 출처)을 모두 필수화한다. 둘 중 하나라도 누락되거나 출처가 불명확하면 행을 열어 둔다.

**Why:** tasks.json의 historical_fixture는 is_service_evidence=false다. service_conformance에서 픽스처를 거부한 결과는 거부 동작의 증거로만 쓸 수 있다. 저장소의 readiness 회귀 시험을 실행해 현재 19개 행 모두 open임을 확인했다. 별도 메모리 시험에서는 과제 상태와 로그를 통과로 둔 채 같은 픽스처를 넣자 test에서 P06·P07이 모두 open, release에서 모두 closed가 됐다. origin을 명시하면 현행 v1 판정기는 알 수 없는 필드로 거부했다. 따라서 이번 결정으로 증거 기준은 확정됐고, 09 문구와 판정기 반영은 남아 있다.

**Options:** ['채택 — 합성 입력은 개별 시험에 허용하고, 행 완료는 그 행이 요구하는 실제 관찰로 판정한다. P18·P19는 D-16에 따라 가상 계약을 써도 실제 참가자가 실제 화면에서 수행한 이해 시험 결과를 인정한다.', '기각 — P06·P07을 합성 자료만으로 닫는 예외로 둔다. 09 §0과 BLUEPRINT §9.5에 해당 예외의 근거가 없다.', '기각 — environment=release만 확인한다. 같은 환경에서도 합성 입력을 실행할 수 있다.']

**Revisit if:** 판정기 반영 시 release+fixture와 origin 누락으로는 P06·P07이 닫히지 않는지 재검증한다. D-02·D-17의 실제 증거가 등록되면 해당 행을 재판정한다. 합성 자료만으로 행을 닫는 예외는 BLUEPRINT §13 절차에 따라 새 ADR과 관련 계약에 반영될 때만 재검토한다.
