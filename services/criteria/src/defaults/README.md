# 기본값 후보 — T-KN-13

기본 필요액·참고 통계 기본값 후보 적재기다. 통합안 D-08·O05에 따라
후보는 `applied=false`이며 사용자에게 표시하지 않는다. 사용자 가정이
있으면 항상 우선하고, 가정도 없으면 0이나 평균으로 채우지 않는다.

## 현재 상태

**수락 미충족이며 병합 가능한 상태가 아니다.** 제품 크레이트는 이 모듈을
선언하지 않는다. `cargo test -p onjeon-criteria defaults`는 시험 0개를
실행하므로 이 명령의 종료 코드 0은 동작 검증이 아니다.

허용 경로는 `data/criteria/defaults/**`, `services/criteria/src/defaults/**`다.
필요한 연결은 다음 두 파일을 함께 수정해야 하지만 둘 다 허용 밖이다.

- `services/criteria/src/lib.rs`: `pub mod defaults;` 선언.
- `services/criteria/tests/conformance.rs`: `data/criteria/defaults`가 없어야
  한다는 기존 단정을 실제 후보 적재·출처·비노출 검증으로 변경.

fix round 2에서도 두 파일의 허용 경로 추가를 요청했다. 응답 전에는 수정하지
않는다. 검토 가능한 변경안은 `evidence/product-integration.patch`다. 이 패치는
아직 적용되지 않았고 제품 연결이 완료되었다는 증거가 아니다.

검증 진입점 `verification/Cargo.toml`은 시험 전용(`fixture_only`) 별도
워크스페이스다. `onjeon-criteria`의 공용 타입·검증기를 사용하고 `../mod.rs`로
**현재 원본 소스**를 컴파일한다. 임시 배선이나 제품 파일 수정은 하지 않는다.
제품 워크스페이스 연결을 대신하지 않으며 루트 `cargo test --all`에 포함되지 않는다.

```sh
cargo test --manifest-path services/criteria/src/defaults/verification/Cargo.toml --locked --offline --lib
cargo test --manifest-path services/criteria/src/defaults/verification/Cargo.toml --locked --offline --test product_api
```

실행 결과: 모듈 시험 18개 중 17개 통과·후보 납품 시험 1개 실패(F2).
별도 제품 API 시험은 `onjeon_criteria::defaults`를 가져오는 컴파일 단계에서
실패한다(F1/F3). 소스 문구 검색 대신 실제 공개 API 연결을 검사한다. 후보 납품 시험은 저장소
실제 경로를 찾고 디렉터리와 판이 존재하는지 먼저 검사한다. 미존재 경로가
빈 저장소로 처리되어 통과하는 기존 검증 공백을 없앴다.
제품 API 시험은 실제 납품 판을 제품 API로 적재한 뒤 비노출·참고 통계
라벨·사용자 가정 우선도 검사한다. 모듈 연결 전에는 컴파일 실패한다.
최종 작업 파일의 입력 해시와 명령 출력은 `evidence/`에 기록한다.

## 후보 파일 계약

정식 적재 경로는 `data/criteria/defaults/candidates/<slug>.json`이며,
계약 정본은 이 디렉터리의 `default-file.schema.json`이다.

| 항목 | 필수 내용 |
|---|---|
| `candidate` | `def:<slug>` ID, 종류, 이름, 적용 대상·상황, 갱신 주기, `applied=false`, 기록 시각 |
| `versions` | 1개 이상의 판, 기간, 통계 값, 출처, 근거, 기록 시각, origin |
| `sources` | 1개 이상, `raw:sha256:<64>`와 `evidence_kind=public_statistic`만 |
| 정정 | 새 판 + 바로 이전 판 `supersedes` + 정정 사유, 기존 판 유지 |
| 배송 자료 | `origin=pipeline`; 시험 자료는 `tests.rs`의 `origin=fixture`만 |

적재기는 출처·적용 대상·갱신 주기 누락, `applied=true`, 알 수 없는 키,
개인 영역 식별자, 잘못된 수치 형태·날짜·정정 사슬을 거부한다.
`for_service()`는 비어 있고 `display()`의 표시 종류는 “참고 통계”뿐이다.
`effective()`는 사용자 가정을 우선한다. DB 적재·적용 승인·필요성 결과
생성은 이 모듈에 없다. RawAsset의 실재·바이트 해시는 현재 적재기가
확인하지 않으므로 출처 문법 검증을 보관본 검증으로 주장하지 않는다.

## 실제 통계 후보

**0건이며 명세의 데이터 산출물은 미완료다.** `data/criteria/defaults/`도
아직 없다. 빈 후보 집합을 납품 완료로 간주하지 않는다.

공식 [e-나라지표 건강보험 보장률 통계표](https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do?freq=Y&idx_cd=2763&period=N&stts_cd=276302)와
[지표정보](https://www.index.go.kr/unity/potal/main/EachDtlPageDetail.do?idx_cd=2763)를
확인했다. 공표 주기는 1년이고 자료 출처는 국민건강보험공단 조사다.
다만 작업 환경에서 원본 직접 수신은 TLS 오류·연결 시간 초과로 실패했다.
웹에서 읽은 내용으로 원본 바이트 해시를 만들거나 후보 값을 채우지 않았다.

후보 납품에는 보존 원본·실제 SHA-256, 기관·통계표·기준연도, 적용 대상,
갱신 주기, 해시를 참조하는 `origin=pipeline` 판이 필요하다.
개인 필요액으로 환산하거나 적용을 활성화하는 결정은 하지 않았다.

fix round 2 직접 수신도 TLS 오류로 실패했다(`evidence/source_acquisition.log`).
웹 도구로 읽은 통계표를 재구성해서 RawAsset으로 등록하지 않았다.

납품 시험은 출처마다 `data/criteria/defaults/raw-assets/manifest.json`의
`assets` 배열에서 정확히 하나의 수신 기록을 요구한다. 필드는 `ref`,
`origin=pipeline`, `url`(HTTPS), `retrieved_at`(RFC3339), `http_status=200`,
`content_type`, `byte_length`, `agency`, `statistic_table`, `reference_year`다.
`raw-assets/<SHA-256>.raw`의 보존된 전체 응답 바이트가 비어 있지 않고 크기·해시가
일치해야 한다. 변조·빈 응답·허구 해시를 거부하는 시험을 실행했다. 이 검사는
저장된 바이트의 일치 검증이며 기관의 수치를 자동으로 승인하는 절차는 아니다.
