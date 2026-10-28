# Audit 3 — sources 워크플로 R2 비밀값의 단계 범위

대상: `audit3-sources-workflow-secret-scope`, `.github/workflows/sources.yml`.
연결: Blueprint A1~A4·L1·L2·M0, 09 제품 목적 대응표 P03.

## 판정과 변경

지적은 `sources.yml:73-78`의 작업 수준 `env`가 R2 endpoint·검증용 키 쌍·예산 원장 쓰기 키 쌍을 `apt-get`과 pip 설치를 포함한 작업 전체에 노출한다는 것이다. 이 작업 트리의 시작 시점에는 [Audit 2의 단계 범위 제한](2026-10-26_ci_secrets_step_scope.md)이 이미 적용되어 있어 지적된 상태가 아니었다. 현재 [sources.yml](../../../.github/workflows/sources.yml)에서 다섯 비밀값 참조는 `Every archived key matches the pinned listing`(87–91행)과 `Reproduce from the archive`(101–105행) 두 소비 단계의 개별 `env`에만 있다. 작업 공통 `env`(73–74행)에는 비밀값이 아닌 `JOB` 경로만 남는다. `apt-get`·venv·pip을 실행하는 `Extractors` 단계(38–42행, 77–83행)와 checkout·artifact 액션, detect 작업 전체에는 `env`가 없어 R2 자격이 상속되지 않는다. 이번 작업은 그 범위를 유지하고 계약 시험이 실제 파일의 변이를 검출하는지 확인하는 증거를 추가한다.

설치 명령은 `pdfplumber==0.11.10`·`boto3==1.43.100`으로 버전 고정이며 `ci.yml`의 `boto3==1.43.100` 설치와 같은 저장소 관례다. 해시 고정은 도입하지 않았다. 지적의 해소 수단은 비밀값 범위 제한이고, 전이 의존성 해시 목록을 수동 워크플로에 유지하는 비용이 크기 때문이다.

## 회귀 증거

[test_workflow_secret_scope.py](../../../tools/tests/test_workflow_secret_scope.py)는 Audit 2에서 추가된 계약 시험으로 실제 `sources.yml`의 두 소비 단계에 각각 정확한 다섯 바인딩이 있는지 검사한다. 그 밖의 위치 — 작업/워크플로 `env`, 다른 단계·작업, 액션 입력, 실행 스크립트 — 의 비밀값 참조와 자격 환경변수 정의를 거부하며, 소비 단계 안의 설치·액션 호출도 거부한다. 표준 라이브러리만 쓰고 기존 Python CI 전체 시험에서 자동 발견된다.

[job-env-mutation.log](../../../tools/evidence/audit3-sources-workflow-secret-scope/job-env-mutation.log)는 실제 `sources.yml`의 메모리 복사본에 지적 상태를 복원한 검사다. 다섯 바인딩을 작업 수준 `env`로 옮기면 계약 검사가 `secret outside consumer step env`로 거부하고, `Extractors` 설치 단계에 비밀값 `env`를 부여해도 같은 이유로 거부한다. 디스크의 워크플로는 바꾸지 않았다.

## 실행 결과

2026-10-28, 이 작업 트리에서 실행했다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_workflow*.py' -v` | 32개 통과, 종료 0 | [워크플로 회귀 로그](../../../tools/evidence/audit3-sources-workflow-secret-scope/workflow-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1,233개 실행, 실패 0·건너뜀 6, 종료 0 | [전체 Python 로그](../../../tools/evidence/audit3-sources-workflow-secret-scope/python-tests.log) |
| `python3 -I tools/ci/check_product_purpose.py` | P01~P19 작업 연결·아홉 시험 ID 정합성 통과, 종료 0 | [제품 목적 연결 검사](../../../tools/evidence/audit3-sources-workflow-secret-scope/product-purpose.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 검사 45/45·존재 검사 72/72 통과, 종료 0 | [설계 검사](../../../tools/evidence/audit3-sources-workflow-secret-scope/spec-check.log) |
| `python3 tools/vocab_check.py` | 49축·270값 통과, 종료 0 | [어휘 검사](../../../tools/evidence/audit3-sources-workflow-secret-scope/vocabulary.log) |
| `python3 tools/validation_check.py` 및 `--selftest` | 내부 정합성·변이 38개 통과, 종료 0 | [일관성 검사](../../../tools/evidence/audit3-sources-workflow-secret-scope/validation.log), [변이 자체검사](../../../tools/evidence/audit3-sources-workflow-secret-scope/validation-selftest.log) |

건너뜀은 비공개 로컬 원본이 필요한 기존 시험 5개와 구버전 조건부 PUT 시험 1개다. 비밀값 위치·설치 단계 무자격·버전 고정·보호 경로 무변경의 텍스트 대조는 [final-checks.log](../../../tools/evidence/audit3-sources-workflow-secret-scope/final-checks.log)에 기록했다.

이 증거는 `sources.yml`의 비밀값 범위에 한정한다. 실제 GitHub Actions 실행·R2 접근·비밀값 조회나 P03·출시 완료 증거를 대체하지 않는다. 단계별 `env`는 같은 단계 안의 프로세스에는 자격을 그대로 제공하며, 의존성 자체의 신뢰성이나 단계 사이의 프로세스 격리를 보장하지 않는다. commit·push는 수행하지 않았다.
