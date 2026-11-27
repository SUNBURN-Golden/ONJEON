# Audit 8 공유 어휘 메타데이터 생성

`audit8-codegen-drops-screen-ko`의 회귀 증거다. `vocabulary.json`의 값별 `screen_ko`와 `deprecated_aliases`, 수집 상태 `maps_to`, `diff_type`의 `group`을 공유 Rust·TypeScript·Dart 패키지에서 조회할 수 있다. 화면 문구의 `null`과 별칭 목록의 순서를 보존한다. 디코더는 정본 코드만 받으며 직렬화는 같은 코드를 내보낸다. 기존 Rust `DiffType::group()`의 대응은 TypeScript와 Dart에도 생성한다. [조회 API](../../../packages/schemas/README.md#화면-문구와-어휘-메타데이터)

모바일 공통 빈 화면과 내 정보의 가입내역 표시는 `PolicyHoldingsStatus.screenKo`를 읽는다. 빈 화면 위젯 시험은 다섯 문구를 문자열 단위로 확인하고, 가입내역 미확인 상태에 본인 응답으로 확인된 보험 없음 문구가 표시되지 않는지 검사한다. [위젯 시험](../../../apps/mobile/test/states_test.dart) · [경로 시험](../../../apps/mobile/test/routing_test.dart)

시나리오 API는 `CalculationIssueCode::screen_ko()`를 읽어 계산 보류 설명을 구성한다. 분모가 0인 공개·개인 시나리오 응답의 문구를 정본과 대조하고, 입력이 필요한 응답과 구분되는지 확인했다. [시나리오 회귀 시험](../../../services/scenario-api/tests/scenario.rs)

정본 사본에서 문구·별칭·매핑·그룹을 각각 바꾸고 수집 매핑을 생략해 보았다. 각 변경은 세 언어의 어휘 생성물에만 반영된다. JSON Schema와 OpenAPI 생성물의 바이트를 함께 대조했다. [생성기 회귀 시험](../../../packages/schemas/codegen/tests/test_schemas.py)

| 로컬 실행 | 결과 |
|---|---|
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 31개 생성물 일치. Rust 빌드, TypeScript 5.9.3 타입 검사와 Node 런타임 시험 26개, Dart 3.13.5 분석 및 픽스처 왕복 통과. TypeScript가 정본의 50개 축·271개 값에 대해 코드와 메타데이터를 대조하고 축별 과거 표기의 디코딩을 거부했다. Dart는 `display_status`의 문구와 별칭, `host_access`의 매핑, `diff_type`의 그룹을 정본과 대조했다. TypeScript의 `PlanView` 픽스처와 Dart의 `DiffType` 값에서 그룹 문구를 조회했다. |
| 컴파일한 TypeScript 작업용 사본의 메타데이터를 한 필드씩 변조한 뒤 Node 회귀 시험 실행 | 문구를 `null`로 바꾸거나 별칭을 빠뜨리면 `display_status.input_missing`, 수집 매핑을 바꾸면 `host_access.not_checked`, 그룹을 바꾸면 `diff_type.gain_coverage`에서 실패했다. 네 변조가 각각 종료 코드 1을 냈다. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` | 이전 `contracts-*` 태그 부재를 보고했고 필드 삭제 자체 시험을 통과했다. |
| `ONJ_COMPAT_ALL_CLIENTS=1 python3 -I -m unittest discover -s packages/schemas/codegen/tests -v` | 143개 통과. 합성 태그의 세 언어 호환 탐침과 메타데이터 변경의 재생성 시험을 포함한다. |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 작업 공간 566개 통과, 기존 무시 1개. 별도 매니페스트의 키 순서, 시나리오 API, 온톨로지 실행기 시험은 각각 2개, 4개, 4개 통과. `cargo fmt --all -- --check`와 Clippy도 통과했다. |
| `flutter analyze --no-pub`, `flutter test --no-pub`, `dart run tool/krw_lint.dart` (`apps/mobile/`, Flutter 3.47.7) | 분석 및 금액 연산 lint 통과. 가입내역 문구·경로를 포함한 위젯 시험 103개 통과. |
| `python3 -m unittest discover -s tools/tests -v` | 기본 시스템 임시 디렉터리로 실행해 1,806개 통과, 기존 건너뜀 6개. |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과. |
| `python3 tools/vocab_check.py`, `python3 -I tools/ci/check_product_purpose.py` | 정본·생성 문서와 P01~P20 작업·시험 ID 연결 검사 통과. |

P08·P10·P12·P15·P19의 출시 완료에는 실제 릴리스 상품과 계약의 계산·비교, 화면 상태별 캡처와 이해도 시험 증거가 필요하다. [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)
