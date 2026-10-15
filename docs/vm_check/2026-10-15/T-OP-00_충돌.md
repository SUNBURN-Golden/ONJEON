# T-OP-09 도구가 T-OP-00의 정적 검사·증거 해시와 충돌하는 지점

작성 2026-10-15. 대상: 부모 커밋 `c74a545a45d1aba9eee71b76d81b3017ac16bbbb` 위에 `tools/daemon/runner_verify/**`·`docs/vm_check/**`를 얹은 작업 트리. **이 충돌은 해결되지 않았다.** 해결에 필요한 두 파일이 이 과제의 허용 경로 밖이라 고치지 않았다.

## 충돌 내용

| 명령 | 결과 |
|---|---|
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` (이 작업 트리) | **182건 중 11건 실패** |
| 같은 명령, `runner_verify/` 없이 부모 커밋만 | 통과(T-OP-00 증거 로그 `tools/daemon/reports/unittest.log`: 182건 OK) |
| 같은 명령, 아래 "필요한 변경"만 임시 사본에 적용 | 182건 중 **1건 실패**(증거 해시 시험만) |

실패 11건은 모두 두 원인에서 나온다.

1. `tools/daemon/static_checks.py`는 `tools/daemon/` 아래의 모든 `*.py`·`*.json`을 `rglob`으로 훑는다. 이 도구는 프로세스 실행·시계·HTTP·시그널이 본질이라 다음을 어길 수밖에 없다(`runner_verify` 소스에서 센 위반 건수).
   - 프로세스·네트워크 import와 호출(`subprocess`, `socket`, `http`, `signal.signal`): 17건
   - 벽시계 import(`time`, `datetime`): 15건
   - 스케줄러·상주 루프·시그널 문구: 3건 (`standin.py`의 시험용 하트비트 루프)
   - 둘째 해시 정의(`sha256`; 자격 토큰·호스트 식별의 해시): 3건
   - 모델 식별자 단어(CLI 이름이 확인표·시험에 나온다): 26건
   - 함수 이름의 `merge`(병합 함수가 *잡히는지* 보는 시험 `test_a_merge_function_would_be_caught`): 1건
   이 규칙은 T-OP-00 데몬 코어(그 자체는 상주·실행 기능이 없어야 한다)를 위한 것이고 옳다. 이 도구는 데몬 코어가 아니다.
2. `tools/tests/test_daemon_dry_run.py`의 `test_evidence_logs_name_the_parent_commit_and_source_hash`는 `tools/daemon/`(`reports/`·`__pycache__` 제외) 전체의 내용 해시를 `tools/daemon/reports/*.log` 머리말과 맞춘다. 파일을 하나 더하는 것만으로 해시가 달라진다.

## 필요한 변경 (T-OP-00 쪽 과제에서)

1. `tools/daemon/static_checks.py`: `_py_files`와 `no_model_identifiers`의 훑기에서 `runner_verify/` 하위를 제외한다. **제외로 풀리는 것은 데몬 코어 검사뿐이다.** `runner_verify`는 자체 `static_checks.py`(제품 브랜치 쓰기·병합 없음, 비밀값·모델 식별자·원문 누출 없음, 확인되지 않은 종료 코드 없음)와 `docs/vm_check/<날짜>/static_checks.log`로 따로 검사한다.
2. `tools/daemon/README.md`의 해시 계산 명령에서 `runner_verify/`를 제외하고, `tools/daemon/reports/dry_run.log`·`unittest.log`를 다시 만든다.

임시 사본(`git archive HEAD` + `runner_verify/` + 위 1번)에서 확인한 결과: 증거 해시 시험 하나만 남았고, 그것은 2번으로 풀린다. 이 변경은 작업 트리에 적용하지 않았다.

## 이 과제가 한 것과 하지 않은 것

- 한 것: 도구 자체의 정적 검사를 따로 두고 통과시켰다(`static_checks.log`). 파일 핸들·함수 이름 등 고칠 수 있는 것은 고쳤다.
- 하지 않은 것: T-OP-00의 두 파일을 고치지 않았다(허용 경로 밖). 위 11건은 이 과제의 결과가 아니라 열린 항목이다. T-OP-00 시험이 이 작업 트리에서 통과한다고 말하지 않는다.
