# Audit 8 결정 ID 구분과 T-CT-05 병합 게이트

기준 HEAD는 `32365d1`이다. [결정 원장 §1.2](../../../docs/blueprint/DECISIONS.md#decision-id-namespaces)에 번호 02~18의 확정 방향과 작업 묶음 결정을 나란히 기록했다. `BP-D-04`는 PDF 선택 입력과 가족력 선택 개인화이며 `D-04`는 기존 R2 토큰 사용 결정이다. `BP-D-17`은 R2 비용 제한이며 `D-17`은 개인자료 외부 AI 전송·보존·삭제 정책이다. 각 작업 묶음 ID는 DEC 원문이나 검토본 §8에 연결된다.

이 기준판에는 Audit 6에서 추가한 `D-09`·`D-10` 병합 게이트가 이미 있다. T-CT-05 설명은 감리 근거와 두 게이트 ID 등록을 요구한다고 명시한다. 두 DEC는 감리 대기 상태다. 첫 출시 판정은 [09 제품 목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 실제 완료 증거를 따른다.

## 회귀 검증

- [결정 원장 시험](../../tests/test_decision_records.py)은 17개 행의 ID와 원문 링크, 검토 항목의 작업 색인 범위, 주요 충돌의 의미, 구분표로 가는 링크를 확인한다. 새 시험을 변경 전 문서에서 실행했을 때 02~15번 행과 검토본 링크의 누락을 검출했다.
- [데몬 상태 전이 시험](../../tests/test_audit6_missing_gates.py)은 실제 T-CT-05 작업 정의와 모의 PR을 사용한다. 선행 과제 충족 후 작성·리뷰를 진행하고, 감리 통과를 관측해도 두 실행 게이트가 빠져 있으면 `decision_pending`이다. 이전 원장 ID, 현행 원장 ID, 한쪽 게이트만 등록한 경우에도 대기를 유지했다. 두 실행 게이트를 모두 모의 등록한 뒤 `merge_wait(ready)`에 도달했다.

## 로컬 실행 결과

| 검사 | 결과 |
|---|---|
| 결정 ID·상태·병합 집중 회귀 | 60개 통과 |
| Python 전체 `unittest discover -s tools/tests -v` | 1,800개 실행, 1,794개 통과, 6개 건너뜀 |
| 데몬 실행기 검증 `unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| Rust 작업 공간 `cargo test --all --locked --offline` | 537개 통과, 1개 무시 |
| Scenario API · 온톨로지 실행기 Rust 시험 | 각각 4개 통과 |
| 스키마 호환 시험 | 기본 검사의 33개와 Dart·TypeScript 검사를 포함한 2개 통과 |
| 데몬 `dry_run.py --scenario all --require-all` | 필수 시험 33/33 실행, 세부 검사 695개 통과 |
| 작업 명세 `spec_check.py` | 기계 검사 47/47, 존재 검사 72/72 |
| 결정 색인·Blueprint·제품 목적 표 검사 | 통과 |
| 온톨로지·상태 어휘·수집 원장·V1 문서 검사 | 통과 |

기준판과 작업 계약을 대조했다. 변경 범위는 67개 과제 중 T-CT-05의 `blocked_by` 설명 한 항목이다. 09 제품 목적 대응표는 기준판과 일치한다.

Python에서 건너뛴 시험은 로컬 원본 보관본이 필요한 5개와 이전 botocore 호환성 1개다. `check_compat.sh --latest`는 로컬 비교 태그가 없어 자체 시험을 실행해 통과했고, 태그가 있는 경우의 Dart·TypeScript 비교는 시험이 만든 로컬 저장소에서 검증했다.
