# Audit 1: BLUEPRINT Rust 시험 수 수정 검증

2026-10-25 | 대상: `audit1-blueprint-test-count`, fix round 3 (아래 병합 재검증 기록 포함).

`docs/BLUEPRINT.md` §11 "코드" 행(318행)을 다음처럼 고쳤다.

> Rust 단위·통합 테스트 39개 + 문서 시험(doctest) 3개

2026-10-09 기준 합계 42건이라는 날짜와 재실행 근거인
[REVERIFY_87a19c5 §2](REVERIFY_87a19c5.md#2-실제-실행-범위) 링크를 함께 적었다.
이 수치는 현재 워크스페이스의 시험 수가 아니다.

근거는 `evidence/audit1_blueprint_test_count/`의
[cargo_test_87a19c5.log](evidence/audit1_blueprint_test_count/cargo_test_87a19c5.log)와
[cargo_test_839ecdb.log](evidence/audit1_blueprint_test_count/cargo_test_839ecdb.log)다.
두 로그 모두 단위·통합 시험 39개, doctest 3개, 실패 0,
종료 코드 0이며 `tools/tests/test_validation_test_counts.py`가 이 내용을 대조한다.
당시 CI 로그와 실행 ID는 저장소에 없어 CI 실행을 인용하지 않으며, 재실행 값이라는 설명을 유지한다.

이전 라운드에서 허용 경로 밖에 추가한 감사 문서와 증거 로그는 되돌리고,
검증 기록과 로그를 모두 허용 경로인 `docs/blueprint/validation/` 아래에 모았다.
이번 작업의 허용 경로에 `docs/BLUEPRINT.md`가 명시되어 해당 행을 직접 수정했다.

두 커밋의 바이너리별 통과 수는 같다.

| 시험 바이너리 (`packages/rules-engine`) | 통과 |
|---|---|
| `src/lib.rs` 단위 시험 | 5 |
| `tests/golden.rs` | 3 |
| `tests/loader_and_arith.rs` | 8 |
| `tests/mutation.rs` | 1 |
| `tests/real_clauses.rs` | 6 |
| `tests/review_fixes.rs` | 10 |
| `tests/soundness.rs` | 2 |
| `tests/vocabulary.rs` | 4 |

위 8개 바이너리 합계가 39건이고 문서 시험(doctest) 3개는 별도로 센다.

회귀 시험은 이제 합산값만 적은 행을 거부하고, 39 + 3의 구분·기준일·재실행 근거를 요구한다.
회귀 검증으로 기준 커밋 `bbcdb0b`의 BLUEPRINT 내용을 메모리에서 읽도록 대체해
`Blueprint` 시험 3건 중 2건이 실패하는 것을 확인했다(합산값만 기재, 기준일·근거 누락).
현재 문서로 전체 `test_validation_test_counts` 15건이 통과했다.

| 재실행 명령 | 결과 |
|---|---|
| `python3 -m unittest tools.tests.test_validation_test_counts -v` | 15건 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 568건 실행, 562건 통과·6건 건너뜀, 실패·오류 0 |
| `python3 tools/vocab_check.py` | 45축·228값 통과 |
| `python3 tools/validation_check.py` | 14표본·142조항·26 gap 내부 일관성 통과 |
| `python3 tools/validation_check.py --selftest` | 변조 38종 모두 의도한 사유로 적발 |
| `cargo fmt --all -- --check` | 통과 |
| `cargo clippy --all-targets -- -D warnings` | 통과 |
| `cargo test --workspace` | 현재 8개 크레이트, 55개 결과 구간, 388건 통과(단위·통합 385 + doctest 3), 실패 0 |

Python 건너뜀 6건은 비공개 원본/로컬 보관본이 필요한 5건과 현재 botocore가
조건부 쓰기를 지원하여 적용되지 않는 구버전 시험 1건이다.
`git diff --check`도 통과했다. 작업 전 기준 커밋 `bbcdb0b`와 비교한 변경·신규 파일
7개는 모두 허용 경로 안에 있으며, 옮긴 두 증거 로그는 이동 전과 바이트가 같다.


## Fix round 3: main 병합 충돌 해결과 재검증

`docs/BLUEPRINT.md` §11 코드 행의 충돌을 해결했다. 이 노드의 2026-10-09 기준
단위·통합 시험 39개 + doctest 3개 및 재실행 근거 링크와, main의 R2 보존·대조
도구·비용 한도 장치 및 대안인 미배포 AWS S3 정의 설명을 한 행에 함께 유지했다.
다른 병합 내용은 유지했고, 커밋·푸시·GitHub 호출은 하지 않았다.

수정 전 기존 두 회귀 모듈을 함께 실행하면 25건 중 assertion 실패 9개가 발생했다
(중복 코드 행 3개, R2 목록 누락 subtest 5개, 오래된 S3 문구 1개).
충돌 해결 후 같은 25건이 모두 통과했다. 기존 시험이 두 변경 의도와 근거 로그를
각각 검사하므로 제품 동작이나 시험 조건을 변경하지 않았다.

아래는 병합 결과에서 직접 실행한 결과다. 각 명령의 종료 코드는 0이었다.
로그는 [round3/](evidence/audit1_blueprint_test_count/round3/)에 보관했다.
이 로그의 행 끝 공백과 파일 끝 빈 줄만 정리했으며, 이전 두 기준 커밋의 증거 로그는 유지했다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest tools.tests.test_validation_test_counts tools.tests.test_storage_provider_docs -v` | 25건 통과 | [focused.log](evidence/audit1_blueprint_test_count/round3/focused.log) |
| `python3 -m unittest discover -s tools/tests -v` | 789건 실행, 783건 통과·6건 건너뜀, 실패·오류 0 | [python-tests.log](evidence/audit1_blueprint_test_count/round3/python-tests.log) |
| `cargo fmt --all -- --check` → `cargo clippy --all-targets -- -D warnings` → `cargo test --workspace` | 모두 통과. Rust 단위·통합 399건 + doctest 3건, 무시 1건, 실패 0 | [rust-checks.log](evidence/audit1_blueprint_test_count/round3/rust-checks.log) |
| `python3 tools/vocab_check.py` → `python3 tools/validation_check.py` → `python3 tools/validation_check.py --selftest` → `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 어휘·내부 일관성·변조 38종 통과, 설계 명세 기계 44/44·존재 72/72 통과 | [validation.log](evidence/audit1_blueprint_test_count/round3/validation.log) |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir target/audit1-ontology` → `python3 -I docs/blueprint/proposals/온톨로지/검증/ontology_check.py target/audit1-ontology/debug/ontology-case-runner` | 빌드 및 질문 11/11·제약 자체 시험 15/15·릴리스/문서 모델 25/25 통과 | [ontology.log](evidence/audit1_blueprint_test_count/round3/ontology.log) |

현재 병합 결과의 시험 수는 위와 같으며 §11의 역사적 39 + 3과 구분한다.
Python 건너뜀 6건의 이유는 위 2차 기록과 같다.
`git ls-files -u`는 비어 있고, main(`MERGE_HEAD`) 대비 이 노드의 diff 및
미추적 파일은 모두 허용 경로 안이다. 금지된 네 경로의 main 대비 diff는 비어 있다.
main 대비 이 노드의 `git diff --check MERGE_HEAD`도 통과했다.
main에서 들어온 기존 로그와 PDF의 공백은 증거·픽스처를 유지하기 위해 수정하지 않았다.
