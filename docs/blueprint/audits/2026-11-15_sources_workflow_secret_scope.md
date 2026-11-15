# Audit 6 — sources 워크플로 시크릿 범위와 변수 전달

대상 노드: `audit6-sources-workflow-secret-scope`.
연결: BLUEPRINT A1~A4·Q7·L1·L2·M0, 09 제품 목적 대응표 P03.

## 변경과 기존 해소 상태

시작 시점의 `sources.yml`에는 R2 endpoint·검증 키 쌍·예산 원장 키 쌍이 이미 두 보관소 소비 단계의 개별 `env`에만 있다. 설치·checkout·artifact·detect 단계에는 전달되지 않는다. pip 직접 의존성도 `pdfplumber==0.11.10`, `boto3==1.43.100`으로 고정되어 있다. `ci.yml`에는 이미 최상위 `permissions: contents: read`와 두 checkout의 `persist-credentials: false`가 있다. 이 설정은 유지하며 기존 회귀 시험으로 다시 검증한다.

남아 있던 버킷 변수 네 참조를 수정했다. `vars.ONJEON_RAW_BUCKET`·`vars.ONJEON_DERIVED_BUCKET`은 `reproduce.env`에서 비밀값이 아닌 환경변수로 전달하며, `run:`에서는 각각 `"s3://$ONJEON_RAW_BUCKET"`·`"s3://$ONJEON_DERIVED_BUCKET"`으로 확장한다. 값의 따옴표나 명령 치환 문자열이 Bash 소스가 되지 않는다. 작업 실행 조건의 `vars.*`는 셸 코드가 아니므로 유지한다. 수동 실행·동시성·예산·OCR 옵션·보고서 경로도 유지한다.

## 회귀 검증

새 `tools/tests/test_workflow_source_variables.py`는 기존 CI의 전체 Python 탐색에 포함된다.

- 실제 워크플로의 버킷 환경변수 바인딩을 검사하고 모든 `run: |` 블록에서 `vars.*` 직접 삽입을 거부한다. 점·대괄호 표기 및 두 버킷 각각의 직접 삽입 회귀 네 변이를 검출한다.
- 실제 두 소비 스크립트를 추출해 Bash로 실행하며 Python 명령만 임시 인자 기록기로 대체한다. 정상 버킷과 따옴표·세미콜론·명령 치환·백틱·줄바꿈·공백·glob 문자가 든 값, OCR 활성·비활성의 네 조합을 검사한다. 두 목록 대조와 재현 호출의 URI·작업·옵션·보고서 인자가 보존되고 주입 표식 파일이 생성되지 않아야 한다.
- 기존 시크릿 범위 시험은 실제 파일의 다섯 바인딩을 작업 수준으로 옮긴 변이와 8개 비소비 단계 각각에 노출하는 40개 변이를 거부한다. CI 보안 통합 시험은 실제 CI 선언의 권한 제거·확대 여섯 변이와 checkout·액션 참조 회귀를 거부한다.

파서는 저장소의 현재 블록형 YAML 배치에 한정하며 일반 YAML 파서가 아니다. 단계별 환경변수는 같은 단계의 프로세스나 의존성 자체의 신뢰성을 보장하지 않는다. 실제 GitHub 실행·R2 요청·시크릿 조회는 수행하지 않는다.

## 실행 증거와 제품 완료 범위

명령별 종료 코드·소요 시간은 [Python 검사 기록](../../../tools/evidence/audit6-sources-workflow-secret-scope/python-checks.json)과 [Rust 검사 기록](../../../tools/evidence/audit6-sources-workflow-secret-scope/rust-checks.json), 재실행 방법과 로그 안내는 [증거 README](../../../tools/evidence/audit6-sources-workflow-secret-scope/README.md)에 남긴다.

2026-11-15 이 작업 트리에서 워크플로 시험 37개·CI 보안 통합 시험 5개가 통과했다. 전체 Python 시험은 1,633개 실행·실패/오류 0·기존 건너뜀 6개(비공개 원본 필요 5개, 구버전 botocore 대상 1개)다. Rust 작업 공간은 532개 통과·기존 무시 1개, 온톨로지 실행기는 4개 통과했다. 포맷·Clippy·어휘·검증 자료·40개 변이 자체검사·제품 목적 연결·설계 명세·설계도 수치·추적 파일 자격 검사도 종료 0이다. Cargo 출력은 이 작업 트리의 `target/audit6-sources`로 지정해 최종 검증했다.

이것은 워크플로 finding의 로컬 검증 증거다. P03의 실제 R2 관측 목록 대조·변경 재처리·릴리스 화면, 상품/계약 트윈·소비자 UX, P01~P19 전체·첫 출시 완료 증거를 대체하지 않는다. commit·push·GitHub 호출은 하지 않았다.
