# Audit 1: PR 공통 완료 기준의 적용 상태

과제 ID: `audit1-pr-template-tasks-fields`.
작성·검증 역할: Codex 구현 담당. 실행 경로: 이 worktree의 Codex 도구 → bash → Python/Rust 시험 명령.
검증 기준 SHA: `24a253ee464bf1084aab3885cc45e4024c9135ff` + 이 과제의 미커밋 변경분. 검증일: 2026-10-26.

허용 경로에 `.github/pull_request_template.md`가 없으므로, 과제 명세가 허용한 대안인 **채택 전 비구속 선언**으로 해결했다. `tasks.json`의 기존 `_status`(채택된 정본이 아닌 검토용 초안)에 더해 `common_done_criteria`의 적용 상태를 `non_binding_until_adopted`로 명시했다. 묶음 README §0.1과 03 §2도 같은 상태와 현행 BLUEPRINT·PR 템플릿 링크를 제공한다.

채택 시 과제 ID, 작성 모델 역할·실행 경로, 대상 SHA, 테스트 로그 필드를 PR 템플릿에 반영하고 JSON·두 문서의 상태를 함께 갱신하도록 적었다. 기존 공통 완료 기준과 과제 정의는 그대로 보존했다. 사용자 지시·개별 과제의 시험 의무와 09_제품목적_대응표의 제품 완료 증거 기준은 계속 적용한다.

회귀 시험은 JSON·두 문서의 적용 상태 일치, 현행 기준 링크의 실제 경로, 채택 시 필요한 네 필드, 기존 추적·로그 기준 보존을 검사한다. 기존 CI의 `unittest discover -s tools/tests -v`가 자동으로 발견한다. 선언 추가 전 4개 시험 실행에서 실패 6건을 확인했고, 추가 후 4개 모두 통과했다.

| 실행 명령 | 결과·로그 |
|---|---|
| `python3 -I -m unittest discover -s tools/tests -p test_pr_policy.py -v` | PASS: 4개, [로그](pr-policy-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | PASS: 834개 실행(828개 통과·6개 건너뜀), [로그](python-tests.log) |
| `CARGO_NET_OFFLINE=true cargo test --all --offline --no-fail-fast` | PASS: Rust 402개 통과·1개 무시, 중첩 Python 39개·129개 통과, [로그](rust-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | PASS: 기계 44/44·존재 72/72, [로그](spec-check.log) |
| `python3 tools/vocab_check.py` | PASS: 49축·269값, [로그](vocabulary.log) |
| `python3 tools/validation_check.py` | PASS: 내부 정합성, 원본 재검증 아님, [로그](validation.log) |
| `python3 tools/validation_check.py --selftest` | PASS: 변이 38개 검출, [로그](validation-selftest.log) |

Python의 건너뜀 6개는 기존 조건부 시험이다: 로컬 원본 보관소 미설정 2개, 로컬 원본 보관소·pdftotext 필요 3개, 설치된 botocore가 조건부 쓰기를 지원해 구버전 대상 시험 1개. Rust의 무시 1개는 명시적으로 무시된 `regenerate_declared_abox_fixture`다.

기존 HEAD와 비교해 새 PR 정책 메타데이터 두 필드 외 `tasks.json` 전체가 동일함을 확인했다. `git diff --check`도 통과했다([범위 검사](change-scope.log)). 이 증거는 문서 적용 상태의 정합성을 증명하며, 제품 출시나 P01~P19의 완료 증거를 대신하지 않는다.
