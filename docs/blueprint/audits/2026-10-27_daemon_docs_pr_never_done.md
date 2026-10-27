# Audit 2 — 문서 PR이 `done`에 닿지 못하던 `merged` 두 행

기록일: 2026-10-27. 노드: `audit2-daemon-docs-pr-never-done`. 시험 ID: `docs-pr-complete`(T-OP-00, 05 M23).
검증 기준 커밋: `4da09a4b80b77443dad408a9af5de1e7526c62b8`(이 변경은 그 위의 미커밋 작업 트리).

## 발견

`daemon_rules.json`의 `merged → audit_queued`와 `merged → done`은 같은 `(merged, impl_counter_incremented)`를 쓰는데 두 행 모두 `cond`가 없었다. docs-only 구분은 `when` 문장에만 있었고, 코어는 문장을 읽지 않는다. 그래서 [전이 엔진](../../../tools/daemon/core/transition_engine.py)은 cond가 없는 첫 행(`audit_queued`)을 늘 골랐다. 문서 PR은 데이터만으로는 `done`에 닿지 못하고 구현 PR처럼 감리 대기로 갔다. 모의 실행이 `done`에 닿은 것은 관측 계층이 `apply_event(..., to="done")`로 목적지를 직접 지정했기 때문이다. `handle_event`도 사건의 `to` 키를 받아, 밖에서 넣은 사건이 목적지를 정할 수 있었다. 행이 하는 일은 데이터가 정한다는 원칙(T-OP-00 수락 기준)에 어긋난다.

[수정 전 재현](../../../tools/evidence/audit2-daemon-docs-pr-never-done/before.log): 기준 커밋을 임시 디렉터리에 풀고 새 시험 파일만 바꿔 넣어 실행했다. 6개 중 4개 시험이 실패했고, 하위 사례를 포함한 실패는 5건이다(종료 1).

- `merged`인 문서 과제에 `impl_counter_incremented`(`docs_only: true`)를 넣으면 `('merged', 'audit_queued', …)`로 갔다.
- `(merged, impl_counter_incremented)`의 두 행 모두 cond가 없었다.
- `apply_event`에 `to` 인자가 있었다.
- cond를 지우는 변이 시험도 기준 커밋에서는 `done`으로 갔다. 관측 계층의 `to`가 결함을 가렸기 때문이다.

관측 계층을 거친 문서 PR 경로와 구현 PR 경로 시험 둘은 기준 커밋에서도 통과한다. 그 경로의 겉 결과는 원래 맞았다.

## 수정

- [규칙 파일](../proposals/설계검토_결과/daemon_rules.json): `merged → done` 행에 cond `event.docs_only == true`, `merged → audit_queued` 행에 cond `event.docs_only != true`를 더했다. 두 행은 배타다. 값이 없으면 구현 PR로 세어 감리를 거친다(감리를 건너뛰는 쪽으로 열리지 않는다). `core_contract.events_in.payloads.impl_counter_incremented = ["docs_only"]`을 더했다.
- [관측 계층](../../../tools/daemon/core/observation.py) `_count_landing`: docs-only 판정은 그대로다(변경 경로가 모두 `docs/**` 이거나 라벨 `docs-only`, G51). 그 판정을 사건의 `docs_only`로 넘기기만 하고 목적지는 지정하지 않는다. 카운터·묶음은 엔진이 실제로 `merged → audit_queued`를 적용했을 때만 올린다.
- [전이 엔진](../../../tools/daemon/core/transition_engine.py) `apply_event`와 [엔진](../../../tools/daemon/core/engine.py) `handle_event`에서 `to`(목적지 지정)를 없앴다. 지금 전이표에는 같은 `(from, event)`를 쓰는 행 가운데 cond가 없는 행이 하나도 없다. 시험이 이것을 전이표 전체에서 계산한다.

같은 내용을 [04 §2.2 전이표](../proposals/설계검토_결과/04_자동개발명세.md)의 `merged → audit_queued / done` 행, [05 M23](../proposals/설계검토_결과/05_VM실행준비.md), [07 F07 행](../proposals/설계검토_결과/07_수정대응표.md), [spec_gaps G51](../../../tools/daemon/spec_gaps.py), [데몬 README](../../../tools/daemon/README.md)에 적었다. G51은 계속 열려 있다. docs-only 판정 규칙 자체(경로 패턴·라벨)는 여전히 코드에 있고, 이 노드는 행 선택만 데이터로 옮겼다.

## 회귀 증거

[`DocsOnlyLandingCond`](../../../tools/tests/test_daemon_dry_run.py)(6개)는 다음을 확인한다.

- 구조: 같은 `(from, event)`를 쓰는 모든 행 묶음에 cond 없는 행이 없다. 두 `merged` 행의 cond가 정확히 `== true` / `!= true`이고 배타다. 페이로드 표에 `docs_only`가 있다.
- 코어 직접 입력: `merged`인 과제에 `docs_only: true`를 넣으면 `done`, `false`이거나 값이 없으면 `audit_queued`.
- 목적지 지정 없음: `apply_event`에 `to` 인자가 없다. `handle_event`에 `"to": "done"`을 넣어도 구현 PR은 `audit_queued`로 간다.
- `docs-pr-complete`: `docs/**`만 바꾼 PR과 라벨 `docs-only` PR이 `merge_wait → merged → done`이고, 카운터 0·묶음 없음·`increment_counter` 기록 0이다.
- 구현 PR은 `audit_queued`, 카운터 1, 묶음 B1에 들어가며 `increment_counter` 기록이 1건이다.
- 변이 시험: 두 행의 cond를 지우면 문서 PR이 첫 행(`audit_queued`)으로 가고 카운터가 1이 된다. 지적이 그대로 재현된다.

dry_run 보고서의 M23(docs-pr-complete)에 "merged→done 행은 cond event.docs_only == true로 골랐다" 검사를 더했다. 전이 기록의 `cond_evaluated`를 비교한다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest tools.tests.test_daemon_dry_run.DocsOnlyLandingCond -v` | 수정 전 4개 시험 실패·하위 사례 포함 5건(종료 1), 수정 후 6개 통과 | [before.log](../../../tools/evidence/audit2-daemon-docs-pr-never-done/before.log), [focused.log](../../../tools/evidence/audit2-daemon-docs-pr-never-done/focused.log) |
| `python3 -m unittest tools/tests/test_daemon_dry_run.py` | 207개 통과 | [unittest.log](../../../tools/daemon/reports/unittest.log) |
| `python3 -I tools/daemon/dry_run.py … --scenario all --require-all` | 검사 666건·실패 0건·명세 공백 표시 0건 | [dry_run.log](../../../tools/daemon/reports/dry_run.log) |
| `python3 -m unittest discover -s tools/tests -v` | 1017개 실행·통과, skip 6, 종료 0 | [python-tests.log](../../../tools/evidence/audit2-daemon-docs-pr-never-done/python-tests.log) |
| 어휘·검증 자료·검증기 selftest·`spec_check.py`(기계 44/44·존재 72/72)·`check_product_purpose.py`·`blueprint_status.py`·`git diff --check` | 모두 종료 0 | [consistency-checks.log](../../../tools/evidence/audit2-daemon-docs-pr-never-done/consistency-checks.log) |

전체 Python 시험 전에 온톨로지 runner를 작업 트리 안(`CARGO_TARGET_DIR=target`)에 빌드했다. skip 6개는 로컬 비공개 원본이 필요한 기존 검사 5개와, 설치된 botocore에는 해당하지 않는 구버전 검사 1개다. 새 시험은 skip하지 않았다. Rust 파일은 바꾸지 않아 `cargo test`는 다시 돌리지 않았다. 데몬 보고서 두 개는 기준 커밋과 현재 소스 해시로 다시 만들었다. 위 결과는 로컬 실행이며 원격 CI 결과가 아니다.

## 증명 범위

이 증거는 모의 어댑터를 쓰는 데몬 코어와 규칙 데이터의 전이 선택만 검증한다. 실제 GitHub PR의 경로·라벨 관측이나 실제 실행기(T-OP-09)의 동작은 증명하지 않는다. 열린 명세 공백 G51~G57의 해결이나 데몬 가동 승인도 주장하지 않는다. [09 제품목적 대응표 §5](../proposals/설계검토_결과/09_제품목적_대응표.md#5-출시-완성품이-아닌-것혼동-방지)에 따라 데몬은 개발 도구이고 T-OP-08 축 5의 운영 기록으로만 연결된다. 이 시험은 P01~P19의 실제 데이터·화면·출시 완료 증거를 대신하지 않는다.
