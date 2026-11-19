# DEC-CANON-AUDIT7-CONTRACT-EFFECT 계약 효과 어휘 변경 승인

2026-11-19. Codex가 이번 빌드 지시와 [개발 결정 위임 기록](DEC-O17.md)에 따라 내린 가역적 개발 결정이다. [DEC-CANON-T-CT-02](DEC-CANON-T-CT-02.md)의 승인은 당시 지정한 축과 `doc_role` 보강에 한정된다.

`audit7-vocab-contract-effect-axis`에서 어휘 1.9.0을 1.10.0으로 올리고 아래 두 축을 추가하는 것을 승인한다. 값의 근거는 현재 [rule-0.2 로더](../../packages/rules-engine/src/rule.rs)와 [평가기](../../packages/rules-engine/src/eval.rs)다.

| 축 | 승인한 값 | 적용 필드 |
|---|---|---|
| `contract_effect` | `none`, `void_refund_premium`, `terminated_pay_reserve` | 규칙의 선언과 결과의 `effect`·`conditional_effect` |
| `contract_effect_kind` | `none`, `applies`, `undetermined` | 결과의 `contract_effect.kind` |

```json
{
  "canon_change_approval": {
    "decision_ref": "DEC-CANON-AUDIT7-CONTRACT-EFFECT",
    "scope_paths": ["packages/schemas/vocabulary.json", "docs/blueprint/VOCABULARY.md"]
  }
}
```

승인 조건은 기존 정본에 대한 추가 전용 검사, 어휘 문서와 계약 타입 재생성, 세 필드의 정본 참조, 로더·직렬화 값 집합의 일치 시험이다. 규칙이 선언한 효과와 주어진 조건에서의 적용 여부를 따로 기록하므로 조건 미확정을 효과 없음과 구별할 수 있다. 값의 추가·개명이나 약관 의미 변경에는 새 결정이 필요하다. 병합은 독립 검토와 사용자 병합 지시를 따르며, 서비스 적용은 BLUEPRINT §9.3의 검수·릴리스 관문을 따른다.
