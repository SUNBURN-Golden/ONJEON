# Audit 6 — 푸시 refspec 무검증 원격 쓰기

기록일: 2026-11-11. 노드: `audit6-daemon-push-refspec-validation`.
기준 커밋: `1f0ef65e06485e23551878d30ff783248db28602` + 이 노드의 미커밋 변경.
범위: T-OP-00·T-OP-09 개발 도구, G26(`fenced_write`). BLUEPRINT §11의 개발 도구 보강이며 [09 §5](../proposals/설계검토_결과/09_제품목적_대응표.md)의 출시 완성품 제외 항목이다. P01~P19의 실제 데이터·트윈·화면·출시 완료 증거를 대신하지 않는다.

## 발견과 수정 전 증거

실행기 검증 어댑터([adapters.py](../../../tools/daemon/runner_verify/adapters.py))의 `RealGit.push`와 `PushRemote.execute`는 작성자 요청의 `sha`·`branch`를 그대로 `<sha>:refs/heads/<branch>` refspec으로 조립해 `git push`에 넘겼다. `fencing.fenced_write`의 검사와 [규칙 데이터](../proposals/설계검토_결과/daemon_rules.json) 어디에도 두 값의 모양·소유 검사가 없었다. `--receive-pack=…` 같은 값은 refspec이 아니라 git 옵션으로 읽히고, `+` 접두사는 강제 푸시를 만들며, 잘린 sha는 git이 임의로 확장 해석하고, 다른 과제·보호 브랜치 이름은 원격이 거부하기 전까지 그대로 대상이 됐다.

[수정 전 로그](../../../tools/evidence/audit6-daemon-push-refspec-validation/before.log)는 기존 구현에 회귀 시험을 먼저 추가한 결과다. 모의 코어 시험 10개가 하위 사례 포함 실패 46건·오류 1건, 실제 git 원격 시험 3개가 실패 18건·오류 2건(종료 1)이었다. 정상 요청의 `--` 구분자·원격 반영 검사도 함께 실패했다.

## 구현 계약

- [규칙](../proposals/설계검토_결과/daemon_rules.json)의 `operations.fenced_write.checks` 마지막에 `push_refspec` 검사를 추가했다(`pred: push_refspec_valid == true`, `fail_key: invalid_refspec`). 실패 처리는 필수 필드 누락과 같은 R-13 `envelope_rejected_invalid`이며 inbox_seen을 점유하지 않고 상태·임대를 바꾸지 않는다. 기존 필수 식별자 → 임대 일치 → 중복 → 활성·만료 → 데몬 경유 순서 뒤에 놓아 우선순위는 그대로다. `pr_update`는 refspec이 없으므로 이 검사를 건너뛴다.
- [fencing.py](../../../tools/daemon/core/fencing.py)의 `push_refspec_valid`은 push 요청의 `sha`가 40자리 소문자 16진수 전체이고 `branch`가 임대 기록(`lease_record.branch`)의 브랜치와 완전히 같은지(시도 번호 포함)를 본다. 검사 목록·실패 키는 규칙 데이터에서 읽으므로, 데이터에서 이 검사를 빼면 회귀가 이를 잡는다.
- [adapters.py](../../../tools/daemon/runner_verify/adapters.py)의 `valid_push_refspec`은 어댑터가 임대 기록을 갖지 않으므로 같은 모양 검사에 과제 범위를 더한다: 브랜치는 `task/<task_id>-a<시도>` 꼴이고 과제가 요청의 과제와 같아야 한다. `RealGit.push`와 `PushRemote.execute`는 자격 조회 전에 이 검사를 반복하며, 실패 시 `PushFailed`를 올리고 원시 값은 로그에 남기지 않고 `invalid_refspec` 거부 사실만 `remote_writes.jsonl`에 기록한다. 두 푸시 경로 모두 refspec 앞에 `--` 구분자를 붙여 요청의 어떤 부분도 git 옵션으로 읽히지 않게 했다.

## 회귀 검증

- [`PushRefspecFencing`](../../../tools/tests/test_daemon_dry_run.py)(모의 코어, 7개): 잘못된 sha 15종·다른 브랜치·옵션 모양·`+` 접두사·refspec 확장 13종과 각각 누락이 R-13 noop(`failed_check: push_refspec`)이고 원격 쓰기·inbox_seen·상태가 변하지 않음을 검사한다. 거부는 키를 소비하지 않아 같은 봉투 ID의 수정 재전송은 실행된다. 정상 push·refspec 없는 pr_update는 계속 쓰고, 만료(R-11)·중복·데몬 우회의 기존 우선순위는 유지된다. 발송 직전 재검사(`check_write`)도 같은 검사를 평가하고, 규칙 데이터에서 검사를 지우면 악의 refspec이 원격 어댑터까지 통과함을 확인한다.
- [`PushRefspecAdapter`](../../../tools/tests/test_daemon_dry_run.py)(모의 git, 3개): 잘못된 refspec은 자격 조회·git 호출 전에 `PushFailed`가 되고 `remote_writes.jsonl`에 `invalid_refspec` 기록이 남는다. 두 푸시 경로 모두 인자 목록이 `push <원격> -- <refspec>` 순서임을 검사한다.
- [`PushRefspecGit`](../../../tools/daemon/runner_verify/tests/test_runner_verify.py)(실제 git 원격, 3개): 정상 push가 `--` 뒤 refspec으로 원격에 반영되고 pre-receive가 승인하며, 잘못된 16종(sha 9·branch 7)은 git·원격에 도달하지 않고 refs·push 로그가 그대로다. 보존(push) 경로는 같은 검사를 통과하고, 과제가 다른 정상 모양 브랜치는 자격 범위 문제로 원격이 거부한다.

실행 결과와 재현 명령은 [증거 안내](../../../tools/evidence/audit6-daemon-push-refspec-validation/README.md), [수정 전·후 로그](../../../tools/evidence/audit6-daemon-push-refspec-validation/after.log), [전체 데몬 시험](../../../tools/daemon/reports/unittest.log), [모의 시나리오](../../../tools/daemon/reports/dry_run.log)에 남긴다. 데몬 보고서의 소스 해시는 README에 명시한 절차로 갱신했고, [o13 픽스처](../../../tools/tests/fixtures/o13_unchanged_gates.json)는 `daemon_rules.json`의 구조 대조(추가된 검사·실패 키·설명 외 무변경) 뒤 해시를 갱신했다.

| 실행 | 결과 |
|---|---|
| 신규 회귀 `PushRefspecFencing`·`PushRefspecAdapter` | 10개 통과 |
| 신규 회귀 `PushRefspecGit`(실제 git 원격) | 3개 통과 |
| 전체 데몬 시험 | 299개 통과, 종료 0 |
| 전체 모의 시나리오 `--require-all` | 검사 692건 통과, 필수 ID 33/33, 누락·미등록·중복 0 |
| 전체 Python `unittest discover -s tools/tests -v` | 1,567개 실행, 실패·오류 0, skip 6, 종료 0 |
| `cargo +1.98.1 test --all --locked --offline` | 종료 0 |
| 온톨로지 실행기 `cargo test --locked --offline` | 종료 0 |

Python skip 6개는 기존과 같다(원본 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해서 해당하지 않는 구버전 거부 시험 1개). 새 회귀의 skip은 없다. 전체 Python 로그는 [여기](../../../tools/evidence/audit6-daemon-push-refspec-validation/python-tests.log), Rust 로그는 [여기](../../../tools/evidence/audit6-daemon-push-refspec-validation/rust-tests.log)와 [여기](../../../tools/evidence/audit6-daemon-push-refspec-validation/ontology-runner-tests.log)에 있다.

## 한계

임대 브랜치와의 일치 검사는 코어가 임대 기록으로 하고 어댑터는 모양·과제 범위만 검사하므로, 코어를 거치지 않는 경로의 임대 일치는 원격의 자격 범위(`RV_PUSH_CREDENTIAL`·pre-receive)가 막는다. 푸시 대상 URL 자체는 설정값이며 이 노드의 검사 대상이 아니다. 실제 GitHub·운영 원격, 상주 데몬 가동, 실데이터 접근, 첫 출시 관문은 이 변경이 승인하지 않는다.
