# Audit 2: 제품 목적 관문(`purpose-rows-all-closed`) 미구현

기록일: 2026-10-27. 노드: `audit2-purpose-gate-unimplemented`. 결정: [audit2-purpose-gate-unimplemented](../../decisions/audit2-purpose-gate-unimplemented.md)(선택 D).
연결: [09 제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md) §6·§7, tasks.json T-OP-08.

## 발견과 현재 상태

감사 지적: P01~P19의 닫힘을 판정할 `purpose-rows-all-closed` 판정기, `tools/release_readiness/check.py`, 증거 디렉터리가 없고 spec_check G47은 문자열만 맞춘다. 09가 기계 검사 관문이 되도록 T-OP-08의 판정기를 지금 만들어야 하는가.

| 지적 | 작업 트리 대조 | 조치 |
|---|---|---|
| `tools/release_readiness/check.py`·`docs/release-readiness/evidence/`가 없음 | **맞다.** 둘 다 없다. 닫힌 행은 0/19이며 09 §7도 "완료 증거는 아직 없다"고 적는다 | 만들지 않는다. T-OP-08의 `allowed_paths`·`produces`이고, 선행 5개(T-OP-07·T-OP-00·T-OP-09·T-KN-14·T-CT-07)가 post_merge가 아니며, 과제 상태는 데몬 기록에만 있고 증거 등록부 형식도 정해지지 않았다. 지금 만들면 닫힘을 꾸미거나 항상 실패한다(결정 문서 선택 A·B 기각 사유) |
| G47이 문자열 존재만 봄 | **설계상 그렇다.** spec_check 요약이 G47을 "존재 검사"로 분류하고 보호된 설계 묶음 안에 있다 | 바꾸지 않는다(선택 C 기각). 대신 CI 정적 검사 `tools/ci/check_product_purpose.py`를 보강 |
| 09가 기계 검사되지 않음 | **일부만 맞다.** `check_product_purpose.py`(시험 14개, CI의 `tools/tests`에서 실행)가 이미 P01~P19 행·구현 과제 실재·§6 시험 ID 9개 등록을 검사했다. 하지만 세 가지 빈틈이 있었다 | 아래 규칙 3개 추가 |

보강 전 빈틈(아래 [before.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/before.log)에서 6개 변이 모두 종료 코드 0):

1. 시험 ID가 **아무 과제에나** 등록돼 있으면 통과했다. `purpose-rows-all-closed`를 T-OP-07로 옮기거나 `acquisition-reason-not-counted`를 T-OP-01로 옮겨도 통과했다.
2. 축소·후속 칸에 근거가 없거나 없는 결정을 인용해도 통과했다. 09 §6은 이 칸을 근거(결정 ID·정본)가 있을 때만 제외로 인정한다.
3. T-OP-08이 최종 관문에서 빠지거나 `--purpose … --evidence docs/release-readiness/evidence/` 판정 명령이 지워져도 통과했다. 이러면 닫힘 관문 자체가 소리 없이 사라질 수 있다.

## 추가한 규칙

| 규칙 | 검사 |
|---|---|
| PURPOSE-OWNER | §6이 정한 담당 과제 중 하나 이상이 각 시험 ID를 `required_test_ids`에 등록해야 한다. T-DT-04 `acquisition-reason-not-counted`, T-AP-04 `coverage-status-counts-acquired-only`, T-KN-08 `label-kinds-complete`, T-TW-05 `switch-diff-evidence-trace`·`multi-contract-relation-trace`, T-MB-03·T-MB-04·T-AP-07 중 하나에 `first-view-priority`·`decisive-conditions-not-hidden`·`no-composite-score`, T-OP-08 `purpose-rows-all-closed`. 담당 외 과제에 추가로 등록된 사본은 허용한다(현재 T-MB-02의 `decisive-conditions-not-hidden`) |
| PURPOSE-SCOPE | 축소·후속 칸이 `—`가 아니면 근거(`ADR-nnnn`, `DEC-*`, `D-nn`, `Onn`, `BLUEPRINT §n`)를 하나 이상 인용해야 하고, 인용한 근거가 모두 저장소에 있어야 한다. `ADR-nnnn`·`DEC-*`·`D-nn`은 `docs/decisions/`의 파일(`D-nn`은 `DEC-D-nn.md`), `Onn`은 `docs/blueprint/DECISIONS.md`의 행, `BLUEPRINT §n`은 `docs/BLUEPRINT.md`의 제목이다. 표에 축소·후속 열이 없으면 PURPOSE-ROWS로 실패한다 |
| PURPOSE-GATE | T-OP-08이 있고 `final_gate: true`이며 `required_test_ids`에 `purpose-rows-all-closed`가 있고, `tests`에 `python3 -I tools/release_readiness/check.py`로 시작하면서 `--purpose docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md`와 `--evidence docs/release-readiness/evidence/`를 포함한 명령이 있어야 한다 |

§6 담당 표는 코드의 `TEST_OWNERS`에 있고 `test_owner_map_matches_section_six`가 09 §6 본문을 파싱해 일치를 확인한다. 현재 저장소의 축소·후속 칸 10개(P01·P02·P03·P06·P09·P11·P14·P17·P18·P19)는 모두 실재하는 근거를 인용한다(P18은 `BLUEPRINT §1`).

이 검사는 정적 연결 검사다. 행이 닫혔는지(구현 과제의 post_merge 상태, 완료 증거 로그)는 판정하지 않으며 출력 문구도 "0 rows proven closed"라고 적는다. 닫힘 판정은 계속 T-OP-08 `purpose-rows-all-closed`의 몫이다.

## 회귀 시험

[`tools/tests/test_product_purpose.py`](../../../tools/tests/test_product_purpose.py): 14개에서 22개로 늘었다. 기존 `test_required_id_on_any_task_passes`는 빈틈 1을 고정하던 시험이라 담당 과제로의 분산·담당 외 사본 허용 시험으로 바꿨다. 추가한 시험은 다음과 같다. 시험 ID 9개 각각을 담당 외 과제로 옮기면 PURPOSE-OWNER, 실제 tasks.json의 담당 등록, §6↔`TEST_OWNERS` 일치, T-OP-08 관문 약화 변이 6종(최종 관문 해제·키 삭제·명령 삭제·`--purpose` 누락·다른 증거 경로·다른 판정기)과 과제 삭제, 실제 T-OP-08 명령 형태와 유일한 final_gate, 근거 형식 5종의 통과와 근거 없음·없는 근거 인용 실패(줄 번호 포함), 실제 09 축소·후속 칸 10개의 근거 보유, 축소·후속 열 삭제. `--selftest`도 규칙마다 변이 하나씩(7개)과 정상 2개로 늘렸다.

## 직접 실행한 검증 증거

| 명령 | 결과·로그 |
|---|---|
| 감독기 1차 실행과 같은 조건(`runner/target` 없음)에서 `test_ontology_runner_io_error.py` | 오류 18개, 모두 `runner/target/debug/ontology-case-runner` 없음. 이 VM의 `CARGO_TARGET_DIR`가 공유 디렉터리를 가리켜 새 작업 트리에 실행기가 없었다. 이번 변경과 무관: [python-tests-initial.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/python-tests-initial.log) |
| `CARGO_TARGET_DIR=target cargo build --locked --offline` (온톨로지 실행기) | 종료 코드 0: [ontology-build.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/ontology-build.log) |
| [purpose_mutation.py](../../../tools/evidence/audit2-purpose-gate-unimplemented/purpose_mutation.py) + HEAD의 `check_product_purpose.py` | 실제 tasks.json·09의 임시 사본에 빈틈 6개를 심어도 7회 모두 종료 코드 0: [before.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/before.log) |
| 같은 스크립트 + 수정한 검사기 | 변이 없는 사본은 종료 코드 0, 변이 6개는 모두 종료 코드 1이고 의도한 규칙이 행·과제를 짚는다: [after.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/after.log) |
| `python3 -I -m unittest discover -s tools/tests -p test_product_purpose.py -v` | 22개 통과: [product-purpose-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/product-purpose-tests.log) |
| `python3 -I -m unittest discover -s tools/tests -v` | 종료 코드 0, 1,153개 실행·실패 0·건너뜀 30개. 건너뜀은 모두 이 VM의 환경 제약(boto3/botocore 미설치·구버전 25개, `ONJEON_ARCHIVE_RAW`·로컬 원본 보관소·pdftotext 필요 5개)이다: [python-tests.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/python-tests.log) |
| 수치·결정 색인·어휘·검증 자료·제품 목적(본 검사·selftest)·명세 검사, `git diff --check` | `blueprint_counts.py`·`blueprint_status.py`·`vocab_check.py`·`validation_check.py`(본 검사·selftest)·`check_product_purpose.py`(본 검사·selftest)·`spec_check.py`(기계 44/44·존재 72/72)·`git diff --check` 모두 종료 코드 0: [consistency-checks.log](../../../tools/evidence/audit2-purpose-gate-unimplemented/consistency-checks.log) |

## 제품 목적과 한계

09가 "철저한 수집·관리, 지식·레이블링, 디지털 트윈, 소비자 화면"의 완료 기준을 각 담당 과제와 최종 관문에 묶어 두는지를, 작업이 더 들어오기 전에 CI에서 지키게 하는 변경이다. `tools/release_readiness/check.py`와 증거 등록부는 여전히 없다. P01~P19 중 닫힌 행은 0개이며, 이 검사를 통과했다고 어느 행이 구현되거나 닫힌 것은 아니다. 닫힘 판정은 T-OP-08이 선행을 마친 뒤 `purpose-rows-all-closed`로 한다. 다시 검토할 조건은 결정 문서의 "Revisit if"를 따른다. T-OP-08이 대기열에 오를 때, 데몬 과제 상태나 증거 등록부 형식이 저장소에 먼저 정해질 때, 운영자가 조기 닫힘 현황판을 요청할 때, 09에 행이나 시험 ID가 추가될 때다.
