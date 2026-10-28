# packages/schemas: 계약 패키지 (`onjeon-contracts`)

앱·API·엔진·릴리스 빌더가 주고받는 형태의 단일 출처. 어휘 정본(`vocabulary.json`)의 enum과 JSON Schema 열두 문서를 정의하고, 거기서 Rust·TypeScript·Dart 타입을 생성한다. 과제 T-CT-01(골격), 어휘 1.6.0 반영은 T-CT-02, 1.7.0은 Audit 1의 기존 규칙 DSL 축 등록, 1.8.0은 Audit 2의 명시적 문자열 리터럴 `str` 추가다. 근거: 02_구현계약 §1·§5·§6(검토용 묶음, 채택 전), 화면 설계서 §11. 이 패키지는 계약의 **모양**이다. 의미 검사(릴리스 빌더, DB 제약, evidence_ref 파서)는 후속 과제(T-CT-03~05, T-KN-*)의 몫이다.

## 구성

| 경로 | 내용 |
|---|---|
| `vocabulary.json` | 상태 어휘 정본(1.8.0). 변경은 정본 변경을 승인한 과제(T-CT-02, Audit 1 DSL 축 등록, Audit 2 명시적 문자열 리터럴 등)만 한다 |
| `json/*.schema.json` | 손으로 쓴 JSON Schema(2020-12 부분집합). `common`(ID·근거 참조·금액·결과 상태), `assertion`, `release_manifest`, `evaluation_result`, `scenario_result`, `coverage_detail`, `compare_view`, `plan_view`, `evidence_view`, `need_result`, `premium_observation`, `contract_snapshot`, `error_response` |
| `json/vocabulary.schema.json` | **생성물.** 어휘의 모든 축이 `enum`으로 들어 있는 유일한 스키마 |
| `src/generated/` | 생성된 Rust(serde). `src/checks.rs`는 손으로 쓴 교차 필드 검사 |
| `codegen/generated/ts/`, `codegen/generated/dart/` | 생성된 TypeScript·Dart 패키지 |
| `codegen/*.py`, `*.sh` | 생성기, 스키마 lint, 호환 검사, 빌드 확인 |
| `codegen/tests/` | Python 시험, 시험 전용 픽스처(`*.fixture.json`) |
| `evidence_ref.md` | evidence_ref 문법(정규식은 `json/common.schema.json`) |

## 명령

```text
bash packages/schemas/codegen/gen.sh                     # 생성물 재생성
bash packages/schemas/codegen/gen.sh --check             # 생성물이 최신인지(CI)
cargo test -p onjeon-contracts                           # Rust 시험
python3 -I -m unittest discover -s packages/schemas/codegen/tests   # 스키마·호환 검사 시험
bash packages/schemas/codegen/build_check.sh             # 세 언어 생성물 빌드
bash packages/schemas/codegen/check_compat.sh <prev_tag> # 이전 태그와 호환 검사
bash packages/schemas/codegen/check_compat.sh --selftest # 필드 삭제를 넣으면 실패하는지 자체 시험
```

`build_check.sh`는 TypeScript는 `tsc`(`TSC="node /path/tsc.js"`로 지정 가능), Dart는 `dart analyze`와 픽스처 왕복 실행으로 확인한다. 도구가 없으면 그 언어는 **빌드하지 않은 것**이고 `SKIPPED`와 종료 코드 3을 낸다. `ONJ_REQUIRE_TOOLCHAINS=1`이면 실패다. 기존 CI 워크플로는 TypeScript·Dart를 빌드하지 않으므로(아래 '한계'), 세 언어 빌드의 근거는 `ONJ_REQUIRE_TOOLCHAINS=1`로 돌린 이 스크립트의 로그(`RESULT: all three languages build`, tsc·Dart 버전 포함)를 `codegen/evidence/build_check.log`로 **커밋한 것**이다(아래 '증거'). PR 본문에 붙인 로그는 리뷰 대상이 아니다.

## 증거 (`codegen/evidence/`)

Audit 2 어휘 1.8.0의 최신 검증은 [별도 색인](../../tools/evidence/audit2-engine-string-literals/README.md)에 있다. 생성물 최신성·Rust 빌드와 workspace 시험은 통과했고, TypeScript·Dart는 도구 미설치로 빌드를 건너뛰었다. 아래 `codegen/evidence/`의 세 언어 빌드 기록은 해당 색인에 적힌 과거 트리의 증거다.

검증 명령의 실제 출력을 커밋한 디렉터리다. CI는 TypeScript·Dart를 빌드하지 않고 리뷰어는 PR 본문을 보지 않으므로, 커밋된 파일만이 리뷰어가 대상 SHA에서 읽을 수 있는 근거다. 색인은 [`codegen/evidence/EVIDENCE.md`](codegen/evidence/EVIDENCE.md)이고 로그마다 정확한 명령·종료 코드·도구 버전·로그를 만든 부모 커밋·`packages/schemas` 트리(증거 디렉터리 제외)의 sha256을 적는다.

- `build_check.log`: `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh`. **세 언어 빌드의 유일한 근거**이며 `RESULT: all three languages build`로 끝난다. CI가 이 단계를 대신하지 않는다.
- `cargo_test.log`: `cargo test -p onjeon-contracts`(파이썬 시험 묶음, `gen.py --check`, `check_compat.sh --selftest` 포함).
- `vocab_check.log`: `python3 tools/vocab_check.py`.
- `check_compat.log`: `check_compat.sh --selftest`와 태그 없는 호출. `contracts-*` 태그가 없어 **실제 이전 태그와의 비교는 일어나지 않았다**(미검증). 자체 시험이 보이는 것은 필드 삭제가 실패한다는 것까지다.
- `rule02.log`: `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts`. rule-0.2를 지원하는 `main`의 엔진과 합친 트리에서 돌려 round-trip 시험이 건너뛰지 않는다.

로그는 자동으로 갱신되지 않는다. 스키마·생성기·시험·이 README가 바뀌면 EVIDENCE.md의 트리 해시(`bash packages/schemas/codegen/tree_hash.sh`로 다시 계산)가 맞지 않게 되므로 같은 명령을 다시 돌려 로그를 바꾼다. `codegen/tests/test_evidence.py`는 로그가 전부 있고 통과 기록이며 절대 경로·비밀값·버전 붙은 식별자가 없는지만 검사하고, 해시가 현재 트리와 같은지(신선도)는 검사하지 않는다. 이 디렉터리는 생성물도 스키마 입력도 아니라서 `gen.py --check`·lint·호환 검사가 읽지 않는다. 로그에 절대 경로·모델 식별자·비밀값을 넣지 않는다(기록 전에 치환하고 grep으로 확인).

## 규칙

- **enum은 어휘 정본에서만 온다.** 스키마 파일에는 `enum`·`const`가 없고, 모든 어휘 값은 `vocabulary.schema.json`(생성물)을 `$ref`한다. 어휘와 다르게 손으로 고친 생성물, 스키마 안의 `enum`은 lint 오류다(`codegen/tests/test_schemas.py`).
- **어휘에 아직 없는 축은 `x-onjeon-pending-axis` 문자열이다.** 02_구현계약이 값을 정했지만 어휘(1.6.0)에 축이 없는 것(아래 표)은 닫힌 enum처럼 쓰지 않고 소문자 snake_case 패턴의 문자열로 둔다. 어휘 정본을 이 패키지의 과제가 바꿀 수 없기 때문이다. 어휘에 그 축이 들어오는 순간 lint가 실패해서 `$ref`로 바꾸게 한다. 어휘 1.6.0(T-CT-02)에서 아홉 축·열한 필드가 그렇게 `$ref`로 옮겨갔다(아래 '1.6.0에서 승격된 축').
- 알 수 없는 enum 값은 역직렬화 실패다(성공으로 처리하지 않음). 알 수 없는 필드는 무시한다. 선택 필드 추가(minor)가 구버전 클라이언트를 깨지 않게 하려는 것이다. 스키마 문서는 `additionalProperties: false`로 닫혀 있다. 새 enum 값은 §5에서 minor지만 구버전 클라이언트는 그 값을 읽지 못한다. 앱이 지원 범위를 선언하는 이유다(§5 마지막 행).
- 금액은 정수 원(`Krw`). 부동소수점은 화면 표시 전용 만원 값(`Budget.*_man`, `CurrentPaid.man`, `PriceLine.man`)에만 있고, 예산 판정과 정렬은 원 단위로 한다(화면 설계서 §11). 시험이 부동소수점 필드 목록을 고정한다.
- 시각 필드는 어휘 정본의 이름만 쓴다: 02가 쓴 `valid_from`·`valid_to`는 폐기 별칭이라 `effective_from`·`effective_to`, 가격 기준일은 `source_as_of`. 모델 식별자 원문은 싣지 않고 `model_ref_hash`만 싣는다.
- 교차 필드 불변식은 `src/checks.rs`에서 검사한다: accepted ⇒ 검수 결정, `origin=fixture` ⇒ accepted 불가, 주장은 `object` 또는 `value` 하나, 가격 비교 자격의 조건(K13), 막힌 시나리오는 엔진 결과 없음, 엔진 결과 모양(`payout`·`contract_effect`가 `eligibility`를 따르고 `kind`마다 그 kind의 필드만 있음), 오류 클래스와 코드의 일치. DB 제약(T-CT-05)과 릴리스 빌더(T-KN-07)의 대체가 아니다.
- 규칙 엔진 직렬화와 `EvaluationResult`가 같은 모양인지는 엔진을 실제로 돌려 확인한다(`rule_engine_output_deserializes_into_evaluation_result`; rule-0.2 규칙의 효과는 `rule_02_contract_effects_round_trip_when_the_engine_supports_them`). 후자는 엔진이 rule-0.2 규칙을 거부하면(이 브랜치가 갈라진 시점의 엔진, PR #105 이전) 거부 이유만 확인하고 `VACUOUS:`를 찍은 채 끝난다. 즉 그 엔진에서는 **아무것도 검증하지 않는다.** `main`(#105 병합 후)의 엔진과 합친 빌드(CI가 시험하는 것)에서만 세 모양(`applies`·`none`·`undetermined`)을 실제로 돌린다. `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts`는 그 건너뜀을 실패로 만든다. `contract_effect`(rule-0.2, G23)는 엔진이 rule-0.2를 지원한 뒤(PR #105)로 모든 결과에 실린다. 그 전 엔진 빌드의 결과에는 없으므로 계약에서는 **선택 필드**다. 없음은 '효과 없음'이 아니라 '엔진이 보고하지 않음'이고, 효과 없음은 `kind=none`이다. 필수로 올리는 것은 깨지는 변경(§5)이라 다음 계약 판의 몫이다.

## 버전과 호환 검사 (02 §5)

패키지 버전은 이 디렉터리 `Cargo.toml`의 `version`이고 태그는 `contracts-x.y.z`다. 깨지는 변경 = 필드 삭제·타입 변경·필수 ↔ 선택 변경·필수 필드 추가·enum 값 삭제·타입 삭제(major, `0.x`에서는 minor를 올려야 한다). 선택 필드·타입·enum 값 추가는 버전을 올리면 된다. 스키마가 바뀌었는데 버전이 그대로면 실패한다.

`check_compat.sh <prev_tag>`는 (1) 이전 태그의 스키마와 구조 비교, (2) 깨지는 변경이 없으면 이전 태그의 스키마에서 현재 생성기(`emit_rust`)로 다시 만든 Rust 클라이언트(태그에 커밋된 생성물 그대로가 아니다)로 새 스키마에서 만든 최소 문서를 읽는 컴파일 탐침을 돌린다. 깨지는 변경을 major 상향으로 선언했으면 탐침은 건너뛴다. 탐침 문서의 enum 값은 이전·새 어휘에 **모두** 있는 값 중 새 어휘 순서의 첫 값이다(`compat.enum_sample`): 새 값이 축의 맨 앞에 들어와도 구버전 클라이언트가 모르는 값을 먹여 거짓 비호환을 내지 않는다. 이전 판에 없던 축이나 이전 값이 전부 지워진 축만 새 어휘의 첫 값으로 물러선다(후자는 구조 비교가 먼저 깨지는 변경으로 잡는다). `contracts-*` 태그가 하나도 없으면(첫 릴리스) 비교 대상이 없다고 밝히고 자체 시험만 돌린다.

탐침 크레이트는 실행마다 다른 이름(`compat_probe_<해시>`)을 받는다. 탐침들이 `CARGO_TARGET_DIR`(`target/compat-probe`)을 공유하므로 같은 이름이면 동시에 도는 두 탐침(`cargo test` 안의 자체 시험과 파이썬 시험)이 서로의 실행 파일을 실행할 수 있기 때문이다. 저장소에 `Cargo.lock`이 있으면 그 잠금으로 serde를 고정해 새로 해석하지 않는다(캐시에 있으면 레지스트리 접근도 없다). 종료 코드: 0 호환, 1 비호환, 2 사용법·준비 오류. 탐침을 만들거나 빌드하지 못한 것은 2이지 비호환 판정이 아니다.

## 한계와 열린 항목

- **CI 워크플로 단계는 아직 연결되지 않았다(후속 과제로 남김).** 대신 `cargo test --all`이 `gen.py --check`, 파이썬 시험 묶음, `check_compat.sh --selftest`(필드 삭제 시 실패 확인)를 실행하므로 기존 CI의 cargo 단계가 이 셋을 지킨다. TypeScript·Dart 빌드는 도구가 필요해 cargo가 돌리지 않는다. 그 빌드의 근거는 커밋된 `codegen/evidence/build_check.log`뿐이다. `.github/workflows/`는 이 과제의 허용 경로 밖이다. 연결할 때 추가할 단계: `python3 -I packages/schemas/codegen/gen.py --check`, `python3 -I -m unittest discover -s packages/schemas/codegen/tests`, `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh`(tsc·Dart SDK 설치 필요), `ONJ_REQUIRE_RULE_02=1 cargo test -p onjeon-contracts`(엔진이 rule-0.2를 지원하는 `main`에서 round-trip 시험이 건너뛰지 않게), 태그가 생긴 뒤 `bash packages/schemas/codegen/check_compat.sh contracts-<이전>`. 이 단계는 `git fetch --tags` 후 `ONJ_REQUIRE_BASELINE=1`로 돌려 태그가 없을 때 조용히 통과하지 않게 한다(`check_compat.sh`는 이 값이 1이면 태그 부재를 오류 2로 처리). 후속 연결 담당: **구현자(사람)**. 과제 그래프(tasks.json)는 `.github/workflows/**`를 어느 과제의 허용 경로에도 넣지 않고 구현자 관리로 둔다(T-CT-06 비고와 같은 규칙).
- 호환 컴파일 탐침은 Rust만이다. TypeScript·Dart는 현재 스키마의 빌드와 픽스처 확인만 하고 이전 태그 생성물로의 교차 컴파일은 하지 않는다. 구조 비교는 세 언어에 공통이다.
- 첫 `contracts-*` 태그는 아직 없다. 태그를 찍는 것은 릴리스 절차의 몫이다. 따라서 실제 이전 태그에 대한 호환 검사는 아직 한 번도 돌지 않았다(`codegen/evidence/check_compat.log`).
- 02가 닫지 않은 것: 주장 ID 표기(`a:` 대 `assertion:`, `evidence_ref.md`), `release_hash`와 `content_sha256`의 관계(스키마는 `content_sha256`만), `need_result.id`·`conclusion_id` 형식, `special_conditions`·`usage_counters` 항목 형식(임의 JSON), `judged_by` 등의 값 집합. 임의로 정하지 않고 자리만 두었다(`scope_relation`의 값 집합은 어휘 1.6.0이 온톨로지 설계안 §13에서 가져와 닫았다).
- `PlanView`는 화면 설계서 §11을 따른다. 검증 표본(`docs/blueprint/validation/screen/*.json`)은 `won`·`man_display` 같은 §11에 없는 필드를 쓰는 설계 검증용 사본이라 이 스키마에 맞추지 않았다.
- OpenAPI(T-CT-03), 오류 코드 표·분석 이벤트·도메인 이벤트(T-CT-04)는 이 과제에 없다. `ErrorResponse`는 형태만 정의한다.
- 픽스처는 시험 전용이다. 제품 코드에서 쓰지 않으며, `origin`이 있는 픽스처는 모두 `origin=fixture`이고 어느 것도 accepted가 아니다(예외 없음, `test_fixtures_are_marked_test_only`). 비교 자격(`comparison_eligible=true`)은 accepted를 요구하고 `origin=fixture`는 accepted일 수 없으므로, 그 경우는 파일로 두지 않고 Rust 시험이 `PremiumObservation.full.fixture.json`에서 메모리 안에서만 만든다.

### 어휘 승격 대기 축 (`x-onjeon-pending-axis`)

값의 출처는 02_구현계약(§1.2·§1.4·§1.5·§1.6·§1.7·§2.4·§4.2·§6.1)과 PREMIUM_DATA_CONTRACT·DATA_PIPELINE_CONTRACT다. 값 집합이 02에 없는 축(`judged_by`, `not_comparable_reason`, `line_kind`, `payment_cycle`)은 형식만 제한한다. 이 표와 스키마의 일치는 `codegen/tests/test_schemas.py`(`Readme`)가 검사한다. 어휘 1.6.0 이후 남은 대기 축은 18개, 필드 21개다.

| 축 | 쓰는 필드 |
|---|---|
| `applicability` | `Amount.applicability`, `CompareCell.applicability` |
| `blocked_reason` | `BlockedBy.reason` |
| `chain_level` | `ChainStep.level` |
| `contract_effect` | `ContractEffectResult.conditional_effect`, `ContractEffectResult.effect` |
| `contract_effect_kind` | `ContractEffectResult.kind` |
| `dependency_producer` | `ConclusionDependency.produced_by` |
| `dependency_state` | `DependencyInfo.dependency_state` |
| `detail_layer` | `DetailLayer.layer` |
| `evidence_kind` | `Amount.evidence_kind`, `CompareCell.evidence_kind` |
| `judged_by` | `InputJudgement.judged_by` |
| `line_kind` | `ViewLine.kind` |
| `not_comparable_reason` | `NotComparableReason.reason` |
| `overlap_state` | `UnknownOverlap.state` |
| `package_binding` | `PremiumObservation.package_binding` |
| `payment_cycle` | `PremiumObservation.payment_cycle` |
| `plan_tab` | `PlanView.tab` |
| `statement_kind` | `NeedReason.statement_kind` |
| `value_kind` | `AssertionValue.value_kind` |

### 1.6.0에서 승격된 축 (T-CT-02)

어휘 1.6.0이 들어오면서 lint가 요구한 대로 아래 필드는 대기 문자열에서 `vocabulary.schema.json`의 `$ref`(닫힌 enum)로 바뀌었다. 세 언어 생성물에서 그 필드의 타입이 문자열에서 enum으로 바뀌고, 알 수 없는 값은 역직렬화 실패가 된다(1.5.0 때는 패턴만 맞으면 통과했다). `contracts-*` 태그가 아직 없으므로 호환 판 비교 대상은 없다.

| 필드 | 축 | 비고 |
|---|---|---|
| `Assertion.origin`, `PremiumObservation.origin` | `assertion_origin` | `checks.rs`의 `ORIGIN_FIXTURE`가 `AssertionOrigin::Fixture`가 됐다 |
| `SnapshotComponent.confirm_party`, `SnapshotComponent.fact_source` | `confirm_party`, `fact_source` | |
| `ErrorResponse.error_class` | `error_class` | **전송 형태가 바뀌었다.** 1.5.0은 클래스 글자(`V`), 1.6.0은 어휘 낱말(`validation`). `code`의 클래스 글자(`VANSLUXT`)는 그대로이고, 글자와 낱말의 대응은 `checks.rs`의 `error_class_letter`가 고정하며 `check_error_response`가 둘의 일치를 검사한다 |
| `EvidenceLink.role` | `evidence_role` | |
| `ResultState.knowledge_freshness`, `ResultState.usage_restriction` | `knowledge_freshness`, `usage_restriction` | |
| `NeedResult.verdict`, `NeedSummary.verdict` | `need_verdict` | |
| `ScopeRelationEntry.value` | `scope_relation` | 어휘 축의 타입 이름 `ScopeRelation`(enum)과 겹쳐서 객체 정의 `ScopeRelation`을 `ScopeRelationEntry`로 바꿨다. 필드 이름 `scope_relations`와 전송 형태는 그대로다 |
| `Assertion.correction_reason` | `correction_reason` | lint가 요구한 것은 아니다. 1.5.0 때 자유 문자열이었지만 어휘 1.6.0이 이 축의 `applies_to`를 Assertion으로 정했으므로 같은 규칙(enum은 어휘에서만)으로 옮겼다 |

어휘 1.6.0의 나머지 새 축 `fact_kind`·`criterion_source_kind`와 `doc_role`의 새 값은 이 패키지의 스키마에 해당 필드가 없어 바뀐 것이 없다.

- **정규식에 박힌 닫힌 집합.** `ErrorResponse.code`의 구역 2자(`CT|DT|KN|TW|PS|AP|OP`)와 클래스 글자(`VANSLUXT`)는 어휘 축이 아니라 패턴 안의 닫힌 목록이다. 클래스 글자와 `error_class` 낱말의 대응은 위 표대로 `checks.rs`에 있고, 구역 목록과 오류 코드 표는 T-CT-04가 흡수해야 한다.
- **제약은 생성물이 강제하지 않는다.** `pattern`·`minimum`·`minItems`는 시험용 `validate.py`만 검사한다. 세 언어 클라이언트는 음수 `Krw`나 잘못된 ID도 역직렬화한다. 필수이면서 null을 허용하는 키(`release_id` 등)는 Rust(`deserialize_with = "Option::deserialize"`)와 TypeScript(필수 속성)가 키 부재를 거부하고, Dart `fromJson`은 부재와 null을 구분하지 않는다.
