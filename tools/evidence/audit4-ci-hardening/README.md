# Audit 4 — ci.yml 읽기 권한 재검증

기록일: 2026-11-03. 노드: `audit4-ci-hardening`.
기준 커밋: `66f9c7309cb60431b388aa59c4bec14e70bafdf0` + 이 노드의 미커밋 변경.
연결: [BLUEPRINT](../../../docs/BLUEPRINT.md) A1~A6·Q7·M0의 구현 검증 기반,
[09 제품 목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md) §5 개발 도구.

## 판정과 변경

요구된 [ci.yml](../../../.github/workflows/ci.yml)의 최상위 설정은 작업 시작 시점부터 존재했다.

```yaml
permissions:
  contents: read
```

이 설정과 두 작업의 checkout 자격 증명 비보존 설정은 유지했다.
[Audit 3 기록](../../../docs/blueprint/audits/2026-10-28_ci_permissions_and_pins.md)에
연결된 기존 조기 CI 검사도 유지했다. 따라서 워크플로에 중복 권한 블록을 추가하지 않았다.

[test_ci_workflow_security.py](../../tests/test_ci_workflow_security.py)의 기존 변이 시험을
2가지에서 6가지로 확장했다. 실제 CI에 선언된 검사 셸 본문을 임시 저장소에서 실행해,
현재 설정은 통과하고 아래 변경은 권한 진단과 함께 실패함을 확인한다.

- 최상위 권한 블록 삭제
- `permissions: {}`
- `permissions: read-all`
- `contents: none`
- `contents: write`
- `contents: read`와 추가 `pull-requests: write`

실제 워크플로 파일은 변조하지 않는다. 이 시험은 기존 CI의 전체 Python discovery에서 실행된다.

## 실행 근거

모든 명령은 이 작업 트리에서 실행했다. Cargo에는 `RUSTUP_TOOLCHAIN=1.98.1`을 지정하고
의존성 잠금과 오프라인 모드를 사용했다. 온톨로지 실행기는 `target/audit4-ci-ontology`에 빌드했다.

| 검사 | 결과 | 로그 |
|---|---|---|
| `python3 tools/workflow_check.py` | 종료 0, 정확한 최상위 읽기 권한 확인 | [permissions.log](permissions.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_*workflow*.py' -v` | 35개 통과, 신규 권한 변이 6가지 모두 실행 | [workflow-tests.log](workflow-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/audit4-ci-ontology/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1,330개 실행, 실패 0·기존 건너뜀 6, 종료 0 | [python-tests.log](python-tests.log) |
| `cargo test --all --locked --offline` | 478개 통과, 기존 ignored 1, 종료 0 | [rust-tests.log](rust-tests.log) |
| `cargo fmt --all -- --check`, `cargo clippy --all-targets --locked --offline -- -D warnings` | 모두 종료 0 | [fmt.log](fmt.log), [clippy.log](clippy.log) |
| 온톨로지 실행기 빌드·단위 시험·사례 검사 | 모두 종료 0, 단위 시험 3개 통과 | [ontology-build.log](ontology-build.log), [ontology-tests.log](ontology-tests.log), [ontology-check.log](ontology-check.log) |
| 어휘·검증 자료 내부 일관성·변조 selftest·설계 묶음 | 모두 종료 0 | [vocabulary.log](vocabulary.log), [validation.log](validation.log), [validation-selftest.log](validation-selftest.log), [spec-check.log](spec-check.log) |
| 데몬 모의 실행 `--scenario all --require-all --quiet` | 종료 0, 기존 명세 공백 보고 유지 | [daemon-dry-run.log](daemon-dry-run.log) |
| `python3 -I tools/blueprint_counts.py` | 종료 0 | [blueprint-counts.log](blueprint-counts.log) |

Rust 및 나머지 검사 명령과 종료 코드는 [rust-summary.json](rust-summary.json),
[checks-summary.json](checks-summary.json)에 기록했다. Python 건너뜀 6개는 로컬 원본이 필요한
기존 시험 5개와 설치된 botocore에 해당하지 않는 구버전 조건부 PUT 시험 1개다.

이 기록은 로컬 CI 설정·회귀 검증 증거다. 실제 GitHub Actions 실행이나
P01~P19의 실제 데이터·소비자 화면·첫 출시 완료 증거를 대신하지 않는다.
commit·push·GitHub 호출은 수행하지 않았다.

## Fix round 1

수정 라운드 1은 코드 결함이 아니라 로컬 도구 체인 선택 실패를 고쳤다.
Rust 1.98.1은 설치돼 있었지만 이 작업 트리에 rustup 재정의가 없어 일반
`cargo`가 도구 체인을 고르지 못했다. README의 로컬 시험 절차대로 경로 한정
재정의를 등록하고, 환경 변수 재정의 없이 전체 시험을 다시 실행했다.
감사 항목 자체(`permissions: contents: read`)는 기준 커밋에 이미 있었으며
변이 시험이 그 최소 권한을 계속 요구한다. 새 로그와 해시는
[fix-round1](fix-round1/README.md)에 있다.

