# onjeon-rules-engine

규칙 DSL v0.1의 결정적 평가기. 제3부 §49, ADR-0003. 이 크레이트가 계산의 유일한 구현이다.

## 보장하는 것

- 3값 논리(참·거짓·모름). 모르는 입력은 0이나 거짓으로 바뀌지 않는다.
- 금액은 정수 원. 부동소수점이 없다. 반올림 규칙과 단위는 규칙에 명시해야 한다(`unspecified`는 하한~상한 범위를 돌려준다).
- 허용 목록 연산자만 로드된다. 모르는 연산자, 부동소수점 리터럴, 반올림 누락, `month_end` 누락, `date_add`·`multiply_rate`·`days_between` 파라미터의 알 수 없는 키(`day` 단위의 `month_end` 포함), 알 수 없는 최상위 키는 로드 단계에서 거부된다.
- 로드 단계에서 모든 식의 타입을 검사한다(bool·int·money·rate·date·string). `{"eq":["target_event",1]}`처럼 타입이 다른 값의 비교, bool·string의 순서 비교, `all`/`any`/`not`/`if` 조건에 쓴 비불리언, 금액 연산자에 쓴 비금액, 가지 타입이 다른 `if`, 불리언이 아닌 `eligibility`, 금액이 아닌 `amount`(`"amount": true`)는 오류 위치(경로)와 함께 로드에서 거부된다. 금액 `money`는 정확한 값과 범위를 구분하지 않으므로 범위를 비교하는 오류는 아직 평가 단계에서만 잡힌다(아래 "아직 없는 것").
- 같은 입력·규칙·엔진 버전이면 바이트 단위로 같은 결과를 낸다. 결과에는 평가 trace, 결과를 막은 누락 입력, 입력 스냅샷 해시가 들어 있다.
- 공개 가능한 규칙은 근거 참조가 하나 이상 있어야 하고 소속 릴리스(`release_id`)를 밝혀야 한다(불변 원칙 5). 합성 규칙은 `fixture_only`다.
- 결과마다 `rule_version`, `release_id`, `rule_content_hash`, `evidence_refs`가 붙는다. `rule_content_hash`는 규칙 JSON을 정규화(모든 객체 키를 `BTreeMap`으로 명시 정렬한 compact JSON)한 SHA-256이며 최상위 `release_id`는 제외한다. `serde_json`의 `preserve_order` 기능 여부와 무관하며, fixture 규칙의 해시는 `packages/fixtures/rules/fixture-rule-001.content_hash`에 고정되어 테스트로 검증된다. 버전을 올리지 않고 내용을 바꿔도 해시가 달라지므로 과거 계산이 어떤 규칙 내용을 썼는지 결과만으로 식별된다.
- `evidence_refs`의 각 항목은 공백만으로 이뤄진 빈 문자열일 수 없다(`evidence_refs[i]`: blank). 모든 `publication_state`에 적용되며, `fixture_only`가 아닌 규칙은 비어 있지 않은 근거가 최소 1개 필요하다.
- 로드된 `Rule`은 불변이다. 필드는 비공개이고 읽기 접근자만 있다. 규칙을 바꾸려면 `source_json()`을 복사해 고친 뒤 `Rule::from_json`으로 다시 로드해야 하며, 이때 재검증과 재해시가 일어난다. 따라서 결과에 붙는 해시와 실제로 실행된 논리가 어긋날 수 없다.
- `if`의 조건이 모름이면 두 가지(then·else)를 모두 평가하되, 한쪽이 오류(오버플로·타입·날짜 범위)를 내도 규칙 전체를 실패시키지 않고 그 가지를 모름으로 취급한다. 결과는 모름이며 blocker는 조건의 모르는 입력과 다른 모르는 가지의 입력이다. 가지 하나가 오류여도 다른 가지의 값을 답으로 내지 않는다. 조건이 확정되어 선택된 가지의 오류, 두 가지 모두의 오류는 그대로 오류다. 흡수된 오류는 trace에 `error: ...` 항목으로 남는다.
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
| `golden` | §34.1 경계표 확장 14건(`packages/fixtures/rules/*.cases.json`), 재현성, trace. 케이스별 `trace`·`input_snapshot_hash`는 `fixture-rule-001.golden.json`, `rule_content_hash`는 `fixture-rule-001.content_hash`와 `real.content_hashes.json`(실규칙 전체)에 고정되어 회귀를 잡는다. 의도한 변경일 때만 갱신 |
| `mutation` | 규칙을 의도적으로 망가뜨린 11개 변이가 골든 표에 모두 잡히는지 |
| `soundness` | 입력을 숨겨도 확정 결과가 다른 확정 결과로 뒤집히지 않는지(I1). 합성 fixture와 `fixtures/rules/real/*.cases.json`의 실제 규칙 7개 전부에 적용하며, 모든 실제 규칙이 확정 케이스를 하나 이상 갖는지 확인한다. 모름을 `false`/`0`으로 바꾸는 평가기를 같은 검사기가 잡아내는지(음성 대조)도 본다 |
| `static_types` | 로드 단계 타입 검사: 감사 예시 두 건, 연산자별 거부와 오류 경로, 올바른 타입은 그대로 로드·평가 |
| `loader_and_arith` | 반올림 모드, 상한, `days_between` 포함 여부·역순 날짜 거부, 달력 연산, 로더 거부 규칙 |
| `unknown_branch_errors` | 조건이 모름일 때 가지의 오류가 모름+blocker가 되는지, 선택된 가지·양쪽 가지의 오류는 유지되는지, trace 기록 |
| `review_fixes` | 결과의 규칙 버전·릴리스·내용 해시·근거, 재로드 시 동일성, 범위의 연속 계산, 날짜 범위·오버플로(`i64::MIN`·`i64::MAX` 포함) |
| 문서 테스트 | 로드된 규칙의 필드 수정이 컴파일되지 않음(`compile_fail`)과 같은 준비 코드의 정상 동작 |
| 단위 | 진리표(§49.3), 날짜 변환, 요율 파싱 |

## 아직 없는 것

금액 범위와의 비교(`lt` 등)는 아직 평가 단계의 명시적 타입 오류로 거부한다(범위인지 여부는 값에 달려 있어 로드 때 알 수 없다). 범위가 기준값을 걸치는 경우를 모름으로 처리할지는 W3 설계에서 정한다. 그 밖에 `first_match`, `in_set`, 상환형 연산(`subtract_deductible`, `coinsurance`, `pro_rata`, `cumulative_cap`), 청구 이력 상태, 코드 체계(KCD) 참조형, 규칙 스키마(JSON Schema) 파일. 제3부 §49.2, §54.4 W3에서 필요하다.
