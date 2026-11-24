# Audit 8 — T-CT-02 어휘 생성물 편집 권한

2026-11-20 KST. 기준 커밋 `06bdeca`에서 어휘와 생성물은 이미 일치했다. 작업 정의에는 어휘 스키마, Rust·Dart·TypeScript 생성물과 스키마 README를 함께 고칠 권한이 빠져 있었다.

- T-CT-02의 허용 경로·충돌 잠금·산출물에 생성물과 README를 반영했다. 승격 필드의 JSON Schema·검사·픽스처와 필요한 계약 판 갱신도 허용한다. 수락 명령으로 생성물 최신성 검사, 워크스페이스 시험과 호환성 검사를 등록했다. 정본 변경 봉투의 권한은 기존 두 어휘 파일에 한정된다. [작업 계약](../proposals/설계검토_결과/tasks.json) · [조건부 정본 승인 기록](../../decisions/DEC-CANON-T-CT-02.md)
- 대기 축 18개 중 `applicability`와 `evidence_kind`는 T-CT-08, `payment_cycle`과 `package_binding`을 포함한 16개는 T-CT-09에 배정했다. T-CT-09는 S2의 계약 작업이며 T-OP-08의 선행에 들어간다. 값 집합 확정과 정본 승격은 후속 작업이다. [대기 축과 담당 과제](../../../packages/schemas/README.md#어휘-승격-대기-축-x-onjeon-pending-axis)

## 재현과 회귀 시험

임시 어휘 사본의 `doc_role`에 합성 값을 하나 추가해 `gen.expected_outputs()`를 실행했다. 현재 파일과 비교했을 때 `json/vocabulary.schema.json`, Rust의 `vocabulary.rs`, Dart의 `vocabulary.dart`, TypeScript의 `vocabulary.ts`가 달라졌다. 같은 변경 경로와 README를 데몬의 R-01 경로 판정에 넣었을 때 기준 작업 정의는 거부했고, 갱신한 작업 정의는 통과했다.

경로 회귀 시험은 생성기가 반환한 전체 경로와 README를 대상으로 편집 권한·잠금·산출물 선언을 대조한다. 스키마 README 시험은 대기 필드와 담당 과제를 대조한다. `payment_cycle` 담당을 지우거나 이중 배정한 메모리 입력은 각각 해당 이유로 실패했다. [경로 회귀 시험](../../../tools/tests/test_vocabulary_task_scope.py) · [대기 축 회귀 시험](../../../packages/schemas/codegen/tests/test_schemas.py)

| 검증 | 결과 |
|---|---|
| `python3 tools/vocab_check.py` 및 `python3 -I packages/schemas/codegen/gen.py --check` | 50축·271값 확인 및 생성물 30개 일치 |
| `cargo test --all --locked --offline` | 537개 통과, 기존 무시 1개. 어휘와 생성 enum의 일치 및 README 담당 검사 포함. 내부 Python 생성기 시험 138개 중 Dart·TypeScript 도구가 필요한 2개는 건너뜀 |
| `cargo test -p onjeon-rules-engine --test vocabulary --locked --offline` | 9개 통과 |
| 시나리오 API·온톨로지 실행기 독립 Cargo 시험 | 각각 4개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,771개 실행, 실패 0, 기존 건너뜀 6개. 두 Cargo 잠금 경로 검사를 포함한 경로 회귀 시험 5개는 별도 재실행해 통과 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 21개 통과 |
| 작업 명세·부트스트랩·제품 목적 정적 검사 | 명세 기계 검사 47개와 존재 검사 72개 통과. 부트스트랩 기존 경로 권고 6개. 09의 P01~P19 링크 확인 |
| `bash packages/schemas/codegen/check_compat.sh --latest` | 필드 삭제 자체 시험 통과. 이전 `contracts-*` 태그가 없어 출시 판끼리의 대조는 미실행 |

이 기록은 작업 권한과 대기 축 배정의 검증 증거다. 첫 출시 판정은 09가 요구하는 실제 데이터·실제 화면·출시 증거를 따른다. [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)
