# DEC-CANON-T-CT-02 T-CT-02 어휘 정본 변경 조건부 승인

상태: 기록(Fable 5.1 위임 결정, 2026-10-13 17:46 KST) | 위임: 준태님 2026-10-13 16:58 KST 위임 | 대상 과제: T-CT-02

이 문서는 **Fable 5.1이 준태님의 위임(2026-10-13 16:58 KST)에 따라 내린 결정**을 2026-10-13 17:46 KST 기준으로 원문 그대로 기록한다. 기록자는 결정을 다시 판단하거나 고치지 않았다. 아래 "결정 원문"의 JSON이 기록의 본문이다.

## 기록 항목

| 항목 | 값 |
|---|---|
| decision_id | `DEC-CANON-T-CT-02` |
| decided_by | Fable 5.1 (delegated) — 준태님 2026-10-13 16:58 KST 위임 |
| decided_at | 2026-10-13 17:46 KST |
| critical | false |
| reversible | true (결정 원문 why: 되돌릴 수 있고(Git, 기존 값 불변)) |
| decision | 승인(조건부). 병합은 승인하지 않는다 |
| options_considered | A 채택, B·C·D 기각 |
| why | 결정 원문 `why` |
| revisit_if | 결정 원문 `revisit_if` |

## 결정 원문

```json
{
 "critical": false,
 "decision": "승인(조건부). T-CT-02 지시 봉투에 canon_change_approval{decision_ref: \"DEC-CANON-T-CT-02\", scope_paths: [\"packages/schemas/vocabulary.json\", \"docs/blueprint/VOCABULARY.md\"]}를 실어 보낼 수 있다. 내용은 명시된 12개 새 축과 doc_role 값 보강으로 한정하고, 기존 값 삭제·개명·문구 변경 금지, 출처(02 §1.2·§1.4·§1.5·§4.2, 온톨로지 설계안 §13)에 있는 값만, 어휘 1.6.0, VOCABULARY.md는 --write로 재생성, vocab_check와 cargo vocabulary 시험 통과. 병합은 승인하지 않는다: 단독 PR, 즉시 감리, 작성 계열 밖 독립 리뷰, 사용자 병합 지시가 그대로 필요하다. 적용: 그록봇이 decisions_recorded에 DEC-CANON-T-CT-02를 등록하고 과제 정의의 canon_change_approval에 위 값을 넣는다.",
 "options_considered": [
  "A. 지금 좁은 범위·조건부 승인(채택)",
  "B. 사용자가 별도 결정 ID로 지시할 때까지 보류(기각: 가동 결정과 위임이 있고, 추가 전용·Git 복구 가능, 병합 관문에 사용자 지시가 남아 통제 유지, 보류 시 T-CT-05·T-KN-12·T-CT-01 enum 기준이 함께 멈춤)",
  "C. 범위 확대(vocab_check.py·BLUEPRINT §6·docs/decisions 포함)(기각: scope_paths는 허용 경로 안 정본만, BLUEPRINT.md는 금지 경로, vocab_check.py는 정본 아님)",
  "D. 이 결정에 값 목록 확정(기각: 값 내용은 과제와 즉시 감리의 몫)"
 ],
 "why": "정본 보호의 목적은 명시 범위·추가 전용·단독 PR·즉시 감리·사람 병합으로 지켜진다. 되돌릴 수 있고(Git, 기존 값 불변) 실제 돈·법무·비밀값·배포에 닿지 않아 critical이 아니다. 이 승인만으로는 아무것도 병합·배포되지 않는다. T-CT-02는 S0 직렬 구간이라 봉투를 막으면 후속 과제가 멈춘다.",
 "revisit_if": "빌더가 13개 축 밖의 축·값이 필요하거나 기존 값을 삭제·개명·문구 변경해야 할 때(새 결정, 그 전엔 verdict_requested 반송); 사용자가 가동 결정을 거두거나 정본 변경 절차를 달리 지시할 때; D-21 경로의 새 ADR이 정본 반영 절차를 다르게 정할 때; daemon_rules의 decision_record 필드나 canon_change_approval 검증 규칙이 바뀔 때"
}
```

## 이 기록의 범위

- 이 기록은 결정의 기록일 뿐이다. 어휘 정본(`packages/schemas/vocabulary.json`, `docs/blueprint/VOCABULARY.md`)은 이 기록으로 바뀌지 않는다. 바꾸는 일은 T-CT-02 과제의 몫이다.
- 승인은 조건부이며 병합을 포함하지 않는다. 병합에는 결정 원문대로 단독 PR, 즉시 감리, 작성 계열 밖 독립 리뷰, 사용자 병합 지시가 그대로 필요하다.
- 결정 원문의 "적용"(그록봇이 `decisions_recorded`에 `DEC-CANON-T-CT-02`를 등록하고 과제 정의의 `canon_change_approval`에 값을 넣는 일)은 이 PR에서 하지 않았다. 이 PR은 기록 문서 한 개만 추가한다.
