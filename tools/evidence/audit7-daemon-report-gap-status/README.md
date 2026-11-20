# Audit 7 실행기 보고서의 R1 상태 집계

2026-10-16 실행 보고서는 R1에 `GAP` 1건을 기록하면서 시나리오 결과를 `PASS` 14/15로 표시했다. 시험 원격의 직접 푸시 거부와 데몬 경유 봉투의 R-11 기록은 각각 관찰됐다. 두 관찰 사이의 연결은 `GAP`으로 남아 있다. [2026-10-16 보고서](../../../docs/vm_check/2026-10-16/RESULTS.md).

수정 전 회귀 시험에서 `GAP`만 있는 경우와 `PASS`와 `GAP`이 섞인 경우가 `PASS`, `UNCONFIRMED`와 `GAP`이 섞인 경우가 `UNCONFIRMED`로 집계됐다. CLI를 실행한 시험에서도 R1이 `PASS`로 집계됐다. 현재 집계는 이 네 경우를 `PARTIAL`로 표시한다. `FAIL`은 다른 검사 상태보다 우선한다. [집계 구현](../../daemon/runner_verify/report.py) · [회귀 시험](../../daemon/runner_verify/tests/test_runner_verify.py).

## 로컬 재실행

```sh
bash tools/daemon/runner_verify/run.sh --remote auto \
  --report target/audit7-daemon-report-gap-status/runner/runner_verify.json \
  --scenario R1,R19,R20 --no-cli
```

| 시나리오 | 상태 | 통과 검사 |
|---|---|---|
| R1 | PARTIAL | 14/15 |
| R19 | PASS | 6/6 |
| R20 | PASS | 5/5 |

새 보고서는 검사 26건 중 `GAP` 1건, 실패 0건, 미확인 0건을 기록했다. JSON의 `late-write-fenced` 항목과 콘솔·로그·`RESULTS.md`에 R1의 `PARTIAL` 상태가 표시됐다. 정적·로그 검사는 모두 통과했고 명령은 0으로 종료했다.

보존된 2026-10-16 JSON의 검사 결과를 수정된 집계 규칙으로 다시 계산하면 22개 중 `PASS` 16개, `PARTIAL` 6개, `FAIL` 0개, `UNCONFIRMED` 0개다. 저장된 값과 비교해 상태가 바뀐 행은 R1 하나다. 위 재실행은 임시 로컬 원격을 사용한 개발 도구 시험이며 T-OP-08 축 5의 운영 기록에 해당한다. [09 제품 목적 대응표 §5](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지).

## 프로젝트 검증

| 실행 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,767개 실행, 1,761개 통과, 6개 skip |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 80개 통과. 임시 로컬 원격을 사용했고 외부 벤더 CLI를 `PATH`에서 제외했다 |
| `cargo test --all --locked --offline` | 537개 통과, 1개 ignored |
| 시나리오 API와 온톨로지 실행기의 `cargo test --locked --offline` | 각 4개 통과 |
| 설계 묶음 `spec_check.py`, `check_product_purpose.py`, 데몬 `dry_run.py --scenario all --require-all` | 모두 통과. 모의 데몬은 검사 695건, 필수 시험 ID 33/33을 실행했다 |

Python 시험에서 건너뛴 6개는 보관 원본 경로가 필요한 2개, 로컬 보관소와 `pdftotext`가 필요한 3개, 설치된 botocore보다 오래된 버전을 대상으로 하는 1개다.
