# Audit 5 — sources.yml R2 자격 증명의 단계 범위

대상 노드: `audit5-sources-yml-step-scoped-secrets`.
연결: BLUEPRINT A1~A4·L1·L2·M0, 09 제품 목적 대응표 P03.

## 지적 해소 확인

지적은 `sources.yml:73-78`의 작업 수준 R2 자격 증명이 `apt-get`·`pip install`에도 전달된다는 것이다. 이 작업 트리에는 [Audit 2 수정](2026-10-26_ci_secrets_step_scope.md)과 [Audit 3 재검증](2026-10-28_sources_workflow_secret_scope.md)이 이미 반영되어 있다. 따라서 워크플로를 다시 수정하지 않고 실제 파일을 검사하는 회귀 시험을 보강했다.

[sources.yml](../../../.github/workflows/sources.yml)의 `reproduce.env`에는 비밀값이 아닌 `JOB` 경로만 있다. 아래 다섯 바인딩은 `Every archived key matches the pinned listing`과 `Reproduce from the archive` 두 단계의 개별 `env`에만 있다.

| 환경변수 | GitHub secret 참조 이름 |
|---|---|
| `ONJEON_S3_ENDPOINT` | `ONJEON_S3_ENDPOINT` |
| `R2_ACCESS_KEY_ID` | `R2_VERIFIER_ACCESS_KEY_ID` |
| `R2_SECRET_ACCESS_KEY` | `R2_VERIFIER_SECRET_ACCESS_KEY` |
| `R2_LEDGER_ACCESS_KEY_ID` | `R2_LEDGER_ACCESS_KEY_ID` |
| `R2_LEDGER_SECRET_ACCESS_KEY` | `R2_LEDGER_SECRET_ACCESS_KEY` |

두 `Extractors` 단계의 apt·venv·pip 설치, checkout·artifact 액션, detect 실행과 요약에는 이 바인딩이 없다. 버킷 변수 조건·수동 실행·동시성·시간 제한·작업 명세·예산 통제는 기존 파일을 그대로 검증한다.

## 추가 회귀 시험

[test_workflow_secret_scope.py](../../../tools/tests/test_workflow_secret_scope.py)는 CI의 기존 `unittest discover`에 포함된다. 기존 합성 워크플로 시험에 실제 파일을 읽는 다음 두 검사를 추가했다.

- `test_live_job_level_credentials_regression_is_rejected`: 두 소비 단계의 `env`를 제거하고 다섯 바인딩을 작업 공통 `env`로 이동한다. 지적 상태를 복원한 메모리 복사본을 `secret outside consumer step env`로 거부한다.
- `test_live_nonconsumer_steps_reject_each_credential`: 실제 비소비 단계 8개에 바인딩을 하나씩 추가한 40가지 메모리 변이를 같은 이유로 거부한다. detect·reproduce의 설치 단계, checkout·artifact 액션, detect 실행과 요약을 모두 포함한다.

실제 워크플로의 정상 바인딩 검사와 누락·중복·잘못된 secret 매핑·소비 단계 내부 설치 거부 시험도 유지한다. 변이는 파일에 쓰지 않으며 secret 값을 읽지 않는다. 검사기는 저장소의 현재 블록형 YAML 배치를 전제로 하는 표준 라이브러리 계약 시험이다.

## 실행 증거

2026-11-10, 해당 작업 트리에서 실행한 명령·종료 코드·출력은 [증거 디렉터리](../../../tools/evidence/audit5-sources-yml-step-scoped-secrets/)에 보관한다.

- [워크플로 회귀 로그](../../../tools/evidence/audit5-sources-yml-step-scoped-secrets/workflow-tests.log): `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v`, 34개 통과, 종료 0.
- [전체 Python 로그](../../../tools/evidence/audit5-sources-yml-step-scoped-secrets/python-tests.log): `python3 -m unittest discover -s tools/tests -v`, 1,431개 실행·실패 0·건너뜀 6, 종료 0. 건너뜀은 로컬 원본이 필요한 기존 시험 5개와 설치된 botocore가 이미 조건부 PUT을 지원해 적용되지 않는 구버전 시험 1개다.
- [Rust 작업 공간 로그](../../../tools/evidence/audit5-sources-yml-step-scoped-secrets/rust-tests.log): `cargo test --all --locked --offline`, 문서 시험 포함 513개 통과·기존 픽스처 재생성 시험 1개 무시, 종료 0.
- [온톨로지 실행기 로그](../../../tools/evidence/audit5-sources-yml-step-scoped-secrets/ontology-tests.log): 실행기 디렉터리에서 `cargo test --locked --offline`, 4개 통과, 종료 0.
- [문서·계약 검사 로그](../../../tools/evidence/audit5-sources-yml-step-scoped-secrets/checks.log): 제품 목적 연결, 설계 명세, 어휘, 검증 자료 정합성·변이 자체검사, 결정 색인·기준일, `git diff --check` 모두 종료 0.
- [최종 범위 검사](../../../tools/evidence/audit5-sources-yml-step-scoped-secrets/final-checks.log): 허용 경로, 워크플로 원본 유지, 워크플로·시험 파일 SHA-256, 로컬 증거 링크와 diff 공백 검사를 확인했다.

이 증거는 워크플로 자격 증명의 단계 범위 finding에 한정한다. 실제 GitHub Actions·R2를 실행하거나 secret을 조회하지 않았다. 단계별 `env`는 같은 단계 안의 프로세스에 자격을 제공하므로 의존성 신뢰성이나 단계 간 프로세스 격리를 증명하지 않는다. 실제 R2 관측 목록 대조·소비자 화면·P03 전체·첫 출시 완료 증거는 별도다.
