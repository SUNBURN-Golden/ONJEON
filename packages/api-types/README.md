# packages/api-types: `onjeon-api-types`

OpenAPI v1(공개·개인·관제)의 서버 쪽 Rust 타입. 과제 T-CT-03. `onjeon-contracts`(뷰·어휘 enum)에 의존하고 같은 직렬화 규칙을 따른다(알 수 없는 enum은 역직렬화 실패, 알 수 없는 필드는 무시).

- `src/generated/` 는 `packages/schemas/openapi/*.v1.yaml`에서 `bash packages/schemas/codegen/gen.sh`로 만든 **생성물**이다. 손으로 고치지 않는다.
  - `types.rs`: 요청·응답·쿼리 구조체. 모든 응답 구조체는 필수 `release_id`를 가진다.
  - `operations.rs`: `OPERATIONS`(기본 면의 연산 표: id·방법·경로·캐시 분류·캐시 키·역할·요청/응답 타입 이름). 스켈레톤 연산은 `skeleton` 피처가 있을 때만 `SKELETON_OPERATIONS`로 컴파일된다.
- `src/checks.rs`: JSON Schema로 쓸 수 없는 요청 불변식(`cov_ids` xor `concept_id` 등). 누락을 기본값으로 메우지 않는다.
- 피처 `skeleton`은 **기본 꺼짐**이다. 켜는 것은 별도 결정이다(제3부 §58). 스켈레톤 전용 타입도 이 피처 뒤에만 있다.

```text
cargo build -p onjeon-api-types
cargo test  -p onjeon-api-types                       # 기본 면
cargo test  -p onjeon-api-types --features skeleton   # 예약 연산·타입이 컴파일되고 표에 표시되는지
```

계약 문서와 한계는 `packages/schemas/openapi/README.md`를 본다. 이 크레이트에는 HTTP 서버가 없다(T-AP-01).
