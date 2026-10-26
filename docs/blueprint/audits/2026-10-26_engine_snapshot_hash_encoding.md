# Audit 2: 입력 스냅샷 해시의 정규 JSON 인코딩

대상 노드: `audit2-engine-snapshot-hash-encoding` (2026-10-26).

기존 `input_snapshot_hash`는 `Value::Display`의 Rust Debug 문자열을
`이름=값\n`으로 연결했다. 예를 들어 bool 입력 `{a: true, b: false}`와
`{"a=true\nb": false}`는 서로 다른 스냅샷인데도 같은 바이트를 해시했다.
새 구현은 평가에 사용된 타입 있는 값 전체를 정규 JSON으로 해시한다.

## 인코딩 계약

- SHA-256 입력은 compact UTF-8 JSON이며 끝 개행·BOM은 없다.
- 최상위 객체의 키는 모든 선언 입력 이름이다. 모든 객체 키는 `BTreeMap`으로
  재귀 정렬한다. `serde_json/preserve_order` 설정에 의존하지 않는다.
- 값은 `{"type":"bool","value":true}` 같은 태그 객체다. 태그는
  `bool`, `int`, `money`, `date`, `string`, `class_money_list`, `unknown`이다.
  내부 값 `money_range`·`rate`도 같은 방식으로 직렬화한다.
- 누락과 명시적 `null`은 기존처럼 `{"type":"unknown"}`으로 통일한다.
  bool·정수·금액·문자열은 서로 다른 타입이며 미확인은 false·0·빈 문자열과 다르다.
- 날짜는 평가기의 1970-01-01 기준 일수다. 목록은 입력 순서를 유지하며
  각 항목의 `class`·`krw`를 보존하고 미확인 금액은 JSON `null`로 표현한다.
- 문자열과 입력 이름은 JSON 이스케이프를 사용하고 Unicode 정규화를 하지 않는다.
  따라서 `=`·개행·따옴표·역슬래시는 객체나 항목 경계를 만들 수 없다.
- 규칙 내용 해시의 정규화 도구를 공통 모듈로 옮겨 재사용한다. 규칙 해시에만
  최상위 `release_id` 제외를 적용한다. 같은 이름의 **입력은 해시에서 제외하지 않는다**.

새 형식은 기존 스냅샷 해시와 호환되지 않는다. 결과의 `engine_version`을
`0.1.0+snapshot-json-1`로 구별한다. 기존 계산을 재현할 때는 기록된 엔진 버전을
사용해야 한다. 규칙 내용 해시·지급 판정·trace의 골든은 그대로 유지한다.
공유 fixture는 수정하지 않고, 현재 입력 해시는 엔진 소유
[`fixture-rule-001.snapshot-json-1.hashes.json`](../../../packages/rules-engine/tests/fixtures/fixture-rule-001.snapshot-json-1.hashes.json)에 별도 고정했다.
이 값들은 Python `json`·`hashlib`로 독립 계산했다.

## 검증

[`snapshot_hash.rs`](../../../packages/rules-engine/tests/snapshot_hash.rs)는
두 DSL 버전의 구분자 충돌 회귀, 특수 이름(`release_id` 포함),
모든 입력 타입과 i64 경계, 한국어·제어 문자·Unicode,
누락/null 동등성, 객체 키 순서 독립, 목록 항목·순서 보존을 검사한다.
전체 타입을 포함한 수기 정규 JSON 바이트의 SHA-256과도 대조한다.
공통 모듈 단위 시험은 중첩 구조체의 키 정렬과 내부 타입 태그를 고정한다.

로컬 실행 증거는
[`evidence/audit2-snapshot-hash-encoding`](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/)에 보관한다.
실행 결과는 아래 표에 기록한다. 원격 CI 결과가 아니다.

Rust 1.98.1에서 실행했다([toolchain.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/toolchain.log)).

| 명령·대조 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --test snapshot_hash --test golden --offline` | 회귀 6개·골든 7개 통과 ([focused.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/focused.log)) |
| 기존 `snapshot_hash` 함수만 임시 복원 후 새 회귀 시험 실행 | 4개 통과·2개 예상 실패: 구분자 충돌 재현 및 정규 JSON 해시 불일치 검출. 실행 후 수정 소스를 바이트 단위로 복원 ([legacy-negative-control.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/legacy-negative-control.log)) |
| `cargo test --all --offline` | Rust 단위·통합·문서 시험 434개 통과·실패 0·기존 ignored 1, 내부 Python 시험 39개·129개 통과 ([workspace.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/workspace.log)) |
| `cargo fmt --all -- --check` | 통과 ([fmt.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/fmt.log)) |
| `cargo clippy --all-targets --offline -- -D warnings` | 통과 ([clippy.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/clippy.log)) |
| `python3 -m unittest discover -s tools/tests -v` | 915개 실행·실패 0·기존 skip 6 ([python-tests.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/python-tests.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 44/44·존재 검사 72/72 통과 ([spec-check.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/spec-check.log)) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·G12 시험 ID 정적 검사 통과 ([product-purpose.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/product-purpose.log)) |

허용 경로·보호 파일 보존·추가 문서 링크·diff 공백 검사는
[final-checks.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/final-checks.log)에 기록한다.

## Fix round 1: main 병합 충돌 해결

`09_제품목적_대응표.md`의 같은 위치에 추가된 입력 스냅샷 해시 검증(P08·P14)과
숫자 전용 날짜 파싱 검증(P08)을 모두 보존했다. 정규 JSON 해시 구현·골든과
main의 날짜 파싱 수정·회귀 시험을 함께 유지했다. 커밋·푸시 없이 충돌만 해결했으며
병합 커밋은 감독자가 수행한다.

병합된 작업 트리에서 Rust 1.98.1로 다시 실행한 로컬 증거는
[`round1/`](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/)에 둔다.

| 명령·대조 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --test snapshot_hash --test golden --test date_format --offline` | 해시 6개·골든 7개·날짜 3개 통과 ([focused.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/focused.log)) |
| `cargo test --all --offline` | Rust 시험 439개 통과·실패 0·기존 ignored 1, 내부 Python 시험 39개·129개 통과 ([workspace.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/workspace.log)) |
| `cargo fmt --all -- --check` | 통과 ([fmt.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/fmt.log)) |
| `cargo clippy --all-targets --offline -- -D warnings` | 통과 ([clippy.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/clippy.log)) |
| `python3 -m unittest discover -s tools/tests -v` | 915개 실행·실패 0·기존 skip 6 ([python-tests.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/python-tests.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 44/44·존재 72/72 통과 ([spec-check.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/spec-check.log)) |
| `python3 -I tools/ci/check_product_purpose.py` | 통과 ([product-purpose.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/product-purpose.log)) |
| `python3 tools/vocab_check.py` | 49축·269값 통과 ([vocabulary.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/vocabulary.log)) |
| `python3 tools/validation_check.py` / `--selftest` | 내부 정합성·변조 38개 검출 통과 ([validation.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/validation.log), [validation-selftest.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/validation-selftest.log)) |

충돌 인덱스 해소·두 감사 링크 보존·허용 경로·보호 파일·문서 링크·diff 공백 검사는
[final-checks.log](../../../packages/rules-engine/evidence/audit2-snapshot-hash-encoding/round1/final-checks.log)에 기록한다.
main에서 가져온 날짜 파싱 증거 로그 두 개의 끝 빈 줄만 제거해 공백 검사도 통과시켰다.

## 제품 목적과 완료 범위

BLUEPRINT A5, Q5·Q7, L6, I18, M0 엔진 유지보수와 연결된다.
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의
P08(시나리오 재현)·P14(입력부터 근거까지 추적)에 필요한 기반 검증이다.
합성 규칙 회귀 증거이며 실제 상품·소비자 화면·첫 출시 완료를 주장하지 않는다.
