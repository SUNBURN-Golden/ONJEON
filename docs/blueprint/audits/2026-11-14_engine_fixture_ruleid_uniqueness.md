# Audit 6: fixture rule_id 유일성과 사례 목록 대조

검증일: 2026-11-14. 노드: `audit6-engine-fixture-ruleid-uniqueness`.
BLUEPRINT A1·A5, Q5·Q7, L6, I2·I18, M0 엔진 기반과
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 변경 범위

[공통 하네스](../../../packages/rules-engine/tests/common/mod.rs)의 파일명과
`rule_id.json` 일치 검사는 Audit 5에서 이미 적용돼 있었다. 이번에는 `BTreeMap::entry`의
occupied 분기에서 파일 경로·중복 ID를 포함한 오류를 내고 vacant 분기에서만 삽입한다.
같은 내용의 복사본과 다른 내용을 가진 동일 ID 모두 덮어쓰기 전에 실패한다.
파일명 정렬과 `*.cases.json` 제외 동작은 유지한다.

`kyobo-wholelife-death.cases.json`의 `rule_ids`는 유지하고 검사한다. 이 선택적 필드가
있으면 비어 있지 않은 배열이어야 하며 각 값은 공백만이 아닌 문자열이고 중복이 없어야 한다.
각 사례의 `rule` 또는 기본 `rule_id`로 선택한 규칙 집합이 선언 목록과 정확히 같아야 한다.
목록 밖 선택·선택 규칙 누락·사례 없는 선언을 파일 경로와 함께 거부한다.
공유 파일과 별도 목록을 선언한 추가 파일을 각각 검사하고, 병합 뒤에는 공유 목록으로 다시
검사한다. 추가 사례가 공유 규칙의 사례 누락을 숨기거나 공유 목록 밖 규칙을 추가할 수 없다.
목록·사례 순서와 기존 입력·기대값·규칙 내용 해시는 변경하지 않는다.

[harness_guards.rs](../../../packages/rules-engine/tests/harness_guards.rs)는 기존 7개에
회귀 시험 6개를 추가했다. 정상 두 규칙·기본 선택·역순 목록·추가 사례 보존과
형식·중복·집합 불일치·파일별 검사 및 병합 후 검사를 격리된 fixture로 검증한다.
실제 공유 fixture와 엔진 실행 코드는 변경하지 않았다.

## 실행 증거

Rust 1.98.1을 사용했다. 아래 로그는 로컬 실행 증거이며 원격 CI 결과가 아니다.
전체 검증의 Cargo 빌드와 하네스 격리 크레이트는 이 작업 트리의 `target/`에 두었다.
Python의 온톨로지 시험은 기존 계약대로 저장소 밖의 임시 파일 생성·정리를 검증한다.

| 명령 | 결과·로그 |
|---|---|
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 단위·통합·문서 시험 523개 통과·실패 0·기존 ignored 1개, 내부 Python 39개·129개 통과: [workspace.log](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/workspace.log) |
| `cargo test -p onjeon-rules-engine --locked --offline` | 기본 규칙 상속 검증 보완 후 최종 엔진 단위·통합 257개와 doctest 3개 통과: [engine.log](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/engine.log) |
| `python3 -m unittest discover -s tools/tests -v` | 기본 임시 디렉터리 환경으로 전체 재실행: 1,609개 실행·실패 0·기존 조건부 skipped 6개: [python.log](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/python.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 별도 온톨로지 runner 4개 통과: [ontology-runner.log](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/ontology-runner.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/fmt.log), [clippy.log](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write`·`python3 -I tools/blueprint_counts.py` | §11 단위·통합 257개·doctest 3개 갱신·대조: [갱신](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/counts-write.log), [대조](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/counts.log) |
| `python3 -I tools/blueprint_status.py`·`python3 -I tools/ci/check_product_purpose.py`·`python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 상태 색인·제품 목적·명세 정합성 통과: [상태](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/status.log), [제품 목적](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/product-purpose.log), [명세](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/spec-check.log) |

첫 Python 전체 실행은 `TMPDIR`을 작업 트리 안으로 지정하여 저장소 밖 경로를 요구하는
온톨로지 임시 파일 시험 3개가 실패했다([원래 로그](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/python-in-tree-tmp.log)).
`TMPDIR`·`TEMP`·`TMP`를 해제한 기본 환경에서 해당 파일의
[6개 시험은 모두 통과](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/python-tempfile-recheck.log)했다.
시험 코드나 기존 저장소 밖 임시 파일 정책은 변경하지 않았다.

[음성 대조 스크립트](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/negative_control.py)는
작업 트리 `target/`의 임시 크레이트에서 정상 하네스와 검사 제거 변이를 실행한다.
저장소의 실제 하네스는 바꾸지 않으며 임시 크레이트를 삭제한다.

직접 실행한 `python3 -I packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/negative_control.py`는
종료 코드 0으로 [통과](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/negative-control.log)했다.
각 변이의 내부 Cargo 종료 코드 101은 기대한 결함 검출이다.

| 하네스 상태 | 결과 |
|---|---|
| 정상 | [13개 통과](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/baseline.log) |
| 중복 삽입 검사 제거 | [1개 실패](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/missing-duplicate-guard.log) |
| 파일명 검사 제거 | [2개 실패](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/missing-filename-guard.log) |
| 공유 파일 목록 검사 제거 | [3개 실패](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/missing-shared-inventory-guard.log) |
| 추가 파일 목록 검사 제거 | [2개 실패](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/missing-supplement-inventory-guard.log) |
| 병합 후 공유 목록 검사 제거 | [1개 실패](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/missing-merged-inventory-guard.log) |

[범위 검사](../../../packages/rules-engine/evidence/audit6-fixture-ruleid-uniqueness/scope.log)로
허용 경로·보호 문서·공유 fixture·엔진 실행 코드 불변, 증거 링크와 공백 검사를 확인했다.

## 증명 범위

시험 하네스의 규칙 식별·목록 검사를 보강한 `fixture_only` 로컬 증거다.
실제 전 상품 데이터·승인 규칙 릴리스·상품 및 계약 트윈·소비자 화면·원문 좌표 추적,
P08·P14 전체·첫 출시 완료를 뜻하지 않는다.
commit·push·GitHub 호출은 수행하지 않았다.
