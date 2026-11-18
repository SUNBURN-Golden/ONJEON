# Audit 7 작업 계약 ADR 검증

2026-11-18, `audit7-adopt-task-bundle-adr` 작업 트리에서 ADR-0020과 동기화 변경 후 실행한 로컬 검증이다. 부모 커밋의 시험 결과를 재사용하지 않는다.

변경: ADR-0019의 기존 한정 채택 유지, S0~S5 → M0~M6 다대다 대응, T-OP-02의 V1 비대체, ADR-0014 결정 6에 대한 T-TW-02 로컬 엔진·픽스처 한정 예외. BLUEPRINT §7·§9·§11·§13, 원장과 두 계약을 동기화했다.

실행 명령·결과와 한계는 아래 로그에 기록한다. 문서 회귀는 단계 대응, V1의 잔여 조건, 서비스 적용 제한, 이전 ADR과 두 계약의 동기화를 검사하며 제한 삭제·대응 변경 변이가 검출됨을 확인한다. 엔진의 런타임 서비스 차단 기능을 새로 구현하거나 검증했다는 뜻은 아니다. 실제 R2·이종 AI 제공자·프로덕션에 접근하지 않았으며 V1·출시 완료 증거는 별도다.

| 명령 | 결과 | 로그 |
|---|---|---|
| `python3 -m unittest tools.tests.test_audit7_task_bundle_adr -v` | 6개 통과, 조건 삭제·대응 변경 변이 검출 포함 | [focused-tests.log](focused-tests.log) |
| `python3 -m unittest tools.tests.test_pr_policy tools.tests.test_audit7_task_bundle_adr -v` | 31개 통과 | [contract-checks.log](contract-checks.log) |
| `python3 -I tools/ci/check_product_purpose.py` | 통과 | [contract-checks.log](contract-checks.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47·존재 72/72 통과 | [contract-checks.log](contract-checks.log) |
| `python3 -I tools/blueprint_status.py` / `tools/blueprint_counts.py` | 결정 42개(ADR 20·DEC 22) 색인·현재 등록 수 일치 | [contract-checks.log](contract-checks.log) |
| `cargo test --all --locked --offline` | 532개 Rust 시험·doctest 통과(엔진 외 작업 공간 포함) | [rust-tests.log](rust-tests.log) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | 4개 통과 | [ontology-runner-tests.log](ontology-runner-tests.log) |
| `python3 -I tools/vocab_check.py` / `tools/validation_check.py` / `tools/validation_check.py --selftest` | 모두 종료 코드 0 | [status-checks.log](status-checks.log) |
| `python3 -I tools/release_readiness/check.py --purpose docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md --registry docs/blueprint/proposals/설계검토_결과/tasks.json --evidence docs/release-readiness/evidence/` | 예상한 종료 코드 1: P행 19개·기능 64개 모두 open, closed=0·excluded=0 | [status-checks.log](status-checks.log) |
| `git diff --check` | 통과 | [contract-checks.log](contract-checks.log) |

출시 판정기의 코드 1은 회귀 시험 실패가 아니라 실제 완료 증거의 미등록을 정직하게 확인한 결과다. 새 ADR의 채택이나 로컬 시험으로 V1·출시 관문이 닫히지 않는다.

결정 원장에 BP-D-21을 추가하자 기존 고정 목록 회귀 두 개가 20개만 기대해 실패했다([초기 로그](ledger-tests-initial.log)). `test_decision_records.py`의 현행 목록을 21개로 갱신하고 과거 ID 대응은 원래 20개를 유지했다. 변경 후 `python3 -m unittest tools.tests.test_audit7_task_bundle_adr tools.tests.test_decision_records tools.tests.test_decisions_ledger_sync -v`는 45개 모두 통과했다([재실행](ledger-tests.log)).

최종 전체 Python 재실행: `python3 -m unittest discover -s tools/tests -v` — **1702개, 실패 0, 건너뜀 6, 종료 코드 0**([python-tests.log](python-tests.log)). 건너뜀은 원본 아카이브가 필요한 5개와 구형 botocore 전용 1개다. 초기 전체 실행의 실패는 위 고정 원장 목록 두 건뿐이며 [python-tests-initial.log](python-tests-initial.log)에 보존했다.

최종 변경 파일과 실행 로그의 SHA-256, 기준 HEAD·도구 버전은 [manifest.json](manifest.json)에 고정한다. Git commit·push·GitHub 호출은 하지 않았다.
