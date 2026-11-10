# Audit 5 — 결정 원장·결정 기록 재대조

기록일: 2026-11-10. 노드: `audit5-decisions-ledger-sync`.
연결: [결정 원장](../DECISIONS.md), [원장 §3.1](../DECISIONS.md#31-결정-게이트-기록-dec-),
[DEC 기록 디렉터리](../../decisions/README.md),
[Audit 5 검증 증거](../../../tools/evidence/audit5-decisions-ledger-sync/README.md).

## 감리 지적과 조치

감리 지적은 네 가지다. 첫째, 원장 O01이 열린 결정처럼 남아 있었으나
ADR-0018(2026-10-10 사용자 결정)이 우체국보험 포함·기관 유형 구분·공제
제외(확보율 분모에서도 제외)를 확정했다. 둘째,
`data/registry/cooperatives_and_others.csv`의 우체국 행이 "범위 결정
대기"로 남아 있었다. 셋째, 원장 O16이 열린 결정처럼 남아 있었으나
DEC-D-12가 소비자 앱의 원문 이미지·발췌 표시(선택 C)를 결정했다. 넷째,
DEC-* 기록의 원장 행이 없었고 이전 원장의 두 자리 확정 방향 ID가
DEC-D-02·DEC-D-04 실행 게이트와 혼동될 수 있었다.

O01·등록부 문구·DEC 전체 색인은 Audit 2와 Audit 4에서 이미 정정됐다.
이 노드는 그 상태를 다시 전수 대조하고, 남아 있던 두 가지를 고쳤다.

| 지적 | 현재 처리 | 근거 |
|---|---|---|
| O01이 열린 결정 | 원장 O01 행이 `해결`로 ADR-0018·BP-D-19의 포함·제외 범위와 남은 구현 작업을 적는다 | [O01 행](../DECISIONS.md#3-구현-전-미정-사항과-차단-범위) |
| 등록부 "범위 결정 대기" | `cooperatives_and_others.csv`의 우체국 행은 `ADR-0018: 범위 포함`, 공제 13행은 범위·분모 제외를 적는다 | [등록부](../../../data/registry/cooperatives_and_others.csv) |
| O16이 열린 결정 | O16 행을 `해결(앱 표시 결정 질문)`으로 바꾸고 DEC-D-12의 결정·남은 조건을 분리해 적는다 | [O16 행](../DECISIONS.md#3-구현-전-미정-사항과-차단-범위) |
| DEC-* 원장 행 없음 | §3.1이 `docs/decisions/DEC-*.md` 18개와 일대일 대응하는 행을 유지한다 | [원장 §3.1](../DECISIONS.md#31-결정-게이트-기록-dec-) |
| 이전 ID와 DEC 게이트 혼동 | §1은 `BP-D-*`(확정 방향)와 `DEC-D-*`(실행 결정 게이트)를 구분하고, §2 충돌 해소표에 이전 두 자리 ID·DEC-D-02·DEC-D-04의 혼동을 명시했다. §1.1 대응표는 이전 표기를 `BP-D-*`로만 읽으며 DEC 파일명·게이트에 적용하지 않는다 | [원장 §1·§2](../DECISIONS.md) |

O16의 앱 표시 결정 질문은 해결됐지만, 공개 저장소의 새 원문 발췌 추가와
저장소 공개 범위·그 밖의 재배포 조건은 남은 조건이다. 이 노드는 그
조건을 열린 결정으로 되돌리지도, 승인으로 승격하지도 않는다. DEC-D-12
원문의 "공개 저장소에 새 원문 발췌를 추가하는 일을 승인하지 않는다"는
제한도 그대로다.

## 회귀 시험

[tools/tests/test_audit5_decisions_ledger_sync.py](../../../tools/tests/test_audit5_decisions_ledger_sync.py)는
감리 지적을 구조로 고정한다. O01 행의 ADR-0018 해결 표기, 모든 등록부
CSV 셀의 대기 문구 부재, O16 행의 DEC-D-12 해결·잔여 조건 분리, §3.1과
DEC 파일 집합의 일대일 대응, 이전 두 자리 ID의 매핑과 `DEC-D-02`·`DEC-D-04`
게이트 분리, 감리·증거 문서 링크 유효성을 검사한다. 수정 전 원장에서
실행하면 O16·ID 혼동·증거 링크 3건이 실패하고, 수정 후 6건이 통과한다.
로그는 [evidence README](../../../tools/evidence/audit5-decisions-ledger-sync/README.md)에
명령·종료 코드와 함께 기록한다.

## 검증 범위

| 로컬 실행 | 결과 |
|---|---|
| 집중 회귀 시험 | 6건 통과 ([focused.log](../../../tools/evidence/audit5-decisions-ledger-sync/focused.log)) |
| Python 전체 시험 | 1,474건 실행, 실패·오류 0, 건너뜀 6 ([python-tests.log](../../../tools/evidence/audit5-decisions-ledger-sync/python-tests.log)) |
| `python3 -I tools/blueprint_status.py` | 37개 ADR/DEC 색인 일치 ([status.log](../../../tools/evidence/audit5-decisions-ledger-sync/status.log)) |
| `python3 -I tools/blueprint_counts.py` | 규칙 7·변조 40·축 49, Rust 248 + doctest 3 ([counts.log](../../../tools/evidence/audit5-decisions-ledger-sync/counts.log)) |
| `git diff --check` | 공백 오류 없음 ([status.log](../../../tools/evidence/audit5-decisions-ledger-sync/status.log)) |

이 변경은 결정을 새로 내리거나 승인 상태를 승격하지 않는다. 문서 정합성
수정이며 실제 공시 데이터 접근·수집·배포·P01~P19 완료·T-OP-08 출시 판정
증거가 아니다. `docs/PRINCIPLES.md`, `docs/data/`,
`docs/design/CONSUMER_FLOW_SPEC.md`, `DECISION_REQUIRED.md`는 수정하지
않았다. commit·push·GitHub 호출·비밀값 조회·외부 저장소 접근은 수행하지
않았다.
