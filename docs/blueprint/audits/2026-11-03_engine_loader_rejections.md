# Audit 4: 기존 엔진 로드 거부 조건의 회귀 시험

대상 노드: `audit4-engine-loader-rejection-tests` (2026-11-03).

감리 지적은 이미 구현된 로드 단계 거부 조건에 직접 시험이 없다는 것이다.
`packages/rules-engine/src/rule.rs`의 검사를 유지하고
[`loader_rejections.rs`](../../../packages/rules-engine/tests/loader_rejections.rs)에
13개 회귀 시험을 추가했다. 로더·평가기·기존 규칙·골든 파일의 실행 동작은 변경하지 않았다.

## 검증 범위

JSON 값(`Rule::from_json`)과 JSON 텍스트(`Rule::from_json_str`)에서 같은 거부 경로와
사유를 확인한다. 공통 문법은 `rule-0.1`·`rule-0.2` 모두 검사하며, 확장 전용 문법은
0.2에서 상세 검증하고 0.1의 버전 거부를 별도로 검사한다.
식 오류는 `if: false`의 미선택 `then` 가지에서도 거부되어야 한다.

| 영역 | 직접 검증한 거부 조건·정상 대조 |
|---|---|
| 문서·메타데이터 | JSON 구문 오류, 비객체 문서, 필수 키 누락·타입, 미지원 최상위 키, calendar·공개 상태·스키마·unknown 정책, 빈 버전·릴리스 ID, 공개 가능 규칙의 누락/null 릴리스, 잘못된 contract_effect. calendar 생략·정상 릴리스는 허용 |
| 선언·근거 | inputs 비객체·미지원/비문자열 입력 타입(미사용 입력도 포함), evidence_refs 비배열·비문자열 항목 |
| 식·리터럴 | null·배열·빈/복수 키 연산 객체, if 필수 키 누락·추가 키, 음수/실수/문자열/정수 범위 초과 krw, 잘못된 rate·input. 0·i64::MAX 금액과 정상 요율은 허용 |
| 인자 수 | all/any 1~64, add/min/max 2~64, 비교·상한·곱셈·비례·분배·날짜·구간표의 고정 인자 수. 비배열·하한 미달·상한 초과 거부, 정상 하한 및 가변 연산 64개 허용 |
| 반올림 | multiply_rate·pro_rata·divide_count의 비객체 파라미터·누락/미지원/잘못된 타입의 rounding·unit·추가 키. 허용 모드 5개 × 단위 4개를 모두 로드·평가 |
| 날짜 | days_between 포함 플래그의 누락·비불리언·추가 키, date_add 기간 타입·미지원 단위·잘못된 month_end. 포함 플래그 4조합·정상 날짜 식 로드·평가 |
| 구간표 | 비배열·0/65개 구간·잘못된 행·범위를 넘는 연수·음수 요율·비객체/비문자열 boundary. 1/64개 구간·300년 경계·두 boundary 허용 |
| 목록·버전 | max_over 미선언/비목록/잘못된 인자, 목록 비교 6종 거부. 확장 연산 6개의 버전 관문을 입력 선언 오류와 독립적으로 확인하고 class_money_list·contract_effect의 0.1 거부도 검사 |

정상 대조는 두 로드 진입점의 source JSON·내용 해시와 전체 평가 결과 바이트가 같음을
확인한다. 기존 `loader_and_arith`·`rule_02`·`static_types`·`identity_evidence` 등의
시험도 유지하며 기존 범위를 대체하지 않는다.

## 변이 검출 증거

[`negative_control.py`](../../../packages/rules-engine/evidence/audit4-loader-rejections/negative_control.py)는
이 worktree의 `target/` 아래 임시 크레이트에 소스와 새 시험만 복사한다.
정상 로더는 13개 모두 통과하고, 다음 검사를 각각 독립적으로 완화하면 지정 회귀 시험이
컴파일 후 실패한다(종료 코드 101, `0 passed; 1 failed`). 원본 소스는 수정하지 않는다.

1. Asia/Seoul 제한 제거.
2. 빈 release_id 허용.
3. 반올림 파라미터 추가 키 허용.
4. 반올림 단위 2 허용.
5. 날짜 포함 플래그 추가 키 허용.
6. 연산 인자 수 상한 제거.
7. 구간표 64개 상한 제거(65행 자체는 정상 오름차순).
8. 연산 객체의 복수 키 허용.
9. 0.2 연산의 버전 관문 제거.

실행 요약: [negative-control.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/negative-control.log).
개별 `control-*.log`도 같은 디렉터리에 보존한다.

## 실행 결과

로컬 Rust 1.98.1, 오프라인 의존성으로 검증했다. 원격 CI 결과가 아니다.
실행 로그: [`audit4-loader-rejections`](../../../packages/rules-engine/evidence/audit4-loader-rejections/).

| 명령·검사 | 결과·증거 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test loader_rejections --test readme_test_table` | 새 시험 13개·README 정합성 5개 통과: [focused.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/focused.log) |
| `python3 -I packages/rules-engine/evidence/audit4-loader-rejections/negative_control.py` | 정상 13개 통과·독립 변이 9개 모두 검출: [negative-control.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/negative-control.log) |
| `cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 491개 통과·실패 0·기존 ignored 1: [workspace.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/workspace.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 실행기 시험 3개 통과: [ontology.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/ontology.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/ontology/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1,341개 실행·실패 0·기존 skip 6: [python-tests.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/python-tests.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 통과: [fmt.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` 후 읽기 검사 | 엔진 등록 수 226개·doctest 3개 일치: [counts-write.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/counts-write.log), [counts.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/counts.log) |
| `python3 -I tools/blueprint_status.py`·`python3 -I tools/ci/check_product_purpose.py` | 결정 색인·P01~P19 작업 연결 검사 통과: [status.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/status.log), [product-purpose.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/product-purpose.log) |
| 설계 묶음·온톨로지 검사 | 통과: [spec-check.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/spec-check.log), [ontology-check.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/ontology-check.log) |
| 어휘·검증 자료·변조 자체 시험 | 통과: [vocab.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/vocab.log), [validation.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/validation.log), [validation-selftest.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/validation-selftest.log) |

위 명령은 모두 종료 코드 0이다. 음성 대조 내부의 Cargo 실패는 기대한 결함 검출이다.
Rust 작업 공간에는 Python 39개·129개를 실행하는 통합 검사도 포함된다.
허용 경로·보호 파일·로더/평가기/공유 픽스처 보존·로컬 링크·공백 검사는
[scope.log](../../../packages/rules-engine/evidence/audit4-loader-rejections/scope.log)에 기록했다.
commit·push·GitHub 호출은 수행하지 않았다.

## 제품 목적과 한계

BLUEPRINT A2·A5, Q2·Q5·Q7, L6, I2·I4·I5, M0 엔진 유지보수 및
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의
P08(시나리오 계산)·P14(규칙·근거 식별)의 기반 검증이다.
시험은 `fixture_only` 합성 규칙이며 실제 상품 릴리스·소비자 화면·원문 좌표 사슬이나
P08·P14 전체·첫 출시 완료 증거를 대신하지 않는다. 운영·법률·비용 결정은 변경하지 않았다.
