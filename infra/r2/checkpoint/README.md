# 원장 체크포인트와 O17 관문 (T-OP-04)

R2 비용 제한 원장(`infra/r2/BUDGET.md`)이 대량 수집 전에 필요한 것들을 모았다. 결정: ADR-0017, 결정 원장 O14·O17(`docs/decisions/DEC-O14.md`, `DEC-O17.md`), D-04(`DEC-D-04.md`). 구현: `tools/r2_budget.py`. 시험: `tools/tests/test_r2_checkpoint.py`.

| 문서 | 내용 | 상태 |
|---|---|---|
| [DESIGN.md](DESIGN.md) | 원장 체크포인트 설계와 구현 | **구현·시험됨**(로컬 저장소·S3 스텁), 실제 R2의 시험 원장에서도 쓰기·읽기·audit 확인(VERIFICATION.md) |
| [lock_rules.json](lock_rules.json), [LOCK_RULES.md](LOCK_RULES.md) | 버킷 잠금 규칙안(O14) | **안(案)만.** 기간은 미정, 적용하지 않음, 무기한 없음. `r2_budget.py lock-rules`가 검사 |
| [TOKENS.md](TOKENS.md) | 토큰 재발급 절차(D-04) | 절차서. 재발급은 소유자 몫이며 하지 않았음 |
| [CONCURRENCY.md](CONCURRENCY.md) | 동시성 통제: 무엇이 어디서 강제되는가 | 기존 통제 + 체크포인트 쓰기 규칙. 환경 사이 통제는 운영 규칙 |
| [VERIFICATION.md](VERIFICATION.md), [real_r2_record.json](real_r2_record.json) | 실제 R2 검증 절차와 기록 | **실행함, 완료 아님**(`status: executed_with_failures`): pass 8 · fail 1(`token-scope-no-admin`) · 미확인 2. 실패·미확인이 남아 done이 아니다 |

## 이 과제가 하지 않은 것

- 범위 제한 토큰을 받지 못했다(D-04 재발급은 하지 않음). 대신 준태님이 2026-10-16 19:45 KST에 이번 검증에 한해 기존 환경 자격의 사용을 명시 승인해, 그 자격으로 시험 접두사·시험 버킷에서만 실제 R2를 실행했다. 이 승인은 다른 용도로 이어지지 않는다.
- 기존 객체를 삭제·덮어쓰지 않았고, 시험으로 만든 버킷 2개도 지우지 않았다(소유자 정리).
- 버킷 잠금을 적용하지 않았다. 적용은 O14의 미정 값(기간 N 등)과 소유자 승인이 필요한 별도 실행 단계다.
- 정책(`budget_policy.json`)과 작업 파일(`jobs/`)은 바꾸지 않았다. 체크포인트는 정책 해시를 그대로 쓴다.
- 대량 자동 수집을 켜지 않았다. 지정 환경 하나·동시 1개·수동 실행·고정 키 작업만이라는 O17 기본값은 그대로다.
