# Audit 7 — 원장 GET 바이트와 HTTP 시도 상한

`audit7-budget-accounting-gaps` · BLUEPRINT L1/M1 · 09 P02·P03

Audit 5의 수정이 현재 작업 트리에 반영돼 있다. `Session.open()`은 `ACTIVE`를
설정하기 전에 `budget=self`로 원장 클라이언트를 생성한다. 기본 원장과 주입된
S3 원장 모두 첫 접근 전에 세션 계량기를 연결한다. 정산에서는 `ACTIVE`를
비운 뒤에도 같은 계량기로 원장 GET 본문을 센다. 클라이언트는
`total_max_attempts`로 정책의 최초 요청 포함 상한을 적용한다.
[기존 구현 기록](2026-11-10_r2_budget_ledger_metering.md).

실제 botocore 1.43.114와 루프백 S3에서 실행하는 기존 정책별 시험에 기본 상한
3회와 소진 시 저장된 객체 검사를 추가했다. 소진 시 입장 기록은 남고 예약은
기록되지 않으며, 보관소 접근은 비활성 상태이고 로컬 잠금은 해제된다. 성공
경로에서는 원장 GET 본문 길이와 계량값이 일치한다.
[회귀 시험](../../../tools/tests/test_r2_budget.py#L902).

| 클라이언트 설정 | 준비한 503 응답 | 원장 GET 응답 순서 | 계상된 재시도 | GET 본문 바이트 | 예약 |
|---|---:|---|---:|---:|---|
| `total_max_attempts=3` | 2 | 503, 503, 200 | 2 | 487 | 성공 |
| `total_max_attempts=3` | 3 | 503, 503, 503 | 2 | 0 | 없음 |
| 이전 설정을 메모리에서 재현한 `max_attempts=3` | 3 | 503, 503, 503, 200 | 3 | 487 | 성공 |

바이트 수는 합성 원장 표본의 측정값이다. 입장 재시도 한도는 3이므로 네 번째
요청을 막는 동작은 SDK의 총 시도 상한에서 나온다. 기존 변이 검증은 이전
재시도 설정, 클라이언트 생성 시 세션 전달 누락, 원장 본문 계량 누락을 각각
검출했다. 이전 재시도 설정에서는 503 세 번 뒤 네 번째 GET이 성공해 새 소진
시험의 `BudgetError` 검사가 실패한다.
[변이 검증](../../../tools/evidence/audit5-r2-budget-ledger-metering/verify_mutations.py).

| 실행 | 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p test_r2_budget.py -k policy_total_attempts -v` | 총 시도 1·2·3·4회의 성공·소진 8개 하위 사례 통과 |
| `python3 tools/evidence/audit5-r2-budget-ledger-metering/verify_mutations.py` | 변이 3개 검출 |
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 160개 통과 |
| `python3 -m unittest discover -s tools/tests -v` | 1,719개 통과, 기존 건너뜀 6개 |
| `cargo test --all --locked --offline --target-dir target/workspace` | 537개 통과, 기존 무시 1개 |
| `cargo test --manifest-path services/scenario-api/Cargo.toml --locked --offline --target-dir target/scenario-api` | 4개 통과 |
| `cargo test --manifest-path docs/blueprint/proposals/온톨로지/검증/runner/Cargo.toml --locked --offline --target-dir target/ontology-runner` | 4개 통과 |

온톨로지·설계 묶음·설계도 수치·제품 목적·어휘·레지스트리·V1 내부 일관성
검사와 Rust 포맷·Clippy 검사도 통과했다.

검증은 로컬 합성 데이터와 루프백으로 수행했다. P02의 실제 공시 문서 확보율과
P03의 실제 R2 관측 목록 대조는 제품 완료 증거로 남아 있다.
[제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
