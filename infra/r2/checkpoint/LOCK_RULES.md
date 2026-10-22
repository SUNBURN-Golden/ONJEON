# 버킷 잠금 규칙안 (O14, 적용하지 않음)

근거: `infra/r2/README.md` §2·§4, `docs/decisions/DEC-O14.md`(보수적 기본값: 도구의 조건부 쓰기 + 삭제 명령 없음 + 별도 사본, 무기한 잠금 금지, 승인 전 적용 금지). 기계 판독: [lock_rules.json](lock_rules.json). 검사: `python3 -I tools/r2_budget.py lock-rules`(요청 없음).

R2에는 버전 관리·Object Lock이 없다. 덮어쓰기·삭제를 저장소 단에서 막는 것은 버킷 잠금(접두어별 규칙, 기간 또는 날짜)뿐이다.

## 규칙안

| 규칙 | 버킷 · 접두어 | 조건 | 기간 N |
|---|---|---|---|
| raw-objects | `onjeon-raw-sources` · `objects/` | Age | 미정 |
| raw-observations | `onjeon-raw-sources` · `observations/` | Age | 미정 |
| ledger-records | `onjeon-budget-ledger` · `ledger/v1/` | Age | 미정 |
| ledger-checkpoints | `onjeon-budget-ledger` · `checkpoint/v1/` | Age | 미정 |
| ledger-admissions | `onjeon-budget-ledger` · `admission/v1/` | Age | 미정 |
| ledger-closures | `onjeon-budget-ledger` · `closed/v1/` | Age | 미정 |
| 파생 버킷 | `onjeon-derived-sources` | 잠그지 않거나 짧게 — DEC-O14가 고르지 않음 | 미정 |

기간 N과 그 근거는 소유자 승인 대상이고 어떤 값도 정하지 않았다. 아래 제약은 값이 아니라 **값이 지켜야 할 조건**이다.

## 무기한 잠금이 없는 방식

1. 조건 종류는 `Age`(객체 생성 후 N일)만 허용한다. `Indefinite`는 물론 고정 날짜(`Date`)도 허용하지 않는다(날짜는 갱신 없이 무기한 근처로 쓰이기 쉽다).
2. N은 1 이상 3650 이하의 정수다. 그 밖은 사실상 무기한으로 보고 검사기가 거부한다.
3. 기간이 미정인 규칙 파일은 `proposed_not_applied`여야 하고, 규칙은 `enabled: false`이며 승인 기록이 없다. `approved`·`applied`로 바꾸려면 모든 규칙의 N, `approval.by/at/record`가 필요하다. 시험(`LockRules`)이 이 규칙들을 고정한다.

## 기간 선택이 지켜야 할 조건 (값을 정하지 않고 적음)

- **잘못 올린 객체:** 기간 안에는 지울 수 없다. 개인 계약·건강·가족력·DNA 자료는 수집 단계에서 막는 것이 우선이다. 잠긴 객체의 처리 절차는 미정(DEC-O14)이다.
- **원장은 휴지기를 넘어야 한다:** 기간 잠금은 객체가 만들어진 시점부터 센다. 원장 꼬리 기록이 N일보다 오래되면 잠금이 풀려 지워도 감지하지 못한다(BUDGET.md §5). 실행이 없는 기간이 N을 넘을 수 있으면 기록을 새로 쓰는 실행(`status`)이 N 이전에 필요하다. N은 가장 긴 예상 휴지기보다 길어야 한다.
- **체크포인트와 원기록:** audit는 원기록 전체를 다시 읽는다. 원기록이 잠금 기간 뒤 지워지면 audit는 지워진 구간을 확인하지 못한다. `ledger/v1/`의 N은 audit를 하려는 기간 이상이어야 한다.
- **해제 권한:** 규칙 변경은 Admin 권한 토큰 또는 대시보드 계정만 한다. 수집·검증·원장 토큰은 Admin이 아니다(TOKENS.md).

## 적용 전에 정해야 하는 것 (DEC-O14의 미정 항목)

기간 N과 근거, 잘못 올린 객체 처리 절차, 원장 버킷 접두어·기간·해제 권한의 확정, 파생 버킷 선택. 모두 소유자 승인 뒤 별도 실행 단계에서 적용하고 ADR로 남긴다. 이 과제는 적용하지 않았다.
