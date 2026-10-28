# onjeon-rules-engine

규칙 DSL v0.1의 결정적 평가기(`schema_version` `rule-0.1`, 그리고 `rule-0.2` 연산 확장). 제3부 §49, ADR-0003. 이 크레이트가 계산의 유일한 구현이다.

## 보장하는 것

- 3값 논리(참·거짓·모름). 모르는 입력은 0이나 거짓으로 바뀌지 않는다.
- 금액은 정수 원. 부동소수점이 없다. 반올림 규칙과 단위는 규칙에 명시해야 한다(`unspecified`는 하한~상한 범위를 돌려준다).
- 허용 목록 연산자만 로드된다. 모르는 연산자, 부동소수점 리터럴, 반올림 누락, `month_end` 누락, `date_add`·`multiply_rate`·`days_between` 파라미터의 알 수 없는 키(`day` 단위의 `month_end` 포함), 알 수 없는 최상위 키는 로드 단계에서 거부된다.
- 로드 단계에서 모든 식의 타입을 검사한다(bool·int·money·money_range·rate·date·string). `{"eq":["target_event",1]}`처럼 타입이 다른 값의 비교, bool·string의 순서 비교, `all`/`any`/`not`/`if` 조건에 쓴 비불리언, 금액 연산자에 쓴 비금액, 가지 타입이 호환되지 않는 `if`, 불리언이 아닌 `eligibility`, 금액이 아닌 `amount`(`"amount": true`)는 오류 위치(경로)와 함께 로드에서 거부된다. 범위가 될 수 있는 금액(`money_range`)은 `eq`·`ne`·`lt`·`lte`·`gt`·`gte`의 어느 쪽 피연산자에도 쓸 수 없으며 로드에서 거부된다. `unspecified` 반올림과 금액 연산·`if`의 범위 가능성을 전파한다. 정확한 금액과 범위 금액을 섞은 `if` 및 금액 계산·출력은 허용한다.
- 같은 입력·규칙·엔진 버전이면 바이트 단위로 같은 결과를 낸다. 결과에는 평가 trace, 결과를 막은 누락 입력, 입력 스냅샷 해시가 들어 있다.
- `input_snapshot_hash`는 변환된 전체 선언 입력을 타입 태그(`type`·`value`)가 있는 compact UTF-8 JSON으로 직렬화하고, 모든 객체 키를 재귀적으로 정렬한 바이트의 SHA-256이다. 누락·`null`은 모두 `{"type":"unknown"}`, 날짜는 epoch 일수이며 목록 순서는 보존한다. 입력 이름·문자열·목록 class는 JSON으로 이스케이프하므로 `=`·개행으로 구조를 위조할 수 없다. 표시용 `Display`·`Debug`와 독립적이다. 이 형식부터 결과의 `engine_version`에 `+snapshot-json-1`이 붙으며, 이전 형식의 해시와 직접 비교하지 않는다. [Audit 2 계약·검증 증거](../../docs/blueprint/audits/2026-10-26_engine_snapshot_hash_encoding.md).
- 공개 가능한 규칙은 근거 참조가 하나 이상 있어야 하고 소속 릴리스(`release_id`)를 밝혀야 한다(불변 원칙 5). 합성 규칙은 `fixture_only`다.
- 결과마다 `rule_version`, `release_id`, `rule_content_hash`, `evidence_refs`가 붙는다. `rule_content_hash`는 로드한 규칙 JSON 값을 모든 객체 키 순서만 `BTreeMap`으로 재귀 정렬해 compact JSON으로 다시 쓴 바이트의 SHA-256이며 최상위 `release_id`만 제외한다(중첩된 `release_id`는 포함). 파일의 공백·키 순서·문자열 이스케이프 표기는 파싱 단계에서 사라지므로 해시에 영향이 없지만, 값 자체는 정규화하지 않는다: 유니코드 형식(NFC/NFD, 완성형/조합형 한글)·문자열 앞뒤 공백·배열 순서(`all`/`any` 자식, `evidence_refs`)는 그대로 해시되고, 같은 뜻의 다른 표기(`"0.5"`·`"0.50"`·`{"rate":"0.5"}`), 생략한 기본값과 명시한 기본값(`calendar`, rule-0.2 `contract_effect: "none"`), 평가에 쓰이지 않는 `example_kind`도 서로 다른 해시가 된다. 따라서 해시가 같으면 같은 규칙 내용이지만, 해시가 다르다고 계산 논리가 다르다는 뜻은 아니다. `serde_json`의 `preserve_order` 기능 여부와 무관하며, 합성 규칙의 해시는 `packages/fixtures/rules/fixture-rule-001.content_hash`, 실제 조항 규칙 7개의 해시는 `packages/fixtures/rules/real.content_hashes.json`에 고정되어 로더와 모든 실제 사례의 결과에서 대조된다. 버전을 올리지 않고 내용을 바꿔도 해시가 달라지므로 과거 계산이 어떤 규칙 내용을 썼는지 결과만으로 식별된다.
- `rule_id`와 `evidence_refs`의 각 항목은 빈 문자열이나 공백만으로 이뤄진 문자열일 수 없다. `evidence_refs` 안의 동일 문자열 중복도 거부한다(`evidence_refs[i]`: blank 또는 duplicate). 두 DSL 버전과 모든 `publication_state`에 적용되며, `fixture_only`가 아닌 규칙은 근거가 최소 1개 필요하다. 검증은 값을 정리·정렬·중복 제거하지 않으므로 정상 규칙의 근거 순서와 내용 해시는 유지된다.
- 로드된 `Rule`은 불변이다. 필드는 비공개이고 읽기 접근자만 있다. 규칙을 바꾸려면 `source_json()`을 복사해 고친 뒤 `Rule::from_json`으로 다시 로드해야 하며, 이때 재검증과 재해시가 일어난다. 따라서 결과에 붙는 해시와 실제로 실행된 논리가 어긋날 수 없다.
- `if`의 조건이 모름이면 두 가지(then·else)를 모두 평가하되, 한쪽이 오류(오버플로·타입·날짜 범위)를 내도 규칙 전체를 실패시키지 않고 그 가지를 모름으로 취급한다. 결과는 모름이며 blocker는 조건의 모르는 입력과 다른 모르는 가지의 입력이다. 가지 하나가 오류여도 다른 가지의 값을 답으로 내지 않는다. 조건이 확정되어 선택된 가지의 오류, 두 가지 모두의 오류는 그대로 오류다. 흡수된 오류는 trace에 `error: ...` 항목으로 남는다.
- 자격(`eligibility`)이 모름일 때 금액 계산이 실패하면 `undetermined{conditional_amount: unknown}`과 자격의 누락 입력을 반환하고 오류를 trace에 기록한다. 계산에 성공한 조건부 금액과 금액의 누락 입력은 유지하며, 자격이 참이면 금액 오류를 그대로 반환하고 거짓이면 금액을 평가하지 않는다. [Audit 2 수정·검증 증거](../../docs/blueprint/audits/2026-10-26_engine_unknown_elig_amount_error.md).
- `all`/`any`는 자식의 성공 결과를 결합한 뒤 오류를 전파할지 정한다. `all`에 거짓 또는 `any`에 참이 하나라도 있으면 자식 순서와 관계없이 그 값으로 확정되고, 다른 자식의 오류·모름은 결론을 막지 않는다(blocker 없음). 확정하는 자식이 없으면 첫 오류를 그대로 반환한다(모름인 자식이 있어도 동일). 모든 자식을 평가해 기존 trace를 유지하며, 흡수한 오류는 해당 자식의 부분 trace 대신 `error: ...` 항목으로 남는다. 따라서 `all: [false, 오류]`는 거짓, `any: [true, 오류]`는 참이며 오류가 앞에 있어도 같다. 두 DSL 버전의 2항·중첩식·`if` 조합과 즉시 오류 반환 변이 검출은 [Audit 3 회귀 증거](../../docs/blueprint/audits/2026-10-28_engine_all_any_short_circuit.md)를 따른다.
- 반올림 미지정으로 생긴 금액 범위는 이후 `multiply_rate`, `add`, `min`, `max`, `apply_cap`에서 하한·상한을 각각 계산해 이어진다.
- 날짜는 정확히 0으로 채운 ASCII 숫자 `YYYY-MM-DD` 형식의 1900-01-01~2199-12-31만 지원한다. 규칙 리터럴과 평가 입력 모두 `2026-+1-+5` 같은 부호 포함 날짜와 `2026-1-5` 같은 0 채움 누락을 거부한다. 잘못된 날짜 표기를 정규화해 별도 내용 해시를 가진 규칙으로 로드하지 않는다. `date_add` 기간은 로드 단계에서 제한(일 110,000, 월 3,600, 년 300)되고, 계산 결과가 범위를 벗어나면 오버플로 대신 `DateOutOfRange` 오류를 낸다.
- `days_between`은 두 DSL 버전에서 시작일 ≤ 종료일인 구간의 일수다. 일수 차이를 `Δ`라 하면 `max(0, Δ - 1 + inclusive_start + inclusive_end)`로 센다(참=1, 거짓=0). 같은 날은 양 끝을 모두 포함할 때 1일, 나머지는 0일이다. 시작일이 종료일보다 늦으면 포함 플래그와 관계없이 해당 식 경로의 `EvalError::Type` 오류다. 음수·절댓값·0으로 바꾸지 않으므로 입력 역전으로 `lt` 임계값을 충족하지 않는다. 날짜 하나라도 누락·`null`이면 기존 모름과 누락 입력을 유지한다. 오류의 `all`/`any`·미확정 `if`·미확정 자격 금액에서의 흡수 규칙은 위 계약을 따른다. [Audit 2 검증 증거](../../docs/blueprint/audits/2026-10-26_engine_days_between_negative.md).

## 문자열 리터럴 (rule-0.1·rule-0.2)

고정 문자열은 `{"str":"surgery"}`로 쓴다. 입력과 비교하는 새 규칙은 `{"eq":[{"input":"event"},{"str":"surgery"}]}`처럼 입력 참조와 상수를 명시한다. `str`은 JSON 문자열 하나만 받으며 `Expr::Lit(Value::Str)`로 로드된다. 빈 문자열·한글·이스케이프·숫자형 문자열을 그대로 보존하고 입력 이름 조회, 요율 변환, 공백 제거, 유니코드 정규화를 하지 않는다. 같은 이름의 입력이 선언되어 있거나 누락되어도 상수의 값은 바뀌지 않는다.

문자열은 같은 타입끼리 `eq`·`ne`로 비교하고 `if`의 가지 등 문자열 식으로 합성할 수 있다. 비교 입력이 누락되거나 `null`이면 모름과 해당 입력 blocker를 유지한다. 비문자열 인자, 생성자의 추가 키, 타입이 다른 비교, 문자열의 순서 비교(`lt`·`lte`·`gt`·`gte`)는 로드에서 거부한다.

기존 일반 문자열은 계속 **선언된 입력 이름 우선, 그다음 요율**로 해석한다. 따라서 `"surgery"`는 미선언 상태에서 오류이며, 선언되면 입력 참조다. 이를 자동으로 상수로 바꾸지 않는다. 기존 규칙을 다시 쓸 필요는 없지만 새 컴파일 출력은 명시적 `input`·`str` 형태를 사용한다. 이전 엔진은 `str`을 거부하므로 새 규칙 배포 전에 지원 엔진을 먼저 배포해야 한다. 기존 골든 결과·trace·내용 해시·입력 스냅샷 해시의 고정값은 변경하지 않았다. [결정과 검증 증거](../../docs/decisions/audit2-engine-string-literals.md).

## rule-0.2 (T-TW-02)

`schema_version`이 `rule-0.2`인 규칙만 아래를 쓴다. `rule-0.1` 규칙은 그대로 로드·평가되고, 0.1 문서에서 아래 연산·입력 타입·`contract_effect`를 쓰면 로드에서 거부된다. 근거는 GAP_REPORT §5, ADR-0014 §6. 실제 상품군 규칙은 해당 마일스톤(M5·M6)에서 사례와 함께 추가하며, 지금 있는 시험 규칙은 모두 `fixture_only` 합성 규칙이다.

| 연산 | 형태 | 규칙 |
|---|---|---|
| `multiply_count` | `[money, int]` → money | 횟수는 0 이상(음수는 평가 오류), 오버플로는 오류. 금액 범위는 양 끝을 곱한다 |
| `subtract_floor0` | `[money, money]` → money | 음수면 0. 한쪽이라도 모름이면 모름(0 하한이 모름을 0으로 만들지 않는다). 범위는 `[a.min-b.max, a.max-b.min]`을 각각 0으로 올린다 |
| `pro_rata` | `[money, part, whole, {rounding, unit}]` → money | `part`·`whole`은 둘 다 int 또는 둘 다 정확한 money(범위 가능 식은 로드에서 거부). `whole=0`은 오류가 아니라 **모름**(blocker 없음), `part>whole`은 오류. 반올림·단위 필수 |
| `divide_count` | `[money, int, {rounding, unit}]` → money | 균등 배분·1일 평균. 횟수 0은 모름. 반올림·단위 필수 |
| `anniversary_band` | `[date_from, date_at, [[years, "rate"]...], {boundary}]` → rate | 경과 만 연수 구간표. 첫 구간은 0년, 시작 연수는 엄격 증가, 값은 요율 문자열(금액에는 `multiply_rate`로 곱한다). `boundary`는 필수: `lower_inclusive`(기념일 당일부터 새 구간) / `upper_inclusive`(기념일 당일까지 이전 구간, 다음 날부터 새 구간; 첫 구간은 항상 적용). 2월 29일 기산의 평년 기념일은 2월 말일(엔진 가정, 원문 관례는 G13). `date_at < date_from`은 오류 |
| 목록 입력 `class_money_list` + `max_over` | 입력 `[{class, krw}]`, `{"max_over": "<입력 이름>"}` → money | 같은 `class`에서는 최고 금액 하나만, 다른 `class`는 각각 더한다(G04). 빈 목록은 0(사건 없음이 확정), 목록이 없거나 항목의 `krw`가 `null`이면 모름(모르는 항목이 최고일 수 있다). 목록은 비교할 수 없고 `max_over` 인자는 선언된 목록 입력의 이름이어야 한다 |
| `contract_effect` | 최상위 키 `none`/`void_refund_premium`/`terminated_pay_reserve`(기본 `none`) | 결과의 `contract_effect`: 적격이면 `applies{effect}`, 부적격이면 `none`, **적격 미정이면 `undetermined{conditional_effect}`**(규칙이 효과를 선언했는데 `none`으로 바뀌지 않는다). rule-0.1 결과는 항상 `none`. 값은 규칙 내용 해시에 포함된다 |

코드 판정·시간 단위 판정·누적 사용량·외부 파라미터 조회는 여전히 DSL 밖(입력 단계)이다. 금액 범위와의 비교 및 `pro_rata`의 범위 가능 `part`·`whole`은 로드 단계에서 거부한다(정확한 값만 허용).

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

공유 `CARGO_TARGET_DIR`에서 다른 작업 트리의 시험 바이너리를 재사용하면 컴파일된 `CARGO_MANIFEST_DIR`가 삭제된 경로를 가리켜 fixture 로딩이 실패할 수 있다. 작업 트리별 검증은 `CARGO_TARGET_DIR="$PWD/target" cargo test --all --locked --offline`로 실행한다. [Audit 3 fix round 1 캐시 진단·재검증](../../docs/blueprint/audits/2026-10-28_engine_parse_date_strict.md#fix-round-1-공유-cargo-캐시의-다른-작업-트리-경로).

| 테스트 | 내용 |
|---|---|
| `golden` | §34.1 경계표 확장 15건(공유 `packages/fixtures/rules/*.cases.json` + 엔진 `tests/fixtures/cases/*.cases.json`), 재현성, trace. 합성 규칙과 실제 조항 규칙 7개·105사례에서 파일 재로딩, 규칙·입력의 중첩 객체 키 순서를 독립적으로 정순/역순 조합 4개로 바꾼 새 JSON 로딩 뒤 전체 결과 바이트(trace·누락 입력·버전·근거·두 해시 포함)를 비교한다(I18). 고정된 7개 규칙 목록과 실제 사례 수로 검사 누락을 거부한다. 케이스별 `trace`는 `fixture-rule-001.golden.json`과 추가 반올림 케이스의 `tests/fixtures/fixture-rule-001.rounding.golden.json`, 현재 형식의 `input_snapshot_hash`는 엔진 소유 `tests/fixtures/fixture-rule-001.snapshot-json-1.hashes.json`(공유 파일의 이전 해시를 대체), `rule_content_hash`는 `fixture-rule-001.content_hash`와 `real.content_hashes.json`(실규칙 전체)에 고정되어 회귀를 잡는다. 의도한 변경일 때만 갱신 |
| `snapshot_hash` | 두 DSL 버전에서 구분자 주입 충돌 방지, 특수 입력 이름·문자열, 전체 입력 타입·타입 구분·정수 경계, 수기 정규 JSON의 SHA-256 대조, 객체 키 순서 독립, 누락/null 동등성, 목록 class·금액·순서 보존, 엔진 버전·직렬화 재현성 |
| `mutation` | 합성 규칙을 손으로 망가뜨린 11개 변이 + 모든 규칙(합성 1개, `fixtures/rules/real`의 실제 규칙 7개)에서 기계적으로 만든 변이 336개가 골든 표에 모두 잡히는지. 변이기: 비교 연산자 뒤집기(`eq↔ne`, `lt↔lte`, `gt↔gte`, `lt↔gt`, `lte↔gte`), 정수·`krw`·`date_add` 값·요율 소수 끝자리 ±1, 불리언 리터럴 반전, `multiply_rate` 반올림 방식을 다른 4가지로 교체, `all`/`any` 자식 하나 제거, `all↔any`, `if`의 then/else 교체. 변이가 로드되지 않거나, 원본이 자기 케이스를 통과하지 못하거나, 케이스가 없으면 실패한다. 살아남은 변이는 `EQUIVALENT` 허용 목록(규칙·변이·사유, 현재 비어 있음)에 없으면 실패하며, 목록에 낡은 항목이 있어도 실패한다. 변이기가 항상 "죽었다"고 답하지 않는지(무변이 규칙·근거만 바뀐 규칙은 살아남음)도 음성 대조로 본다 |
| `fixture_supplements` | 공유 사례를 그대로 보존하면서 엔진 소유 경계 사례 59개를 추가하는지, 공유 기본 입력·규칙 ID와 사례별 덮어쓰기를 유지하는지, 공유/추가 사례의 ID 충돌을 거부하는지 |
| `real_clauses` | 실제 조항 설계 검증 사례를 정확히 105개(공유 47개 + 엔진 경계 58개) 실행하고, 로드된 모든 규칙에 사례가 하나 이상 있는지 검사한다. 파일별 삭제·단일 사례 삭제·예기치 않은 사례 추가·사례 없는 규칙 추가를 각각 거부하는 회귀 시험. 사례를 의도적으로 변경할 때만 고정 수를 갱신한다. [Audit 2 검증 증거](../../docs/blueprint/audits/2026-10-26_engine_real_clauses_count_assert.md) |
| `soundness` | 알려진 입력을 하나씩 `null` 또는 키 삭제로 숨겨도 확정 결과가 다른 확정 결과로 뒤집히지 않는지(I1). 이미 모르는 입력은 숨김 조합 수에서 제외한다. 합성 fixture와 `fixtures/rules/real/*.cases.json`의 실제 규칙 7개 전부에 적용하며, 고정된 7개 규칙 목록과 규칙별 실행 수로 모든 실제 규칙이 확정 케이스를 하나 이상 갖는지 확인한다. 모름을 `false`/`0`으로 바꾸는 평가기를 같은 검사기가 두 누락 방식 모두에서 잡아내는지(음성 대조)도 본다. 자격 입력을 숨겼을 때 금액 오버플로·날짜 범위·런타임 타입 오류가 판정 불가로 반환되는지, 누락 입력·trace·재현성 및 자격 확정 시 오류 유지를 확인한다 |
| `rule_02` | rule-0.2 연산 7종: 연산별 골든·경계(0, `i64::MAX`, 기념일 당일, 윤일)·변이(연산·반올림·구간표·경계 규칙을 바꾼 규칙이 골든 표에 잡힘)·건전성(입력을 하나씩 숨겨도 확정값이 뒤집히거나 0이 되지 않음), `whole=0` 모름, 0.1 문서에서의 거부, `contract_effect` 3상태 |
| `static_types` | 로드 단계 타입 검사: 감사 예시 두 건, 연산자별 거부와 오류 경로, 올바른 타입은 그대로 로드·평가 |
| `string_literals` | 두 DSL 버전의 명시적 `str`: eq/ne·양쪽 피연산자·일치/불일치, 입력명 충돌, 숫자형·한글·빈 문자열·이스케이프 보존, 누락/null 모름·blocker, 비문자열·추가 키·타입 불일치·순서 비교 거부, if/논리 합성, 기존 일반 문자열의 입력 우선·요율 해석 유지 |
| `range_comparisons` | Audit 2의 `p=201` 사례, 두 DSL 버전·비교 6종·양쪽 피연산자의 범위 거부, 모든 금액 연산과 `if`의 범위 전파, 정확한 금액 비교·범위 출력·모름 보존, `pro_rata` 비율 인자의 정확한 금액 제약. [검증 증거](../../docs/blueprint/audits/2026-10-26_engine_range_compare_static.md) |
| `loader_and_arith` | 반올림 모드, 상한, `days_between` 포함 여부·역순 날짜 거부, 달력 연산, 로더 거부 규칙. 두 DSL 버전·날짜 단위 전체에서 `date_add` 미지원 키·필수 키 대체·미선택 가지의 잘못된 파라미터 거부와 정상 달력 계산을 검증([Audit 2 증거](../../docs/blueprint/audits/2026-10-26_engine_date_add_unknown_keys.md)) |
| `days_between` | 두 DSL 버전·포함 플래그 4조합에서 역순 날짜의 비교 6종·임계값 0/1/90/180 거부, 리터럴·계산 날짜 오류 경로, 정상 순서·같은 날·윤일의 0일 포함 경계값·trace·재현성, 누락·null의 모름·blocker 유지 |
| `date_format`·날짜 단위 시험 | 두 DSL 버전의 날짜 리터럴·평가 입력에서 선행 `+`·0 채움 누락·공백·비ASCII 숫자 거부, 숫자 위치별 비숫자 거부, 정상 형식·윤일·지원 경계 보존. JSON 텍스트 로드에서 부호의 유니코드 이스케이프도 거부하고 정상 날짜의 재로드·평가 해시를 보존한다. [Audit 2](../../docs/blueprint/audits/2026-10-26_engine_parse_date_plus_sign.md)·[Audit 3 재검증·변이 증거](../../docs/blueprint/audits/2026-10-28_engine_parse_date_strict.md) |
| `identity_evidence` | 두 DSL 버전·모든 공개 상태·두 로드 진입점에서 빈/공백 ID·근거와 인접/비인접 중복 근거 거부, 오류 경로, 픽스처만 빈 근거 목록 허용, 정상 ID·근거 순서·해시·결과 보존. [Audit 2 검증 증거](../../docs/blueprint/audits/2026-10-26_engine_empty_ids_evidence.md) |
| `unknown_branch_errors` | 조건이 모름일 때 가지의 오류가 모름+blocker가 되는지, 선택된 가지·양쪽 가지의 오류는 유지되는지, trace 기록 |
| `all_any_errors` | 날짜 범위·오버플로·타입 오류와 모름을 포함한 자식 순서 6종에서 확정 결과 유지, 확정 자식이 없을 때 오류 전파, 모름의 blocker, 흡수 오류 trace·직렬화 재현성. `soundness`에도 오류를 내는 입력을 숨겨도 독립적인 확정 결과가 유지되는 회귀 시험 추가. [Audit 2 검증 증거](../../docs/blueprint/audits/2026-10-26_engine_all_any_lazy_error.md). Audit 3은 두 DSL 버전의 정확한 2항 사례·중첩식·`if` 조합과 즉시 오류 반환 변이 검출을 추가했다([증거](../../docs/blueprint/audits/2026-10-28_engine_all_any_short_circuit.md)) |
| `overflow` | `add`·`multiply_rate`의 `EvalError::Overflow` 경로를 `i64::MAX` 경계에서 직접 검증: 정확히 `MAX`는 통과, 1 초과는 오류(감김·포화 없음), 단위 올림(`ceil`/`half_up`/`half_even`)·`unspecified` 범위 상한·범위 입력의 한쪽 경계만 넘는 경우, 오류 경로 문자열. `min`/`max`/`apply_cap`은 넘치지 않음 |
| `content_hash_scope` | `rule_content_hash`의 범위(키 순서만 정렬): 공백·키 순서·문자열 이스케이프·최상위 `release_id`는 무시하고, 중첩 `release_id`·유니코드 형식(NFC/NFD·한글 자모)·문자열 공백·배열 순서·같은 뜻의 요율 표기·생략/명시 기본값·`example_kind`는 해시를 바꾼다(같은 평가 결과여도). [Audit 2 검증 증거](../../docs/blueprint/audits/2026-10-27_readme_adr_list.md) |
| `readme_test_table` | 이 표의 첫 열 이름과 `tests/*.rs` 파일의 일치(누락·낡은 행 모두 실패), 행 하나 삭제·이름 변경을 잡는 음성 대조, 해시 계약 문장에 "정규화" 대신 키 순서·유니코드·`release_id` 범위가 적혀 있는지 |
| `review_fixes` | 결과의 규칙 버전·릴리스·내용 해시·근거, 재로드 시 동일성, 범위의 연속 계산, 날짜 범위·오버플로(`i64::MIN`·`i64::MAX` 포함) |
| `vocabulary` | 직렬화 상태와 어휘 정본의 일치. 입력 타입 6개·반올림 5개·날짜 기간 단위 3개·연산자 키 28개의 정확한 값 집합, 로더 수용·미지원 값 거부, rule-0.2 전용 입력·연산의 버전 제한 |
| 문서 테스트·`immutable_rule_doctests` | 로드된 규칙의 필드 수정이 비공개 필드 접근 오류로 컴파일되지 않음(`compile_fail,E0616`)과 같은 준비 코드의 정상 동작. stable rustdoc는 오류 코드 표기를 강제하지 않으므로 통합 테스트가 두 예제의 실제 진단 코드가 모두 `E0616`인지 검사 |
| 단위 | 진리표(§49.3), 날짜 변환, 요율 파싱 |

Audit 1에서 빠진 DSL 축은 어휘 1.7.0의 `input_type`·`rounding`·`duration_unit`·`rule_operator`로 등록했다. 내부 enum `InputType`·`Rounding`·`DurUnit`과 `rule.rs`의 로더 허용 목록이 출처다. 리터럴 생성자와 `input`, 세 키 형식의 `if`도 연산자 축에 포함한다. 엔진의 허용 동작은 바꾸지 않았다. 회귀 검증은 `cargo test -p onjeon-rules-engine --test vocabulary`로 실행한다. 기존 어휘에서는 새 시험 4개가 각각 축 누락으로 실패한다.

Audit 2의 어휘 1.8.0은 `rule_operator`에 `str`을 추가하며, 두 DSL 버전의 로더 수용과 생성된 Rust·TypeScript·Dart 어휘에도 반영한다.

요율 리터럴은 `"0.5"`와 `{"rate":"0.5"}` 두 표현 모두 끝자리 ±1 변이를 만든다. 생성기 회귀 테스트는 소수·정수·0의 정확한 변이와 명시적 요율의 입력 이름 충돌을 확인한다. 실제 변호사선임비용 규칙의 요율 3개를 명시적 표현으로 바꿔도 변이 79개(요율 변이 6개 포함)가 유지되고 골든 표에 모두 잡히는지 검증한다.

추가한 경계 사례 59개는 허용 경로인 `packages/rules-engine/tests/fixtures/cases/`에 둔다. 공유 `packages/fixtures/rules/` 파일은 수정하지 않는다. 공통 로더는 같은 상대 경로의 추가 사례를 읽고 공유 기본 입력·규칙 ID를 재사용하며, 골든·변이·건전성·실제 조항 시험이 같은 확장 사례를 쓴다. Kyobo 소액암 규칙의 공유 사례 6개로는 살아남는 변이 16개가 로컬 사례 11개를 더하면 모두 잡히는지도 음성 대조로 확인한다.

`cargo test --test mutation -- --nocapture`로 규칙별 골든 케이스·변이 수와 전체 생존 변이 수를 볼 수 있다. 규칙 하나라도 생성된 변이가 없으면 실패한다. 로컬 재실행 결과와 CI 실행 제약은 [변이 테스트 실행 증거](MUTATION_TEST_EVIDENCE.md)에 기록했다.

## 아직 없는 것

금액 범위와의 비교 의미는 아직 지원하지 않는다. 범위 가능 식은 로드에서 보수적으로 거부하며, 상수·입력에 따라 정확한 값이 되거나 상한·0배·확정 `if` 조건으로 범위가 사라질 수 있어도 예외를 추론하지 않는다. 범위가 기준값을 걸치는 경우를 모름으로 처리할지는 W3 설계에서 정한다. 그 밖에 `first_match`, `in_set`, 상환형 연산(`subtract_deductible`, `coinsurance`, `cumulative_cap`; `pro_rata`는 rule-0.2에 있음), 청구 이력 상태, 코드 체계(KCD) 참조형, 규칙 스키마(JSON Schema) 파일. 제3부 §49.2, §54.4 W3에서 필요하다.

Audit 3 I1·I18·실제 규칙 해시 검사 보강의 실행 결과와 범위는 [검증 증거](../../docs/blueprint/audits/2026-10-28_engine_invariant_tests_strengthen.md)에 기록한다. 실제 조항 규칙은 계속 `fixture_only` 설계 검증 자료다.
