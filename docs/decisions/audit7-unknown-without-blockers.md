# Decision: `pro_rata` with whole=0 and `divide_count` with 0 return Unknown with empty blockers (eval.rs:619-62

Decided by Claude Sonnet 5.5 xhigh (ONJEON autoloop, 2026-11-18 09:40 KST); reversible.

**Decision:** `pro_rata`의 `whole=0`과 `divide_count`의 `count=0`이 결과 금액을 결정하는 경우, 엔진은 금액을 `unknown`으로 유지하고 구조화된 사유 코드 `zero_denominator`와 연산 경로를 반환한다. 지급 요건 판정은 그대로 유지한다. API는 해당 금액의 `display_status`를 `hold`로 파생하고, 화면에 ‘나눌 기준이 0이라 금액을 계산할 수 없어요’를 표시한다. 분모가 실제로 누락되거나 `null`이면 `missing_inputs`와 `input_missing`으로 필요한 입력을 묻는다. `class_money_list`는 `twin-runtime`의 `input_stage::fill`이 책임진다. 해당 범위에 사건이 없다는 명시적 사용자 확인, 가상 시나리오의 명시적 가정, 또는 범위 전체를 확인한 근거가 있을 때만 `[]`를 전달한다. 미응답, 불완전한 자료, 출처를 확인할 수 없는 빈 배열은 `null`로 전달한다. 사건 목록은 확인됐으나 개별 금액이 미확인이면 해당 항목의 `krw: null`을 보존한다.

**Why:** BLUEPRINT §8 I1, DEC-O12, `scenario_result.schema.json`에 부합한다. `missing_inputs`는 실제로 필요한 입력 이름을 담고, `blocked_by`는 엔진 호출 전 차단에 쓰인다. 현재 `fill`은 요청 배열을 그대로 복사하므로 빈 배열의 의미를 엔진에 전달하기 전에 확인해야 한다. 사전 빌드된 엔진 시험 41개와 입력 단계 시험 15개가 통과했고, `case-runner` 8개 사례에서 두 0 분모의 사유 누락과 목록 입력의 0원·미확인 구분을 재현했다. 읽기 전용 환경이므로 구현과 새 회귀 시험은 미완료다. finding을 닫으려면 두 연산의 0과 누락·null, 선택되지 않은 분기, 확인된 빈 목록과 근거 없는 빈 목록, 항목 금액 null을 엔진·입력 단계·API/화면에서 검증해야 한다. 09의 P08·P16 완료 판정에는 실제 릴리스 데이터의 응답과 화면 증거가 필요하다.

**Options:** ['`hold`와 `zero_denominator`로 계산 보류 사유를 표시한다. 채택.', '`input_missing`으로 분모를 다시 묻는다. 이미 확인된 0을 누락으로 표시하게 된다.', '`not_applicable`, 0원 또는 평가 오류로 처리한다. 각각 지급 요건 판정, 금액 또는 rule-0.2의 정상 `unknown` 결과를 바꾼다.']

**Revisit if:** 검수된 실제 약관이 0 분모에 별도의 계산 결과를 정하거나, 사건 없음의 확인 범위를 현재 입력 출처로 표현할 수 없는 경우.
