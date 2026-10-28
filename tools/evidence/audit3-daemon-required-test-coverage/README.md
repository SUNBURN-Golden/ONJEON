# audit3-daemon-required-test-coverage 실행 증거

기준 커밋 `b7aed69f98ee3d943ca105287b7b3679e7308bcb` + 이 노드의 변경. [감리 수정 기록](../../../docs/blueprint/audits/2026-10-28_daemon_required_test_coverage.md). T-OP-00 개발 도구의 시험 커버리지 증거이며 09의 P01~P19 출시 완료 증거가 아니다.

| 증거 | 실행·결과 |
|---|---|
| [before.log](before.log) | 빈 함수 회귀 2개, 하위 사례 실패 34건: 필수 ID 각각 33건과 무표기 시나리오 1건. 수정 전에는 검사가 없어도 CLI 종료 0 |
| [after.log](after.log) | 신규 등록/함수 변이 7개와 양방향 CLI·빈 실행 회귀 6개, 총 13개 통과 |
| [regressions.log](regressions.log) | 신규 등록/함수 변이·설계 검사 cond/vacuous·정적 검사 회귀 69개 통과 |
| [전체 데몬 시험](../../daemon/reports/unittest.log) | `python3 -m unittest tools/tests/test_daemon_dry_run.py -v`: 269개 통과 |
| [전체 기대·실제 값](../../daemon/reports/dry_run.log) | `--scenario all --require-all`: 49개 시나리오, 검사 692건 통과, 필수 ID 33/33, 누락·미등록·중복 0 |
| [coverage.json](coverage.json) | 위 실행 로그에서 추출·대조한 정본 필수 ID 33개별 M 번호·통과 검사 수. STATIC은 정적 13개 + 설명 키 비교 2개 = 15개 |
| [python-tests.log](python-tests.log) | `python3 -m unittest discover -s tools/tests -v`: 1,210개, 실패·오류 0, skip 6 |
| [rust-tests.log](rust-tests.log) | `cargo test --all`: 통과, 기존 fixture 재생성 시험 1개 ignored |
| [spec-check.log](spec-check.log) | G12b 포함 기계 45/45·존재 72/72 통과 |
| [checks.log](checks.log) | 정적 CLI 13개·어휘·검증 자료·변조 selftest 38개·BLUEPRINT 결정 색인/수치·제품 목적 대응표 검사 통과 |
| [manifest.json](manifest.json) | 소스·시험·증거 파일 해시와 검증 결과 |

모든 성공 실행의 종료 코드는 0이다. Python skip 6개는 로컬 원본 보관소 미설정 2개, 보관소·pdftotext 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해 적용되지 않는 구버전 거부 시험 1개다. 신규 커버리지 회귀와 데몬 시험에는 skip이 없다.

등록 삭제·함수 정의 삭제·빈 실행은 필수 ID **각각 33개 전부**에 적용한다. 기존 16개 코어와 나머지 17개 흐름 시나리오 모두를 같은 기준으로 검사한다. 함수 목록은 소스를 실행하지 않고 AST로 읽으며 실제 실행 목록과 일치함도 시험한다. 기존 G12의 과제 필드들은 모두 남긴 채 등록 목록만 비우면 G12b와 설계 검사 CLI가 실패하는 회귀도 포함한다.

설계 묶음의 [실행로그_dry_run.txt](../../../docs/blueprint/proposals/설계검토_결과/검증/실행로그_dry_run.txt)는 현재 `--quiet` 전체 출력이며, `Coverage.test_dry_run_reports_all_required_ids_run`이 매 실행마다 대조한다. [실행로그_spec_check.txt](../../../docs/blueprint/proposals/설계검토_결과/검증/실행로그_spec_check.txt)도 현재 검사 결과로 갱신했다. 데몬 공용 로그의 소스 해시는 `d904a958d52c7eb3b8098021ff87179c19f46ef2918bc15af0fff1386a513a77`이며 [기존 해시 절차](../../daemon/README.md#증거-기록reports)와 `Cli.test_evidence_logs_name_the_parent_commit_and_source_hash`로 대조한다.

재현:

```sh
python3 -m unittest tools/tests/test_daemon_required_test_coverage.py -v
python3 -m unittest tools/tests/test_daemon_dry_run.py -v
python3 -m unittest discover -s tools/tests -v
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet
python3 -I tools/daemon/static_checks.py
cargo test --all
git diff --check
```

AST 검사는 등록 형식·지역 함수 정의의 존재만 확인한다. 실행 통과는 CLI와 unittest가 별도로 확인한다. 남아 있는 명세 공백 8건은 dry-run 요약에 그대로 표시한다. 이번 변경은 그 공백·실제 제공자 실행·제품 데이터·소비자 화면·출시 준비 완료를 주장하지 않는다. 작업 트리에서 커밋·푸시하거나 GitHub를 호출하지 않았다.
