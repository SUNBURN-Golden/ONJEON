# Audit 8 보관소 에뮬레이터 분류와 예산 경계

`audit8-emulator-provider-bypass` · 2026-11-28 · BLUEPRINT §4 L1 · 09 P02·P03 · ADR-0016·0017

Audit 5의 로컬 호스트 허용 목록과 Audit 7의 AWS 경로 폐기가 이미 적용되어 있었다. 일반 AWS S3와 임의 원격 저장소 주소는 `ONJEON_S3_ENDPOINT`로 지정해도 거부된다. 남은 우회는 파서 차이였다. URL의 호스트를 포함하는 부분(`netloc`)에 역슬래시가 있으면 Python은 `@` 뒤의 호스트를 읽을 수 있지만, SDK의 HTTP 파서는 역슬래시 앞의 호스트를 사용할 수 있었다.

`provider_of`는 제공자를 분류하기 전에 `netloc`에 역슬래시가 있는 URL을 거부한다. 예산 작업 없이 허용되는 에뮬레이터는 HTTP(S) `localhost`와 `127.0.0.1`이다. 원격 저장소에는 HTTPS R2와 예산 작업을 요구한다. 이 규칙은 CLI 인자와 `ONJEON_S3_ENDPOINT`에 공통으로 적용된다. 거부 메시지에는 입력 주소를 포함하지 않는다.

## 검증

```sh
python3 -m unittest discover -s tools/tests -p test_store_provider.py -v
python3 -m unittest discover -s tools/tests -p 'test_r2_budget*.py' -v
python3 tools/evidence/audit5-archive-provider-classification/check_provider_mutation.py
```

- 수정 전에는 추가·확장한 회귀 시험 세 개에서 하위 사례 13개가 실패했다. 수정 후 제공자 시험 31개 중 30개가 통과했고, 구버전 botocore 전용 사례 하나를 건너뛰었다.
- `source_archive.py listing`과 `verify_sources.py detect`는 환경 변수의 AWS 주소와 파서 해석이 엇갈리는 주소를 클라이언트 생성 전에 거부했다. 보고서와 출처 요청 없이 종료했다. 저장소 생성 시험은 CLI 인자·환경 변수, 예산 세션 유무, 원장 여부를 교차 검사했다.
- R2 예산 시험 95개가 통과했다. 정상 루프백 에뮬레이터 접근과 DNS 끝 점이 붙은 HTTPS R2의 예산·계량 경로도 시험했다. Audit 5 변이 검사에서 임의 원격 주소를 에뮬레이터로 되돌리는 분기를 기존 회귀 시험 세 개가 모두 검출했다.

Rust 1.98.1의 `cargo test --all --locked --offline`에서 566개가 통과했고 ABox 픽스처 재생성 시험 1개를 건너뛰었다. 삽입 순서 2개, 시나리오 API 4개, 온톨로지 실행기 4개도 통과했다. 제품 목적 대응표 검사, 설계 묶음 검사, Blueprint 집계가 통과했다.

`python3 -m unittest discover -s tools/tests -v`는 1,822개 중 1,816개가 통과했다. 로컬 원본이 필요한 5개와 구버전 botocore 전용 1개를 건너뛰었다. `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v`는 81개가 통과했다.

보관소 시험에는 모의 SDK 클라이언트, Stubber와 로컬 HTTP 스텁을 사용했다. P02의 실제 공시 문서 확보율과 P03의 R2 관측 목록 대조는 각 행의 완료 증거가 필요하다. [09 제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md).
