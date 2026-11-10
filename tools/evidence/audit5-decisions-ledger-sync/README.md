# audit5-decisions-ledger-sync evidence

기록일: 2026-11-10. 노드: `audit5-decisions-ledger-sync`.
감리 지적: 원장 O01이 ADR-0018 이후에도 열린 결정으로 보였고, 등록부
우체국 행이 "범위 결정 대기"로 남았으며, O16이 DEC-D-12 이후에도 열린
결정으로 보였고, DEC-* 기록의 원장 행이 없었으며, 이전 원장의 두 자리
확정 방향 ID가 DEC-D-02·DEC-D-04 실행 게이트와 혼동될 수 있었다.

수정: O01·등록부·DEC 전체 색인은 Audit 2·Audit 4의 정정을 유지했다.
이 노드는 O16 행을 `해결(앱 표시 결정 질문)`으로 바꾸고 DEC-D-12의
남은 조건을 분리했으며, §1·§2에 확정 방향(`BP-D-*`)과 실행 결정
게이트(`DEC-D-*`)의 ID 혼동 해소를 명시했다. 결정 내용·승인 상태·관문은
바꾸지 않았다.

## 로그

| 파일 | 명령 | 결과 |
|---|---|---|
| [before.log](before.log) | 수정 전 문서에 새 회귀 시험 실행 | 3건 실패(O16·ID 혼동·증거 링크) |
| [focused.log](focused.log) | `test_audit5_decisions_ledger_sync` + 기존 원장·결정·등록부 시험 | 모두 통과(신규 6건 포함) |
| [python-tests.log](python-tests.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -v` | 1,474건 실행, 실패·오류 0, 건너뜀 6 |
| [status.log](status.log) | `python3 -I tools/blueprint_status.py`·`git diff --check`·`git status` | §11 결정 색인 37개 ADR/DEC 일치, 공백 오류 없음 |
| [counts.log](counts.log) | `python3 -I tools/blueprint_counts.py` | 규칙 7·변조 40·축 49, Rust 248 + doctest 3 |

`before.log`와 `focused.log`는 같은 시험 파일을 수정 전·후 문서에 실행한
결과다. 전체 Python 시험은 기존 `tools/tests` 자동 발견으로 새 시험을
포함한다. Cargo·온톨로지 코드는 이 노드에서 변경하지 않았으므로 Rust
시험은 실행하지 않았고, 그 사실을 결과에 숨기지 않는다.

## 범위

문서 정합성 수정이며 실제 공시 데이터 접근·수집·배포·출시 완료 증거가
아니다. O16의 저장소 공개 범위·새 원문 발췌 추가 조건과 DEC-D-12의
공개 저장소 발췌 제한은 그대로 남는다. `docs/PRINCIPLES.md`, `docs/data/`,
`docs/design/CONSUMER_FLOW_SPEC.md`, `DECISION_REQUIRED.md`는 수정하지
않았다. commit·push·GitHub 호출·비밀값 조회·외부 저장소 접근은 수행하지
않았다.
