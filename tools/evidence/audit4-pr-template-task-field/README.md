# Audit 4: PR 과제·P행 추적 필드 적용안

노드: `audit4-pr-template-task-field` | 작성·검증: Codex 구현 담당, 로컬 도구 → bash → Python/Rust.
기준 SHA: `799b17f97f7923134ef36ccaa4d473d9a09de791` + 이 디렉터리의 미커밋 산출물.
검증일: 2026-11-04.

## 적용 상태와 경로 제한

**finding 미해결: 실제 `.github/pull_request_template.md`는 변경하지 않았다.**
노드의 허용 경로에는 `.github/workflows/**`만 있고 `.github/pull_request_template.md`는 없다.
해당 파일을 수정할 수 있는지 사용자에게 확인을 요청했으며, 답변 전에는 허용 경로인 `tools/**` 안에만 적용안과 검증 증거를 작성했다.
이 디렉터리의 준비 완료는 적용 패키지에 한하며 finding 해결이나 제품 완료를 뜻하지 않는다.
불가역·비용·법률·비밀·운영 결정은 필요하지 않아 `DECISION_REQUIRED.md`는 작성하지 않았다.

[적용 패치](pull_request_template.patch)는 기존 PR 템플릿에 아래 필드를 추가하고,
회귀 시험을 기존 CI가 발견하는 `tools/tests/test_pr_template_traceability.py`에 설치한다.
[미리보기](pull_request_template.preview.md)와 [시험 원본](test_pr_template_traceability.py)을 함께 제공한다.

- `tasks.json` 과제 ID: 복수 과제와 목록 밖 감리 노드의 ID·사유.
- 09 제품목적 대응표 P행: P01~P19 복수 행과 해당 없음의 사유.
- 개별 과제 `done_criteria`·`required_test_ids`와 PR 수락 기준.
- P행 완료 증거에 기여하는 범위, 남은 공백, 증거·테스트 로그 경로.

개발 도구는 09 §5·T-OP-08 축 5의 운영 기록으로 연결한다. 합성 시험·개별 작업 완료와
제품 완료를 구분하며, ADR-0019의 `common_done_criteria=non_binding_until_adopted` 상태를 유지한다.
기존 A·Q·L·I·M·R 연결, 변경 영향, 검증·한계, 확인 목록은 보존한다.

## 검증

| 명령 | 결과·증거 |
|---|---|
| `python3 -m unittest discover -s tools/evidence/audit4-pr-template-task-field -p test_pr_template_traceability.py -v` | 실제 템플릿 대상 FAIL 6개: [누락 재현](before-tests.log). 적용 전에는 실패가 정상이며 finding을 그대로 검출한다 |
| `python3 tools/evidence/audit4-pr-template-task-field/verify_preview.py` | 미리보기 대상 PASS 6개, 패치와 미리보기·시험 원본 일치, `git apply --check` 통과: [로그](preview-tests.log). 실제 템플릿 변경 없음 |
| `python3 -m unittest discover -s tools/tests -p test_pr_policy.py -v` | PASS 23개: [로그](pr-policy-tests.log). 기존 한정 채택·공통 PR 기준 미채택 유지 |
| `python3 -I tools/ci/check_product_purpose.py` | PASS: [로그](product-purpose.log). 09의 행·작업·필수 시험 ID 정합성만 검사 |
| `python3 -m unittest discover -s tools/tests -v` | PASS: 1,368개 실행·6개 건너뜀: [로그](python-tests.log). 실제 템플릿·기존 CI 시험 기준이며 패키지 안의 새 시험 6개는 위 미리보기 시험으로 별도 실행 |
| `cargo test --all --locked --offline` | PASS: Rust 495개·무시 1개, 중첩 Python 39개·129개: [로그](rust-tests.log). 적용 전 저장소 기준 |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline` | PASS: 온톨로지 실행기 4개: [로그](ontology-runner-tests.log) |

패치 적용 허용이 확인되면 저장소 루트에서 다음 순서로 적용·검증한다. 아래 적용 명령은 아직 실행하지 않았다.

```sh
git apply --check tools/evidence/audit4-pr-template-task-field/pull_request_template.patch
git apply tools/evidence/audit4-pr-template-task-field/pull_request_template.patch
python3 -m unittest discover -s tools/tests -p test_pr_template_traceability.py -v
python3 -m unittest discover -s tools/tests -v
git diff --check
```

이는 템플릿 입력란의 회귀 시험이며 PR 본문 작성 내용의 자동 검사기는 아니다.
실제 데이터·상품/계약 트윈·소비자 화면·사용자 이해 시험 또는 P01~P19 출시 완료 증거를 대체하지 않는다.
