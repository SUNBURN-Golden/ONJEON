# Audit 5: 빈 규칙 ID와 공백 ID 재검증

검증일: 2026-11-09. 노드: `audit5-engine-validate-rule-id`.
BLUEPRINT A1·A5, Q5·Q7, L6, I2·I18, M0 엔진 기반과
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정과 변경

감사 지적은 `rule_id`가 빈 문자열이나 공백이어도 로드되어 결과의 식별자가 비게 된다는
것이다. 작업 시작 시 [로더](../../../packages/rules-engine/src/rule.rs)에는 이미
`rule_id.trim().is_empty()` 검사와 `rule_id` 경로의 `must not be empty` 오류가 있었다.
[Audit 2 수정](2026-10-26_engine_empty_ids_evidence.md)과 기존 회귀 시험을 확인했다.
`from_json_str`도 JSON 파싱 후 `from_json`을 호출하므로 같은 검증을 거친다.

실행 코드는 변경하지 않았다. 기존 검증이 감사 사례를 차단함을 재검증하고
[identity_evidence.rs](../../../packages/rules-engine/tests/identity_evidence.rs)를 보강했다.

- 기존 빈 ID 시험에 수직 탭·폼 피드, NEL·NBSP, 줄·문단 구분자, 좁은 NBSP·중간 수학
  공백을 추가했다. 빈 문자열·ASCII 공백·전각 공백도 계속 거부한다.
- 새 시험은 원시 JSON의 `\u0020`, `\t\r\n`, `\u00a0\u2003\u3000`을 실제로
  디코딩한 뒤 두 로더가 `rule_id` 경로와 오류 메시지를 보존하며 거부하는지 확인한다.
- 새 정상 대조 시험은 ASCII·한글·앞뒤 공백을 포함한 비어 있지 않은 ID가 원본 JSON,
  접근자, 지급 가능·지급 불가·판정 불가 결과와 직렬화에 그대로 남는지 검사한다.
  판정 불가는 자격 입력의 null·키 누락을 각각 검사한다. 재로딩 후 결과 전체 바이트가
  같고, ID의 앞뒤 공백을 제거하면 내용 해시가 달라지는지도 확인한다.

모든 ID 검사는 두 DSL 버전(`rule-0.1`, `rule-0.2`)·세 공개 상태
(`fixture_only`, `candidate`, `released`)·두 공개 로더에 적용한다.
정상 ID를 trim하거나 새 ID 형식 제한을 도입하지 않았다. 공유 fixture·골든값은 유지한다.

[음성 대조 스크립트](../../../packages/rules-engine/evidence/audit5-validate-rule-id/negative_control.py)는
작업 트리 안의 임시 크레이트에서 정상 로더로 7개 시험이 통과하는지 확인한다. 이어
`rule_id`의 빈 값 검사만 제거하면 일반 공백·이스케이프 공백 시험 2개가 실패하고
나머지 5개가 통과하는지 검사한다. 실제 로더는 변경하지 않으며 임시 크레이트는 삭제한다.

## 직접 실행한 검증

Rust 1.98.1과 작업 트리 전용 `CARGO_TARGET_DIR`를 사용했다. 로컬 실행 증거이며
원격 CI 결과를 주장하지 않는다. 로그는
[검증 디렉터리](../../../packages/rules-engine/evidence/audit5-validate-rule-id/)에 둔다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --test identity_evidence --locked --offline` | 7개 통과·실패 0: [focused.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/focused.log) |
| `python3 -I packages/rules-engine/evidence/audit5-validate-rule-id/negative_control.py` | 정상 7개 통과, 검증 제거 시 2개 실패로 결함 검출: [요약](../../../packages/rules-engine/evidence/audit5-validate-rule-id/negative-control.log), [정상](../../../packages/rules-engine/evidence/audit5-validate-rule-id/control-baseline.log), [변이](../../../packages/rules-engine/evidence/audit5-validate-rule-id/control-missing-guard.log) |
| `python3 -I tools/blueprint_counts.py --write` | §11 엔진 등록 수 234개·doctest 3개 반영: [counts-write.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/counts-write.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 499개 통과·실패 0·기존 ignored 1개. 내부 Python 시험 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/workspace.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 온톨로지 runner 시험 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/ontology-runner.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/clippy.log) |
| `python3 -I tools/blueprint_counts.py`·`python3 -I tools/blueprint_status.py` | 등록 수·결정 색인 일치: [counts.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/counts.log), [status.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/status.log) |
| `python3 -I tools/ci/check_product_purpose.py`·`python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 제품 목적·명세 정합성 통과: [product-purpose.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/product-purpose.log), [spec-check.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/spec-check.log) |
| `python3 -m unittest discover -s tools/tests -v` | 전체 1,403개 실행·실패 0·skipped 6개: [python.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/python.log) |

모든 최상위 검증 명령은 종료 코드 0이다. 음성 대조의 내부 Cargo 실패(101)는 기대한
결함 검출이다. [scope.log](../../../packages/rules-engine/evidence/audit5-validate-rule-id/scope.log)에
허용 경로·보호 문서·실행 코드·공유 fixture 불변, 감사 문서 링크와 공백 검사를 기록한다.
commit·push·GitHub 호출은 수행하지 않았다.

## 증명 범위

P08·P14의 엔진 기반과 I2 결과 식별의 로컬 회귀 증거다. 합성 규칙에 `candidate`·
`released` 상태를 지정해 검증할 뿐 실제 공개 상품 릴리스가 아니다. 실제 전 상품
데이터·소비자 화면·P08·P14 전체 완료·첫 출시 완료 증거를 대체하지 않는다.
