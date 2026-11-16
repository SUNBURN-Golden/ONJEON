# audit6-blueprint-s12-decisions-sync 검증 증거

기록일: 2026-11-16. 변경 내용·분류 근거는 [감리 기록](../../../docs/blueprint/audits/2026-11-16_blueprint_s12_decisions_sync.md)을 따른다.

원장 O01~O19에 결정 상태를 명시하고 §12의 기록된 결정·기록 없는 질문과
대조한다. 기존 결정·위임 지위·관문·`decisions_recorded`는 바꾸지 않았다.

| 로그 | 실행·종료 코드 | 결과 |
|---|---|---|
| [before.log](before.log) | 아래 기준 문서 대조, exit 1(예상 실패) | 동일 신규 시험 7건 실행, 실패 5건. 상태 열·현재 제목·증거 연결·O01/O04 행 부재 검출 |
| [focused.log](focused.log) | 아래 집중 시험, exit 0 | 100건 통과(신규 7건 포함) |
| [python-tests.log](python-tests.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -v`, exit 0 | 1,663건 실행, 실패·오류 0, 조건부 건너뜀 6 |
| [rust-tests.log](rust-tests.log) | `cargo test --all --locked --offline`, exit 0 | 532건 통과, 실패 0, 기존 무시 1 |
| [ontology-tests.log](ontology-tests.log) | 온톨로지 runner 디렉터리에서 `cargo test --locked --offline`, exit 0 | 4건 통과 |
| [blueprint-status.log](blueprint-status.log) | `python3 -I tools/blueprint_status.py`, exit 0 | 37개 ADR/DEC 색인 일치 |
| [blueprint-counts.log](blueprint-counts.log) | `python3 -I tools/blueprint_counts.py`, exit 0 | 실제 조항 규칙 7·변조 40·어휘 축 49·엔진 시험 266+doctest 3 일치 |
| [scope.log](scope.log) | Git diff·기존 원장 행 대조·`git diff --check`, exit 0 | 허용 경로만 변경, 보호 문서·19개 원장 행의 기존 다섯 열·작업 관문 보존 |

집중 시험은 저장소 루트에서 다음 명령으로 실행했다(표준 출력·오류는
`focused.log`로 저장).

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tools.tests.test_audit6_blueprint_decisions_sync \
  tools.tests.test_blueprint_s12_sync_decisions \
  tools.tests.test_audit5_decisions_ledger_sync \
  tools.tests.test_decisions_ledger_sync \
  tools.tests.test_decision_records \
  tools.tests.test_audit5_confirm_agent_made_decisions \
  tools.tests.test_purpose_table_decision_sync \
  tools.tests.test_o13_ruling -v
```

`before.log`는 최종 신규 시험에 수정 전 `HEAD:docs/BLUEPRINT.md`와
`HEAD:docs/blueprint/DECISIONS.md`를 입력한 결과다. `git show`로 두 파일을
이 증거 디렉터리 안의 임시 디렉터리에 복사하고, 시험 모듈의 `BLUEPRINT`·
`LEDGER` 경로만 `unittest.mock.patch.object`로 바꿔 실행했다. 작업 문서는
되돌리지 않았고 임시 파일은 실행 뒤 삭제했다. 전체 Python 자동 발견은
이 신규 시험과 기존 시험을 함께 실행한다. 상태 되돌림·열린 목록 이동·
미정 질문 누락 변이도 신규 시험 안에서 문서 문자열로 검증한다.

로컬 문서 정합성 증거이며 실제 전 상품 수집·트윈·소비자 UX·P01~P19
전체·첫 출시 완료 증거를 대신하지 않는다. 보호 문서는 수정하지 않았고
commit·push·GitHub 호출·비밀값 조회·실제 수집·배포를 수행하지 않았다.
