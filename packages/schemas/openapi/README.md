# packages/schemas/openapi: API v1 초안 (공개·개인·관제)

과제 T-CT-03. 근거: 02_구현계약 §2·§4, SYSTEM_CONTRACT §10 경로 제안, 제3부 §46.4(계정 삭제·내보내기)·§58(스켈레톤). 이 디렉터리는 **계약의 초안**이다. 서비스(T-AP-*, T-PS-*, T-WB-02)는 아직 없고, 경로는 어느 서버에도 연결되어 있지 않다.

| 파일 | 면 | 인증 | 캐시 |
|---|---|---|---|
| `public.v1.yaml` | 공개 API (C-14) `/v1/...` | 없음 | GET은 공개 캐시 가능(키에 `release_id`와 `x-onjeon-cache-key`), POST·오류는 `no-store` |
| `personal.v1.yaml` | 개인 API (C-15) `/v1/...` | 세션 필수 | **모든 응답 `Cache-Control: private, no-store`**, 공개 캐시 금지 |
| `console.v1.yaml` | 관제 API (C-16) `/console/v1/...` | 2FA 세션, 역할 `operator`·`policy_owner`·`reader` | 개인 API와 같음 |

## 형식

파일은 `.yaml`이지만 내용은 JSON이다(JSON은 YAML 1.2의 부분집합). 저장소에 YAML 파서가 없고 생성기·시험이 표준 라이브러리만 쓰기 때문이다. 어떤 YAML·OpenAPI 도구로도 읽힌다. 손으로 고칠 때는 JSON 문법을 지킨다.

`components.schemas`는 `packages/schemas/json`과 같은 JSON Schema 부분집합이다(구조체는 `additionalProperties: false`, `enum`·`const` 없음, enum은 `../json/vocabulary.schema.json`의 `$ref`만). 계약 뷰(`CompareView`, `ScenarioResult`, ...)는 `../json/*.schema.json`을 `$ref`하고 다시 정의하지 않는다. 쿼리 파라미터는 생성기가 `<OperationId>Query` 구조체로 만든다. 멀티파트 폼의 바이너리 파트(`format: binary`)는 JSON이 아니므로 생성 타입에서 빠진다.

## 규칙(생성기 lint가 강제, `codegen/openapi_model.py`)

- **모든 2xx 응답 본문에 필수 `release_id`(ReleaseId)가 있다.** 계약 뷰는 이미 가지고 있고 나머지는 응답 봉투가 넣는다. 모든 2xx 응답은 `X-Onjeon-Release-Id` 헤더도 낸다. 오류 응답(`ErrorResponse`, T-CT-01 계약)에는 본문 `release_id`가 없다: 그 필드를 더하면 계약 판이 바뀐다. 헤더는 오류 응답에서 릴리스가 정해졌을 때만 실린다. **오류 응답의 본문에는 release_id가 없다**는 것이 이 초안의 알려진 예외다.
- 관제 응답의 `release_id`는 응답 시점의 현재 공개 릴리스이고, 첫 릴리스 전에는 `null`이다(키는 필수).
- 개인·관제 문서: 오류를 포함한 모든 응답이 `Cache-Control` 헤더를 선언하고 값이 `private, no-store` 하나로 고정된다. 문서 최상위 `x-onjeon-cache-policy`가 금지 지시어(`public`, `s-maxage`, `max-age`, `stale-while-revalidate`, `stale-if-error`, `immutable`)를 적고, 개인·관제 연산에는 `x-onjeon-cache-key`가 없다.
- 공개 문서: GET만 공개 캐시 가능하고 캐시 키에 `release_id`가 있다. 비교·시나리오처럼 입력이 결과를 정하는 POST는 `no-store`다(서버 안 캐시 키는 입력 해시 + `release_id` + `comparison_basis_id`).
- 업로드·계산 요청(`policy-imports`, `scenarios`, `evaluations`, `need-assessments`(공개·개인), `plans`)은 본문에 필수 `idempotency_key`가 있다(시험 `test_calculation_and_upload_requests_carry_an_idempotency_key`; 생성기 lint가 아니다). 상태·결과 조회 경로(`GET`)는 `policy-imports`, `evaluations`, `plans`에만 있다. 시나리오·필요 진단 결과는 저장하지 않으므로 조회 경로가 없고, 이를 검사하는 lint나 시험도 없다.
- 알 수 없는 enum은 오류다(어휘 `$ref`만 쓰고 생성 타입이 역직렬화에서 거부한다).
- 금액은 정수 원(`Krw`). 부동소수점은 원본 영역 bbox 좌표뿐이다(시험이 고정).

## 스켈레톤 (제3부 §58)

경로·권한 이름·플래그만 예약한다. 구현·화면·노출은 없다.

| 경로 | 플래그 | 기본값 |
|---|---|---|
| `POST /v1/consultation-requests` | `consultation_enabled` | off |
| `POST /v1/quote-requests` | `quotes_enabled` | off |

연산에 `x-onjeon-skeleton: true`, `x-onjeon-flag`, `x-onjeon-flag-default: false`와 태그 `skeleton`이 있다. 플래그가 꺼져 있으면 404다. 요청 타입은 `profile_id`와 `idempotency_key`뿐이라 미래 기능용 사용자 데이터를 받지 않는다. 스켈레톤은 개인 문서에만 둘 수 있다.

**비노출:** 생성 산출물의 기본 면에는 스켈레톤이 없다. Rust는 `skeleton` 피처(기본 꺼짐) 뒤의 `#[cfg]`, TypeScript는 `skeleton.ts`(`index.ts`가 내보내지 않음), Dart는 `lib/skeleton.dart`(`onjeon_api.dart`가 내보내지 않음). 스켈레톤 전용 타입은 "기본 연산이 닿지 않는 구조체"로 계산해 자동으로 가둔다. 누출 정적 검사(`codegen/tests/test_openapi.py`)는 스켈레톤 연산·타입·플래그 이름이 기본 산출물, 공개·관제 문서, 손으로 쓴 Rust 파일, 스켈레톤을 지운 개인 문서에 나타나지 않음을 확인하고, TypeScript·Dart 빌드는 기본 진입점으로 스켈레톤을 쓰는 코드가 컴파일되지 않음을 확인한다. 스켈레톤을 켜는 것은 별도 결정이다.

## 생성물

```text
bash packages/schemas/codegen/gen.sh           # 계약 타입과 API 타입 재생성
bash packages/schemas/codegen/gen.sh --check   # 최신 여부(CI)
```

| 출력 | 위치 |
|---|---|
| 서버 타입(Rust, 크레이트 `onjeon-api-types`) | `packages/api-types/src/generated/` |
| TypeScript 클라이언트 타입 | `packages/schemas/codegen/generated/ts-api/` (계약 타입은 `../ts`) |
| Dart 클라이언트 타입 | `packages/schemas/codegen/generated/dart-api/` (계약 타입은 `package:onjeon_contracts`) |

연산 표(`operations`: id·방법·경로·캐시 분류·캐시 키·역할·요청/응답 타입 이름·스켈레톤)도 세 언어로 생성된다. "클라이언트"는 타입과 연산 표까지다. HTTP 호출 코드는 없다(앱 골격 T-MB-01의 몫).

시험: `cargo test -p onjeon-api-types`(연산 표가 문서와 같은지, 픽스처 왕복, 캐시 분류, 스켈레톤 비노출·`--features skeleton`, `gen.py --check`, 파이썬 OpenAPI 시험), `python3 -I -m unittest discover -s packages/schemas/codegen/tests`, `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh`. 픽스처는 `codegen/tests/api_fixtures/*.fixture.json`이고 시험 전용이다.

## 증거와 한계

- 실행 로그는 `packages/schemas/codegen/evidence/ct03/`에 커밋돼 있다(`ct03/EVIDENCE.md`가 색인).
- **인증 수단은 정해지지 않았다.** `POST /v1/auth/sessions`는 `provider`·`credential`을 불투명 값으로 받는 자리표시다(인증 설계는 제3부 §54.2 6번). 자격 증명은 저장·로그 금지.
- **D-11(비회원 서버 저장 없는 계산)은 보류.** `POST /v1/evaluations`에 `ephemeral` 모드는 없고 연산에 `x-onjeon-pending-decision: D-11`만 적었다.
- 내보내기는 기계 판독 JSON만 정했다. 사람용 PDF(제3부 §46.4)는 이 초안에 없다.
- 다음 값 집합은 어휘 정본에 아직 없어 소문자 snake_case 패턴 문자열이고 설명에만 후보를 적었다: 확보 층 이름, 가져오기·삭제·확보 작업 상태, 삭제 단계, 확인 주체, 신고 분류, 검수 역할, 감사 행위, 품질 지표, 임계값 이름, 비용 분류. 어휘에 들어오는 과제(T-CT-02)가 `$ref`로 바꾼다. 이 값들은 이 문서가 새로 만든 것이므로 확정이 아니다.
- 오류 코드 표와 `message_key`는 T-CT-04의 몫이다. 이 문서는 어떤 코드가 어느 응답에 쓰이는지 정하지 않고 오류 클래스(V·A·N·S·L·U·X·T)에 해당하는 상태 코드(400·401·403·404·409·429·422·500·504)만 고른다.
- `Cache-Control`의 유효 시간 숫자는 정하지 않았다(T-AP-01).
- 생성된 Dart `fromJson`과 TS 타입은 관제 본문에 `release_id` 키가 없어도 받는다(T-CT-01 §6.5와 같은 한계). 키 존재는 Rust만 강제한다.
- 민감 필드(`SessionRequest.credential`, `PolicyImportForm.password`)를 가진 생성 Rust 타입은 `Debug`를 파생하므로 `{:?}`로 로그하면 값이 찍힌다. 로그 금지는 사용처의 규칙이다. 가림 처리는 T-AP-01 전에 생성기에 더할 후속이다.
- `cov_ids` xor `concept_id`, `contract_ids` xor `cov_ids`는 JSON Schema 부분집합으로 쓸 수 없어 `onjeon-api-types`의 `checks`가 검사한다. 그 외 제약(`pattern`·`minimum`)은 파이썬 시험용 검증기만 확인하고 생성 타입은 강제하지 않는다(contracts와 같다).
- **OpenAPI diff 호환 검사(02 §5의 "공개·개인·관제 API 경로 `/v1`")는 아직 없다.** `check_compat.sh`는 `json/` 스키마만 비교한다. 필드 삭제를 `/v2`로 강제하는 검사는 후속이다.
- CI 워크플로(`.github/workflows/`)는 이 과제의 허용 경로 밖이라 연결하지 않았다. `cargo test --all`이 `gen.py --check`와 OpenAPI 시험을 돌리므로 기존 cargo 단계가 그것을 지킨다. TypeScript·Dart 빌드는 도구가 필요해 CI가 돌리지 않고, 근거는 커밋된 로그뿐이다.
- `packages/schemas/README.md`(T-CT-01)는 이 과제의 허용 경로가 아니라 고치지 않았다. 그 문서의 구성표·`tree_hash.sh` 값(`codegen/evidence/EVIDENCE.md`)은 이 디렉터리와 새 생성물을 포함하지 않은 시점의 것이라 지금 트리와 해시가 다르다. T-CT-01 로그를 낡았다고 읽어야 한다(로그가 보이는 사실은 그 시점의 것).
