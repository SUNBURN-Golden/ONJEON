# audit6-daemon-credential-ttl-vs-lease 실행 증거

2026-11-13 · 기준 커밋 `28fa4a440b97bb19a8a2adc0f71e1c3340cf8cdb` 위 변경.
[수정 기록](../../../docs/blueprint/audits/2026-11-13_daemon_credential_ttl_vs_lease.md) ·
[회귀 시험](../../daemon/runner_verify/tests/test_runner_verify.py)(`CredentialLeaseFencing`).
[manifest.json](manifest.json)은 변경 파일·시험·문서·실행 로그의 SHA-256을 기록한다.

7,200초 자격을 그대로 보유해도 3,600초 리스가 끝나면 pre-receive hook이
직접 푸시를 거부한다. 자격 발급 때 신뢰할 상태·시계 파일 경로를 원격 레코드에
바인딩하고, 푸시마다 현재 리스 ID·활성 상태·만료를 확인한다. 하트비트 갱신은
새 만료 시각을 따르며, 별도 `preserve_credential`의 인계 후 보존 권한은 유지한다.

| 증거 | 결과 |
|---|---|
| [before.log](before.log) | HEAD의 hook·issue-credential만 복원하고 새 회귀 2개 실행: 실패 4건, 종료 1. 만료 후 직접 푸시와 두 빌더 자격 재발급이 허용됨을 재현. 실행 후 수정 소스를 복원했다 |
| [credential-tests.log](credential-tests.log) | 새 회귀 10개 통과, 종료 0 |
| [runner-tests.log](runner-tests.log) | 실행기 전체 80개 통과(새 회귀 10개·R1~R22 시나리오 포함), 종료 0 |
| [python-tests.log](python-tests.log) | 전체 Python 1,600개 실행, 실패·오류 0, 기존 skip 6개, 종료 0 |
| [rust-tests.log](rust-tests.log) | 워크스페이스 515개 통과, 기존 ignored 1개, 종료 0 |
| [ontology-runner-tests.log](ontology-runner-tests.log) | 온톨로지 실행기 4개 통과, 종료 0 |
| [mock-scenarios.log](mock-scenarios.log), [static-checks.log](static-checks.log) | 모의 검사 695건·필수 ID 33/33·코어 정적 검사 13개 통과, 종료 0 |
| [spec-check.log](spec-check.log) | 기계 검사 46/46·존재 검사 72/72 통과, 종료 0 |
| [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log), [blueprint-status.log](blueprint-status.log), [blueprint-counts.log](blueprint-counts.log) | 어휘·검증 자료·변조 탐지·결정 색인·등록 수 검사 통과, 종료 0 |
| [workflow-check.log](workflow-check.log), [workflow-tests.log](workflow-tests.log) | CI 정책 검사·워크플로 회귀 15개 통과, 종료 0 |
| [format.log](format.log), [clippy.log](clippy.log), [tracked-secrets.log](tracked-secrets.log) | 포맷·경고 거부 린트·추적 자격 파일 검사 통과, 종료 0 |

CI `rules-engine` 잡은 일반 Python 탐색 뒤 `CredentialLeaseFencing` 10개를 별도로 실행한다.
새 시험 10개는 실제 발급 명령·임시 로컬 bare 원격을 사용한다. 리스 만료 전에
직접 푸시가 반영되고, tick·재시작·회수 없이 만료된 뒤에는 거부·ref 불변·로그
사유를 확인한다. 갱신된 리스에서는 같은 자격으로 원래 만료 뒤에도 푸시할 수
있으며 갱신된 만료 뒤에는 거부된다. 종료·교체된 리스, 바인딩 누락, 상태
소실·손상, 잘못된 만료·시계 값도 거부한다. 정확한 리스/자격 만료 경계는
hook의 시계만 고정해 검사한다. 만료된 리스의 빌더 자격 재발급은 기록도
추가하지 않으며, 보존용 자격은 만료 뒤에도 쓰고 회수 뒤에는 거부된다.

재현 명령(루트에서 README의 Rust·잠긴 의존성 준비 후):

```sh
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify.CredentialLeaseFencing -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 -I tools/daemon/static_checks.py
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all --quiet
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I tools/blueprint_status.py
python3 -I tools/blueprint_counts.py
python3 tools/workflow_check.py .github/workflows/ci.yml .github/workflows/pr-traceability.yml
python3 -m unittest discover -s tools/tests -p test_workflow_pins.py -v
cargo fmt --all -- --check
cargo clippy --locked --offline --all-targets -- -D warnings
python3 -I tools/check_tracked_secrets.py
```

전체 Python의 skip 6개는 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개,
설치된 botocore에 해당하지 않는 구버전 조건 1개다. 실행기 시나리오의 벤더 CLI 등
미확인 항목은 기존 검증 한계를 유지하며 실제 호스트 검증으로 승격하지 않는다.

Git 변경은 이 작업 트리의 미커밋 파일뿐이다. 시험의 Git commit·push 대상은
버려지는 로컬 검증 저장소이며 제품 저장소의 commit·push·GitHub 호출은 없다.
09 §5·T-OP-09 개발 도구 증거이며 실제 호스트 설정·상주 데몬 가동 승인이나
P01~P19·첫 출시 완료 증거를 대신하지 않는다.
