# Audit 7 공시 보관소 AWS 경로 폐기

작업 `audit7-s3-path-superseded`. ADR-0016의 Cloudflare R2 결정을 공시 보관 경로에 반영했다. [ADR-0016](../../decisions/ADR-0016-원본-보관소-R2.md).

## 변경

- 미배포 CloudFormation 템플릿 `infra/s3/source-archive.cfn.yaml`과 AWS 설정·실행 절차를 삭제했다. 기존 예제는 필수 `--job`을 빠뜨렸고 파생 버킷 정책은 원본 버킷의 `PutObjectRetention`, `PutObjectLegalHold`, `BypassGovernanceRetention` 거부를 빠뜨렸다. 편집 범위 밖인 수집 계약 §3.1의 옛 `infra/s3/` 참조도 폐기 안내에서 R2 명령으로 이어진다. [폐기 안내](../../../infra/s3/README.md) · [R2 운영 안내](../../../infra/r2/README.md).
- Python 보관 도구는 `s3://` 대상에 `--endpoint-url` 또는 `ONJEON_S3_ENDPOINT`를 요구한다. 주소가 없거나 AWS를 비롯한 허용 범위 밖의 원격 주소면 SDK 클라이언트 생성 전에 종료한다. HTTPS R2는 `--job`과 원장 절차를 거치고 `file://`와 루프백 S3 에뮬레이터는 로컬 검증에 사용한다. [보관 도구](../../../tools/source_archive.py) · [출처 검증 도구](../../../tools/verify_sources.py).
- Rust 수집 클라이언트는 공시 보관의 원격 전송을 지원하지 않는다. 기존 AWS 분류의 예산 세션 차단과 루프백 전송 범위를 주석에 명시했다. [Rust 수집 클라이언트](../../../services/collect/src/lib.rs).
- ADR-0017과 R2 비용 문서에서 AWS 접근을 설명하던 한 줄씩을 갱신했다. D-04 회귀 픽스처는 두 문서 해시와 변경 설명만 갱신했다. 결정 게이트와 R2 비용 정책 해시는 기존 값과 일치한다. [게이트 픽스처](../../../tools/tests/fixtures/o13_unchanged_gates.json).

## 검증

| 검사 | 관측 결과 |
|---|---|
| 수정 전 회귀 시험 3개 | 엔드포인트 누락과 빈 문자열이 `aws`로 분류됐다. 예산 또는 원장 경로에서 SDK 클라이언트 생성 시도가 검출됐다. 3개 시험 모두 실패했다. |
| 수정 후 제공자·문서 시험 | 60개 실행, 실패 0, 설치된 botocore가 조건부 쓰기를 지원해 구버전 전용 시험 1개 건너뜀. 주소 누락·빈 설정·명시적 AWS 주소를 거부하고 `--job`을 준 실제 보관 CLI도 원장과 보고서 생성으로 진행하지 않는다. R2 작업 필수 조건, 조건부 쓰기·SHA-256·SSE 헤더 생략과 루프백 허용을 재검증했다. |
| AWS 배포 자산 및 안내 | `infra/s3/`에 폐기 안내만 남고 배포 명령과 템플릿이 사라졌는지 검사했다. 루트 README와 BLUEPRINT의 현행 R2 표기도 대조했다. |
| CLI 확인 | `python3 -IS`로 보관·출처 검증 CLI를 실행했다. 각 CLI가 엔드포인트 누락(작업 유무 두 가지), 명시적 AWS 주소, 작업 없는 R2 주소를 종료 코드 1로 거부했고 결과 파일이 생기지 않았다. `file://` 목록 작성은 엔드포인트·작업·SDK 없이 성공했다. |
| `python3 -m unittest discover -s tools/tests -v` | 1,739개 실행, 실패 0, 6개 건너뜀(로컬 실보관본 필요 5개, 구버전 botocore 전용 1개). |
| `ONJ_REQUIRE_RULE_02=1 cargo test --all --locked --offline` | Rust 시험 537개 통과, 픽스처 재생성 시험 1개 무시. 시나리오 API와 온톨로지 실행기 시험은 각 4개 통과. |
| 정합성 검사 | `cargo fmt`, `cargo clippy`, BLUEPRINT 결정·수치 검사, 설계 명세 검사, 온톨로지 검증, 공유 어휘 검사와 검증 자료 변이 40개 모두 통과. |

회귀 시험은 `python3 -m unittest tools.tests.test_store_provider tools.tests.test_storage_provider_docs tools.tests.test_readme_index -v`로 실행한다. [제공자 시험](../../../tools/tests/test_store_provider.py) · [문서 시험](../../../tools/tests/test_storage_provider_docs.py).

검증은 로컬 SDK 스텁과 루프백으로 수행했다. 실제 공시 문서 확보율과 R2 관측 목록 대조는 P02·P03의 남은 완료 조건이다. [제품목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
