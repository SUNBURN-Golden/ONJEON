# Audit 2: README ADR 목록·엔진 시험 표·규칙 내용 해시 문구

기록일: 2026-10-27. 노드: `audit2-readme-adr-list`.
연결: BLUEPRINT §11, ADR-0003, [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) P08·P14.

## 발견과 현재 상태

감사 지적은 세 가지였다. 작업 트리에서 각각 다시 대조했다.

| 지적 | 이 노드 시작 시점 | 조치 |
|---|---|---|
| `README.md:22`의 ADR 목록이 0011까지만 있음 | 이미 해소됨. `audit1-readme-adr-list-stale`(978175b, 2026-10-22)이 0012~0018과 `DEC-*` 안내를 추가했고 [`tools/tests/test_readme_index.py`](../../../tools/tests/test_readme_index.py)가 디렉터리의 `ADR-*.md` 번호와 행을 양방향으로 대조한다 | 문서는 그대로 두고 감사 상태(0011 뒤 삭제)로 되돌린 변이를 기존 시험이 잡는지 확인했다 |
| `packages/rules-engine/README.md` 시험 표에 `real_clauses.rs`·`vocabulary.rs` 행이 없음 | 이미 해소됨. `vocabulary` 행은 `audit1-vocab-add-dsl-axes`(9ec9db4), `real_clauses` 행은 `audit2-engine-real-clauses-count-assert`(c3f4d73)에서 들어갔다. 다만 표와 `tests/*.rs`를 대조하는 시험이 없어 다음 시험 파일도 같은 방식으로 빠질 수 있었다 | 표↔파일 일치 시험 `readme_test_table` 추가 |
| 내용 해시를 "정규화"라고 부름(실제로는 키 순서만 정렬) | **미해소**. `README.md:14`가 "규칙 JSON을 정규화(…)한 SHA-256"이라고 적었다 | 문구 정정과 범위 고정 시험 `content_hash_scope` 추가 |

## 내용 해시의 실제 범위

[`canonical.rs`](../../../packages/rules-engine/src/canonical.rs)는 `serde_json`이 파싱한 값을 `BTreeMap` 객체로 옮겨 compact JSON으로 다시 쓰고, [`rule.rs`](../../../packages/rules-engine/src/rule.rs)의 `canonical_bytes`가 최상위 `release_id`만 뺀다. 값은 바꾸지 않는다. README 문장은 이제 아래를 그대로 적는다.

- 해시에 영향이 없는 것: 파일의 공백, 객체 키 순서(중첩 포함), 문자열 이스케이프 표기(`s`와 `s`), 최상위 `release_id`.
- 해시를 바꾸는 것: 중첩된 `release_id`, 유니코드 형식(NFC `é` 대 NFD `e`+결합 부호, 완성형 `한` 대 조합형 자모), 문자열 앞뒤 공백, 배열 순서(`evidence_refs`, `all` 자식), 같은 뜻의 요율 표기(`"0.5"`·`"0.50"`·`{"rate":"0.5"}`, 평가 결과는 같음), 생략한 기본값과 명시한 기본값(`calendar: "Asia/Seoul"`, rule-0.2 `contract_effect: "none"`; 로드된 효과는 같음), 평가에 쓰이지 않는 `example_kind`.

따라서 해시가 같으면 같은 규칙 내용이지만, 해시가 다르다고 계산 논리가 다르다는 뜻은 아니다. 엔진 동작과 고정된 해시(`fixture-rule-001.content_hash`, `real.content_hashes.json`)는 바꾸지 않았다. 의미 수준 정규화를 도입하면 모든 결과의 해시가 바뀌므로 이 노드의 범위가 아니다.

## 회귀 시험

| 시험 | 검사 |
|---|---|
| [`content_hash_scope.rs`](../../../packages/rules-engine/tests/content_hash_scope.rs) (7개) | 위 두 목록의 각 항목. 요율 표기·기본값 사례는 평가 결과나 로드된 효과가 같다는 것도 함께 확인해 "같은 뜻, 다른 해시"임을 보인다 |
| [`readme_test_table.rs`](../../../packages/rules-engine/tests/readme_test_table.rs) (4개) | README `## 테스트` 표 첫 열의 이름 집합 = `tests/*.rs` 파일 이름 집합(누락·낡은 행 모두 실패), `real_clauses`·`vocabulary`·새 두 행의 존재, 행 삭제·이름 변경 음성 대조, 해시 문장에 "JSON을 정규화"/"정규화(" 표현이 없고 "키 순서만"·"값 자체는 정규화하지 않는다"·유니코드·`release_id`가 있는지 |
| 기존 [`test_readme_index.py`](../../../tools/tests/test_readme_index.py) | 루트 README ADR 행과 디렉터리의 양방향 대조(변경 없음) |

## 직접 실행한 검증 증거

| 명령 | 결과·로그 |
|---|---|
| `cargo test -p onjeon-rules-engine --offline --test readme_test_table --test content_hash_scope` (README 수정 전) | 종료 코드 101. `content_hash_scope` 7개 통과(엔진 동작은 원래 이랬다), `readme_test_table` 4개 중 3개 실패: "정규화(" 문구, 새 행 누락: [before.log](../../../tools/evidence/audit2-readme-adr-list/before.log). 이 실행의 `golden` 누락 진단은 당시 시험 파서의 버그(표 첫 데이터 행 건너뜀)였고 수정 후 재실행했다 |
| 같은 명령 (수정 후) | 종료 코드 0, 11개 통과: [focused.log](../../../tools/evidence/audit2-readme-adr-list/focused.log) |
| README에서 `real_clauses`·`vocabulary` 행 삭제 + "정규화(" 문구 복원 후 `--test readme_test_table` | 종료 코드 101, 4개 모두 실패(누락 파일 이름 보고). 원본 복원 후 다시 통과: [table-guard-mutation.log](../../../tools/evidence/audit2-readme-adr-list/table-guard-mutation.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_readme_index.py -v` 와 [adr_mutation.py](../../../tools/evidence/audit2-readme-adr-list/adr_mutation.py)(README:22를 0011 뒤에서 자른 감사 상태) | 현재 README 5개 통과. 변이에서는 `test_every_adr_number_is_listed`가 0012~0018 누락으로 실패: [root-readme-adr.log](../../../tools/evidence/audit2-readme-adr-list/root-readme-adr.log) |
| `cargo test --all --offline` | 종료 코드 0, Rust 458개 통과·실패 0·기존 ignored 1개: [workspace.log](../../../tools/evidence/audit2-readme-adr-list/workspace.log) |
| `cargo fmt --all -- --check` · `cargo clippy --all-targets --offline -- -D warnings` | 둘 다 종료 코드 0: [fmt.log](../../../tools/evidence/audit2-readme-adr-list/fmt.log) · [clippy.log](../../../tools/evidence/audit2-readme-adr-list/clippy.log) |
| `python3 -I tools/blueprint_counts.py --write` | §11 Rust 단위·통합 시험 등록 수 182 → 193(새 시험 11개). 이후 검사 모드 통과: [consistency-checks.log](../../../tools/evidence/audit2-readme-adr-list/consistency-checks.log) |
| `python3 -I -m unittest discover -s tools/tests -v` | 종료 코드 0, 1,138개 실행·실패 0·건너뜀 30개. 건너뜀은 모두 이 VM의 환경 제약(boto3/botocore 미설치·구버전 25개, `ONJEON_ARCHIVE_RAW`·로컬 원본 보관소·pdftotext 필요 5개)이며 이번 변경과 무관하다. 온톨로지 실행기는 실행 전에 `CARGO_TARGET_DIR=target cargo build --locked --offline`로 빌드했다: [python-tests.log](../../../tools/evidence/audit2-readme-adr-list/python-tests.log) |
| 수치·결정 색인·어휘·제품 목적·명세 검사, `git diff --check` | `blueprint_counts.py`·`blueprint_status.py`(결정 문서 변경 없음, 색인 그대로)·`vocab_check.py`·`validation_check.py`·`check_product_purpose.py`·`spec_check.py`(기계 44/44·존재 72/72)·`git diff --check` 모두 종료 코드 0: [consistency-checks.log](../../../tools/evidence/audit2-readme-adr-list/consistency-checks.log) |

## 제품 목적과 한계

엔진 문서가 결과에 붙는 `rule_content_hash`의 뜻을 과장하지 않게 하는 정정이다(BLUEPRINT A5 근거 사슬, P08·P14). 해시가 "같은 규칙 내용"을 식별한다는 보장은 유지되며, 의미가 같은 규칙을 같은 해시로 묶는다고 주장하지 않는다. 문서·합성 규칙 회귀 증거일 뿐 실제 릴리스 규칙·상품 데이터·소비자 화면·출시 완료를 증명하지 않는다.
