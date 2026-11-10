Audit 4 finding: `.github/pull_request_template.md` has no field for a `tasks.json` task ID or a P row. Without one, PRs can't be traced to the completion standard.

## Acceptance
- [ ] finding resolved with tests/evidence

## Builder summary
[적용 패치와 검증 증거](/workspace/onjeon-run/wt/audit4-pr-template-task-field/tools/evidence/audit4-pr-template-task-field/README.md)를 준비했습니다. 미리보기 회귀 시험 6개와 기존 Python·Rust 테스트가 통과했습니다.

실제 템플릿은 허용 경로 목록 밖이라 미수정이며 finding은 미해결입니다. `.github/pull_request_template.md` 수정도 허용하시겠습니까? 아래 상태는 패치 검토 준비를 뜻합니다.

STATUS: READY

Builder: st_build

Refs #413
