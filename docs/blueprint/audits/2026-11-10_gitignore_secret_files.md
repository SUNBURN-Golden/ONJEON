# Audit 5 — 로컬 자격 증명·가상 환경 경로 차단

기록일: 2026-11-10. 노드: `audit5-gitignore-secret-files`.
기준 커밋: `308b4fa28f5dec99d212d9a8477d019f4d8a5e89` + 이 노드의 미커밋 변경.
연결: [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) §5 개발 도구.

## 지적과 경로 제약

감리 지적은 무시 규칙에 `.env*`, `*.pem`, `*.key`, `.venv/`를 추가하라는 것이다.
저장소 루트 `.gitignore`는 이 노드의 allowed_paths 밖이므로 가드가 그 변경을 거부했고,
루트 파일 변경은 되돌렸다. 대신 같은 결과를 허용 경로 안에서 두 층으로 만든다.

## 변경

1. 쓰기 가능한 최상위 트리 루트에 동일한 `.gitignore` 규칙을 둔다:
   `apps/`, `data/`, `infra/`, `packages/schemas/`, `packages/rules-engine/`,
   `services/`, `tools/`. Git은 하위 디렉터리의 무시 파일을 그 트리 전체에 적용하므로
   각 트리에서 만든 `.env`, `.env.*`, 인증서·키, `.venv/`가 `git add`에 들어가지 않는다.
2. [check_tracked_secrets.py](../../../tools/check_tracked_secrets.py)는
   `git ls-files`로 추적 경로 전체를 검사해 위 이름이 하나라도 추적되면 종료 1로 실패한다.
   디렉터리 깊이와 무관하며 루트 경로도 포함하므로, 루트 `.gitignore`를 고칠 수 없는
   범위에서도 추적 커밋은 막는다. `ci.yml`의 의존성 설치 전 단계에서 실행한다.
   유일한 예외는 `infra/compose/.env.example`이다. 비밀 항목이 빈 자리표시자 템플릿이며
   [test_compose_static.py](../../../infra/compose/tests/test_compose_static.py)가 빈 값을 검사한다.

## 시험

- [test_gitignore.py](../../../tools/tests/test_gitignore.py): 7개 트리의 실제 무시 파일에
  네 규칙이 있는지, 실제 저장소의 `git check-ignore --no-index`가 루트·중첩 경로를
  무시하고 비슷한 이름(`env.example`, `*.pem.txt`, `*.key.example`, `.venv-notes/`)은
  무시하지 않는지, 임시 저장소의 `git add --all`이 민감한 이름만 제외하는지 검사한다.
- [test_tracked_secrets.py](../../../tools/tests/test_tracked_secrets.py): 네 종류의
  추적 경로 탐지, 예외 템플릿, 깨끗한/오염된 임시 저장소의 CLI 종료 코드, 현재 트리 통과,
  `ci.yml` 연결을 검사한다.

## 한계

루트에 생긴 미추적 `.env`·`.venv/`는 루트 `.gitignore`를 고칠 수 없어 로컬에서 자동으로
무시되지 않는다. 다만 추적되면 CI 검사가 병합 전에 실패한다. 무시 규칙과 검사는 이미
추적된 파일을 제거하지 않으며 강제 추가(`git add -f`)를 막지 않는다. `.env*`는 새
`.env.example`도 무시하므로 템플릿을 새로 추적하려면 명시적인 예외가 필요하다.
이 증거는 로컬 개발 도구 검증이며 제품 목적 행이나 첫 출시 완료 판정을 바꾸지 않는다.

## 검증

명령·종료 코드·로그는
[이번 노드의 증거](../../../tools/evidence/audit5-gitignore-secret-files/README.md)에 기록한다.
commit·push·GitHub 호출·비밀값 조회는 수행하지 않았다.
