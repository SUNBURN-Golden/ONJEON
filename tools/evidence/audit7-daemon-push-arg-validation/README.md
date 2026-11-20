# Audit 7 데몬 푸시 인자 검증

기준 커밋 `63ead4d39da4bf828f5b55888d96f37fccbb3923`에는 SHA 형식 검사와 Git 인자 구분자 `--`,
코어의 리스 브랜치 비교가 이미 적용돼 있었다. 어댑터에 직접 전달한 같은 작업의 다른 시도 브랜치는
기존 작업별 브랜치 패턴을 통과했다. Git을 모의한 신규 시험을 먼저 실행해 거부 예외가 발생하지 않는
것을 확인했다(`PushFailed not raised`, 종료 1).

`PushRemote.execute`는 코어가 발송 잠금을 유지하는 동안 같은 저장소의 커밋된 스냅샷을 읽는다.
요청의 40자리 소문자 16진수 SHA와 작업 브랜치 형식을 검사하고, 브랜치와 리스 ID가 저장된 현재 리스와
일치할 때만 그 리스의 쓰기 자격을 조회한다. 검증된 SHA와 저장소에서 읽은 브랜치로 refspec을 만들고
`--` 뒤에 전달한다. 브랜치 검증 실패 기록에는 거부된 요청의 SHA나 브랜치가 포함되지 않는다.
[어댑터 구현](../../daemon/runner_verify/adapters.py).

## 회귀 증거

- `PushRefspecAdapter`는 잘못된 SHA와 브랜치 형식, 같은 작업의 다른 시도, 리스 또는 저장된 브랜치 누락,
  현재 리스와 다른 ID가 모두 자격 조회와 Git 실행 전에 거부되는 것을 검사한다. 정상 인자 벡터와
  인계 보존 푸시도 확인한다. [단위 시험](../../tests/test_daemon_dry_run.py).
- `PushRefspecGit`는 잘못된 입력과 다른 시도 브랜치가 Git 호출·원격 ref·원격 기록에 영향을 주지 않고,
  정상 요청의 SHA는 정확한 리스 브랜치에 반영되는 것을 임시 로컬 bare 저장소에서 확인한다.
  [로컬 Git 회귀](../../daemon/runner_verify/tests/test_runner_verify.py).
- 두 시험 클래스와 `PushRefspecFencing`, `FencedWriteDedup`을 묶어 실행한 32개 시험이 통과했다.
  모의 시나리오 검사는 695건, 필수 시험 ID는 33/33이다. [모의 시나리오 기록](../../daemon/reports/dry_run.log).

## 프로젝트 검증

| 실행 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -v` | 1,765개 실행, 1,759개 통과, 6개 skip |
| `python3 -m unittest tools.tests.test_daemon_dry_run -v` | 318개 통과. [공용 데몬 시험 기록](../../daemon/reports/unittest.log) |
| `python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v` | 80개 통과. 임시 로컬 원격과 스크립트 빌더를 사용했고 외부 벤더 CLI는 `PATH`에서 제외했다 |
| `cargo test --all --locked --offline` | 537개 통과, ignored 1개 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과 |
| 온톨로지 실행기 `cargo test --locked --offline` | 4개 통과 |
| `spec_check.py`, `static_checks.py`, `ontology_check.py` | 명세 기계 검사 47/47·존재 검사 72/72, 코어 정적 검사 13/13, 온톨로지 검사 통과 |
| `cargo fmt`, `cargo clippy`, 추적 경로·어휘·검증 자료·BLUEPRINT 검사 | 모두 종료 0 |

Python 전체 시험의 skip 6개는 원본 보관소 환경 미설정 2개, 로컬 보관소와 `pdftotext`가 필요한
시험 3개, 설치된 botocore가 조건부 쓰기를 지원해 적용되지 않는 구버전 시험 1개다. 초기 전체 실행에서
작업 트리 안으로 설정한 `TMPDIR` 때문에 온톨로지 임시 파일 시험 3개가 실패했고, 기본 임시 경로로
전체를 재실행해 위 결과를 확인했다.

이 증거의 적용 범위는 T-OP-09 개발 도구와 T-OP-08 축 5의 운영 기록이다.
[09 제품 목적 대응표 §5](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지).
