# onjeon-rules-engine

규칙 DSL v0.1의 결정적 평가기. 제3부 §49, ADR-0003. 이 크레이트가 계산의 유일한 구현이다.

## 보장하는 것

- 3값 논리(참·거짓·모름). 모르는 입력은 0이나 거짓으로 바뀌지 않는다.
- 금액은 정수 원. 부동소수점이 없다. 반올림 규칙과 단위는 규칙에 명시해야 한다(`unspecified`는 하한~상한 범위를 돌려준다).
- 허용 목록 연산자만 로드된다. 모르는 연산자, 부동소수점 리터럴, 반올림 누락, `month_end` 누락, 알 수 없는 최상위 키는 로드 단계에서 거부된다.
- 같은 입력·규칙·엔진 버전이면 바이트 단위로 같은 결과를 낸다. 결과에는 평가 trace, 결과를 막은 누락 입력, 입력 스냅샷 해시가 들어 있다.
- 공개 가능한 규칙은 근거 참조가 하나 이상 있어야 하고 소속 릴리스(`release_id`)를 밝혀야 한다(불변 원칙 5). 합성 규칙은 `fixture_only`다.
- 결과마다 `rule_version`, `release_id`, `rule_content_hash`, `evidence_refs`가 붙는다. `rule_content_hash`는 규칙 JSON을 정규화한 SHA-256이며 `release_id`는 제외한다. 버전을 올리지 않고 내용을 바꿔도 해시가 달라지므로 과거 계산이 어떤 규칙 내용을 썼는지 결과만으로 식별된다.
- 반올림 미지정으로 생긴 금액 범위는 이후 `multiply_rate`, `add`, `min`, `max`, `apply_cap`에서 하한·상한을 각각 계산해 이어진다.
- 날짜는 1900-01-01~2199-12-31만 지원한다. `date_add` 기간은 로드 단계에서 제한(일 110,000, 월 3,600, 년 300)되고, 계산 결과가 범위를 벗어나면 오버플로 대신 `DateOutOfRange` 오류를 낸다.

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
| `review_fixes` | 결과의 규칙 버전·릴리스·내용 해시·근거, 범위의 연속 계산, 날짜 범위·오버플로 |
| 단위 | 진리표(§49.3), 날짜 변환, 요율 파싱 |

## 아직 없는 것

금액 범위와의 비교(`lt` 등)는 아직 명시적 타입 오류로 거부한다. 범위가 기준값을 걸치는 경우를 모름으로 처리할지는 W3 설계에서 정한다. 그 밖에 `first_match`, `in_set`, 상환형 연산(`subtract_deductible`, `coinsurance`, `pro_rata`, `cumulative_cap`), 청구 이력 상태, 코드 체계(KCD) 참조형, 규칙 스키마(JSON Schema) 파일. 제3부 §49.2, §54.4 W3에서 필요하다.
