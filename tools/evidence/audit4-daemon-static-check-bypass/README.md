# audit4-daemon-static-check-bypass 실행 증거

2026-11-03. 기준 커밋 `9801a383e7c4fa3aee0e0ddf2f79e70b11bc481b` 위의 미커밋 변경. [수정 기록](../../../docs/blueprint/audits/2026-11-03_daemon_static_check_bypass.md) · [검사기](../../daemon/static_checks.py) · [회귀 시험](../../tests/test_daemon_static_checks.py).

| 증거 | 실행 결과 |
|---|---|
| [before.log](before.log) | 새 회귀 19개를 변경 전 검사기에 실행: 하위 사례 포함 실패 35건, 종료 1 |
| [after.log](after.log) | 같은 회귀 19개 모두 통과, 종료 0 |
| [static-checks.log](static-checks.log) | 실제 정적 CLI 13개 검사 모두 통과, 종료 0 |
| [전체 모의 시나리오](../../daemon/reports/dry_run.log) | 검사 692건 통과, 필수 ID 33/33, 누락·미등록·중복 0, 종료 0 |
| [전체 데몬 시험](../../daemon/reports/unittest.log) | 289개 모두 통과, 종료 0 |
| [python-tests.log](python-tests.log) | `tools/tests` 전체 1,340개 실행, 실패·오류 0, 기존 환경 조건 skip 6, 종료 0 |
| [rust-tests.log](rust-tests.log) | Rust 워크스페이스 단위·통합·문서 시험 합계 478개 통과, 기존 fixture 재생성 시험 1개 ignored, 종료 0 |
| [ontology-runner-tests.log](ontology-runner-tests.log) | 온톨로지 실행기 단위 시험 3개 통과, 종료 0 |
| [vocabulary.log](vocabulary.log) | 어휘 49축·270값 일치, 종료 0 |
| [validation.log](validation.log), [validation-selftest.log](validation-selftest.log) | 표본 내부 일관성 및 의도한 변조 40건 탐지, 종료 0 |
| [spec-check.log](spec-check.log) | 설계 묶음 기계 검사 45/45·존재 검사 72/72, 종료 0 |
| [blueprint-status.log](blueprint-status.log), [blueprint-counts.log](blueprint-counts.log) | 결정 색인·현재 등록 수 일치, 종료 0 |

회귀는 별칭 가져오기, `os.execve`·`posix_spawn` 함수군, `getattr(__builtins__, ...)`, 참 리터럴 루프를 포함한다. 추가로 미등록 모듈·하위 모듈·멤버, 와일드카드·상대 경로 탈출, 모듈 별칭·`getattr` 별칭과 계산된 모듈 속성명을 거부한다. 정상 `re.compile`, JSON, 경로 조합, 데이터·포트 조회와 입력 의존 루프는 허용한다. CLI 시험은 다른 cwd·격리 Python에서 복사한 소스에 위반을 주입하고 검사만 수행한다.

재현(저장소 루트, Rust 1.98.1과 잠긴 의존성이 준비된 환경):

```sh
export RUSTUP_TOOLCHAIN=1.98.1
python3 -m unittest tools/tests/test_daemon_static_checks.py -v
python3 -I tools/daemon/static_checks.py
python3 -I tools/daemon/dry_run.py --rules docs/blueprint/proposals/설계검토_결과/daemon_rules.json --tasks tools/daemon/mock_tasks.json --scenario all --require-all
python3 -m unittest tools/tests/test_daemon_dry_run.py -v
python3 -m unittest discover -s tools/tests -v
cargo test --all --locked --offline
cargo test --locked --offline --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml
python3 -I tools/vocab_check.py
python3 -I tools/validation_check.py
python3 -I tools/validation_check.py --selftest
python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py
python3 -I tools/blueprint_status.py
python3 -I tools/blueprint_counts.py
```

Python skip 6개는 보관소 환경 미설정 2개, 로컬 보관소·pdftotext 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다. 이번 회귀 19개와 데몬 289개에는 skip이 없다.

공용 데몬 보고서는 현재 부모 커밋과 소스 내용 해시를 머리말에 기록하며, 기존 `Cli.test_evidence_logs_name_the_parent_commit_and_source_hash`가 대조한다. [manifest.json](manifest.json)은 검사기·시험·문서·로그의 개별 SHA-256을 기록한다. 로컬 시험 실행에서 rustup 기본 툴체인이 없어 `cargo`가 멈춘 문제는 전역 기본값 대신 작업 트리 한정 `rustup override set --path "$PWD" 1.98.1`로 해결했고, 전체 Python·Rust 재실행 기록은 [fix-round1](fix-round1/README.md)에 있다.

이 검사는 일반 객체의 계산된 속성명·일반 데이터 흐름·입력 의존 무한 루프를 모두 판정하는 Python 샌드박스가 아니다. 모의 시나리오가 통과해도 보고서 끝의 기존 명세 공백 G51~G57은 남는다. 이 노드는 개발 도구 보강이며 BLUEPRINT §9.5·09 §5의 구분에 따라 실제 전 상품 수집·트윈·소비자 화면·첫 출시 완료 증거가 아니다. 실제 제공자·R2·GitHub 호출이나 커밋·푸시는 수행하지 않았다.
