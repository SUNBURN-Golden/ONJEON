# Audit 7 0 분모와 사건 목록 검증

2026-11-18, `audit7-unknown-without-blockers` 작업 트리에서 합성 규칙으로 실행했다. [결정과 계약](../../../docs/decisions/audit7-unknown-without-blockers.md).

| 실행 경로 | 확인한 동작 |
|---|---|
| [엔진 rule-0.2 시험](../../../packages/rules-engine/tests/rule_02.rs) | 두 연산의 0 분모는 지급 요건 판정에 따른 미확인 금액을 유지한다. 계산 사유·경로는 선택된 연산과 금액 결과까지 이어진다. 누락·null 분모, 알려진 0에 필요 없는 다른 입력, 분기 선택과 우회, 확인된 빈 목록 및 미확인 금액을 대조한다. |
| [입력 준비 시험](../../../services/scenario-api/src/lib.rs)과 [시나리오 시험](../../../services/scenario-api/tests/scenario.rs) | 확인되지 않은 배열과 외부의 내부 표지는 null로 변환한다. 명시 가정·개인 확인·범위를 확인한 서버 측 빈 목록은 0원으로 평가된다. 실제 트윈 직접 호출의 원시 `[]`와 개별 `krw: null`은 미확인이다. |
| [공개·개인 API 계산 시험](../../../services/scenario-api/tests/scenario.rs) | 두 연산의 0 분모는 `hold`와 어휘의 안내 문구, 누락·null 분모는 `input_missing`과 입력 이름을 반환한다. 선택되지 않은 분기는 정상 금액을 유지한다. 사전 연결 차단 응답에는 엔진 결과가 없다. |
| [폐쇄 스키마 픽스처](../../../packages/schemas/codegen/tests/fixtures/ScenarioResult.zero_denominator.fixture.json) | Rust 계약의 교차 필드 검사, TypeScript 타입 검사, Dart 역직렬화와 직렬화를 통과했다. |

`cargo test --manifest-path services/scenario-api/Cargo.toml --target-dir target/scenario-api --locked --offline -- --nocapture --test-threads=1`의 두 `scenario_wire=` 레코드는 실제 계산 어댑터가 출력한 값이다. 저장소의 `packages/schemas/codegen/validate.py`의 `Validator`로 두 응답을 `ScenarioResult`에 대조했다. [검증된 응답](held-scenarios.json).

마지막 실행의 명령·결과는 [검증 로그](verification.log)에 기록했다. HTTP 엔드포인트와 소비자 앱 연결, 실제 릴리스의 P08·P16 증거는 별도 범위다.
