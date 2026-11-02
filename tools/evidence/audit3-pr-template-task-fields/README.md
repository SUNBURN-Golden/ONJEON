# Audit 3: PR 템플릿 필드 제안 — Fix round 2 인계

검증일: 2026-10-29. 과제 ID: `audit3-pr-template-task-fields`.
대상 SHA: `41114559cc73ff62f2861aa40b87c96d4b81ff6f` + 이 노드의 미커밋 변경.
작성 역할·실행 경로: 구현 담당 → 이 worktree의 도구 → bash → Python/Rust 시험 명령.

## 현재 상태와 범위

**Fix round 2에서 `.github/pull_request_template.md`의 변경을 HEAD로 되돌렸다.**
자동 범위 검사가 `outside allowed_paths: .github/pull_request_template.md`로 거부했고,
사용자가 해당 변경의 되돌리기를 지시했다. 실제 템플릿의 필드 누락은 아직 남아 있다.
이 인계는 범위 위반을 해결하고 적용 가능한 수정안을 준비한 결과이며,
원래 감사 finding이 실제 템플릿에서 해결됐다는 증거가 아니다.

허용된 `tools/` 아래의 [전체 제안](proposed_pull_request_template.md)과
[패치](template.patch)를 보존했다. 템플릿 경로 수정 권한이 있는 후속 작업에서
검토·적용해야 한다. 이 노드에서는 패치를 적용하지 않는다.
공통 PR 기준의 채택은 `tasks.json`의 `_common_done_criteria_status=non_binding_until_adopted`와
[설계 묶음 README §0.1](../../../docs/blueprint/proposals/설계검토_결과/README.md#01-pr-완료-기준의-적용-상태)의 별도 절차를 따른다.
이 작업은 채택 상태를 바꾸지 않는다.

## 준비한 필드

| 필드 | 제안 내용 |
|---|---|
| `task_id` | 작업 명세 과제 ID 또는 감사 노드 ID |
| 제품 목적 P행 | P01~P19와 기여 내용. 개발 도구의 간접 기여와 증거 한계를 기재 |
| `authors` | 작성 모델 역할·도구·실행 경로. 비밀값·모델 식별자 원문 제외 |
| `target_sha` | 검증한 HEAD의 전체 커밋 SHA와 미커밋 변경 포함 여부 |
| `test_log_ref` | 실행 명령·종료 코드·결과를 담은 로그 경로 또는 링크 |

제안은 기존 A·Q·L·I·M·R 추적, 수락 사례, 검증 범위와 한계, 확인 목록을 그대로 보존한다.
제품 목적 P행은 [09_제품목적_대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)를 따른다.
개발 도구의 검증은 P01~P19의 실제 데이터·트윈·소비자 화면 완료나 출시 승인을 대신하지 않는다.

## Fix round 2 검증

[시험 모듈](../../tests/test_pr_template.py)의 `ProposedPrTemplate`은 실제 템플릿 적용과
제안 검증을 구분한다. 여섯 시험이 제안 필드·링크·안내·기존 내용 보존,
실제 템플릿과 제안 사이 diff의 패치 일치, `git apply --check` 성공과 실제 파일 미변경을 검사한다.
전체 Python discovery에도 포함된다. 시험을 통과해도 실제 템플릿에 필드가 추가된 것은 아니다.

| 명령 | 결과·로그 |
|---|---|
| `python3 -m unittest tools.tests.test_pr_template tools.tests.test_pr_policy -v` | 25개 통과, 종료 0. [로그](fix-round2/template-tests.log) |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 45/45·존재 72/72 통과, 종료 0. [로그](fix-round2/spec-check.log) |
| `cargo build --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --target-dir "$PWD/target/ontology"` | 빌드 성공, 종료 0. [로그](fix-round2/ontology-build.log) |
| `ONJEON_ONTOLOGY_RUNNER="$PWD/target/ontology/debug/ontology-case-runner" CARGO_TARGET_DIR="$PWD/target" python3 -m unittest discover -s tools/tests -v` | 1,283개 실행, 실패·오류 0, skip 6, 종료 0. [로그](fix-round2/python-tests.log) |
| `CARGO_TARGET_DIR="$PWD/target" cargo test --all` | 문서 시험 포함 474개 통과, 실패 0, ignored 1, 종료 0. [로그](fix-round2/rust-tests.log) |
| 허용 경로·실제 템플릿 복원·문서 링크·공백 검사 | [로그](fix-round2/change-scope.log) |

각 실행 로그에 명령, 대상 SHA, 미커밋 변경 포함 여부와 종료 코드를 남겼다.
최신 결과는 이 절과 `fix-round2/`만 따른다.

Python skip 6개는 원본 보관 경로 미설정 2개, 로컬 원본·pdftotext가 필요한 재현 시험 3개,
설치된 botocore가 조건부 쓰기를 지원해 해당하지 않는 구버전 거부 시험 1개다.
Rust ignored 1개는 기존 `regenerate_declared_abox_fixture` 재생성 시험이다.

## 이전 라운드 기록

최초 라운드의 `before-tests.log`·`python-tests.log`에는 당시 실제 템플릿의 누락으로
시험 세 건이 실패한 결과가 남아 있다. `proposed-tests.log`는 제안만 검사한 결과다.
`fix-round1/`은 이후 실제 템플릿에 필드를 적용했던 시점의 시험 결과다.
그 변경은 범위 검사에서 거부돼 이번 라운드에서 되돌렸으므로 현재 적용 증거로 사용할 수 없다.
이전 로그는 역사 기록으로만 보존한다.

커밋·푸시·GitHub 호출은 하지 않았다. 금지 문서는 변경하지 않았다.
