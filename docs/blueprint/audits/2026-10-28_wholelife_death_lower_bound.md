# Audit 3: 종신보험 사망 보장개시일 하한

노드: `audit3-wholelife-death-lower-bound`. 기록일: 2026-10-28.

## 상태: 허용 경로 내 활성 규칙 수정 및 검증 (Fix round 5)

Fix round 4의 차단 원인은 `packages/fixtures/`의 허용 경로 밖 수정이었다.
두 공유 규칙과 `real.content_hashes.json`을 HEAD 내용으로 복원했다.
해당 디렉터리에는 이번 라운드의 변경이 없다.

수정된 활성 규칙은 허용 경로인 아래 JSON에 둔다.

- `packages/rules-engine/fixtures/rules/real/kyobo-wholelife-disease-death.json`
- `packages/rules-engine/fixtures/rules/real/kyobo-wholelife-accident-death.json`

두 규칙의 `eligibility.all`에 `gte(death_date, coverage_start_date)`를 추가했다.
다른 규칙 내용은 공유 원본과 동일하다. 기존 계약 5년 미만 상한도 유지한다.
2026-01-01 계약·보장개시에 대해 2025-01-01에 사망하면 두 활성 규칙 모두
`eligibility=false`, `payout=not_payable`을 반환한다.

`packages/rules-engine/fixtures/rules/replacements.json`이 공유 원본 경로와
이전 내용 해시, 교체 경로와 새 내용 해시를 고정한다. 엔진 시험 공통 로더와
`tools/rule_fixture_catalog.py`가 같은 목록을 읽는다. 골든·변이·건전성·실제
조항 시험과 문서 검증·BLUEPRINT 수량 검사는 모두 교체된 활성 목록을 쓴다.
검증 인코딩 자료의 `rules[].file`도 새 JSON을 직접 가리킨다.
교체 파일 누락·해시 불일치는 실패하며 이전 규칙으로 대체하지 않는다.

공유 원본 JSON 자체는 여전히 이전 버그를 재현한다. 활성 목록에서 제외한
역사적 픽스처이며, 새 회귀 시험이 원본과 수정본을 함께 평가하여 원본의
오판 6개가 수정본에서는 사라지는지 검사한다. 엔진 평가기에 상품별
분기나 숨은 조건을 추가하지 않았다. 두 새 규칙도 계속 `fixture_only`다.

## 회귀 검증

엔진 소유 사례 표
`packages/rules-engine/tests/fixtures/cases/real/kyobo-wholelife-death.cases.json`의
`w34`~`w43`은 두 규칙 각각의 다음 경계를 고정한다.

- 계약 전 사망: 부적격·미지급. 감사의 계약일·보장개시일을 사례에 명시했다.
- 계약일과 다른 보장개시일 전날: 부적격·미지급.
- 보장개시일 당일·다음 날: 적격·기존 금액 유지.
- 보장개시일 `null`: `unknown`·`undetermined`와
  `missing_inputs=[coverage_start_date]`, 조건부 금액 유지.

`fixture_supplements` 시험 2개를 추가해 교체 규칙의 유일한 차이가 하한
조건인지, 원본 오판 6개가 검출되는지, 보장개시일 키 누락도 `null`과 같은
모름을 유지하는지 확인한다. Python 시험 6개는 활성 원천·인코딩 참조 일치와
교체 파일/목록 누락·하한 삭제·과거 원본 변경·ID/공개 상태 변경의 거부를 확인한다.
실제 조항 사례는 공유 47개와 엔진 경계 68개, 총 115개다.

## Fix round 5 실행 증거

로그: [엔진 증거 디렉터리](../../../packages/rules-engine/evidence/audit3-wholelife-death-lower-bound/).
Rust 검증은 이 작업 트리의 `CARGO_TARGET_DIR="$PWD/target"`으로 실행했다.
온톨로지 실행기는 같은 트리의 `target/ontology`를 사용했다.

| 실행 | 결과 | 로그 |
|---|---|---|
| `cargo test --all` | 460개 통과, 실패 0, 기존 무시 시험 1개 | `fix-round5-workspace.log` |
| 엔진 `real_clauses`, `fixture_supplements`, `golden`, `mutation`, `soundness`, `readme_test_table` (`--nocapture`) | 44개 통과. 실제 조항 115개, 생성 변이 342개 생존 0, 원본·교체 내용 해시 검사 통과 | `fix-round5-regressions.log` |
| `cargo fmt --all -- --check` | 통과 | `fix-round5-format.log` |
| `cargo clippy --all-targets -- -D warnings` | 통과 | `fix-round5-clippy.log` |
| `python3 tools/vocab_check.py` | 통과 | `fix-round5-vocabulary.log` |
| `python3 tools/validation_check.py` 및 `--selftest` | 통과. 변조 38개 검출 | `fix-round5-validation.log`, `fix-round5-validation-selftest.log` |
| `python3 -I tools/blueprint_counts.py` | 통과. Rust 시험 195개, 문서 시험 3개, 활성 실제 규칙 7개 | `fix-round5-counts.log` |
| Python 전체 `unittest discover -s tools/tests -v` | 1,167개 실행, 실패 0, 건너뜀 6개 | `fix-round5-python.log` |
| 설계 묶음 `spec_check.py` | 기계 검사 44/44, 존재 검사 72/72 통과 | `fix-round5-design-specs.log` |
| 온톨로지 실행기 `cargo test` 및 `ontology_check.py` | Rust 시험 3개, 질문 11/11, 제약 자체 시험 15/15, 릴리스·문서 모델 시험 25/25 통과 | `fix-round5-ontology-tests.log`, `fix-round5-ontology-check.log` |
| 변경 경로·공유 원본 바이트 검사 | 허용 경로 안의 변경만 존재, 공유 원본 3개 HEAD와 일치 | `fix-round5-scope.log` |

Rust의 무시 시험은 수동 픽스처 재생성용 `regenerate_declared_abox_fixture`다.
Python은 로컬 원본 보관소가 필요한 시험 5개와 구형 botocore 전용 시험 1개를
건너뛰었다. 이 검증은 보관된 외부 원본의 재검증을 주장하지 않는다.

## 과거 증거와 제품 범위

`before.log`, `workspace-before.log`, `candidate-tests.log`, `fix-round1-*`부터
`fix-round4-*`는 이전 라운드의 기록이다. 특히 round 4 통과 기록은 허용 경로
밖 변경을 포함했던 시점의 결과이며 현재 수정의 근거로 사용하지 않는다.
`tools/evidence/audit3-wholelife-death-lower-bound/fixture-fix.patch`도 공유 파일을
직접 바꾸던 과거 준비물이며 이번 해결에 적용하지 않는다.
현재의 근거는 `fix-round5-*` 로그와 활성 원천 목록이다.

BLUEPRINT A2·A5 / Q2·Q5·Q7 / L6 / I3·I6 / M2에 연결되는 설계 검증이다.
승인 데이터·릴리스·소비자 화면이나 첫 출시 완료 증거를 대체하지 않는다.
커밋·푸시·GitHub 호출은 하지 않았다.
