# Audit 5 — tasks.json 시험 명령의 셸 구문 오류

대상: `audit5-tasks-json-shell-invalid-tests`.
연결: [`tasks.json`](../proposals/설계검토_결과/tasks.json), [`spec_check.py`](../proposals/설계검토_결과/검증/spec_check.py), 09 제품 목적 대응표 P06(검수·코드 검사).

## 판정과 변경

Audit 5가 보고한 대로 `tasks.json`의 `tests[]`와 `feature_registry[].acceptance_tests[]`에는
셸에서 실행되지 않는 시험 명령이 있었다. 보고된 줄 번호는 Audit 5 시점 기준이므로
현재 파일에서는 내용으로 확인했다.

- T-OP-09(진행 중 작업)의 `<시험용 원격>`·`<날짜>`, T-CT-01의 `<prev_tag>`는 셸이
  리다이렉션으로 읽는다.
- T-CT-05·T-KN-04·T-KN-06의 명령 뒤 괄호 설명, T-OP-03·T-OP-06·T-OP-07·T-UX-01의
  괄호뿐인 설명은 셸 구문 오류다.
- T-AP-02·T-PS-03·T-TW-05와 `feature_registry`의 `me`·`collect`·`labeling`·
  `multi-contract`·`twin-multi`·`consent-deletion`·`no-denominator-signal`은
  `cargo test`에 위치 인자 필터를 둘 이상 넘긴다. `cargo test`는 TESTNAME 필터를
  하나만 받는다.

`spec_check.py`에 G48을 추가했다. 인용부호 밖의 글자만 보는 `unquoted_view`로
`<…>` 자리표시자와 인용하지 않은 괄호를 찾고, 첫 토큰이 명령 이름인지 확인한다.
`cargo_test_filters`는 `-p`·`--test`·`--features`처럼 값을 받는 옵션과 `--` 뒤를
제외하고 위치 인자만 세어 둘 이상이면 실패한다. `시험 …`으로 시작하는 줄은
T-OP-00 필수 시험 ID·수동 증거를 적는 설명이므로 명령 검사에서 건너뛴다.
셸 구문은 과제 시험을, `cargo test` 필터 수는 과제 시험과 기능 수락 시험을 모두
본다(기능 수락 시험은 명령과 산문이 섞여 있어 셸 구문은 보지 않는다). 검사 대상이
0개면 통과가 아니라 실패한다(비공허성).

`tasks.json`·`feature_registry`의 해당 명령은 셸에서 실행 가능한 한 줄 명령으로
고쳤다. T-OP-09는 `$TEST_REMOTE`·`$RUN_DATE`, T-CT-01은 `$PREV_TAG` 환경 변수를
쓰고, T-CT-05는 실제 경로인 `infra/db/public/test.sh`를 부른다. 두 필터 명령은
필터별 명령으로 나눴다. 수동·측정 항목은 기존 관례대로 `시험 …` 설명으로 바꿨다.
`03_작업명세.md`의 같은 칸도 맞췄고, `07_수정대응표.md`에 A-05를 기록했다.

## 회귀와 변이 검증

[`test_spec_check_shell.py`](../../../tools/tests/test_spec_check_shell.py)는
`spec_check.py`를 importlib로 읽어 15개 시험을 실행한다.

- 실제 번들의 모든 검사가 통과하는 기준선.
- `<시험용 원격>`·`<날짜>`·`<prev_tag>`와 괄호 설명·산문 첫 토큰을 거부하고,
  인용한 자리표시자와 진짜 입력 리다이렉션 `< 경로`는 허용한다.
- `cargo test` 필터 하나는 허용, 둘 이상은 거부하며 `--test`·`--features` 값과
  `--` 뒤는 필터로 세지 않는다.
- 과제 시험과 `feature_registry` 수락 시험 각각에 잘못된 명령을 주입하면 G48이
  해당 과제·기능 ID와 함께 실패한다.
- `시험 …` 설명을 추가하면 건너뛴 수만 늘고 검사한 명령 수는 그대로다.
- 모든 시험 목록을 비우면 G48이 0개 검사로 실패한다.

[`check_old_commands.py`](../../../tools/evidence/audit5-tasks-json-shell-invalid-tests/check_old_commands.py)는
보고된 12개 셸 오류 명령과 10개 두 필터 명령을 그대로 넣어 전부 검출되는지 보고,
현재 같은 과제·기능의 명령이 모두 통과하는지 확인한다. 디스크의 번들은 쓰지 않는다.

## 실행 증거와 한계

2026-11-10 이 작업 트리에서 실행한 명령·결과는
[증거 안내](../../../tools/evidence/audit5-tasks-json-shell-invalid-tests/README.md)에 기록한다.

G48은 `tasks.json`의 명령 문자열이 셸 구문으로 파싱되는지만 본다. 명령이 실제로
성공하는지, 참조한 스크립트·바이너리가 존재하는지, 환경 변수가 채워지는지는
검사하지 않는다(경로 존재는 `check_bootstrap.py`의 별도 자문 검사가 본다).
`시험 …`으로 시작하면 내용과 무관하게 건너뛰므로 설명 줄에 명령을 넣는 관례는
검사 대상이 아니다. 이 증거는 설계 번들의 정적 정합성 검증이며 실제 데몬·서비스
동작이나 첫 출시 완료 증거를 대체하지 않는다.
