# Audit 2 — R2 엔드포인트 말미 점의 예산 검사 우회 차단

대상: `audit2-r2-endpoint-trailing-dot`, `tools/source_archive.py::provider_of`.
연결: Blueprint A1·L1~L2·M1, ADR-0017, 09 제품 목적 대응표 P02·P03.

## 발견과 수정

기존 판별은 URL에서 분리한 호스트를 그대로 `.r2.cloudflarestorage.com`과 비교했다. DNS 루트 점이 있는 `<acct>.r2.cloudflarestorage.com.`은 에뮬레이터로 분류되어, 보관소의 R2 예산 작업 필수 검사를 건너뛰었다.

이제 호스트의 말미 점을 제거하고 소문자로 정규화한 뒤 접미사를 검사한다. URL 자체는 수정하지 않는다. 같은 R2 호스트는 말미 점·대소문자·포트·경로와 관계없이 R2로 분류되며 HTTPS, 예산 작업, R2 전용 자격 증명, `auto` 리전과 기존 계량기 경로를 따른다. 다른 호스트의 경로·쿼리에 R2 문자열이 있거나 호스트에 다른 접미사가 붙은 경우는 R2로 분류하지 않는다.

## 회귀 증거

- [`test_store_provider.py`](../../../tools/tests/test_store_provider.py): 정규 주소와 말미 점 주소, 대문자·포트·경로·지역 접두어, HTTP 거부, 유사 호스트의 분류를 검사한다. 명시적 인수와 `ONJEON_S3_ENDPOINT` 모두 예산 작업이 없으면 `boto3.client` 호출 전 중단한다. 말미 점 주소에서도 R2 자격 증명 누락 시 AWS로 대체하지 않고, 조건부 PUT과 SSE 헤더 생략을 유지한다.
- [`test_r2_budget.py`](../../../tools/tests/test_r2_budget.py)의 `test_trailing_dot_store_keeps_the_budget_meter`: 말미 점 주소에 실제 `Meter`가 연결되고 고정 목록 밖 GET과 금지 DELETE가 계량기에서 차단되는지 검사한다. botocore Stubber에 응답을 등록하지 않으므로 요청 처리까지 도달하면 실패한다.
- [수정 전 로그](../../../tools/evidence/audit2-r2-endpoint-trailing-dot/before.log): 새 판별·예산 회귀 검사를 기존 구현에 실행하면 12개 하위 사례가 실패한다. 클라이언트 생성 mock과 Stubber를 사용했으며 실제 R2 요청·자격 증명은 사용하지 않았다.

## 실행 결과

모두 이 작업 트리에서 실행했다. boto3 1.43.100을 사용하며 실제 R2 접근은 하지 않았다.

| 명령 | 결과 | 증거 |
|---|---|---|
| `python3 -m unittest discover -s tools/tests -p test_store_provider.py -v` | 22개 실행, 21개 통과·1개 건너뜀 | [공급자 로그](../../../tools/evidence/audit2-r2-endpoint-trailing-dot/provider-tests.log) |
| `python3 -m unittest discover -s tools/tests -p 'test_r2*.py' -v` | 88개 통과 | [예산 로그](../../../tools/evidence/audit2-r2-endpoint-trailing-dot/budget-tests.log) |
| `python3 -m unittest discover -s tools/tests -v` | 950개 실행, 944개 통과·6개 건너뜀, 종료 코드 0 | [전체 Python 로그](../../../tools/evidence/audit2-r2-endpoint-trailing-dot/python-tests.log) |
| `cargo test --all --locked` | Rust 447개 통과·실패 0개·1개 무시, 내장 Python 39개·129개 통과, 종료 코드 0 | [Rust 로그](../../../tools/evidence/audit2-r2-endpoint-trailing-dot/rust-tests.log) |
| 어휘·검증 자료·검증기 selftest·제품 목적 연결·설계 명세·`cargo fmt`·`cargo clippy` | 모두 종료 코드 0 | [명령·결과 로그](../../../tools/evidence/audit2-r2-endpoint-trailing-dot/consistency-checks.log) |

Python 건너뜀 6개는 로컬 원본 보관소가 필요한 기존 검사 5개와 설치된 botocore가 이미 조건부 PUT을 지원하여 해당하지 않는 구버전 검사 1개다. 신규 회귀 검사는 모두 실행했다.

이 증거는 원본 보관 도구의 예산 경계에 한정한다. 실제 공시 확보율·R2 관측 목록 대조·화면·출시 완료 증거를 대신하지 않으며 P02·P03을 완료 처리하지 않는다.
