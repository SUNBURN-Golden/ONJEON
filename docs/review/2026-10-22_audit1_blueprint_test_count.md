# Audit 1: 설계도의 "Rust 테스트 42개"

검증일: 2026-10-22. 대상: `audit1-blueprint-test-count` finding.

`docs/BLUEPRINT.md` §11 "코드" 행(318행)은 "Rust 테스트 42개"라고 적는다. 이 숫자는 839ecdb(2026-10-09)가
§11을 쓸 때의 `cargo test --workspace` 합계이며, `cargo test`가 따로 세는 두 종류를 합친 값이다:
단위·통합 테스트 39개 + 문서 시험(doctest) 3개. 한쪽만 세는 사람과 어긋나므로 Audit 1은 CI 실행을
인용하거나 "39 + 3"으로 적으라고 했다.

| 위치 | 상태 | 비고 |
|---|---|---|
| `docs/blueprint/validation/REVERIFY_87a19c5.md` §2 "일반 CI" 행 | **고침** | 39 + 3 = 42로 나눠 적고, 근거를 재실행 로그로 바꿨다. 당시 CI 로그는 저장소에 없다 |
| `docs/BLUEPRINT.md` §11 "코드" 행(318행) "Rust 테스트 42개" | **미수정, 보호 문서** | 아래 교체안 |

`docs/BLUEPRINT.md`는 이 작업의 수정 금지 목록에 있어 고치지 않았다(§0.1: 설계도를 바꾸는 경로는 ADR이다).
이 finding은 그 행을 고치기 전에는 닫히지 않는다. 그 파일을 고칠 수 있는 사람(또는 수정 금지가 풀린 다음 작업)이
아래 문구로 바꾸고, 이 표의 "미수정"을 지우면 된다. 시험은 그 전후 모두 통과하도록 짜여 있어 함께 고칠 것이 없다.

## 재실행 확인

CI 로그는 저장소에 없고 실행 ID도 기록돼 있지 않다. REVERIFY 행이 가리키는 PR 병합 커밋 429c1a5는
이 저장소가 가져온 참조에서 도달할 수 없다. 그래서 2026-10-22에 두 커밋의 소스를 `git archive`로 꺼내
각각 `cargo test --workspace`를 돌렸다(당시 워크스페이스 구성원은 `packages/rules-engine` 하나). 출력 전체를
`docs/review/evidence/audit1_blueprint_test_count/`에 두었다(소스를 푼 임시 디렉터리 경로만 `<src-커밋>`으로 바꿨다):

| 커밋 | 로그 | 결과 |
|---|---|---|
| 87a19c5 (2026-10-09, "검증 자료 검사 보강", REVERIFY 대상) | `cargo_test_87a19c5.log` | 테스트 39, 문서 시험 3, 실패 0, 종료 코드 0 |
| 839ecdb (2026-10-09, "원본 보관소(S3) 결정 반영…", §11의 "42개"를 쓴 커밋) | `cargo_test_839ecdb.log` | 테스트 39, 문서 시험 3, 실패 0, 종료 코드 0 |

두 로그의 시험 이름과 바이너리별 통과 수는 같다(출력 순서만 다르다). 바이너리별:

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

위 8개 바이너리의 합이 단위·통합 테스트 39개다. 문서 시험(doctest) 3개는 `onjeon_rules_engine` 크레이트의
것이다. `cargo test --workspace` 합계 42건. 재실행 도구는 cargo·rustc 1.99.1(로그 머리에 기록)이고, 당시 CI와
도구 버전이 달라도 시험 수는 소스가 정하므로 바뀌지 않는다.

현재 main은 워크스페이스가 여러 크레이트로 늘어 합계가 훨씬 크다(아래 실행 결과). 318행의 숫자는 2026-10-09
시점 값이지 현재 값이 아니며, §10.7에 따라 마일스톤이 끝날 때 갱신하는 상태 열이다. 같은 행의 "S3 버킷 정의(미배포)"는
별도 finding(`audit1-blueprint-v1-row-s3-stale`)의 대상이라 여기서 다루지 않는다.

## BLUEPRINT.md 교체안

318행, "Rust 테스트 42개":

> Rust 단위·통합 테스트 39개 + 문서 시험(doctest) 3개(2026-10-09 기준 42건, 재실행 근거는 `docs/blueprint/validation/REVERIFY_87a19c5.md` §2)

## 시험

`tools/tests/test_validation_test_counts.py` (기존 `unittest discover -s tools/tests`에 포함):

- 재실행 로그 2건: `$ git archive <커밋>`·`$ cargo test --workspace` 명령과 `exit code: 0`이 있고, 모든
  `test result:` 행이 `ok`·실패 0이며, 바이너리 통과 수의 합과 `Doc-tests onjeon_rules_engine` 수가 REVERIFY 행의
  39 + 3과 같고, 두 커밋의 바이너리별 수가 같고, 로컬 경로가 없다.
- REVERIFY_87a19c5: 합친 숫자만 적은 "Rust 테스트 N개"가 없고, a + b = c이며, "일반 CI" 행이 재실행 값임과
  CI 로그가 저장소에 없음을 밝히고 로그 디렉터리를 가리킨다.
- 이 기록: 교체안의 39 + 3이 REVERIFY와 같고, 위 바이너리 표가 두 로그의 바이너리별 수와 같다.
- BLUEPRINT: §11 "코드" 행이 숫자를 한 번만 말하고, 아직 합친 숫자면 REVERIFY의 a + b와 같아야 하며(지금은 42),
  교체안이 반영된 뒤에는 행의 39 + 3이 REVERIFY와 같아야 한다. 두 상태 모두 통과하므로 반영 때 시험을 고칠 일이 없다.
- validation README: 이 후속 작업을 가리킨다.

```sh
python3 -m unittest tools/tests/test_validation_test_counts.py -v
python3 -m unittest discover -s tools/tests
python3 tools/vocab_check.py && python3 tools/validation_check.py && python3 tools/validation_check.py --selftest
cargo fmt --all -- --check && cargo clippy --all-targets -- -D warnings && cargo test --all
```

## 실행 결과와 한계

2026-10-22에 이 워크트리(bbcdb0b 기준)에서 실행:

- `git archive`로 꺼낸 87a19c5·839ecdb 각각 `cargo test --workspace`: 둘 다 위 표대로 단위·통합 테스트 39개 +
  문서 시험 3개 = 42건, 실패 0(로그는 `docs/review/evidence/audit1_blueprint_test_count/`).
- `python3 -m unittest tools/tests/test_validation_test_counts.py -v`: 14개 통과.
- `python3 -m unittest discover -s tools/tests`: 565개 실행, 전부 통과(skip 7개).
- `python3 tools/vocab_check.py`: 통과(45축·228값). `python3 tools/validation_check.py`: 통과
  (14 표본·142 조항·26 gap). `--selftest`: 38종 변조 모두 의도한 사유로 적발.
- `cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`: 통과.
- `cargo test --all`(현재 main, 8개 크레이트): 55개 결과 구간, 합계 388개 통과·실패 0. 문서 시험은
  `onjeon_rules_engine`의 3개만 있고 나머지 7개 크레이트는 0개다.
- `spec_check.py`: 기계 검사 44/44, 존재 검사 72/72.

한계: 39 + 3은 재실행 값이다. 당시 CI 작업 로그와 실행 ID는 저장소에 없으므로 "CI 로그 인용"은
못 하고 재실행 로그를 근거로 적었다. 318행의 "42개"는 2026-10-09 시점 값이며 현재 main의 합계와
다르다. `docs/BLUEPRINT.md`는 이 작업의 수정 금지 문서라 위 교체안 반영은 그 파일을 고칠 수 있는 쪽의 몫이다.
