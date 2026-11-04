# Audit 4: PR 과제·P행 추적 강제 (수정 2차)

노드: `audit4-pr-template-task-field` | 작성·검증: Codex 구현 담당, 로컬 도구 → bash → Python/Rust.
기준 SHA: `c657028` + 이 디렉터리의 미커밋 산출물. 검증일: 2026-11-04.

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
  - 목록 외 노드 ID(라벨 표기 또는 인라인 코드 `auditN-...`, 예: ``Node `audit4-pr-template-task-field` ``).
  - 09 제품목적 대응표 P행(`P01`~`P19`).
  - 어느 것도 없으면 `PR-TRACE-MISSING`으로 실패한다.
- `.github/workflows/ci.yml`: `pull_request` 이벤트에서 `github.event.pull_request.body`를
  검사기에 전달한다. 검사기 selftest는 모든 이벤트에서 실행한다.
- `docs/BLUEPRINT.md` §10 규칙 1: PR 본문의 추적 지점 의무와 검사 명령을 단일 기준에 명시했다.
- `tasks.json` `_common_done_criteria_note`, 묶음 `README.md` §0.1, `03_작업명세.md` §2:
  수정 1차의 "템플릿 입력란 추가" 문구를 실제 적용 방식으로 정정했다.
  `common_done_criteria` 전체 채택 상태는 `non_binding_until_adopted` 그대로다.
- `tools/tests/test_pr_body_traceability.py`: 검사 규칙·경계값·CLI 종료 코드·CI 배선·문서
  정합성 회귀 시험 13개. 기존 CI의 `unittest discover -s tools/tests`가 자동 발견한다.
- `tools/ci/README.md`: 검사기 명령·증명 범위·CI 배선을 기록했다.

수정 1차의 미적용 패키지(`pull_request_template.patch`, 미리보기, 별도 시험 사본,
`verify_preview.py`)와 그 로그는 삭제했다. 실제 템플릿은 기준 SHA와 같다.

불가역·비용·법률·비밀·운영 결정은 필요하지 않아 `DECISION_REQUIRED.md`는 작성하지 않았다.

## 검증

| 명령 | 결과·증거 |
|---|---|
| `python3 -I tools/ci/check_pr_body_traceability.py --selftest` | PASS: 위반 6개를 각자의 규칙으로 검출, 정상 5개 통과 ([로그](pr-traceability-selftest.log)) |
| `PR_BODY='Fixes a typo in the README.' python3 -I tools/ci/check_pr_body_traceability.py` | FAIL 1: `PR-TRACE-MISSING` ([로그](missing-handle.log)). 추적 지점이 없는 본문을 실제로 거부한다 |
| `python3 -I -m unittest discover -s tools/tests -p test_pr_body_traceability.py -v` | PASS 13개 ([로그](pr-traceability-tests.log)) |
| `python3 -I -m unittest discover -s tools/tests -p test_pr_policy.py -v` | PASS 23개: 한정 채택·공통 PR 기준 미채택 유지 ([로그](pr-policy-tests.log)) |
| `python3 -I tools/ci/check_product_purpose.py` | PASS: 09 행·과제·필수 시험 ID 정합성 ([로그](product-purpose.log)) |
| `python3 tools/workflow_check.py`, `test_workflow_pins.py`, `test_ci_workflow_security.py` | PASS: 토큰 권한·action SHA 고정·CI 보안 변이 ([로그](ci-workflow-security.log)) |
| `ONJEON_ONTOLOGY_RUNNER=... python3 -m unittest discover -s tools/tests -v` | PASS: 1,381개 실행·6개 건너뜀, 실패/오류 0 ([로그](python-tests.log)) |
| `cargo test --all --locked --offline` | PASS: Rust 495개·무시 1개, 실패 0 ([로그](rust-tests.log)) |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | PASS: 4개 ([로그](ontology-runner-tests.log)) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | PASS: 기계 45/45·존재 72/72 ([로그](spec-check.log)) |
| `python3 -I tools/blueprint_counts.py` | PASS: 등록 수와 일치 |
| `python3 -I -m py_compile ...`, `git diff --check` | PASS ([범위·공백 검사](change-scope.log)) |

새 CI 검사는 이 저장소의 PR 본문(`Node \`audit4-pr-template-task-field\` ...`)처럼 노드 ID가
라벨 또는 `auditN-...` 인라인 코드로 있으면 통과한다. 본문이 비어 있거나 추적 지점이 없으면
CI가 실패한다.

## 한계

- 이 검사는 **추적 지점의 존재**만 본다. 이름 붙인 과제·P행이 완료됐는지, 증거가 있는지,
  PR이 그 작업을 실제로 수행했는지는 검사하지 않는다.
- CI 검사는 병합 후 다음 PR부터 효력이 있다. 이 노드 PR 자체의 통과를 소급해 증명하지 않는다.
- 템플릿 입력란은 추가되지 않았다. 템플릿에 필드를 넣으려면 허용 경로 확장이 필요하며,
  그 판단은 이 노드의 권한 밖이다.
- 실제 데이터·상품/계약 트윈·소비자 화면·사용자 이해 시험 또는 P01~P19 출시 완료 증거를
  대체하지 않는다. `common_done_criteria` 전체 채택 여부도 바뀌지 않았다.
