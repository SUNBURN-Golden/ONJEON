# Audit 5 설계 묶음 정본 상태 문구 범위 축소 검증 증거

검증일: 2026-11-11 (fix round 2 재검증; round 1 2026-11-10). 노드: `audit5-canonize-design-bundle`.
결정 기록: [docs/decisions/audit5-canonize-design-bundle.md](../../../docs/decisions/audit5-canonize-design-bundle.md).

## 변경 요약

기존 공통 상태 문구 `묶음 전체·온톨로지·daemon_rules.json·common_done_criteria는 이번 정본 채택 대상이 아니다`는 이미 채택된 09·tasks.json까지 정본 미채택으로 읽힐 수 있었다. 이를 비구동 잔여물만 가리키도록 바꿨다.

> 묶음의 나머지(01~08, 온톨로지 제안, U-01~U-04, A-01)와 common_done_criteria, daemon_rules.json은 이번 정본 채택 대상이 아니다.

이 문구를 네 개의 상태 문장(`설계검토_결과/README.md:10`, `tasks.json` `_status`, `daemon_rules.json` `_status`, `그록봇_인계/README.md:3`)과 `09_제품목적_대응표.md` 머리말, `DEC-BUNDLE-STATUS.md`, 결정 원장(BP-D-20·DEC-BUNDLE-STATUS 색인 행), `BLUEPRINT.md` §11에 함께 적용했다. 요약 행 두 곳(루트 `README.md` 묶음 행, `BLUEPRINT.md` §7.2)도 같은 범위로 바꿨다. `daemon_rules.json`은 실행 기준이라는 점을 문구에서 계속 명시한다. `tools/tests/test_pr_policy.py`는 새 문구가 위 문서들에 있고 기존 넓은 문구가 없음을 검사하며(`test_scoped_exclusion_covers_every_status_statement_and_the_ledger`), 요약 행 두 곳은 `test_root_readme_and_blueprint_summary_scope_the_exclusion`이 고정한다. 기존 문구를 요구하던 `test_decision_records.py`·`test_decisions_ledger_sync.py`의 대조 문구도 함께 갱신했다.

`daemon_rules.json`의 `_status`가 바뀌어 O13 회귀 시험의 고정 SHA-256을 갱신했다. 같은 시험이 대조하는 `task_gates`·`decision_index`·`ledger_rows`는 바뀌지 않았고, `daemon_rules.json`의 변경은 `_status` 한 줄뿐이다.

## Fix round 2 경과

Round 1 검토(st_design_review)는 BLOCK이었다: 검토된 head(afeaf35)에 결정 기록만 커밋되고 문구·시험·증거는 커밋되지 않은 작업 트리 상태였기 때문이다. Round 2에서 작업 트리의 전체 변경 묶음을 다시 대조하고 아래 검증을 모두 재실행했다. 이 수정은 문구·시험·픽스처·결정 기록·이 증거 디렉터리가 함께 커밋될 때만 해소된다.

## 검증

저장소 루트에서 실행했다. Rust는 README의 로컬 시험 절차대로 작업 트리 경로에 rustup 재정의(1.98.1)를 등록하고 오프라인으로 실행했다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `env -u CARGO_TARGET_DIR python3 -m unittest tools.tests.test_pr_policy tools.tests.test_decision_records tools.tests.test_decisions_ledger_sync tools.tests.test_o13_ruling -v` | 75개 통과, 실패·오류 0 | [집중 시험](focused.log) |
| `env -u CARGO_TARGET_DIR python3 -m unittest discover -s tools/tests -v` | 1,532개 실행·1,526개 통과·기존 건너뜀 6, 실패·오류 0 | [Python 전체](python-tests.log) |
| `cargo test --all --locked --offline` | 70개 시험 묶음·514개 통과, 실패 0 | [Rust 시험](rust-tests.log) |
| `(cd docs/blueprint/proposals/온톨로지/검증/runner && cargo test --locked --offline)` | 4개 통과, 실패 0 | [Rust 시험](rust-tests.log) |
| `python3 -I tools/blueprint_status.py` | ADR/DEC 37개 파일 색인 일치 | [상태 검사](blueprint-status.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 09 P01~P19 작업 연결·9개 필수 시험 ID 등록 일치(정적) | [목적 대응표 검사](product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 46/46·존재 72/72 통과 | [설계 명세 검사](spec-check.log) |
| 적용 문구 존재 확인(8개 문서·요약 행 2곳)과 넓은 문구 잔존 위치 | 각 문서 1회, 결정 원장 2행, 요약 행 각 1회. 넓은 문구는 결정 기록 인용·회귀 상수·이 증거 인용에만 존재 | [문구 범위](scoped-wording.log) |
| `python3 -m json.tool` (tasks.json, daemon_rules.json) | 두 파일 모두 유효한 JSON | [JSON 구문](json-parse.log) |

건너뜀 6개는 round 1과 같은 기존 환경 건너뜀이다(`ONJEON_ARCHIVE_RAW` 미설정 2, botocore 버전 1, 로컬 아카이브·pdftotext 필요 3).

## 한계

이 증거는 문서·권위 문구의 정합성과 회귀 시험 통과만 확인한다. 09 P01~P19의 실제 수집·검수·트윈·소비자 화면·출시 완료 증거를 대신하지 않는다. Rust 코드는 바뀌지 않았으며 Rust 시험은 CI가 실행하므로 함께 통과만 확인했다. `spec_check.py`는 명세 구조·문구·그래프만 보는 정적 검사다.