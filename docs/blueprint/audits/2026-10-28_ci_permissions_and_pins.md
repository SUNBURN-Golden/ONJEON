# Audit 3 — CI 최소 권한과 액션 SHA 고정

기록일: 2026-10-28. 노드: `audit3-ci-permissions-and-pins`.
기준 커밋: `83cf2b6121bb2784df06ff092f7331c4db4c39ef` + 이 노드의 미커밋 변경.
연결: BLUEPRINT A1~A6·Q7·M0의 구현 검증 기반, [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) §5 개발 도구.

## 시작 상태와 변경

감리 지적과 달리 작업 시작 시점의 [ci.yml](../../../.github/workflows/ci.yml)은 이미 최상위 `permissions: contents: read`를 선언하고 있었다. 두 checkout은 `persist-credentials: false`이며, 두 워크플로의 액션 참조 6곳 모두 전체 40자리 SHA로 고정돼 있었다. 이 설정과 SHA는 유지했다. 같은 시작 상태는 [Audit 2 기록](2026-10-26_ci_secrets_step_scope.md)에도 있다. 태그와 커밋의 대응을 조회하는 GitHub 호출은 하지 않았다.

`rules-engine` 작업의 checkout 직후, 설치·빌드 전 첫 검증 단계에 다음 명령을 연결했다.

```sh
python3 tools/workflow_check.py
python3 -m unittest discover -s tools/tests -p test_workflow_pins.py -v
```

첫 명령은 `ci.yml`의 정확한 최상위 `contents: read`와 checkout의 자격 증명 비보존을 검사한다. 두 번째는 `.github/workflows/`와 `.github/actions/` 아래 `.yml`·`.yaml`의 외부 액션을 검사한다. 전체 40자리 SHA가 아닌 태그·브랜치·짧은 SHA는 거부하며 로컬 `./` 액션은 제외한다. 기존 전체 Python 시험에서도 두 검사는 계속 실행된다. 조기 단계는 Python 표준 라이브러리만 사용하므로 boto3 설치나 Rust 빌드의 성공에 의존하지 않는다.

## 회귀 시험

[test_ci_workflow_security.py](../../../tools/tests/test_ci_workflow_security.py)는 실제 `ci.yml`에 선언된 조기 단계의 셸 본문을 추출해 임시 저장소에서 `bash -e`로 실행한다. 임시 저장소에는 현재 `.github/`와 기존 권한 검사기·SHA 검사 시험을 복사한다. 실제 워크플로는 변조하지 않는다.

- 현재 두 워크플로는 종료 0으로 통과한다.
- `ci.yml` 최상위 권한 블록 삭제 또는 `contents: write` 복원은 권한 진단과 함께 실패한다.
- CI의 checkout 두 곳 각각을 `v4`, `main`, 12자리 SHA로 바꾼 6개 하위 사례는 해당 참조를 보고하며 실패한다.

조기 단계를 추가하기 전에는 신규 시험 3개 모두 단계 누락을 검출했다([before.log](../../../tools/evidence/audit3-ci-permissions-and-pins/before.log)). 이는 기존 설정의 권한·SHA 결함 재현이 아니라 새 조기 실행 연결의 누락 재현이다. 추가 후 워크플로 관련 시험 35개가 모두 통과했다([workflow-tests.log](../../../tools/evidence/audit3-ci-permissions-and-pins/workflow-tests.log)).

## 프로젝트 검증

다음은 이 작업 트리에서 두 CI 작업의 명령을 로컬 실행한 결과다. Cargo는 `--offline`으로 실행했다. 온톨로지 실행기는 `target/audit3-ci-ontology`에 빌드했다.

| 검사 | 결과 | 실행 로그 |
|---|---|---|
| 워크플로 권한 CLI 및 관련 회귀 시험 | 종료 0, 시험 35개 통과 | [permissions.log](../../../tools/evidence/audit3-ci-permissions-and-pins/permissions.log), [workflow-tests.log](../../../tools/evidence/audit3-ci-permissions-and-pins/workflow-tests.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/audit3-ci-ontology/debug/ontology-case-runner" python3 -m unittest discover -s tools/tests -v` | 1,236개 실행, 실패 0·기존 건너뜀 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit3-ci-permissions-and-pins/python-tests.log) |
| `cargo fmt --all -- --check`·`cargo clippy --all-targets --offline -- -D warnings` | 종료 0 | [fmt.log](../../../tools/evidence/audit3-ci-permissions-and-pins/fmt.log), [clippy.log](../../../tools/evidence/audit3-ci-permissions-and-pins/clippy.log) |
| `cargo test --all --offline` | 466개 통과, 기존 ignored 1개, 종료 0 | [rust-tests.log](../../../tools/evidence/audit3-ci-permissions-and-pins/rust-tests.log) |
| 온톨로지 실행기 빌드·단위 시험·설계 사례 검사 | 실행기 시험 3개, 질문 11/11·제약 15/15·릴리스/문서 25/25 통과, 종료 0 | [빌드](../../../tools/evidence/audit3-ci-permissions-and-pins/ontology-build.log), [단위 시험](../../../tools/evidence/audit3-ci-permissions-and-pins/ontology-tests.log), [사례 검사](../../../tools/evidence/audit3-ci-permissions-and-pins/ontology-check.log) |
| 어휘·검증 자료 내부 일관성·변조 selftest·설계 묶음 | 종료 0 | [vocabulary.log](../../../tools/evidence/audit3-ci-permissions-and-pins/vocabulary.log), [validation.log](../../../tools/evidence/audit3-ci-permissions-and-pins/validation.log), [validation-selftest.log](../../../tools/evidence/audit3-ci-permissions-and-pins/validation-selftest.log), [spec-check.log](../../../tools/evidence/audit3-ci-permissions-and-pins/spec-check.log) |
| 데몬 모의 실행 `--scenario all --require-all --quiet` | 필수 ID 33/33 실행, 종료 0. 기존 명세 공백 보고는 유지 | [daemon-dry-run.log](../../../tools/evidence/audit3-ci-permissions-and-pins/daemon-dry-run.log) |
| `python3 -I tools/blueprint_counts.py` | 종료 0 | [blueprint-counts.log](../../../tools/evidence/audit3-ci-permissions-and-pins/blueprint-counts.log) |

정적 검사 명령·종료 코드는 [checks-summary.json](../../../tools/evidence/audit3-ci-permissions-and-pins/checks-summary.json), 온톨로지 명령은 [ontology-summary.json](../../../tools/evidence/audit3-ci-permissions-and-pins/ontology-summary.json)에 기록했다.

Python 건너뜀 6개는 비공개 로컬 원본이 필요한 기존 시험 5개와 설치된 botocore에 해당하지 않는 구버전 조건부 PUT 시험 1개다. 신규 회귀 시험은 모두 실행했다. 변경 경로·보호 파일 제외·문서 링크·공백 검사와 소스 해시는 [final-checks.log](../../../tools/evidence/audit3-ci-permissions-and-pins/final-checks.log)에 기록했다.

## 증거의 범위

이 기록과 실행 로그는 로컬 CI 설정·회귀 검증 증거다. 실제 GitHub Actions 실행·상위 액션 저장소의 태그 대응 검증·공시 수집·소비자 화면·P01~P19 출시 완료 증거를 대신하지 않는다. 기존 권한 검사기는 저장소의 블록형 YAML 배치를 대상으로 하며 일반 YAML 해석기가 아니다. commit·push·GitHub 호출·비밀값 조회·R2 접근은 수행하지 않았다.
