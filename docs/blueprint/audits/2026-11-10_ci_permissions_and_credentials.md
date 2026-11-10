# Audit 5 — CI 최소 권한·자격 증명 비보존·액션 SHA 고정

기록일: 2026-11-10. 노드: `audit5-ci-permissions-and-credentials`.
기준 커밋: `8e7a079a78ec302b999cc97c05f472a630563599` + 이 노드의 미커밋 변경.
연결: BLUEPRINT A1~A6·Q7·M0의 구현 검증 기반,
[09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) §5 개발 도구.

## 현재 설정과 변경

감리 지적과 달리 이 작업 트리의 시작 상태에는 이미 아래 설정이 있었다.
[ci.yml](../../../.github/workflows/ci.yml)은 최상위 `permissions: contents: read`를
선언하고, 두 작업의 checkout 모두 `persist-credentials: false`를 지정한다.
두 checkout의 액션 참조는 전체 40자리 SHA
`11d5960a326750d5838078e36cf38b85af677262`로 고정돼 있다.
기존 조기 CI 검사는 설치·빌드 전에 최소 권한·자격 증명 설정과
`.github/workflows/`·`.github/actions/`의 외부 액션 SHA를 검사한다.
설정과 SHA는 유지했다. 과거 미병합 브랜치의 병합 여부와 관계없이 현재 파일로 판정했다.

[test_ci_workflow_security.py](../../../tools/tests/test_ci_workflow_security.py)에
실제 `ci.yml`의 검사 셸 본문을 실행하는 회귀 시험 2개를 추가했다.
각 checkout에서 `persist-credentials: false`를 삭제하거나 `true`로 바꾸는
4가지 변이가 자격 증명 진단으로 실패한다. 다른 단계의 같은 이름 설정으로
checkout의 누락을 가리는 변이도 실패한다. 기존 시험은 현재 설정의 통과,
최상위 권한 변이 6가지의 거부, 두 액션 각각의 태그·브랜치·짧은 SHA 변이
6가지의 거부를 검증한다. 변이는 임시 저장소에만 적용한다.

## 검증 증거와 범위

실행 명령·종료 코드·로그는
[이번 노드의 증거](../../../tools/evidence/audit5-ci-permissions-and-credentials/README.md)에
기록한다. 테스트 결과는 로컬 CI 설정과 회귀 검증의 증거이며 실제 GitHub Actions 실행,
상위 액션 저장소의 태그와 SHA 대응 확인, 실제 공시 데이터·소비자 화면·P01~P19의
첫 출시 완료 증거는 별도다. 권한 검사기는 저장소의 블록형 YAML 배치를 대상으로 한다.
commit·push·GitHub 호출·비밀값 조회·외부 저장소 접근은 수행하지 않았다.

집중 시험 37개, 전체 Python 1,429개(기존 건너뜀 6개), Rust 513개(기존 ignored 1개),
온톨로지 실행기 4개와 현재 `ci.yml`의 나머지 검사는 통과했다.
추가 `tools/ci/tests` 시험 20개 중 2개는 기존 온톨로지→규칙 엔진 의존 경계 위반
3건으로 실패했다. 기준 커밋의 관련 파일을 작업 트리 안 임시 디렉터리에 복원해
동일한 진단·종료 코드를 확인했다([기준선 대조](../../../tools/evidence/audit5-ci-permissions-and-credentials/baseline-dependency-check.log)).
현재 CI 워크플로에는 이 추가 시험 명령이 없으며, 전체 명령 묶음은 그 실패를 반영해
종료 1을 기록했다. 이 노드에서 해당 의존 경계 정책은 변경하지 않았다.
