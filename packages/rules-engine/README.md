# onjeon-rules-engine

규칙 DSL v0.1의 결정적 평가기. 제3부 §49, ADR-0003. 이 크레이트가 계산의 유일한 구현이다.

## 보장하는 것

- 3값 논리(참·거짓·모름). 모르는 입력은 0이나 거짓으로 바뀌지 않는다.
- 금액은 정수 원. 부동소수점이 없다. 반올림 규칙과 단위는 규칙에 명시해야 한다(`unspecified`는 하한~상한 범위를 돌려준다).
- 허용 목록 연산자만 로드된다. 모르는 연산자, 부동소수점 리터럴, 반올림 누락, `month_end` 누락, 알 수 없는 최상위 키는 로드 단계에서 거부된다.
- 같은 입력·규칙·엔진 버전이면 바이트 단위로 같은 결과를 낸다. 결과에는 평가 trace, 결과를 막은 누락 입력, 입력 스냅샷 해시가 들어 있다.
- 공개 가능한 규칙은 근거 참조가 하나 이상 있어야 한다(불변 원칙 5). 합성 규칙은 `fixture_only`다.

## 마스터플랜 §34.1 예시와 다른 점

| 예시 | 구현 | 이유 |
|---|---|---|
| `required_inputs: [...]` | `inputs: {이름: 타입}` | 타입(bool, int, money_krw, date, string)이 있어야 단위 오류를 막는다 |
| `multiply` | `multiply_rate` + `{rounding, unit}` | §49.5: 반올림 기본값 금지 |
| `unit` 없음 | 필수 | 같은 이유 |
| 모르는 입력 | JSON `null` 또는 키 없음 | |
| 지급 결과 | `not_payable` / `payable{amount}` / `undetermined{conditional_amount}` | 판정 불가를 0원과 구분 |

## 테스트

`cargo test`

| 테스트 | 내용 |
|---|---|
| `golden` | §34.1 경계표 확장 14건(`packages/fixtures/rules/*.cases.json`), 재현성, trace |
| `mutation` | 규칙을 의도적으로 망가뜨린 11개 변이가 골든 표에 모두 잡히는지 |
| `soundness` | 입력을 숨겨도 확정 결과가 다른 확정 결과로 뒤집히지 않는지 |
| `loader_and_arith` | 반올림 모드, 상한, `days_between` 포함 여부, 달력 연산, 로더 거부 규칙 |
| 단위 | 진리표(§49.3), 날짜 변환, 요율 파싱 |

## 아직 없는 것

`first_match`, `in_set`, 상환형 연산(`subtract_deductible`, `coinsurance`, `pro_rata`, `cumulative_cap`), 청구 이력 상태, 코드 체계(KCD) 참조형, 규칙 스키마(JSON Schema) 파일. 제3부 §49.2, §54.4 W3에서 필요하다.
