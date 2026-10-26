# Audit 2: 숫자 전용 날짜 파싱

기록일: 2026-10-26. 노드: `audit2-engine-parse-date-plus-sign`.

## 발견과 수정

`parse_date("2024-+2-+9")`가 `2024-02-09`로 해석되었다. 형식의 길이와 구분자만 확인한 뒤 Rust 정수 파서에 넘겨 월·일의 선행 `+`를 허용한 것이 원인이다. 수정 전 회귀 시험에서 공통 파서, 규칙 날짜 리터럴 로드, 평가 날짜 입력의 세 경로에서 재현했다.

[date.rs](../../../packages/rules-engine/src/date.rs)는 길이·구분자를 검사한 다음 연·월·일의 모든 바이트가 ASCII 숫자인지 확인한다. 숫자 검사 후 기존 정수 변환·지원 연도·달력 유효성 검사를 수행한다. 부호·공백·문자·비ASCII 숫자를 거부하며 입력을 정규화하지 않는다. 두 DSL 버전의 날짜 리터럴은 기존 `RuleError` 경로로, 평가 입력은 기존 `EvalError::BadInput`으로 거부된다.

## 회귀 시험과 실행 증거

날짜 단위 시험 2개는 감사 예시와 한쪽에만 `+`가 있는 변형, 모든 숫자 위치에 대한 비숫자 대입, 정상 형식·윤일·지원 경계·잘못된 달력 날짜를 검사한다. [date_format.rs](../../../packages/rules-engine/tests/date_format.rs)의 통합 시험 3개는 `rule-0.1`·`rule-0.2`에서 부호가 있는 리터럴의 오류 경로, 부호가 있는 입력의 오류 종류, 정상 날짜의 지급 결과를 확인한다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --offline --lib --test date_format --no-fail-fast` (수정 전) | 종료 코드 101. 단위 시험 1개·통합 시험 2개 실패로 문제 재현: [before.log](../../../tools/evidence/audit2-engine-parse-date-plus-sign/before.log) |
| `cargo test -p onjeon-rules-engine --offline --lib --test date_format` | 단위 시험 9개·통합 시험 3개 통과: [focused.log](../../../tools/evidence/audit2-engine-parse-date-plus-sign/focused.log) |
| `cargo test --all --offline` | 종료 코드 0. Rust 단위·통합·문서 시험 429개 통과·실패 0·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../tools/evidence/audit2-engine-parse-date-plus-sign/workspace.log) |
| `cargo fmt --all -- --check` | 종료 코드 0, 진단 없음: [fmt.log](../../../tools/evidence/audit2-engine-parse-date-plus-sign/fmt.log) |
| `cargo clippy --all-targets --offline -- -D warnings` | 종료 코드 0: [clippy.log](../../../tools/evidence/audit2-engine-parse-date-plus-sign/clippy.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·필수 시험 ID 등록 정합성 통과: [product-purpose.log](../../../tools/evidence/audit2-engine-parse-date-plus-sign/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과: [spec-check.log](../../../tools/evidence/audit2-engine-parse-date-plus-sign/spec-check.log) |

## 제품 목적과 한계

BLUEPRINT A2·A5, Q2·Q5, L6, M0 엔진 기반 및 [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08의 시나리오 계산을 뒷받침하는 날짜 입력 검증이다. 합성 규칙을 사용한 로컬 회귀 증거이며, 실제 릴리스의 감액·면책 경계일 시나리오 기록, 화면 연결 또는 출시 완료를 주장하지 않는다.
