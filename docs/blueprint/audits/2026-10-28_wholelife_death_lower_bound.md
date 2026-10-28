# Audit 3: 종신보험 사망 보장개시일 하한

노드: `audit3-wholelife-death-lower-bound`. 기록일: 2026-10-28.

## 상태: 수정 패치 검증 완료, 원본 반영 대기

요청된 두 규칙과 골든 해시 파일은 노드의 허용 경로 목록에 포함되지 않는다.
따라서 원본 파일은 변경하지 않았으며 경로 허용 확인을 요청했다.
**발견 사항은 현재 작업 트리에서 아직 해결되지 않았다.**

[준비된 패치](../../../tools/evidence/audit3-wholelife-death-lower-bound/fixture-fix.patch)는
두 규칙의 `eligibility.all`에 `gte(death_date, coverage_start_date)`를 추가하고,
변경된 두 규칙의 정규 JSON SHA-256을 기존 골든 해시 파일에 갱신한다.
규칙별 계약 전 사망(2025-01-01 사망 / 2026-01-01 계약), 계약일과 다른
보장개시일의 전날·당일·다음 날, 보장개시일 `null` 사례를 엔진 소유 표에
추가했다. 총 10개다. 하한은 당일을 포함하며, 보장개시일 미확인은
`unknown`·`undetermined`와 `missing_inputs=[coverage_start_date]`를 기대한다.

## 실행 증거

로그: [엔진 증거 디렉터리](../../../packages/rules-engine/evidence/audit3-wholelife-death-lower-bound/).

| 실행 | 결과 |
|---|---|
| 원본 규칙 + 추가 사례, `cargo test -p onjeon-rules-engine --test real_clauses every_real_clause_case_matches` | 의도한 실패. 두 규칙에서 계약 전·보장개시 전날·개시일 미확인 6개 오판을 재현. `before.log` |
| 원본 작업 트리 `cargo test --all` | 실패. 변이 시험이 원본 규칙의 계약 전 사망 사례 실패를 감지. `workspace-before.log` |
| 허용 경로 안의 임시 복사본에만 패치 적용 후 엔진 `cargo test -- --nocapture` | 196개 통과(문서 시험 3개 포함), 실패 0. 실제 조항 사례 115개(공유 47 + 엔진 경계 68), 생성 변이 342개 생존 0, 두 규칙의 새 해시 고정 검사 통과. `candidate-tests.log` |
| `cargo fmt --all -- --check` | 통과. `format.log` |
| `python3 tools/vocab_check.py` | 통과. `vocabulary.log` |
| `python3 tools/validation_check.py` 및 `--selftest` | 통과. `validation.log`, `validation-selftest.log` |
| 설계 묶음 `spec_check.py` | 기계 검사 44/44, 존재 검사 72/72 통과. `design-specs.log` |

임시 복사본은 엔진 코드·사례와 공유 규칙을 복사하고 문서·스키마를 원본에
읽기 연결했다. 별도 Cargo 작업공간·대상 디렉터리에서 시험한 뒤 삭제했다.
이 실행은 원본 작업 트리의 전체 시험 통과를 뜻하지 않는다.

## Fix round 1 재검증

2026-10-28 원본 작업 트리에서 다시 실행했다. 준비된 패치는
`git apply --check`를 통과하고 두 골든 해시를 독립적으로 재계산해
패치 값과 일치함을 확인했다. 원본 파일 변경은 여전히 허용 경로 예외
응답을 기다리고 있다. 규칙을 바꾸지 않고 사례를 무시하거나 엔진에
상품별 조건을 숨겨 추가하는 방식으로 시험을 통과시키지 않는다.

| 실행 | 결과 |
|---|---|
| `cargo test -p onjeon-rules-engine --test real_clauses every_real_clause_case_matches -- --nocapture` | 실패. 기존과 같은 6개 오판 재현. `fix-round1-before.log` |
| `cargo test --all` | 실패. `generic_mutants_are_killed_on_every_rule`이 `w39_accident_before_contract` 원본 규칙 실패를 감지. `fix-round1-workspace.log` |
| `cargo clippy --all-targets -- -D warnings` | 통과. `fix-round1-clippy.log` |
| `cargo fmt --all -- --check` | 통과 |
| `python3 tools/validation_check.py`, `python3 tools/vocab_check.py` | 통과 |
| `python3 tools/validation_check.py --selftest` | 38개 변조 검증 통과. `fix-round1-validation-selftest.log` |
| `python3 -I tools/blueprint_counts.py` | 통과. Rust 시험 193개, 문서 시험 3개, 실제 규칙 7개 |

## Fix round 2 재검증

2026-10-28 원본 작업 트리의 `cargo test --all`을 재실행했다.
`generic_mutants_are_killed_on_every_rule`은 다시
`w39_accident_before_contract`에서 실패했다. 기대값은 부적격·미지급이지만
현재 규칙은 적격·100,000,000원을 반환한다.
로그: `fix-round2-workspace-before.log`.

`git apply --check`는 준비된 패치를 수용한다. Python의 정렬된 compact
JSON SHA-256으로 현재 골든 해시와 패치의 두 교체 해시를 독립 검증했다.
두 규칙과 `packages/fixtures/rules/real.content_hashes.json`은 여전히
허용 경로 밖이므로, 이 세 파일의 경로 예외를 사용자에게 요청했다.
원본 규칙·해시는 수정하지 않았고 테스트를 우회하지 않았다.

`cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`,
어휘 검사, 검증 자료 검사 및 38개 변조 자체 검사, BLUEPRINT 수량 검사,
설계 묶음 검사(기계 44/44·존재 72/72)는 모두 통과했다.
로그는 같은 엔진 증거 디렉터리의 `fix-round2-*.log`에 있다.
전체 시험 통과와 발견 사항 해결은 아직 주장할 수 없다.

## Fix round 3 재검증

2026-10-28 원본 작업 트리에서 재실행했다. `cargo test --all`은 여전히
`generic_mutants_are_killed_on_every_rule`의
`w39_accident_before_contract`에서 실패한다. 집중 실행한
`every_real_clause_case_matches`도 두 규칙의 계약 전·보장개시 전날·개시일
미확인 6개 오판을 모두 재현한다. 로그는
`fix-round3-workspace-before.log`, `fix-round3-real-clauses-before.log`다.

준비된 패치는 `git apply --check`를 통과했다. 두 원본 해시가 현재 고정값과
일치하며, 각 규칙에 `gte(death_date, coverage_start_date)`를 추가한 JSON의
SHA-256이 패치의 새 고정값과 일치함을 독립 계산으로 확인했다.

`cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`,
어휘 검사, 검증 자료 검사 및 38개 변조 자체 검사, BLUEPRINT 수량 검사,
설계 묶음 검사(기계 44/44·존재 72/72)는 모두 통과했다.
로그는 같은 엔진 증거 디렉터리의 `fix-round3-*.log`에 있다.

두 원본 규칙과 `packages/fixtures/rules/real.content_hashes.json`의
경로 예외를 다시 요청했다. 응답 전에는 이 세 파일을 변경하지 않으며,
발견 사항과 전체 시험 실패는 미해결 상태다. 별도 복사본에서 통과한
이전 실행을 현재 작업 트리의 통과 증거로 사용하지 않는다.

## 제품 목적과 범위

BLUEPRINT A2·A5 / Q2·Q5·Q7 / L6 / I3·I6 / M2에 연결되는
`fixture_only` 설계 검증이다. 09 대응표 P08·P14의 엔진 경계·근거 식별
검증을 보강하지만, 승인 데이터·릴리스·소비자 화면이나 첫 출시 완료 증거를
대체하지 않는다. 원본 반영과 작업 트리 재검증 전에는 감사 수정 완료로
판정할 수 없다. 커밋·푸시·GitHub 호출은 하지 않았다.
