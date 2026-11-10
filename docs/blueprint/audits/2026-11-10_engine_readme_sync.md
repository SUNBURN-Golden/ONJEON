# Audit 5: 엔진 README의 시험 표·`fixture_only`·범위 비교 의미 동기화

검증일: 2026-11-10. 노드: `audit5-engine-readme-sync`.
BLUEPRINT A1·A2·A5, Q7, L6, I6, M1 기반과
[09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 P08·P14에 연결된다.

## 발견 판정과 수정

지적은 세 부분이었다. 작업 시작 시점의 [엔진 README](../../../packages/rules-engine/README.md)를
현재 `main`과 대조해 각각의 상태를 확인했다.

1. **시험 표의 `real_clauses`·`vocabulary` 누락.** 현재 README `## 테스트` 표에는 두 행이
   모두 있다. [Audit 3](2026-10-29_engine_readme_test_table.md)와
   [Audit 4](2026-11-04_engine_readme_test_table.md)에서 이미 수정된 상태이며, 이번 작업이
   새로 추가했다고 주장하지 않는다. 기존 `readme_test_table` 시험은 표의 첫 열과
   `tests/*.rs` 파일을 양방향 대조하고, 두 행의 개별·동시 삭제와 개명을 메모리에서
   재현해 검출한다. 재검증에서 6개가 모두 통과했다.
2. **`vocabulary.json`의 `fixture_only`가 "합성"만 뜻함.** 현재 `publication_state` 축의
   `fixture_only` 정의는 "시험·설계 검증 전용 규칙. 합성 규칙과 실제 조항 기반 검증 규칙을
   포함하며 서비스 데이터가 아님. 근거·릴리스 없이 허용"이다. 축 설명도 이 상태가 원문
   출처(합성·실제 조항)를 구분하는 축이 아님을 밝힌다. 기존 `vocabulary` 시험이 이 문구와
   합성 규칙 1개·실제 조항 규칙 7개가 모두 같은 시험 전용 상태인지 검사한다. 수정이
   필요하지 않았다.
3. **범위 비교를 W3로 미룸.** 재현됐다. README의 "아직 없는 것" 절은 "범위가 기준값을
   걸치는 경우를 모름으로 처리할지는 W3 설계에서 정한다"고 적어, 의미론을 이미 확정한
   [DEC-O12](../../decisions/DEC-O12.md) S3(2026-10-15)와 어긋났다. README의 rule-0.2 절
   뒤 문단과 "아직 없는 것" 절을 DEC-O12 S3에 맞게 고쳤다.

## 변경 내용

- rule-0.2 절 뒤 문단은 금액 범위와의 비교를 여전히 로드에서 거부한다는 사실과 함께,
  비교 의미가 DEC-O12 S3에서 확정됐음을 밝힌다: 범위의 모든 값이 같은 결론에 동의할
  때만 참·거짓이고 아니면 모름, 구간 산술은 단조 연산에만, 범위를 대표값으로 접지 않음,
  `between`은 양 끝 포함 플래그 필수. 연산별 S6 출시 조건 전까지는 capability-blocked다.
- "아직 없는 것" 절에서 W3가 범위 비교의 모름 처리를 정한다는 문장을 삭제하고, 같은
  DEC-O12 S3 의미론과 S6 출시 조건(T-TW-04·T-TW-05)을 적었다. 나머지 미지원 기능 목록과
  §49.2·§54.4 W3 참조는 그대로 둔다.
- [readme_test_table.rs](../../../packages/rules-engine/tests/readme_test_table.rs)에
  `readme_uses_the_dec_o12_range_comparison_semantics` 시험을 추가했다. README가 범위 비교
  의미를 W3로 다시 미루거나 DEC-O12 S3·S6·핵심 의미 문구를 잃으면 실패한다. 동시에
  현재 엔진이 범위 비교를 로드에서 거부하고 capability-blocked라는 설명도 유지되는지
  검사한다.
- README `readme_test_table` 행과 09 제품목적 대응표 P08·P14에 이 증거를 연결했다.

엔진 실행 코드와 로더 동작, 공유 fixture, 골든 해시는 바꾸지 않았다. 이 노드는 문서·시험
동기화이며 범위 비교 구현이나 릴리스가 아니다. 범위 비교의 실제 구현·출시는 연산별 S6
조건과 T-TW-04·T-TW-05를 따른다.

이전 감사 기록인 [2026-10-26 범위 비교](2026-10-26_engine_range_compare_static.md)와
[2026-10-28 재검증](2026-10-28_engine_moneyrange_compare_load_check.md)의
"W3 열린 결정" 문구는 그 실행 시점의 기록이다. DEC-O12 S3의 의미론 확정과 현재 README·09
대응표의 상태는 이 문서를 따른다.

## 직접 실행한 검증

Rust 1.98.1과 작업 트리 전용 `CARGO_TARGET_DIR="$PWD/target"`를 사용했다.
아래 로그는 로컬 실행 증거다.

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --locked --offline --test readme_test_table --test vocabulary --test range_comparisons` | 25개 통과·실패 0: [focused.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/focused.log) |
| `cargo test --all --locked --offline` | 514개 통과·실패 0, 기존 ignored 1개: [workspace.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/workspace.log) |
| `cargo fmt --all -- --check` | 종료 코드 0: [fmt.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/fmt.log) |
| `cargo clippy -p onjeon-rules-engine --all-targets --locked --offline -- -D warnings` | 종료 코드 0: [clippy.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write`·`python3 -I tools/blueprint_counts.py` | 새 시험 1개로 Rust 시험 등록 수 248→249 갱신, 이후 대조 종료 코드 0: [갱신](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/counts-write.log), [대조](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/counts.log) |
| `python3 -I tools/blueprint_status.py` | 종료 코드 0: [status.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/status.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 종료 코드 0, P01~P19 연결 검사: [product-purpose.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/product-purpose.log) |
| `python3 -I tools/vocab_check.py` | 종료 코드 0, 어휘 정본과 생성 문서 대조: [vocab.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/vocab.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 종료 코드 0: [spec-check.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/spec-check.log) |
| `python3 -I -m unittest discover -s tools/tests -v` | 1,506개 실행·실패 0·skipped 60개: [python.log](../../../packages/rules-engine/evidence/audit5-engine-readme-sync/python.log) |

`git diff --check`도 통과했다.

이 기록은 엔진 README와 정본 어휘·시험의 문서 정합성 및 로컬 회귀 증거다. 실제 상품
릴리스, 전 상품 수집, 소비자 화면, 이해도 시험, P08·P14 전체 완료 또는 첫 출시 완료
증거를 대체하지 않는다.
