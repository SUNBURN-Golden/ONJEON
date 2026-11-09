# Audit 5: 엔진 시험 하네스의 규칙 식별·사례 키 검증

검증일: 2026-11-10. 노드: `audit5-engine-test-harness-guards`.
BLUEPRINT A1·A5, Q5·Q7, L6, I2·I18, M0 엔진 기반과
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 변경과 회귀 범위

[공통 하네스](../../../packages/rules-engine/tests/common/mod.rs)는 규칙을 ID 맵에
넣기 전에 파일명이 정확히 `rule_id.json`인지 검사한다. 다른 파일명으로 같은 ID를
추가하면 덮어쓰기 전에 실패한다. 규칙 파일을 정렬하여 진단 순서를 고정한다.
오류에는 파일 경로와 규칙 ID를 남긴다. `*.cases.json`은 규칙 로드 대상에서 제외한다.

공유 사례와 엔진 소유 추가 사례 모두 로드 시점에 사례 키를 검사한다.
공통 허용 키는 `id`·`note`·`expect`이며, 합성 사례는 `inputs`, `base`가 있는
실제 조항 사례는 `rule`·`set`을 추가로 허용한다. `Set` 오타나 형식에 맞지 않는
`inputs`/`set`은 파일 경로·사례 인덱스·ID·잘못된 키를 포함한 오류로 거부한다.
실제 조항의 `set`이 객체가 아닌 경우도 기본 입력으로 조용히 대체하지 않고 거부한다.
`set` 생략·빈 객체, null 값 덮어쓰기, 설명·규칙 선택 메타데이터는 유지한다.

[harness_guards.rs](../../../packages/rules-engine/tests/harness_guards.rs)의 7개 시험은
격리된 임시 fixture 디렉터리에서 실제 공통 로더를 호출한다. 파일명 불일치 단독,
같은 ID를 가진 유효 규칙 두 개의 파일명 순서 양쪽, 공유·추가 사례와 두 입력 형식의
알 수 없는 키, 비객체 `set`, 정상 로드·입력 보존을 검증한다.
기존 공유 fixture·골든 기대값과 엔진 실행 코드는 변경하지 않았다.

[음성 대조 스크립트](../../../packages/rules-engine/evidence/audit5-harness-guards/negative_control.py)는
작업 트리 안의 임시 크레이트에서 정상 7개 통과를 확인한 뒤, 파일명 검사만 제거하면
2개 시험이 실패하고 사례 검사 호출만 제거하면 3개 시험이 실패하는지 확인한다.
저장소 하네스를 변경하지 않으며 임시 크레이트는 삭제한다.

## 직접 실행한 검증

Rust 1.98.1을 사용했다. 최종 검증의 Cargo 빌드·임시 파일은 이 작업 트리의
`target/`에 두었다. 아래는 로컬 실행 증거이며 원격 CI 결과가 아니다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --test harness_guards --test fixture_supplements --test real_clauses --test golden --locked --offline` | 30개 통과·실패 0: [focused.log](../../../packages/rules-engine/evidence/audit5-harness-guards/focused.log) |
| `python3 -I packages/rules-engine/evidence/audit5-harness-guards/negative_control.py` | 정상 7/7, 파일명 검사 제거 시 2개 실패, 사례 검사 제거 시 3개 실패: [요약](../../../packages/rules-engine/evidence/audit5-harness-guards/negative-control.log), [정상](../../../packages/rules-engine/evidence/audit5-harness-guards/control-baseline.log), [파일명 변이](../../../packages/rules-engine/evidence/audit5-harness-guards/control-missing-filename-guard.log), [사례 변이](../../../packages/rules-engine/evidence/audit5-harness-guards/control-missing-case-guards.log) |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 512개 통과·실패 0·기존 ignored 1개, 내부 Python 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit5-harness-guards/workspace.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,403개 실행·실패 0·기존 조건부 skipped 6개: [python.log](../../../packages/rules-engine/evidence/audit5-harness-guards/python.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 온톨로지 runner 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit5-harness-guards/ontology-runner.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit5-harness-guards/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit5-harness-guards/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write`·`python3 -I tools/blueprint_counts.py` | §11 등록 수 247개·doctest 3개 갱신·대조: [갱신](../../../packages/rules-engine/evidence/audit5-harness-guards/counts-write.log), [대조](../../../packages/rules-engine/evidence/audit5-harness-guards/counts.log) |
| `python3 -I tools/blueprint_status.py`·`python3 -I tools/ci/check_product_purpose.py`·`python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 상태 색인·제품 목적·명세 정합성 통과: [상태](../../../packages/rules-engine/evidence/audit5-harness-guards/status.log), [제품 목적](../../../packages/rules-engine/evidence/audit5-harness-guards/product-purpose.log), [명세](../../../packages/rules-engine/evidence/audit5-harness-guards/spec-check.log) |

음성 대조 내부 Cargo 종료 코드 101은 기대한 결함 검출이다. 최상위 검증 명령은
모두 종료 코드 0이다. [scope.log](../../../packages/rules-engine/evidence/audit5-harness-guards/scope.log)에
허용 경로·보호 문서·엔진 실행 코드·공유 fixture 불변, 감사 문서 링크와 공백 검사를 기록한다.

## 증명 범위

시험 하네스의 조용한 규칙 누락·잘못된 사례 실행을 차단하는 로컬 회귀 증거다.
`fixture_only` 검증이며 실제 전 상품 데이터, 승인 데이터에서 상품 트윈으로의 연결,
소비자 화면·원문 좌표 추적, P08·P14 전체 완료·첫 출시 완료 증거를 대체하지 않는다.
commit·push·GitHub 호출은 수행하지 않았다.
