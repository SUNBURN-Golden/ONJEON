# Audit 8 G11 일부 수익자 고의의 지급 판정 보류

교보통합암보험 암 주계약과 교보K-실속종신보험 제1보험기간 재해사망·질병사망 규칙에서 계약자 고의와 수익자 고의를 각각 판정한다. 약관은 일부 수익자가 피보험자를 고의로 해친 경우 다른 수익자의 지급 예외를 둔다. 이전 규칙의 `harmed_by_beneficiary_or_contractor`는 이 경우까지 전체 면책으로 처리할 수 있었다. [암 약관 제9조](../validation/extracts/kyobo_cancer_terms.md#주계약-제9조-보험금을-지급하지-않는-사유) · [종신 약관 제8조](../validation/extracts/kyobo_wholelife_terms.md#제8조-보험금을-지급하지-않는-사유--자살-2년-예외와-지급-급부-매핑) · [G11](../validation/GAP_REPORT.md#3-부족분-등록부).

현행 `v2-validation` 규칙은 엔진 픽스처에 둔다. 공유 경로의 `v1-validation` 규칙과 해시는 과거 결과의 재현에 사용한다. 기존 사례표의 기본값은 고의가 없음을 전제하므로 시험 로더에서만 두 개의 확인된 `false`로 옮긴다. 개정 규칙에 옛 통합 키를 직접 전달하면 평가 오류를 반환한다. [현행 규칙](../../../packages/rules-engine/tests/fixtures/real/) · [개정 해시](../../../packages/rules-engine/tests/fixtures/real.content_hashes.json) · [시험 로더](../../../packages/rules-engine/tests/common/mod.rs).

| 확인된 사실 | 규칙 입력 | 다른 지급 조건을 충족할 때의 결과 |
|---|---|---|
| 계약자와 수익자의 고의 없음 | `intentional_contractor_harm: false`, `beneficiary_harm_excludes_payout: false` | `true` / `payable`, 기존 금액 계산 |
| 단독 수익자의 고의 | `beneficiary_harm_excludes_payout: true` | `false` / `not_payable` |
| 계약자의 고의 | `intentional_contractor_harm: true` | `false` / `not_payable`, 수익자 몫이 불확정이어도 적용 |
| 일부 수익자의 고의 또는 수익자 고의 판단에 필요한 사실 미확인 | `beneficiary_harm_excludes_payout: null` 또는 키 누락 | `unknown` / `undetermined`, `missing_inputs`에 `beneficiary_harm_excludes_payout` |

암 담보 상세 견본 `sc8`에서 소비자 문구는 ‘계산 불가’로 시작하고 금액을 생략한다. 엔진의 `conditional_amount`는 담보 기준 계산액이며 다른 수익자가 받을 몫은 G11 후속 범위다. 이번 검증은 실제 조항 기반 `fixture_only` 범위다. [화면 견본](../validation/screen/coverage_detail.cancer.json) · [제품목적 대응표 P08·P14](../proposals/설계검토_결과/09_제품목적_대응표.md#7-이-표가-말하지-않는-것).

## 로컬 검증

| 검사 | 증거 |
|---|---|
| `cargo test --locked --offline --all` | Rust 시험 557건 통과, 재생성 전용 시험 1건은 기본 실행에서 제외. 실제 조항 규칙 7건의 골든 사례 118건 중 G11 신규 12건은 두 고의 입력의 분리, 일부 수익자 `null`, 계약자 고의 및 다른 독립 면책의 우선을 확인했다. 세 규칙에서 키 누락과 명시적 `null`의 결과 바이트 일치, 구 통합 키 거부, 현행·과거 해시, `EvaluationResult` 왕복을 검증했다. 화면 변조 시험은 `sc8`의 ‘0원’ 표시를 거부했다. |
| `cargo test --locked --offline -p onjeon-rules-engine --test mutation generic -- --nocapture` | 일반 변이 345건, 생존 0건. 개정 규칙의 변이는 암 43건, 재해사망 30건, 질병사망 89건이다. |
| `python3 -I tools/validation_check.py` 및 `--selftest` | 인코딩·화면 견본·약관 발췌 참조의 내부 일관성 통과. 변조 40건을 의도한 이유로 검출했다. |
| `python3 -m unittest discover -s tools/tests -p 'test_blueprint*.py' -v` | 시험 78건 통과. 개정 규칙의 인벤토리 우선순위, 원본 없는 개정 규칙 거부, G11 인코딩의 과거 경로 재선택 또는 규칙 ID 불일치 거부를 검증했다. |
| `python3 -m unittest discover -s tools/tests -v` | 1,812건 중 1,806건 통과. 로컬 원본 보관본이 필요한 5건과 이전 botocore가 필요한 1건은 건너뛰었다. |
| README의 별도 프로젝트 시험 | 순서 보존 Rust 2건, 시나리오 API Rust 4건, 온톨로지 실행기 Rust 4건, 데몬 검증 Python 81건 통과. |
| [Audit 3 음성 대조 실행기](../../../tools/evidence/audit3-engine-invariant-tests-strengthen/negative_controls.py) 수정 후 재실행 | 정상 기준 통과. 공유 해시 변조 7건과 누락 7건은 각각 공유 해시 값과 키 집합 검사에서 거부됐다. 공유 규칙과 해시를 함께 삭제한 21건 중 개정본이 있는 9건은 원본 누락 진단으로, 나머지 12건은 고정 규칙 ID 목록 검사로 거부됐다. |

[실제 조항 및 화면 회귀](../../../packages/rules-engine/tests/real_clauses.rs) · [암 사례](../../../packages/rules-engine/tests/fixtures/cases/real/kyobo-cancer-main-dx.cases.json) · [종신 사례](../../../packages/rules-engine/tests/fixtures/cases/real/kyobo-wholelife-death.cases.json) · [계약 왕복 시험](../../../packages/schemas/src/tests.rs).
