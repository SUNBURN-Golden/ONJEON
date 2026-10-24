# onjeon-rules-engine

규칙 DSL v0.1의 결정적 평가기(`schema_version` `rule-0.1`, 그리고 `rule-0.2` 연산 확장). 제3부 §49, ADR-0003. 이 크레이트가 계산의 유일한 구현이다.

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

## rule-0.2 (T-TW-02)

`schema_version`이 `rule-0.2`인 규칙만 아래를 쓴다. `rule-0.1` 규칙은 그대로 로드·평가되고, 0.1 문서에서 아래 연산·입력 타입·`contract_effect`를 쓰면 로드에서 거부된다. 근거는 GAP_REPORT §5, ADR-0014 §6. 실제 상품군 규칙은 해당 마일스톤(M5·M6)에서 사례와 함께 추가하며, 지금 있는 시험 규칙은 모두 `fixture_only` 합성 규칙이다.

| 연산 | 형태 | 규칙 |
|---|---|---|
| `multiply_count` | `[money, int]` → money | 횟수는 0 이상(음수는 평가 오류), 오버플로는 오류. 금액 범위는 양 끝을 곱한다 |
| `subtract_floor0` | `[money, money]` → money | 음수면 0. 한쪽이라도 모름이면 모름(0 하한이 모름을 0으로 만들지 않는다). 범위는 `[a.min-b.max, a.max-b.min]`을 각각 0으로 올린다 |
| `pro_rata` | `[money, part, whole, {rounding, unit}]` → money | `part`·`whole`은 둘 다 int 또는 둘 다 정확한 money. `whole=0`은 오류가 아니라 **모름**(blocker 없음), `part>whole`은 오류. 반올림·단위 필수 |
| `divide_count` | `[money, int, {rounding, unit}]` → money | 균등 배분·1일 평균. 횟수 0은 모름. 반올림·단위 필수 |
| `anniversary_band` | `[date_from, date_at, [[years, "rate"]...], {boundary}]` → rate | 경과 만 연수 구간표. 첫 구간은 0년, 시작 연수는 엄격 증가, 값은 요율 문자열(금액에는 `multiply_rate`로 곱한다). `boundary`는 필수: `lower_inclusive`(기념일 당일부터 새 구간) / `upper_inclusive`(기념일 당일까지 이전 구간, 다음 날부터 새 구간; 첫 구간은 항상 적용). 2월 29일 기산의 평년 기념일은 2월 말일(엔진 가정, 원문 관례는 G13). `date_at < date_from`은 오류 |
| 목록 입력 `class_money_list` + `max_over` | 입력 `[{class, krw}]`, `{"max_over": "<입력 이름>"}` → money | 같은 `class`에서는 최고 금액 하나만, 다른 `class`는 각각 더한다(G04). 빈 목록은 0(사건 없음이 확정), 목록이 없거나 항목의 `krw`가 `null`이면 모름(모르는 항목이 최고일 수 있다). 목록은 비교할 수 없고 `max_over` 인자는 선언된 목록 입력의 이름이어야 한다 |
| `contract_effect` | 최상위 키 `none`/`void_refund_premium`/`terminated_pay_reserve`(기본 `none`) | 결과의 `contract_effect`: 적격이면 `applies{effect}`, 부적격이면 `none`, **적격 미정이면 `undetermined{conditional_effect}`**(규칙이 효과를 선언했는데 `none`으로 바뀌지 않는다). rule-0.1 결과는 항상 `none`. 값은 규칙 내용 해시에 포함된다 |

코드 판정·시간 단위 판정·누적 사용량·외부 파라미터 조회는 여전히 DSL 밖(입력 단계)이다. 금액 범위와의 비교가 없는 점, `pro_rata`의 `part`·`whole`이 범위가 될 수 없는 점(정확한 값만)도 아직 한계다.

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
| `golden` | §34.1 경계표 확장 15건(공유 `packages/fixtures/rules/*.cases.json` + 엔진 `tests/fixtures/cases/*.cases.json`), 재현성, trace. 케이스별 `trace`·`input_snapshot_hash`는 `fixture-rule-001.golden.json`과 추가 반올림 케이스의 `tests/fixtures/fixture-rule-001.rounding.golden.json`, `rule_content_hash`는 `fixture-rule-001.content_hash`와 `real.content_hashes.json`(실규칙 전체)에 고정되어 회귀를 잡는다. 의도한 변경일 때만 갱신 |
| `mutation` | 합성 규칙을 손으로 망가뜨린 11개 변이 + 모든 규칙(합성 1개, `fixtures/rules/real`의 실제 규칙 7개)에서 기계적으로 만든 변이 336개가 골든 표에 모두 잡히는지. 변이기: 비교 연산자 뒤집기(`eq↔ne`, `lt↔lte`, `gt↔gte`, `lt↔gt`, `lte↔gte`), 정수·`krw`·`date_add` 값·요율 소수 끝자리 ±1, 불리언 리터럴 반전, `multiply_rate` 반올림 방식을 다른 4가지로 교체, `all`/`any` 자식 하나 제거, `all↔any`, `if`의 then/else 교체. 변이가 로드되지 않거나, 원본이 자기 케이스를 통과하지 못하거나, 케이스가 없으면 실패한다. 살아남은 변이는 `EQUIVALENT` 허용 목록(규칙·변이·사유, 현재 비어 있음)에 없으면 실패하며, 목록에 낡은 항목이 있어도 실패한다. 변이기가 항상 "죽었다"고 답하지 않는지(무변이 규칙·근거만 바뀐 규칙은 살아남음)도 음성 대조로 본다 |
| `fixture_supplements` | 공유 사례를 그대로 보존하면서 엔진 소유 경계 사례 59개를 추가하는지, 공유 기본 입력·규칙 ID와 사례별 덮어쓰기를 유지하는지, 공유/추가 사례의 ID 충돌을 거부하는지 |
| `soundness` | 입력을 숨겨도 확정 결과가 다른 확정 결과로 뒤집히지 않는지(I1). 합성 fixture와 `fixtures/rules/real/*.cases.json`의 실제 규칙 7개 전부에 적용하며, 모든 실제 규칙이 확정 케이스를 하나 이상 갖는지 확인한다. 모름을 `false`/`0`으로 바꾸는 평가기를 같은 검사기가 잡아내는지(음성 대조)도 본다 |
| `rule_02` | rule-0.2 연산 7종: 연산별 골든·경계(0, `i64::MAX`, 기념일 당일, 윤일)·변이(연산·반올림·구간표·경계 규칙을 바꾼 규칙이 골든 표에 잡힘)·건전성(입력을 하나씩 숨겨도 확정값이 뒤집히거나 0이 되지 않음), `whole=0` 모름, 0.1 문서에서의 거부, `contract_effect` 3상태 |
| `static_types` | 로드 단계 타입 검사: 감사 예시 두 건, 연산자별 거부와 오류 경로, 올바른 타입은 그대로 로드·평가 |
| `loader_and_arith` | 반올림 모드, 상한, `days_between` 포함 여부·역순 날짜 거부, 달력 연산, 로더 거부 규칙 |
| `unknown_branch_errors` | 조건이 모름일 때 가지의 오류가 모름+blocker가 되는지, 선택된 가지·양쪽 가지의 오류는 유지되는지, trace 기록 |
| `overflow` | `add`·`multiply_rate`의 `EvalError::Overflow` 경로를 `i64::MAX` 경계에서 직접 검증: 정확히 `MAX`는 통과, 1 초과는 오류(감김·포화 없음), 단위 올림(`ceil`/`half_up`/`half_even`)·`unspecified` 범위 상한·범위 입력의 한쪽 경계만 넘는 경우, 오류 경로 문자열. `min`/`max`/`apply_cap`은 넘치지 않음 |
| `review_fixes` | 결과의 규칙 버전·릴리스·내용 해시·근거, 재로드 시 동일성, 범위의 연속 계산, 날짜 범위·오버플로(`i64::MIN`·`i64::MAX` 포함) |
| 문서 테스트·`immutable_rule_doctests` | 로드된 규칙의 필드 수정이 비공개 필드 접근 오류로 컴파일되지 않음(`compile_fail,E0616`)과 같은 준비 코드의 정상 동작. stable rustdoc는 오류 코드 표기를 강제하지 않으므로 통합 테스트가 두 예제의 실제 진단 코드가 모두 `E0616`인지 검사 |
| 단위 | 진리표(§49.3), 날짜 변환, 요율 파싱 |

요율 리터럴은 `"0.5"`와 `{"rate":"0.5"}` 두 표현 모두 끝자리 ±1 변이를 만든다. 생성기 회귀 테스트는 소수·정수·0의 정확한 변이와 명시적 요율의 입력 이름 충돌을 확인한다. 실제 변호사선임비용 규칙의 요율 3개를 명시적 표현으로 바꿔도 변이 79개(요율 변이 6개 포함)가 유지되고 골든 표에 모두 잡히는지 검증한다.

추가한 경계 사례 59개는 허용 경로인 `packages/rules-engine/tests/fixtures/cases/`에 둔다. 공유 `packages/fixtures/rules/` 파일은 수정하지 않는다. 공통 로더는 같은 상대 경로의 추가 사례를 읽고 공유 기본 입력·규칙 ID를 재사용하며, 골든·변이·건전성·실제 조항 시험이 같은 확장 사례를 쓴다. Kyobo 소액암 규칙의 공유 사례 6개로는 살아남는 변이 16개가 로컬 사례 11개를 더하면 모두 잡히는지도 음성 대조로 확인한다.

`cargo test --test mutation -- --nocapture`로 규칙별 골든 케이스·변이 수와 전체 생존 변이 수를 볼 수 있다. 규칙 하나라도 생성된 변이가 없으면 실패한다. 로컬 재실행 결과와 CI 실행 제약은 [변이 테스트 실행 증거](MUTATION_TEST_EVIDENCE.md)에 기록했다.

## 아직 없는 것

금액 범위와의 비교(`lt` 등)는 아직 평가 단계의 명시적 타입 오류로 거부한다(범위인지 여부는 값에 달려 있어 로드 때 알 수 없다). 범위가 기준값을 걸치는 경우를 모름으로 처리할지는 W3 설계에서 정한다. 그 밖에 `first_match`, `in_set`, 상환형 연산(`subtract_deductible`, `coinsurance`, `cumulative_cap`; `pro_rata`는 rule-0.2에 있음), 청구 이력 상태, 코드 체계(KCD) 참조형, 규칙 스키마(JSON Schema) 파일. 제3부 §49.2, §54.4 W3에서 필요하다.
