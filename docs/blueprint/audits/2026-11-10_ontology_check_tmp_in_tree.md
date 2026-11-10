# Audit 5: 온톨로지 검사 임시 규칙 파일 격리

2026-11-10. 노드 `audit5-ontology-check-tmp-in-tree`의 로컬 검증 기록이다.
BLUEPRINT A1·A2·A5, Q5·Q7, L6, I3·I16·I18, 기반 M0와 09 P08·P14의 검증 도구에 연결한다.

`with_bad_rule()`은 저장소의 `규칙/_tmp_bad.json`을 공유했다. 프로세스가 강제 종료되면
이 파일이 남고, 두 실행은 같은 파일을 덮어쓰거나 다른 실행이 사용하는 파일을 삭제할 수 있었다.
이제 `tempfile.NamedTemporaryFile`로 호출마다 OS 임시 디렉터리에 JSON 파일을 만들고,
쓰기 버퍼를 비운 뒤 절대 경로를 콜백에 전달한다. 컨텍스트가 정상 반환·예외·인터럽트 때
파일을 닫고 삭제한다. 원본 규칙 읽기도 컨텍스트로 닫는다.

SIGKILL은 Python 정리 코드를 실행하지 않으므로 OS 임시 디렉터리의 파일은 남을 수 있다.
저장소에는 임시 파일을 쓰지 않으며 다른 실행은 별도의 이름을 사용한다.
강제 종료 회귀 시험은 부모가 소유한 외부 임시 디렉터리로 자식의 임시 파일을 제한해
검증 후 잔여물을 정리한다.

## 검증 증거

- [회귀 시험](../../../tools/tests/test_ontology_check_tempfile.py) 6개: 완성된 JSON·반환값·원본 보존,
  K9 근거 이탈·K15 동결 해시 위반 검출, 콜백 예외·KeyboardInterrupt 정리·전파,
  직렬화 실패 정리, 겹친 두 호출의 독립성, SIGKILL 후 규칙 디렉터리 바이트·파일 목록 보존.
- [수정 전 재현](../../../tools/evidence/audit5-ontology-check-tmp-in-tree/baseline-regression.log):
  HEAD의 함수만 메모리에서 실행하면 새 경로 회귀 시험이 실패한다. 예상 실패를 확인했고
  기존 함수의 정리 코드가 실행된 뒤 저장소에 임시 파일이 없는 것도 확인했다.
- [집중 시험](../../../tools/evidence/audit5-ontology-check-tmp-in-tree/focused-tests.log): 6개 통과.
- [실제 검사 동시 실행](../../../tools/evidence/audit5-ontology-check-tmp-in-tree/concurrent-check.json):
  두 프로세스 모두 종료 코드 0, 표준 출력 동일, 규칙 디렉터리 변경·기존 임시 파일 없음.
  [검사 출력](../../../tools/evidence/audit5-ontology-check-tmp-in-tree/ontology-check.log)은
  질문 11/11, 제약 15/15, 릴리스·문서 모델 25/25, 금액 10/10 통과다.

전체 Python 시험은 1,449개 실행·실패 0·기존 skip 6개, Rust 워크스페이스는
513개 통과·기존 ignored doctest 1개, 온톨로지 실행기는 4개 통과다.
명세·제품 목적·BLUEPRINT 수치·결정 색인 검사도 통과했다.
명령·결과는 [증거 안내](../../../tools/evidence/audit5-ontology-check-tmp-in-tree/README.md)에 기록한다.
기존 Python CI 전체 탐색이 새 회귀 시험을 실행한다.

이 finding의 완료 증거는 `fixture_only` 규칙을 사용하는 검증 도구의 격리·정리에 한정한다.
실제 상품 트윈·릴리스·소비자 화면·P08/P14 전체·첫 출시 완료 증거를 대체하지 않는다.
