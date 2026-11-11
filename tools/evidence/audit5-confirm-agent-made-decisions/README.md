# audit5-confirm-agent-made-decisions evidence

기록일: 2026-11-11. 노드: `audit5-confirm-agent-made-decisions` (fix round 1).
감리 지적: DEC-D-02·D-07·D-08·D-16·O04·O12 여섯 기록은 "Fable autoloop"이
만들었고, D-16은 80%/90% 통과 임계값·동일 오해 3명 규칙·확인 회차 12명이
저장소 어디에도 근거 없는 제안값이라고 스스로 인정한다. 소유자가 이들을
확정( ratify )해야 하는가?

결정: `docs/decisions/audit5-confirm-agent-made-decisions.md`는 소유자를 대신한
확정을 거부한다 — 확정(사용자 확정)은 소유자 전용 행위이고, autoloop이 자기
기록을 확정하는 것은 ADR-0006 §5·DEC-D-02 보기 D·DEC-D-08·audit4-dec-record-authority가
금지하는 자기 승인이다. 여섯 기록은 audit4의 '잠정 autoloop 기록(위임 전)'
분류대로 잠정·가역 위임 개발 기준으로 유지하고, 확정은 기록별 체크리스트로
소유자에게 전달한다(D-07·D-08·O04·O12 원문대로 확정 권고, D-02는 구성 원칙·
정책 소유자만 권고하고 지출·계정·키·접근 확인은 별도 사용자 조치). D-16의
근거 없는 수치는 작업 기준(최소 bar, 통계적 증명 아님)으로 유지하되, 첫 세션 전
docs/ux-tests/PREREG.md에 소유자 확인 또는 교체를 기록해야 하고, 소유자 확인
없는 기준의 확인 회차는 '이해됨'·출시 관문 9(09 P18)의 근거가 못 된다.
tasks.json 관문·데몬 규칙·DEC 기록·원장 행은 바꾸지 않았다.

fix round 1의 국소 시험 실패 둘: (1) cargo rustup 오류는 환경 문제였다 — 새
작업 트리에 README가 요구하는 rustup 재정의가 없어 기본 도구 체인을 선택하지
못했다. README 준비 절차(재정의 + 두 작업 공간 `cargo fetch --locked`)로
해결했다. (2) ResourceWarning은 실제 위생 결함이었다 — tools/verify_sources.py
rows()가 samples.csv를, ontology_check.py가 tbox·abox·규칙 JSON을 닫지 않고
열었다. 둘 다 컨텍스트 매니저로 고치고 회귀 시험을 추가했다
(test_verify_sources.py RowsFileHandling, test_ontology_check_file_handles.py).
전체 Python 시험은 이제 ResourceWarning 없이 실행된다.

## 로그

| 파일 | 명령 | 결과 |
|---|---|---|
| [prep.log](prep.log) | `rustup override set --path "$PWD" 1.98.1` + 두 작업 공간 `cargo fetch --locked` | 재정의 등록, 잠금 의존성 캐시 완료 |
| [focused.log](focused.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -p 'test_audit5_confirm_agent_made_decisions.py' -v` | 신규 회귀 시험 22건 전체 통과 |
| [focused-hygiene.log](focused-hygiene.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest tools.tests.test_verify_sources tools.tests.test_ontology_check_file_handles tools.tests.test_ontology_check_amounts tools.tests.test_ontology_check_tempfile tools.tests.test_ontology_runner_io_error -v` | 66건 통과(건너뜀 3), ResourceWarning을 오류로 승격해도 누수 0 |
| [python-tests.log](python-tests.log) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/tests -v` | 1,583건 실행, 실패·오류 0, 건너뜀 6, ResourceWarning 0 |
| [cargo-tests.log](cargo-tests.log) | `cargo test --all --locked --offline` + 온톨로지 실행기 `cargo test --locked --offline` | 71개 스위트 518건 통과, 실패 0, ignored 1 |
| [status.log](status.log) | `git status --short`·`git diff --check`·`python3 -I tools/blueprint_status.py` | 허용 경로 내 변경뿐, 공백 오류 없음, §11 결정 색인 일치 |

건너뜀 6건은 이 환경에 없는 선택 의존성 때문이다(비공개 원본 보관소
`ONJEON_ARCHIVE_RAW` 2건, 로컬 아카이브·pdftotext 3건, botocore If-None-Match
지원 1건). 이전 라운드와 같은 건너뜀 프로파일이다.

## 범위

- 이 증거는 결정 기록의 근거 대조(여섯 DEC 원문·audit4 분류·원장 §3.1·
  BLUEPRINT §12.1·ADR-0006 §5·tasks.json 관문·09 P18·T-UX-01 완료 기준)와
  회귀 시험 실행만 검증한다. 소유자 확정, D-02 지출·계정·키 발급·접근 확인,
  D-16 수치 확인과 PREREG 작성(T-UX-01 소관)은 여전히 사용자 조치와 후속
  과제의 몫이며 이 노드에서 수행하거나 승인하지 않았다.
- 신규 회귀 시험은 소유자 전용 확정 경계·승격 금지, 여섯 기록의 위임 표기와
  D-16의 근거 없음 인정, 변하지 않은 관문, PREREG 소유자 확인 훅(커밋 뒤에는
  내용까지 검사)을 고정한다. 위생 회귀 시험은 rows()·ontology_check.py의
  파일 핸들 누수를 고정한다(이전 코드는 시험에서 실제로 누수를 재현함).