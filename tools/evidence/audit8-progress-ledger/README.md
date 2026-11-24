# Audit 8 — 과제 상태 원장

## 지적

`tasks.json`과 `03_작업명세.md`에는 과제별 관측 상태가 없었고, 최종 관문
`purpose-rows-all-closed`(`tasks.json` T-OP-08)가 요구하는 `post_merge` 상태를
기계적으로 확인할 수 없었다. 출시 준비 판정기는 작업 상태를
`docs/release-readiness/evidence/readiness.json.task_states`에서 읽었지만,
그 필드는 선택적 레거시 입력이었고 T-OP-08의 쓰기 범위 밖 과제 상태를
증거 등록부와 섞었다.

## 변경

- `docs/blueprint/progress/tasks_state.json`을 추가했다. 등록 과제 ID별로 `state`,
  `merge_sha`, `evidence_path`를 기록한다. 초기 원장은 Git 1차 부모 병합
  이력에서 확인한 20개 SHA를 보존하고, 아직 검토하지 않은 상태·증거 경로는
  `null`로 둔다.
- `tools/release_readiness/check.py`의 `purpose-rows-all-closed`와
  `release-readiness-rejects-incomplete`, `tools/release_readiness/progress.py`가
  같은 원장을 읽는다. 연결 과제마다 `merged`·`audit_queued`·`done` 상태,
  전체 소문자 SHA, 증거 디렉터리 안의 비어 있지 않은 정규 파일을 요구한다.
- `tasks.json` T-OP-08의 산출물·시험 설명과 `03_작업명세.md`, `09_제품목적_대응표.md`,
  `docs/BLUEPRINT.md`를 원장 기준으로 맞췄다. `merged_tasks.json`은 원장으로
  대체해 삭제했다.
- `readiness.json`의 레거시 `task_states`는 형식만 검증하고 판정에는 쓰지 않는다.
- 4차 수정에서 원장 경로를 `docs/blueprint/progress/tasks_state.json`으로
  옮겼다. 감리 지적대로 `docs/progress/`가 이 수정 노드의 허용 경로 밖이어서,
  판정기·진척 보고서·시험·문서 링크·`tasks.json` 소비 설명을 모두 새 경로로
  맞췄다. 원장 내용과 판정 결과는 그대로다. T-OP-08은 원장을 읽기만 하고
  어떤 제품 과제도 쓰기 권한을 갖지 않는다.

갱신 절차와 입력 형식은 [판정기 안내](../../release_readiness/README.md#version-1-task-ledger),
판정 배경과 병합 검증은 [Audit 8 기록](../../../docs/blueprint/audits/2026-11-24_task_state_ledger.md)에 있다.

## 실행 결과

| 명령 | 결과 |
|---|---|
| `python3 -I tools/release_readiness/check.py` | 예상대로 종료 코드 1. P행 open=19, 기능 open=64. 원장에 상태·증거가 없는 연결 과제를 지목 |
| `python3 -I tools/release_readiness/progress.py` | 종료 코드 0. 병합 SHA 20/66, 닫힌 목적 행 0/19 |
| `test_release_readiness.py`, `test_purpose_progress.py`, `test_evidence_paths.py` | 37개 통과 |
| `test_ontology_runner_io_error.py` | 15개 통과. 실제 Cargo 잠금·대체 빌드 실패 진단 포함 |
| `test_ci_rust_toolchain.py`, `test_decision_records.py`, `test_o13_ruling.py` | 50개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,783개 실행, 실패 0개, 6개 건너뜀 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` (Rust 1.98.1) | 537개 통과, 기존 무시 1개 |
| 시나리오 API·온톨로지 실행기 Cargo 시험 | 각각 4개 통과 |
| `python3 -I tools/ci/check_product_purpose.py` | 통과 |
| `python3 -I docs/blueprint/proposals/설계검토_결과/검증/spec_check.py` | 기계 47/47, 존재 72/72 통과 |

전체 실행 로그는 [regression.log](regression.log)에 있다. 이 검증은 증거
포함 여부만 판정하며 T-OP-08 전체 감리나 출시 승인이 아니다.
