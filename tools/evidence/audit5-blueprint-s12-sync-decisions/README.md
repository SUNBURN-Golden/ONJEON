# audit5-blueprint-s12-sync-decisions evidence

기록일: 2026-11-10. 노드: `audit5-blueprint-s12-sync-decisions`.
감리 지적: BLUEPRINT §12가 DEC 기록이 이미 해결한 결정 질문(D-02, D-03,
D-08, D-12/O16, O12, O14, O17)을 열린 결정처럼 나열했다.

수정: §12를 `12.1 결정 기록으로 해결된 사항`과 `12.2 아직 결정되지 않은
사항`으로 나눴다. 감리 지적 항목은 DEC 링크·남은 조건과 함께 §12.1에
두고, §12.2에는 결정 기록이 없는 O19·O15·색 토큰·공개 웹 도메인만
남겼다. 결정 내용·승인 상태·관문은 바꾸지 않았다.

## 로그

| 파일 | 명령 | 결과 |
|---|---|---|
| [before.log](before.log) | `git show HEAD:docs/BLUEPRINT.md`로 되돌린 §12에서 새 회귀 시험 실행 | 7건 실패(§12.1 없음·12.2의 미해결 행) |
| [focused.log](focused.log) | `test_blueprint_s12_sync_decisions` + 기존 §12·결정·보관소 관련 시험 | 모두 통과(신규 7건 포함) |
| [python-tests.log](python-tests.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -v` | 1,466건 실행, 실패·오류 0, 건너뜀 6 |
| [rust-tests.log](rust-tests.log) | `cargo test --all --locked --offline` | 513건 통과, 실패 0, 무시 1 |
| [ontology-tests.log](ontology-tests.log) | `cd docs/blueprint/proposals/온톨로지/검증/runner && cargo test --locked --offline` | 4건 통과 |
| [status.log](status.log) | `python3 -I tools/blueprint_status.py` | 37개 ADR/DEC 색인 일치 |
| [counts.log](counts.log) | `python3 -I tools/blueprint_counts.py` | 규칙 7·변조 40·축 49·Rust 248+doctest 3 |
| [scope.log](scope.log) | `git status`·`git diff --stat`·보호 문서 대조 | 허용 경로만 변경, 보호 문서 불변 |

`before.log`와 `focused.log`는 같은 시험 파일을 수정 전·후 문서에 실행한
결과다. 전체 Python 시험은 기존 `tools/tests` 자동 발견으로 새 시험을
포함한다. Rust 시험 수는 무시된 시험 1건을 포함하지 않는다.

## 범위

문서 정합성 수정이며 실제 공시 데이터 접근·수집·배포·출시 완료 증거가
아니다. `docs/PRINCIPLES.md`, `docs/data/`, `docs/design/CONSUMER_FLOW_SPEC.md`,
`DECISION_REQUIRED.md`는 수정하지 않았다. commit·push·GitHub 호출·비밀값
조회·외부 저장소 접근은 수행하지 않았다.
