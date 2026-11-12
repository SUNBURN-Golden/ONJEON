# audit6-daemon-scope-from-real-diff 실행 증거

2026-11-12. [수정 기록](../../../docs/blueprint/audits/2026-11-12_daemon_scope_from_real_diff.md) ·
[회귀 시험](../../tests/test_daemon_dry_run.py)(`ScopeFromRealDiff`, `DocsOnlyLandingCond`) ·
[실행기 어댑터 시험](../../daemon/runner_verify/tests/test_runner_verify.py)(`test_changed_paths_is_the_real_diff`, R8).
기준 커밋 `c872a7500318a21ed83bf505518310a11e873a00` 위 미커밋 변경이며,
[manifest.json](manifest.json)은 변경 소스·문서·시험·로그의 SHA-256을 기록한다.

| 증거 | 결과 |
|---|---|
| [python-tests.log](python-tests.log) | 전체 Python 1,590개 실행, 실패·오류 0, 기존 skip 6개, 종료 0 |
| [모의 시나리오](../../daemon/reports/dry_run.log) | 검사 695건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 종료 0 |
| [데몬 회귀](../../daemon/reports/unittest.log) | 296개 통과, 종료 0; 현재 소스 내용 해시 기록 |
| [runner-adapter-tests.log](runner-adapter-tests.log) | 실제 실행기 시험 61개 통과(R8 실제 diff 시나리오 포함), 종료 0 |
| [static-checks.log](static-checks.log) | 공용 코어 정적 검사 13/13 통과, 종료 0 |
| [rules-scope-check.log](rules-scope-check.log) | `daemon_rules.json`의 HEAD 대비 차이가 `immediate_audit_paths`·`_immediate_audit_paths_note`뿐; D-04 해시 픽스처는 갱신 이유와 함께 그 파일 해시만 다시 고정 |
| [rust-tests.log](rust-tests.log) | 워크스페이스 514개 통과, 기존 fixture 재생성 시험 1개 ignored, 종료 0 |
| [ontology-runner-tests.log](ontology-runner-tests.log) | 온톨로지 실행기 4개 통과, 종료 0 |
| [spec-check.log](spec-check.log) | 기계 검사 46/46·존재 검사 72/72 통과, 종료 0 |
| [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) | 어휘·검증 자료 일관성·변조 탐지 검사 통과, 종료 0 |
| [blueprint-status.log](blueprint-status.log), [blueprint-counts.log](blueprint-counts.log) | 결정 색인·등록 수 일치, 종료 0 |

핵심 회귀는 변성 검사를 포함한다. `test_removing_the_new_paths_reopens_the_finding`은
새 즉시 감리 경로를 뺀 규칙에서 규칙 파일 PR이 다시 docs-only로 감리 없이
`merged → done`이 되어 finding이 재현됨을 보이고, R8은 실제 프로세스·실제 Git에서
빌더가 커밋한 파일과 다른 경로를 신고했을 때 데몬이 실제 diff를 쓰는지 본다.
기존 skip 6개는 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개,
설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 시험 1개다.

재현(루트에서 Rust 1.98.1·잠긴 의존성 준비 후):

```sh
python3 -m unittest tools/tests/test_daemon_dry_run.py -v
python3 -m unittest tools.daemon.runner_verify.tests.test_runner_verify -v
python3 -I tools/daemon/static_checks.py
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I tools/blueprint_status.py
python3 -I tools/blueprint_counts.py
```

실제 Git 시험(`test_changed_paths_is_the_real_diff`)은 임시 클론만 만들고
init·add·commit·checkout·mv·rev-parse·merge-base·diff를 쓰며 원격을 만들지 않는다.
R8 실제 실행기 시나리오는 기존 runner_verify 경계 안에서만 실행된다.
이번 작업에서 Git 커밋·푸시·GitHub·실제 제공자 호출은 하지 않았다.
이 증거는 09 §5의 개발 도구 보강이며 P01~P19의 완료 판정을 바꾸지 않는다.
