# Audit 4: PR 과제·P행 추적 강제 (수정 4차)

노드: `audit4-pr-template-task-field` | 작성·검증: Codex 구현 담당, 로컬 도구 → bash → Python/Rust.
기준 SHA: `b0108b0` + `origin/main` `b2aed2b` 병합 + 이 디렉터리의 미커밋 산출물. 검증일: 2026-11-04.

## 수정 4차: main 병합

`origin/main`(`b2aed2b`)을 병합하며 `.github/workflows/ci.yml` 한 곳이 충돌했다. 양쪽 의도를
모두 남겼다: 이 노드의 PR 본문 추적 검사(selftest + `pull_request` 본문 검사)와 main의
`Registry normalization regressions` 단계다. 충돌 표시는 남기지 않았고, 병합 뒤
`python3 tools/workflow_check.py`, `test_workflow_pins.py`,
`test_ci_workflow_security.py`, `test_registry_normalize.py`가 모두 통과한다.
PR 본문 추적 검사 자체의 동작·규칙은 3차와 같다.

## 해결 상태와 경로 제한

**finding은 이 노드의 허용 경로 안에서 해결했다. `.github/pull_request_template.md`는 변경하지 않았다.**

수정 1차는 실제 템플릿에 추적 입력란을 넣었으나 그 파일은 노드의 허용 경로
(`docs/BLUEPRINT.md`, `docs/blueprint/**`, `docs/decisions/**`, `packages/schemas/**`,
`packages/rules-engine/**`, `.github/workflows/**`, `tools/**`, `services/**`, `apps/**`,
`data/**`, `infra/**`, `README.md`) 밖이었다. 이번 수정에서 그 변경을 되돌리고, 허용 경로인
`.github/workflows/**`·`tools/**`로 추적 요구를 강제한다.

따라서 **템플릿 자체에는 새 입력란이 없다.** 대신 PR 본문을 CI가 직접 검사하므로 템플릿이
없거나 수정돼도 PR은 작업·완료 기준에 연결되지 않으면 병합 단계에서 실패한다.

- `tools/ci/check_pr_body_traceability.py`: PR 본문에 다음 중 하나가 있어야 통과한다.
  - `tasks.json`에 실제로 존재하는 과제 ID(`T-XX-NN`). 없는 ID는 `PR-TRACE-TASK`로 실패.
  - 목록 외 노드 ID(라벨 표기, 또는 백틱 없이 쓰인 `auditN-...` 슬러그. 예:
    `Node audit4-pr-template-task-field`). 오케스트레이터가 본문 산문과 증거 경로에
    백틱 없이 슬러그를 쓰므로 3차에서 맨 슬러그를 받도록 넓혔다.
  - 09 제품목적 대응표 P행(`P01`~`P19`).
  - 어느 것도 없으면 `PR-TRACE-MISSING`으로 실패한다.
- `.github/workflows/ci.yml`: `pull_request` 이벤트에서 `github.event.pull_request.body`를
  검사기에 전달한다. 검사기 selftest는 모든 이벤트에서 실행한다.
- `docs/BLUEPRINT.md` §10 규칙 1: PR 본문의 추적 지점 의무와 검사 명령을 단일 기준에 명시했다.
- `tasks.json` `_common_done_criteria_note`, 묶음 `README.md` §0.1, `03_작업명세.md` §2:
  수정 1차의 "템플릿 입력란 추가" 문구를 실제 적용 방식으로 정정했다.
  `common_done_criteria` 전체 채택 상태는 `non_binding_until_adopted` 그대로다.
- `tools/tests/test_pr_body_traceability.py`: 검사 규칙·경계값·CLI 종료 코드·CI 배선·문서
  정합성 회귀 시험 15개. 기존 CI의 `unittest discover -s tools/tests`가 자동 발견한다.
  그중 하나는 2차 CI 실패 본문 스냅숏(`actual-pr-body.md`)을 그대로 검사한다.
- `tools/ci/README.md`: 검사기 명령·증명 범위·CI 배선을 기록했다.

수정 1차의 미적용 패키지(`pull_request_template.patch`, 미리보기, 별도 시험 사본,
`verify_preview.py`)와 그 로그는 삭제했다. 실제 템플릿은 기준 SHA와 같다.

불가역·비용·법률·비밀·운영 결정은 필요하지 않아 `DECISION_REQUIRED.md`는 작성하지 않았다.

## 검증

| 명령 | 결과·증거 |
|---|---|
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | PASS: 위반 6개를 각자의 규칙으로 검출, 정상 7개 통과 ([로그](pr-traceability-selftest.log)) |
| `python3 -I tools/ci/check_pr_body_traceability.py --body-file tools/evidence/audit4-pr-template-task-field/actual-pr-body.md` | PASS 0: 백틱 없는 `audit4-pr-template-task-field` 슬러그를 인식 ([본문](actual-pr-body.md), [로그](actual-pr-body.log)). 2차 CI 실패 본문을 그대로 재사용했다 |
| `PR_BODY='Fixes a typo in the README.' python3 -I tools/ci/check_pr_body_traceability.py` | FAIL 1: `PR-TRACE-MISSING` ([로그](missing-handle.log)). 추적 지점이 없는 본문을 실제로 거부한다 |
| `python3 -I -m unittest discover -s tools/tests -p test_pr_body_traceability.py -v` | PASS 15개 ([로그](pr-traceability-tests.log)) |
| `python3 -I -m unittest discover -s tools/tests -p test_pr_policy.py -v` | PASS 23개: 한정 채택·공통 PR 기준 미채택 유지 ([로그](pr-policy-tests.log)) |
| `python3 -I tools/ci/check_product_purpose.py` | PASS: 09 행·과제·필수 시험 ID 정합성 ([로그](product-purpose.log)) |
| `python3 tools/workflow_check.py`, `test_workflow_pins.py`, `test_ci_workflow_security.py` | PASS: 토큰 권한·action SHA 고정·CI 보안 변이 ([로그](ci-workflow-security.log)) |
| `python3 -m unittest discover -s tools/tests -v` | PASS: 1,389개 실행·6개 건너뜀, 실패/오류 0 (main 병합분 포함, [로그](python-tests.log)) |
| `cargo test --all --locked --offline` | PASS: Rust 495개·무시 1개, 실패 0 ([로그](rust-tests.log)) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | PASS: 4개 ([로그](ontology-runner-tests.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | PASS: 기계 45/45·존재 72/72 ([로그](spec-check.log)) |
| `python3 -I tools/blueprint_counts.py` | PASS: 등록 수와 일치 |
| `python3 -I -m py_compile ...`, `git diff --check` | PASS ([범위·공백 검사](change-scope.log)) |

새 CI 검사는 이 저장소의 PR 본문처럼 노드 슬러그가 라벨·백틱 없이 산문이나 경로에 있어도
통과한다(2차에서는 백틱을 요구해 이 PR 자체가 CI에서 실패했다 — 3차 회귀 시험과
[실제 본문 로그](actual-pr-body.log)로 고쳤다). 본문이 비어 있거나 `auditN-...` 슬러그·과제
ID·P행이 모두 없으면 CI가 실패한다.

## 한계

- 이 검사는 **추적 지점의 존재**만 본다. 이름 붙인 과제·P행이 완료됐는지, 증거가 있는지,
  PR이 그 작업을 실제로 수행했는지는 검사하지 않는다.
- GitHub CI 실행 자체는 이 작업 트리 밖에서 일어난다. 실제 PR 본문으로 로컬 검사 통과를
  증명했고, 다음 CI 실행이 최종 확인이다.
- 템플릿 입력란은 추가되지 않았다. 템플릿에 필드를 넣으려면 허용 경로 확장이 필요하며,
  그 판단은 이 노드의 권한 밖이다.
- 실제 데이터·상품/계약 트윈·소비자 화면·사용자 이해 시험 또는 P01~P19 출시 완료 증거를
  대체하지 않는다. `common_done_criteria` 전체 채택 여부도 바뀌지 않았다.
