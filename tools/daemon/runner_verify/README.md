# 실제 실행기 검증 도구 (T-OP-09, 가동 전)

T-OP-00의 모의 검증이 "규칙 파일대로 전이한다"까지만 증명하므로(05 §5), 같은 전이·검증 코어(`tools/daemon/core`)를 **실제 어댑터**로 돌려 05 §6의 R1~R22를 확인한다. 개발 도구다. 출시 완성품의 일부가 아니고(09 §5), 데몬도 아니며(상주 루프·스케줄러 없음), **완료가 가동 승인이 아니다**. 과제는 `T-MOCK-*`뿐이고 제품 브랜치에 쓰기·병합이 없다.

```sh
bash tools/daemon/runner_verify/run.sh --remote auto --report docs/vm_check/<날짜>/runner_verify.json \
  [--scenario R1,R5|<필수 시험 ID>] [--no-cli] [--time-scale 0.05]
python3 -m unittest tools/daemon/runner_verify/tests/test_runner_verify.py
```

`--remote`는 `auto`(버려지는 bare 저장소를 새로 만든다) 또는 **이 도구가 만든** 저장소의 경로다. URL과 제품 저장소는 거부한다(종료 코드 2). 실제 호스트의 보호 브랜치·단기 자격은 사람이 적용하는 설정(04 §8, 05 §4)이라 이 도구가 대신 만들지 못한다: 그 부분은 결과에 "증명하지 않은 것"으로 남는다. 하나라도 검사가 실패하거나 정적·로그 검사가 위반이면 종료 코드 1이다. 미확인은 기록되고 종료 코드를 바꾸지 않는다.

## 무엇이 실제이고 무엇이 아닌가

| 실제 | 대체물·한계 |
|---|---|
| 데몬 작업 하나가 별도 OS 프로세스(`daemon_main.py`). fault 지점에서 **SIGKILL**로 스스로 죽는다(finally·flush 없음) | 데몬이 아니라 한 번에 한 작업을 하는 프로세스다. 전원 차단은 시험하지 않았다 |
| 상태 저장소: 파일 하나, flock + 임시 파일 fsync + rename + 디렉터리 fsync. 동시 프로세스는 같은 잠금을 쓴다 | 하드웨어까지 쓰기 순서가 지켜지는지는 확인하지 못했다 |
| 빌더 프로세스: 자기 세션·프로세스 그룹, 실제 SIGTERM/SIGKILL, 실제 작업 트리 쓰기 | **스크립트 프로세스(`standin.py`)이지 벤더 CLI가 아니다.** claude CLI 하나만 시험 프록시에 붙여 R6·R7·R10·R9(변형)에서 실제로 돌렸다 |
| git: 실제 worktree, 임시 인덱스의 `git add -A` + `git write-tree`(트리 해시는 이 한 곳), `commit-tree`, 실제 push | 원격이 로컬 bare 저장소다 |
| 원격: 보호 브랜치(main·release/*), `task/T-MOCK-*`만 쓰기 가능, hook이 임대별 단기 자격(발급·회수·만료·범위)을 푸시 시점에 검사하고 모든 결정을 `rv/push_log.jsonl`에 남긴다 | 실제 Git 호스트의 설정·토큰 발급 API·거부 응답 형식은 아니다 |
| 전달 경로: 파일 큐(임시 파일 + rename), 로컬 HTTP | 네트워크 지연·재정렬은 없다 |
| 정지 확인: `/proc/<pid>/fd`·`fdinfo`로 쓰기 핸들 검사(이 호스트에 lsof 없음), mtime, tree OID 두 번 | |
| 가득 찬 디스크: user namespace의 64 KiB tmpfs를 git 객체 디렉터리로 | 저장소 전체가 찬 경우의 다른 실패 지점은 보지 않았다 |
| 시계: 실제 시각 + offset 파일. TTL·grace는 offset을 올려 지나가게 하고 `sleep`은 `--time-scale` 비율만 실제로 기다린다 | 이동한 총량은 보고서 `environment`에 적는다. `--time-scale 1`이면 모두 실제로 기다린다 |

## 구성

| 파일 | 내용 |
|---|---|
| `adapters.py` | 코어 포트의 실제 구현: `FileStore`, `ShiftedClock`, `ProcessFaults`(SIGKILL), `RemoteCredentials`, `GroupProcessControl`, `FsWorktree`, `RealGit`, `FileSender`, `PushRemote`, `ProbedBuilderPool` |
| `daemon_main.py` | 데몬 작업 한 개(`grant`·`event`·`submit`·`drain`·`tick`·`restart`·`observe`·`issue-credential`·`serve`). `--die-at 지점[@건너뛸 횟수]`로 SIGKILL |
| `remote.py`, `hook_pre_receive.py` | 시험 원격의 생성·거부 규칙. 표식 파일이 없는 저장소·URL·제품 저장소는 거부 |
| `standin.py` | `T-MOCK-*` 전용 스크립트 빌더(쓰기 루프, SIGTERM 무시, 하트비트, 봉투, 푸시, 다른 세션의 자식) |
| `proxy.py`, `cli_probe.py` | 시험 프록시(429·5xx·401·정상·붙잡기)와 벤더 CLI 시험. 원문은 저장하지 않고 상태 필드만 남긴다 |
| `harness.py`, `context.py`, `report.py` | 상태 디렉터리, 데몬 프로세스 실행, 빌더 쪽 어댑터(수신 검증·작업 트리·자격·프로세스 시작), 결과 기록 |
| `scn_*.py`, `registry.py` | R1~R22 시나리오와 필수 시험 ID 대응 |
| `reporting.py`, `static_checks.py`, `cli.py`, `run.sh` | 결과 파일, 정적·로그 검사, 진입점 |
| `fixtures/` | 시험 전용(`origin=fixture`, `fixture_only=true`): 모의 빌더 둘, 확인표의 CLI 목록 |

## 결과 파일 (`docs/vm_check/<날짜>/`)

`runner_verify.json`(전체), `runner_verify.log`(검사마다 기대·실제를 줄이지 않고), `RESULTS.md`(R별 표·실패·미확인·증명하지 않은 것), `exit_code_table.md`(05 §1b 채움), `summary.json`(05 §2 형식, 확인하지 않은 칸은 "미확인"), `static_checks.log`, `unittest.log`.

결과 값은 `PASS` / `FAIL` / `UNCONFIRMED`(측정할 수 없었음, 사유를 적는다) / `PARTIAL`(일부만 측정) / `GAP`(명세 문장과 관찰이 다르지만 그 R의 통과 기준은 아님)이다. 05 §6의 규칙대로 어느 장치에도 "검증됨"을 쓰지 않는다.

## T-OP-00 정적 검사와의 관계 (T-OP-00b에서 해결됨)

이 도구는 프로세스·git·시계·HTTP가 본질이라 T-OP-00 데몬 코어의 정적 검사(`tools/daemon/static_checks.py`)와 증거 해시(`tools/tests/test_daemon_dry_run.py`, `tools/daemon/README.md`의 해시 명령)를 통과할 수 없다. T-OP-00b(커밋 `1daa4d1`)가 `runner_verify/`를 그 두 검사의 대상에서 뺐다. 이 도구는 자체 `static_checks.py`와 `docs/vm_check/<날짜>/static_checks.log`로 따로 검사한다. 확인: `docs/vm_check/<날짜>/unittest_T-OP-00.log`(T-OP-00 시험, `runner_verify/`가 있는 작업 트리에서 통과).
