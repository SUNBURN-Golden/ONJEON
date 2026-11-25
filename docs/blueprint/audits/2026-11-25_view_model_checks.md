# Audit 8 뷰모델·릴리스·계약 스냅샷 검사

공유 계약에 7개 Rust 검사 함수를 추가했다. `ViewLine.refs`는 JSON Schema에서 한 개 이상이어야 한다. `CompareCell.refs`는 제출할 경우 한 개 이상이어야 하고, Rust 검사는 확인된 값·적용 여부·금액을 제공하는 셀에 근거를 요구한다. 확인을 유보한 빈 셀은 근거 없이 표시할 수 있다. 기존 금액 출처 네 종류는 유지한다. 화면의 큰 지급액을 시나리오로 제한하는 규칙은 표시 위치를 아는 호출부에서 적용한다.

| 계약 | 로컬 회귀에서 확인한 규칙 |
|---|---|
| `PlanView` | 어휘 정본에서 생성한 `DiffType::group()`으로 15개 유형과 4개 묶음의 60개 조합을 대조한다. 면책·감액·제외를 비롯한 감소 유형이 다른 묶음에 섞이면 거부한다. 차이 제공 상태·묶음 중복·금액 출처, 가격의 기준과 기준일 또는 미확인 사유, 필요성 요약과 미해결 참조를 검사한다. |
| `CoverageDetail` | 줄의 근거 누락·빈 배열·잘못된 조항 쪽과 값·금액의 출처 오류를 거부한다. 제외 층이 있으면 보장 층 바로 뒤의 두 번째 자리에 있어야 한다. |
| `CompareView` | 비교축마다 상품 열 하나에 셀 하나를 유지한다. 가격을 제공하면 같은 비교 기준 안에서 각 열을 가격 확인·미확인 중 한 곳에 둔다. 셀에 표시하는 사실과 금액의 참조를 검사한다. |
| `EvidenceView` | 요청 참조와 사슬 첫 참조, 단계별 참조 종류를 대조한다. 조항·구획·원본·관측이 구조와 해시 접두부로 이어지는지 검사한다. 인용을 표시하면 조항 참조를 요구한다. |
| `NeedResult` | 이유가 한 건 이상이어야 한다. 사실·기준 평가·사용자 가정·계산·미확인 이유 각각에 맞는 참조를 검사하고, 기준 평가에는 기준 릴리스 참조를 요구한다. |
| `ReleaseManifest` | 정렬된 고유 구성원 ID, SHA-256 형식, 철회 시각과 사유의 짝, 자기 릴리스에 대한 대체 참조 금지를 검사한다. |
| `ContractSnapshot` | 개인 계약·건강 민감도, 적용 판의 근거와 기간, 담보 참조·가입금액·기준일, 사용자 확인의 주체와 시각을 검사한다. 버전 미확정 상태를 허용한다. |

Rust 시험은 일곱 픽스처를 각 검사기에 통과시킨 뒤 위반이 있는 변형을 거부하는지 확인한다. Python 시험은 참조 배열의 제약을 검사하고, 생성된 Rust·TypeScript·Dart 계약은 같은 픽스처에서 검증한다. [Rust 검사](../../../packages/schemas/src/checks.rs) · [Rust 시험](../../../packages/schemas/src/view_model_tests.rs) · [스키마 시험](../../../packages/schemas/codegen/tests/test_schemas.py).

## 로컬 재실행

| 명령 | 결과 |
|---|---|
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | Rust 시험·문서 시험 557개 통과(신규 계약 회귀 15개 포함), 픽스처 재생성용 시험 1개 기본 제외. 내장 Python 시험은 API 39개·계약 142개 통과. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | 생성물 30개 일치. Rust 빌드, TypeScript 5.9.3 타입 검사, Dart 3.13.5 분석·픽스처 왕복 통과. |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api`와 온톨로지 실행기의 `cargo test --locked --offline` | 각각 4개 통과. `ontology_check.py`의 제약·릴리스·금액 자체 시험도 통과. |
| `python3 -m unittest discover -s tools/tests -v` | 1,809개 중 1,803개 통과, 원본 보관소가 필요한 5개와 옛 botocore가 필요한 1개 건너뜀. |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과. |
| `cargo fmt --all -- --check` 및 `cargo clippy --locked --offline --all-targets -- -D warnings` | 통과. |
| `tools/blueprint_counts.py`, `tools/vocab_check.py`, `tools/validation_check.py`(일반 실행·자체 시험), `검증/spec_check.py` | 통과. 검증 자료 변이 40개를 탐지했다. |
| `ONJ_COMPAT_ALL_CLIENTS=1 bash packages/schemas/codegen/check_compat.sh --latest` | 이전 `contracts-*` 태그가 없어 자체 시험 통과. 작업 시작 시점과 직접 대조하면 `ViewLine.refs` 최소 길이는 비호환 변경이며 `CompareCell.refs`는 선택 필드 추가로 보고된다. 계약은 태그 없는 초판 개발 상태다. 버전 상향에는 이 작업의 허용 경로 밖인 루트 `Cargo.lock` 갱신이 필요하다. |

I6과 I9의 증거 범위는 응답 내부의 참조 연결과 보완안 분류다. 실제 원본 조회·좌표 대조, 릴리스 구성원 확인·내용 해시 재계산, 보완안 차이 계산·화면 표시에는 실제 실행 증거가 필요하다. 출시 판정기를 실행한 결과 09 목적 행 20개와 기능 64개가 열린 상태였다. [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
