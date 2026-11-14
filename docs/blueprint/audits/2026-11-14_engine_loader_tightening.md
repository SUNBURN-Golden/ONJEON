# Audit 6: 규칙 로더 입력 검증

검증일: 2026-11-14. 노드: `audit6-engine-loader-tightening`.
BLUEPRINT A1·A5, Q5·Q7, L6, I2·I3·I5·I18, M0 엔진 기반과
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정과 구현

작업 시작 시 날짜 파서는 이미 ASCII 숫자·고정 폭 `YYYY-MM-DD`만 허용했고,
로더에는 `rule_id.trim().is_empty()` 검사와 `rule_id` 경로의 오류가 있었다.
두 불변성 doctest도 이미 `compile_fail,E0616`을 명시했으며,
`immutable_rule_doctests`가 stable rustdoc의 실제 진단을 검사하고 있었다.
이 세 실행 경로는 유지하고 기존 회귀 시험과 검사 제거 대조로 재검증했다.

남아 있던 결함은 `example_kind` 무검증과 `serde_json::Value` 파싱 중 중복 객체 키의
마지막 값 덮어쓰기였다. 새 거부 시험을 수정 전에 실행해 4개 실패·정상 대조 2개
통과로 재현했다([before.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/before.log)).

- [로더](../../../packages/rules-engine/src/rule.rs)는 선택적 `example_kind`를 기존
  `synthetic_not_a_real_product`, `real_clause_design_validation`,
  `ontology_case_validation` 문자열로 제한한다. 생략은 허용하고 null·다른 타입·빈 값·
  미지원 값은 `example_kind` 경로로 거부한다. 두 DSL 버전·모든 공개 상태에 적용하며
  `publication_state`와의 새 결합 조건은 만들지 않는다. 태그는 공개 자격을 부여하지 않는다.
- [엄격한 JSON 역직렬화](../../../packages/rules-engine/src/strict_json.rs)는 `Value`에
  저장하기 전에 디코딩한 키의 중복을 검사한다. 최상위·중첩 객체·배열 안의 객체·실행에서
  선택되지 않는 가지에도 적용하며, 같은 값의 반복과 유니코드/따옴표 이스케이프 충돌도
  거부한다. 오류는 `$` 경로, `invalid JSON: duplicate JSON key`, 해당 키·행·열을 포함한다.
  정상 JSON 값·수 표현은 기존 파서와 같고 잘못된 문법·후행 데이터·깊이 제한도 유지한다.
- `Rule::from_json`은 이미 파싱한 `Value`를 받으므로 소실된 중복 키를 알아낼 수 없다.
  외부 JSON 텍스트는 `Rule::from_json_str`로 직접 로드해야 한다. 두 진입점의 의미와
  한계를 API 문서와 [README](../../../packages/rules-engine/README.md)에 명시했다.
  별도 `packages/twin-runtime/src/input_stage.rs`의 `load_rule_artifact`는 일반 `Value`
  선파싱 후 `from_json`을 호출하므로 그 경계의 중복 키 거부까지 증명하지 않는다.
  해당 패키지는 이 노드의 편집 허용 경로 밖이며 변경하지 않았다.
- [loader_tightening](../../../packages/rules-engine/tests/loader_tightening.rs) 6개와
  엄격한 JSON 파서 단위 시험 2개를 추가했다. 기존
  [해시 범위 시험](../../../packages/rules-engine/tests/content_hash_scope.rs)의 객체형
  `example_kind`는 이제 의도적으로 거부되므로, 중첩 `release_id` 해시 검증을 정상 입력
  선언 `inputs.release_id`로 옮겼다. 해시 알고리즘·공유 규칙·골든·고정 해시는 변경하지 않았다.

## 결함을 되살린 대조

[대조 스크립트](../../../packages/rules-engine/evidence/audit6-loader-tightening/negative_control.py)는
작업 트리 안의 임시 크레이트에서 원본 회귀 시험이 통과한 뒤 아래 변이를 각각 검출한다.
실제 실행 소스는 바꾸지 않으며 임시 크레이트는 삭제한다.

| 변이 | 기대한 실패 | 로그 |
|---|---:|---|
| 일반 `Value` 파싱으로 중복 키 덮어쓰기 복원 | 중복 키 회귀 3개 | [duplicate-overwrite](../../../packages/rules-engine/evidence/audit6-loader-tightening/control-duplicate-overwrite.log) |
| `example_kind` 검사 제거 | 잘못된 태그 회귀 1개 | [unchecked-example-kind](../../../packages/rules-engine/evidence/audit6-loader-tightening/control-unchecked-example-kind.log) |
| 빈 ID 검사 제거 | 일반·이스케이프 공백 회귀 2개 | [blank-rule-id](../../../packages/rules-engine/evidence/audit6-loader-tightening/control-blank-rule-id.log) |
| 날짜 ASCII 숫자 검사 제거 | 날짜 리터럴·평가 입력·해시 별칭 회귀 3개 | [signed-dates](../../../packages/rules-engine/evidence/audit6-loader-tightening/control-signed-dates.log) |
| 불변성 doctest 하나를 무관한 타입 오류 `E0425`로 대체 | 진단 검사 1개 | [unrelated-doctest-error](../../../packages/rules-engine/evidence/audit6-loader-tightening/control-unrelated-doctest-error.log) |

마지막 변이는 stable rustdoc 자체의 3개 doctest가 통과해도 통합 시험은 실패함을
확인한다. `compile_fail,E0616` 표기만 믿고 무관한 컴파일 오류를 통과시키지 않는다.
대조의 내부 Cargo 종료 코드 101은 기대한 결함 검출이다.
[요약](../../../packages/rules-engine/evidence/audit6-loader-tightening/negative-control.log)과
[정상 대조](../../../packages/rules-engine/evidence/audit6-loader-tightening/control-baseline.log)를 함께 보존한다.

## 직접 실행한 검증

Rust 1.98.1과 작업 트리 안의 `target/`을 사용했다. 최초 수정 전 재현만 환경의
기존 공유 Cargo 빌드 캐시를 사용했고, 이후 빌드·대조는 작업 트리 안에서 수행했다.
원격 CI 결과를 주장하지 않는다. 로그의 머신별 작업 경로는 표시용으로 치환했다.

| 명령 | 증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --test loader_tightening --test date_format --test identity_evidence --test immutable_rule_doctests --test content_hash_scope --locked --offline` | 집중 회귀 25개 통과: [focused.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/focused.log) |
| `python3 packages/rules-engine/evidence/audit6-loader-tightening/negative_control.py` | 정상 통과·5종 변이 검출: [negative-control.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/negative-control.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 531개 통과·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/workspace.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 runner 시험 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/ontology-runner.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,609개 실행·실패 0·기존 환경 조건에 따른 skipped 6개: [python.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/python.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | [fmt.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/fmt.log)·[clippy.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` | 등록 수 265개·doctest 3개: [counts-write.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/counts-write.log) |
| `python3 -I tools/blueprint_counts.py`·`python3 -I tools/blueprint_status.py` | [counts.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/counts.log)·[status.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/status.log) |
| 제품 목적·명세·온톨로지·어휘·검증 자료 정합성 검사 | [product-purpose.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/product-purpose.log)·[spec-check.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/spec-check.log)·[ontology-check.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/ontology-check.log)·[vocab.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/vocab.log)·[validation.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/validation.log)·[validation-selftest.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/validation-selftest.log) |

최종 검증 명령은 모두 종료 코드 0이다. skipped 6개는 로컬 원본·재현 도구 또는
구버전 botocore가 필요한 기존 조건부 시험이다. 허용 경로·보호 문서·공유 규칙과
고정 해시 불변, 문서 링크·공백 검사는 [scope.log](../../../packages/rules-engine/evidence/audit6-loader-tightening/scope.log)에 기록한다.

## 증명 범위

P08·P14의 엔진 입력 검증과 계산 식별·불변성에 관한 로컬 회귀 증거다. 합성 규칙에
`candidate`·`released`를 지정한 시험도 실제 공개 상품 릴리스를 뜻하지 않는다.
실제 전 상품 데이터·상품/계약 트윈·소비자 화면의 연결, P08·P14 전체 완료나
첫 출시 완료 증거를 대체하지 않는다. 보호 문서·공유 픽스처는 변경하지 않았고,
commit·push·GitHub 호출은 수행하지 않았다.


## Fix round 1: 런타임 경계 재현과 적용 대기

리뷰어의 P1은 재현됐다. `load_rule_artifact`가 일반 `Value`로 먼저 파싱하면
`amount: {"krw": 999999999, "krw": 1}`의 앞 금액이 사라지고 `case-runner`가
`evaluated`, `engine_calls: 1`, 1 KRW를 반환한다. 엔진 단독 검증으로 이 경계를
해결했다고 볼 수 없다.

허용 경로의 엔진에는 공개 `strict_json::from_slice`를 추가했고 `Rule::from_json_str`도
이를 사용한다. 바이트 입력의 중복 선언·중첩 기간·이스케이프 키 충돌·잘못된 UTF-8을
검사하는 단위 시험을 추가했다. 엔진 등록 수는 단위·통합 266개, doctest 3개다.

런타임 소스와 회귀 시험은 이 노드의 명시적 허용 경로 밖이므로 범위 확대를 요청한
상태다. [제안 패치와 검증 안내](../../../tools/evidence/audit6-engine-loader-tightening/fix-round1/README.md)에
수정안과 네 회귀 시험을 보존했다. 작업 트리 안의 임시 크레이트에서 기존 로더가
거부 시험 3개에 실패하고 정상 대조 1개가 통과함을 확인했으며, 제안 패치를 적용한
임시 크레이트에서는 네 시험이 모두 통과했다. 요청 시험은 변조 탐지의 조기 차단으로
가려지지 않도록 해당 바이트를 다시 고정해 무결성 검사가 깨끗하고 체인 연결에
성공했음을 먼저 확인한다. 두 DSL 버전에서 중복 금액·동일 값·이스케이프 충돌·
미선택 가지·최상위 선언·중첩 선언을 엔진 실행 전 거부한다.

**실제 `packages/twin-runtime/`에는 아직 적용하지 않았다. 실행 경로의 P1은 열린
상태이며 제안 패치의 통과를 실제 런타임 해결로 주장하지 않는다.** 편집 범위 승인이
필요한 사안이며 비가역·비용·법률·비밀·운영 결정이 아니므로 `DECISION_REQUIRED.md`는
생성하지 않는다.


이번 라운드 직접 검증(실제 작업 트리, 런타임 패치 미적용):

| 명령 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline` | 269개 통과(문서 시험 포함): [엔진](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-engine.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | 532개 통과·기존 ignored 1개: [작업 공간](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-workspace.log) |
| 기존 5종 결함 복원 대조 | 모두 검출: [대조](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-negative-control.log) |
| `cargo fmt --all -- --check` · `cargo clippy --all-targets --locked --offline -- -D warnings` | 종료 0: [fmt](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-fmt.log) · [clippy](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-clippy.log) |
| 별도 온톨로지 runner `cargo test --locked --offline` | 4개 통과: [runner](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-ontology-runner.log) |
| `python3 -I tools/blueprint_counts.py` · `python3 -I tools/blueprint_status.py` | 종료 0: [counts](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-counts-check.log) · [status](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-status.log) |

Python 전체 시험도 1,609개 실행·실패 0·기존 skipped 6개로 종료했다([Python 로그](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-python.log)). 편집 경로 검사는 [scope](../../../packages/rules-engine/evidence/audit6-loader-tightening/fix-round1-scope.log)에 기록한다.
