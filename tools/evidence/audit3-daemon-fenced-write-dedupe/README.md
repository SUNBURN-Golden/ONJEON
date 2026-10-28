# audit3-daemon-fenced-write-dedupe 검증 증거

최신 P1 경쟁 수정·재실행은 [fix-round1/README.md](fix-round1/README.md)를 참조한다. 아래 `before.log`·`after.log`·`python-tests.log`·`checks.log`는 초기 수정 당시의 기록이다. 공용 데몬 보고서 두 개는 fix round 1의 현재 소스 해시로 갱신했다.

기준 커밋 `835dba23f33e8fa871514f89512d2fcd16bc921a` + 이 노드의 미커밋 변경.
설명: [감리 기록](../../../docs/blueprint/audits/2026-10-28_daemon_fenced_write_dedupe.md).

| 증거 | 실행·범위 |
|---|---|
| `before.log` | 기존 구현에 초기 회귀 시험 9개만 추가한 실행. 실패 28건·오류 2건, 종료 1. 서로 다른 ID 시험은 통과 |
| `after.log` | 수정 구현의 회귀 시험 12개, 모두 통과. push·PR 갱신, 동시성, 롤백, 커밋·원격·완료 기록 실패와 FileStore 포함 |
| `python-tests.log` | `python3 -m unittest discover -s tools/tests -v`: 1,175개 실행, 실패·오류 0, skip 6, 종료 0 |
| `checks.log` | 어휘·검증 자료 및 selftest·설계 묶음·BLUEPRINT 등록 수·결정 색인 검사 |
| `../../daemon/reports/unittest.log` | 전체 데몬 코어 단위·회귀 시험, 소스 내용 해시 포함. 초기 257개, fix round 1 결과는 최신 증거 안내 참조 |
| `../../daemon/reports/dry_run.log` | 모의 검사 704건 통과·필수 시험 ID 33/33(누락·미등록·중복 0), 소스 내용 해시 포함 |

회귀 시험 재현:

```sh
python3 -m unittest tools.tests.test_daemon_dry_run.FencedWriteDedup -v
python3 -m unittest tools/tests/test_daemon_dry_run.py
python3 -m unittest discover -s tools/tests -v
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
cargo test --all
```

`cargo test --all`도 실행해 종료 0을 확인했다. 이 로그들은 개발 도구의 로컬 검증이며 실제 Git·GitHub 쓰기나 운영 원격·출시 검증 증거가 아니다.

Python skip은 원본 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개, 설치된 botocore에 해당하지 않는 구버전 거부 시험 1개다. 새 회귀와 데몬 시험은 모두 실행했다.
