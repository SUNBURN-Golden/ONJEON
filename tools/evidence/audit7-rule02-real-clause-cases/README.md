# Audit 7 · 실제 약관의 rule-0.2 계산

KB손해보험과 교보생명의 기존 V1 표본에서 7개 규칙을 실행한다. 설계 검증 인덱스의 `rules[].file`이 현재 판본을 가리킨다. 벌금·변호사비·종신 질병사망은 같은 규칙 ID의 `v2-validation` 개정본이고 나머지 4개는 새 인코딩이다. 0.1 공유 파일과 당시 입력·내용 해시는 과거 계산 재현에 쓰인다. [규칙과 기대값](../../../packages/rules-engine/tests/fixtures/real-0.2/) · [표본별 인덱스와 근거 ID](../../../docs/blueprint/validation/encoded/)

| 부족분 · 연산 | 기존 약관 근거 (PDF 물리 쪽) | 기준 사례와 입력 경계 |
|---|---|---|
| G01 · `multiply_count` | [KB 간병인지원 상해입원일당Ⅲ 제1·2조, 490~491쪽](../../../docs/blueprint/validation/extracts/kb_driver_terms.md) | 일당 3만원 × 3일은 9만원. 같은 입원에서 현금·간병인 지원을 합해 이미 178일 사용했다면 2일분 6만원. 지원 일수 미확인은 금액 미확인. |
| G02 · `subtract_floor0` | [교보실손Ⅴ 질병급여형 제3조 표1, 제6조, 20~21·39~40쪽](../../../docs/blueprint/validation/extracts/kyobo_silson_terms.md) | 인정 본인부담금 8만원, 해당 공제액 2만원이면 6만원. 본인부담금이 공제액 이하이면 0원. 선택한 통원 한도와 연간 잔여 한도도 적용한다. 표1의 기관별 대응은 판독 보류로 공제액을 입력받는다. |
| G03 · `pro_rata` | [KB 자동차사고벌금 제1~3조, 339~340쪽](../../../docs/blueprint/validation/extracts/kb_driver_terms.md) | 벌금 3천만원이면 이 계약의 단독 책임액은 2천만원이다. 다른 계약 책임액 합계가 1천만원 이하면 2천만원, 2천만원이면 1,500만원, 3천만원이면 1,200만원이다. 반올림 근거가 없는 10원 × (10원 / 15원)은 6~7원. 다른 계약의 책임액을 모르면 분담액도 미확인이다. |
| G03 · `divide_count` | [KB 변호사선임비용 제1조 ⑪⑫ 및 예시, 347~349쪽](../../../docs/blueprint/validation/extracts/kb_driver_terms.md) | p.349 예시 1은 세 심급 일괄 6천만원에서 총 1,500만원, 예시 2는 두 심급 일괄 1천만원과 상고심 별도 1천만원에서 총 1천만원이다. 각 위임계약의 총액을 계약 심급 수로 나눈 뒤 진행한 심급마다 50%와 증권 한도를 적용한다. |
| G04 · `class_money_list`와 `max_over` | [교보통합암 NEW플러스수술특약 제5조③④ 및 별표1, 144~145·160쪽](../../../docs/blueprint/validation/extracts/kyobo_cancer_terms.md) | 동시 수술 20만원·200만원이 같은 묶음이면 200만원. 다른 부위에서 독립적인 치료목적으로 받은 40만원 수술이 더 있으면 240만원. 입력 단계가 분류·부위·목적과 개별 수술 지급액을 확인한다. |
| G14 · `anniversary_band` | [교보K-실속종신 제3·8조, 별표1 제1보험기간, 31·36~37·77쪽](../../../docs/blueprint/validation/extracts/kyobo_wholelife_terms.md) | 기본보험금액 8천만원, 보험가입금액 1억원이면 첫해 4천만원에 1주년 당일부터 매년 1천만원씩 가산한다. 적립액은 별도 입력이다. 5주년은 제2보험기간에 속한다. 기존 윤년 사례의 말일 관례는 G13 보류다. |
| G23 · `contract_effect` | [교보통합암 주계약 별표1 주2, 78쪽](../../../docs/blueprint/validation/extracts/kyobo_cancer_terms.md) | 보험기간 중 사망이 확인되면 당시 적립액 지급과 계약 소멸이 함께 적용된다. 사망 시점이 미확인이면 두 결과가 모두 조건부다. 적립액만 모를 때는 소멸 효과가 유지된다. |

KB 제1조는 확정판결로 정한 벌금에 적용된다. 판결이 아직 확정되지 않았으면 현재 지급 요건은 거짓이다. 확정 여부를 모르면 벌금 액수가 입력돼도 지급 미정이다. 확정판결은 확인했고 액수만 모르면 지급 요건은 참이고 금액만 미정이다. [KB 제1조 사례](../../../packages/rules-engine/tests/fixtures/real-0.2/kb-driver-fine.cases.json)

KB 벌금 제2조 제5호에서 일부 수익자가 가해자이면 그 청구는 면책이고 다른 수익자에게는 그 몫을 지급한다. 단독 수익자의 고의가 없다는 사실만으로는 청구인을 판정할 수 없다. 다른 수익자로 확인돼도 그 몫을 모르면 금액은 미정이다. 몫이 확인되면 제3조로 계산한 이 계약 보상책임액과 확인된 몫 중 작은 금액을 지급한다. [KB 제2·3조 사례](../../../packages/rules-engine/tests/fixtures/real-0.2/kb-driver-fine.cases.json)

KB 변호사비 제1조 제1항의 발췌에는 제1~7호만 있다. 일곱 유형에 모두 해당하지 않을 때는 원문으로 확인한 제8호 적용 여부를 입력한다. 확인 전에는 지급 미정, 적용이 확인되면 심급별 금액을 계산하고, 미적용이 확인되면 지급사유 불충족으로 판정한다. p.349의 두 예시는 심급별 금액을 검증한다. [KB 제1조 사례](../../../packages/rules-engine/tests/fixtures/real-0.2/kb-driver-lawyer-fee.cases.json)

교보 제3조는 보장개시일 당일부터 적용하며 별표1의 5년 기간과 체증은 계약일부터 센다. 계약일 1월 1일, 보장개시일 1월 3일이면 1월 2일 일반 질병사망은 지급 대상에서 제외되고, 1월 3일 사망은 같은 금액 입력에서 40,001,000원이다. 보장개시일 미확인은 지급 미정이다. [교보 제3조 사례](../../../packages/rules-engine/tests/fixtures/real-0.2/kyobo-wholelife-disease-death.cases.json)

교보 제8조 제2·3호는 계약자·단독 수익자의 고의와 일부 수익자만의 고의를 구분한다. 1주년 사례에서 일부 수익자만 가해했고 청구인이 누구인지 모르면 지급 여부와 조건부 금액 모두 미정이다. 가해 수익자의 청구는 면책이고, 다른 수익자의 청구는 그 몫을 지급한다. G11에 따라 규칙은 몫을 배분하지 않는다. 다른 수익자에게 확정된 금액을 외부에서 확인한 경우에만 그 금액을 표시한다. 기존 w20의 포괄 입력만으로는 제8조의 어느 경우인지 알 수 없어 0.2 결과가 지급 미정으로 바뀐다. [교보 제8조 사례](../../../packages/rules-engine/tests/fixtures/real-0.2/kyobo-wholelife-disease-death.cases.json)

실행 시험은 71개 기대값을 공개 로더·평가기 출력과 대조한다. 규칙별 내용 해시, 원문 참조, 6개 금액·요율 연산의 실제 실행 trace, 계약 효과의 세 상태도 검사한다. 제품목적 대응표 P08·P14의 로컬 `fixture_only` 증거다. 약관 해석은 AI 1차 해석 상태이며 서비스 적용에는 표 좌표 확인·검수와 해당 상품 릴리스가 필요하다. [엔진 시험](../../../packages/rules-engine/tests/real_clauses_02.rs) · [제품 완료 기준](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)

실행기에서도 현재 인코딩 파일을 따라 71개 사례의 지급액·판정·누락 입력을 대조했다. 벌금 제3조의 초과 조건을 제거한 변이는 합계가 벌금보다 1원 적은 사례에서 2천만원 한도를 넘는 범위를 반환해 검출됐다. [2026-11-19 로컬 검증 로그](verification.log)

저장소 루트에서 다음 명령으로 재현한다.

```sh
cargo test --locked --offline -p onjeon-rules-engine --test real_clauses_02
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I tools/blueprint_counts.py
```
