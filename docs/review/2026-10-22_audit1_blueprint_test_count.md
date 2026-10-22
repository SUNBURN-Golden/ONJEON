# Audit 1: 설계도의 "Rust 테스트 42개"

검증일: 2026-10-22. 대상: `audit1-blueprint-test-count` finding.

`docs/BLUEPRINT.md` §11 "코드" 행(318행)은 "Rust 테스트 42개"라고 적는다. 이 숫자는 839ecdb(2026-10-09)가
§11을 쓸 때의 `cargo test --workspace` 합계이며, `cargo test`가 따로 세는 두 종류를 합친 값이다:
단위·통합 테스트 39개 + 문서 시험(doctest) 3개. 한쪽만 세는 사람과 어긋나므로 Audit 1은 CI 실행을
인용하거나 "39 + 3"으로 적으라고 했다.

| 위치 | 상태 | 비고 |
|---|---|---|
| `docs/blueprint/validation/REVERIFY_87a19c5.md` §2 "일반 CI" 행 | **고침** | 39 + 3 = 42로 나눠 적고, 재실행 값이며 CI 로그는 저장소에 없다고 밝혔다 |
| `docs/BLUEPRINT.md` §11 "코드" 행(318행) "Rust 테스트 42개" | **미수정, 보호 문서** | 아래 교체안 |

`docs/BLUEPRINT.md`는 이 작업의 수정 금지 목록에 있어 고치지 않았다(§0.1: 설계도를 바꾸는 경로는 ADR이다).
이 finding은 그 행을 고치기 전에는 닫히지 않는다. 문서 소유자가 아래 문구로 바꾸면 된다.

## 재실행 확인

CI 로그는 저장소에 없고 실행 ID도 기록돼 있지 않다. REVERIFY 행이 가리키는 PR 병합 커밋 429c1a5는
이 저장소가 가져온 참조에서 도달할 수 없다. 그래서 2026-10-22에 두 커밋의 소스를 `git archive`로 꺼내
각각 `cargo test --workspace`를 돌렸다(당시 워크스페이스 구성원은 `packages/rules-engine` 하나).
두 커밋의 결과가 같다.

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
것이다. `cargo test --workspace` 합계 42건.

- 87a19c5(2026-10-09, "검증 자료 검사 보강"): 테스트 39, 문서 시험 3.
- 839ecdb(2026-10-09, "원본 보관소(S3) 결정 반영…", §11의 "42개"를 쓴 커밋): 테스트 39, 문서 시험 3.
- 현재 main(5cc3a09 기준)은 워크스페이스가 8개 크레이트로 늘어 합계가 훨씬 크다. 문서 시험 3개는 여전히
  `onjeon_rules_engine`에만 있다. 318행의 숫자는 2026-10-09 시점 값이지 현재 값이 아니며, §10.7에 따라
  마일스톤이 끝날 때 갱신하는 상태 열이다.

## BLUEPRINT.md 교체안

318행, "Rust 테스트 42개":

> Rust 단위·통합 테스트 39개 + 문서 시험(doctest) 3개(2026-10-09 기준 42건. 구성은 CI 로그가 아니라 `docs/blueprint/validation/REVERIFY_87a19c5.md`의 재실행으로 확인)

## 시험

`tools/tests/test_validation_test_counts.py` (기존 `unittest discover -s tools/tests`에 포함):

- REVERIFY_87a19c5: 합친 숫자만 적은 "Rust 테스트 N개"가 없고, "테스트 a개 + 문서 시험(doctest) b개 = c건"에서
  a + b = c이며, 재실행 값이고 CI 로그가 저장소에 없다고 밝힌다.
- 이 기록: 교체안의 39 + 3이 REVERIFY 행과 같고, 위 표의 바이너리별 통과 수의 합이 39다.
- BLUEPRINT: §11 "코드" 행의 합친 숫자가 REVERIFY의 a + b와 같다(지금은 42). 합친 숫자 부재 시험은
  `expectedFailure`다. 교체안이 반영되면 "unexpected success"로 실패하므로 그때 데코레이터를 지운다.
  반영된 뒤에는 같은 시험이 행의 39 + 3을 REVERIFY와 대조한다.
- validation README: 이 후속 작업을 가리킨다.

```sh
python3 -m unittest tools/tests/test_validation_test_counts.py -v
python3 -m unittest discover -s tools/tests
python3 tools/validation_check.py && python3 tools/vocab_check.py
cargo test --all
```

## 실행 결과와 한계

2026-10-22에 이 워크트리(5cc3a09 기준)에서 실행:

- `git archive`로 꺼낸 87a19c5·839ecdb 각각 `cargo test --workspace`: 둘 다 위 표대로 단위·통합
  테스트 39개 + 문서 시험 3개 = 42건, 실패 0.
- `python3 -m unittest tools/tests/test_validation_test_counts.py -v`: 9개 통과(기대 실패 1개는
  BLUEPRINT 행이 아직 합친 숫자라서 의도된 것).
- `python3 -m unittest discover -s tools/tests`: 560개 실행, 전부 통과(skip 7개·기대 실패 1개).
- `python3 tools/vocab_check.py`: 통과(45축·228값). `python3 tools/validation_check.py`: 통과
  (14 표본·142 조항·26 gap). `--selftest`: 38종 변조 모두 의도한 사유로 적발.
- `cargo test --all`: 합계 388개 통과·실패 0(문서 시험 3개 포함, `onjeon_rules_engine`에만 있음).
  `cargo fmt --all -- --check` 통과.

한계: 39 + 3은 재실행 값이다. 당시 CI 작업 로그와 실행 ID는 저장소에 없으므로 "CI 로그 인용"은
못 하고 재실행 근거를 적었다. 318행의 "42개"는 2026-10-09 시점 값이며 현재 main의 합계(388)와
다르다. `docs/BLUEPRINT.md`는 이 작업의 수정 금지 문서라 위 교체안 반영은 문서 소유자 몫이다.
