# Audit 8 TypeScript 계약의 enum 런타임 검사

`audit8-ts-runtime-enum-reject`의 공유 계약 회귀 증거다. 첫 출시 완료는 [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 실제 데이터·트윈·소비자 화면 증거로 판정한다.

공유 JSON Schema의 구조체 64개에 대해 `parse<Type>(value: unknown)`을 생성하고 기본 진입점에서 내보낸다. 문서 파서는 기존 어휘 파서를 호출해 중첩 객체와 배열의 미등록 enum 값도 거부한다. 구조체 필드의 타입·필수 여부·`null` 허용 여부를 검사하고 새 구조체 필드는 무시한다. 전체 스키마 제약과 교차 필드 불변식은 별도 검사 대상이다. OpenAPI 전용 `ts-api` 구조체는 정적 인터페이스를 제공한다. [생성기](../../../packages/schemas/codegen/emit_ts.py) · [사용법](../../../packages/schemas/README.md#typescript-문서-읽기).

| 로컬 실행 | 결과 |
|---|---|
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 31개 일치. Rust 1.98.1 빌드, TypeScript 5.9.3 타입 검사와 Node 24.22.1 런타임 시험 23개, Dart 3.13.5 분석·픽스처 왕복 통과. |
| [Node 런타임 회귀](../../../packages/schemas/codegen/tests/ts_roundtrip.cjs) | 12종 문서의 픽스처 18개를 파서에 통과시켰다. `Assertion.criticality`, `Assertion.evidence[0].role`, `Assertion.value.amount_form`, `ScenarioResult.evaluation.eligibility`의 미등록 값을 거부했다. 필수 키, 타입, `null`, 추가 필드 무시와 열린 맵의 키 보존도 확인했다. |
| 작업 트리 안의 생성물 복사본에서 `parseCriticality`의 어휘 포함 검사를 제거하고 컴파일한 뒤 같은 Node 시험 실행 | `c9`에 대한 `TypeError`가 발생하지 않아 회귀 시험이 실패했다. 종료 코드 1. |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 작업 공간 시험 564개 통과, 기존 무시 1개. 별도 매니페스트의 키 순서 보존·시나리오 API·온톨로지 실행기 시험은 각각 2개·4개·4개 통과. |
| `ONJ_COMPAT_ALL_CLIENTS=1 python3 -I -m unittest discover -s packages/schemas/codegen/tests -v` | 합성 태그의 세 언어 호환 탐침을 포함해 142개 통과. `check_compat.sh --latest`는 이전 `contracts-*` 태그 부재를 보고하고 필드 삭제 자체 시험을 통과했다. |
| `python3 -m unittest discover -s tools/tests -v` | 1,812개 실행 중 1,806개 통과, 기존 건너뜀 6개. |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 첫 실행에서 로컬 Git 시간 초과와 제공자 전환 시나리오 실패가 발생했다. 전체 묶음을 단독 재실행해 81개 모두 통과했다. |

CI는 계약 도구 설치 단계에서 `ONJ_REQUIRE_TOOLCHAINS=1`로 생성물 빌드와 런타임 시험을 실행한다. [CI 워크플로](../../../.github/workflows/ci.yml).

## 1차 수정 검증

- 기존 생성물에서 Node `vm` 내부의 `JSON.parse`로 읽은 `Assertion.relation` 픽스처를 `parseAssertion`에 넘기면 `Assertion: expected a plain object`로 실패했다. 새 회귀 시험만 실패했다(23개 통과, 1개 실패).
- 재생성한 파서는 같은 픽스처의 중첩 객체와 배열까지 읽고, 그 배열 안의 미등록 `role`은 `Assertion.evidence[0].role` 경로로 거부한다. 다른 realm의 클래스 인스턴스와 직접 만든 프로토타입도 거부한다. [Node 런타임 회귀](../../../packages/schemas/codegen/tests/ts_roundtrip.cjs)
- `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh`가 생성물 일치와 Node 런타임 시험 24개를 모두 통과했다. OpenAPI TypeScript 픽스처 타입 검사, Dart 분석·픽스처 왕복, 기본 진입점의 스켈레톤 비노출 검사도 통과했다. README에 이 스크립트를 실행하는 현재 CI 단계를 기록했다. [OpenAPI README](../../../packages/schemas/openapi/README.md)
- 최종 생성물로 Python 코드 생성 시험 142개와 Rust 작업 공간 시험 564개가 통과했다(Rust 기존 무시 1개). 별도 매니페스트의 키 순서 보존, 시나리오 API, 온톨로지 실행기 시험도 각각 2개, 4개, 4개 통과했다. 이전 `contracts-*` 태그가 없는 이력에서 `check_compat.sh --latest`는 필드 삭제 자체 시험을 통과했다.
- 시스템 기본 임시 디렉터리로 재실행한 `tools/tests`는 1,806개 통과, 기존 건너뜀 6개였다. `tools/daemon/runner_verify/tests`는 81개 모두 통과했다.
