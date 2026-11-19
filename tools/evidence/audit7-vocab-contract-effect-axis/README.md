# Audit 7 계약 효과 어휘 검증

2026-11-19 기준, 부모 커밋 `f2811e8`의 정본은 1.9.0이며 축 50개와 값 271개를 담고 있었다. 이번 노드는 두 축과 여섯 값을 추가했다. 정본 변경은 이 노드의 [별도 승인 기록](../../../docs/decisions/DEC-CANON-AUDIT7-CONTRACT-EFFECT.md)을 따른다.

## 재현과 회귀 시험

| 검사 대상 | 수정 전 | 수정 후 |
|---|---|---|
| 규칙의 `contract_effect` | 로더·직렬화 대조 시험이 축 누락으로 실패 | 세 코드를 rule-0.2로 로드하고 직렬화한 값이 정본과 일치했다. rule-0.1은 명시한 효과를 거부했다. |
| 결과의 `contract_effect_kind` | 평가 결과 대조 시험이 축 누락으로 실패 | 세 규칙을 각각 참·거짓·미확정 입력으로 평가했다. 결과 태그의 집합과 정본이 일치했고 `applies.effect`와 `undetermined.conditional_effect`에 선언한 효과가 보존됐다. |
| 결과 스키마 | `kind`에 `void_refund_premium`, `effect`에 `applies`, `conditional_effect`에 `undetermined`를 넣은 세 음성 대조가 모두 검사를 통과했다. | 각 필드가 다른 축의 코드를 거부했다. Rust 역직렬화는 미등록 문자열·객체·숫자도 거부했다. `contract_effect`가 통째로 생략된 구버전 결과는 생략 상태로 왕복했다. |

격리한 시험 사본에서 정본에 `unregistered_effect`를 추가하고 엔진의 `applies` 직렬화 이름을 `renamed_result`로 바꿨다. 아래 엔진 시험 두 개가 각각 실패했다(종료 코드 101). 정상 트리에서는 두 시험이 모두 통과한다.

```sh
cargo test --locked --offline -p onjeon-rules-engine --test vocabulary contract_effect
cargo test --locked --offline -p onjeon-contracts contract_effect
python3 -I -m unittest discover -s packages/schemas/codegen/tests -p test_schemas.py -k contract_effect
python3 tools/vocab_check.py --additive-since <(git show f2811e8:packages/schemas/vocabulary.json)
bash packages/schemas/codegen/gen.sh --check
```

## 검증 결과

명령별 종료 코드, 변이 실패의 실제 값, 시험 묶음별 합계는 [실행 로그 발췌](verification.log)에 있다.

| 실행 | 결과 |
|---|---|
| 어휘 추가 전용·생성 검사 | `+2 axes, +6 values, nothing removed/renamed/reworded`. 1.10.0은 축 52개·값 277개, 생성물 30개 일치 |
| `ONJ_REQUIRE_RULE_02=1 ONJ_COMPAT_ALL_CLIENTS=1 cargo test --all --locked --offline` | Rust 539개 통과, 수동 픽스처 재생성 시험 1개 ignored. 포함된 계약 코드 생성·호환 시험 138개 통과 |
| README의 시나리오 API·온톨로지 실행기 Cargo 시험 | 각각 4개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,725개 실행 중 원본 아카이브·구버전 botocore 조건에 해당하는 6개 skip, 실패 0. 이후 승인 범위 회귀 시험을 추가하고 결정·09 대응표·README 색인 시험 71개를 다시 실행해 통과했다. |
| `ONJ_REQUIRE_TOOLCHAINS=1 bash packages/schemas/codegen/build_check.sh` | Rust 1.98.1 빌드, TypeScript 5.9.3 타입 검사, Dart 3.13.5 분석·픽스처 왕복 통과 |
| `cargo fmt --all -- --check`, `cargo clippy --locked --all-targets -- -D warnings` | 통과 |
| `tools/blueprint_counts.py`, `tools/blueprint_status.py`, `tools/validation_check.py` | 엔진 시험 271개·doctest 3개·어휘 축 52개, ADR/DEC 44건 색인, 검증 표본 14건 내부 정합성 일치 |

이 체크아웃에는 `contracts-*` 태그가 없다. 부모 커밋과의 `codegen/compat.py` 구조 대조는 두 축 추가와 `ContractEffectResult` 세 필드의 타입 변경을 보고했다. 배포 시 0.1.0 기준 계약 패키지의 minor 버전과 루트 Cargo 잠금 파일 갱신이 필요하다. 이번 결과는 P08의 엔진·계약 검증이며 실제 릴리스 상품의 경계일 시나리오와 Q1~Q10 골든은 [제품 목적 대응표](../../../docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)에서 별도로 추적한다.
