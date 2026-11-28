# Audit 8 HTTP 200 차단 응답의 원문 보관 방지

`audit8-archive-new-block-pages`는 Blueprint A1·Q7·L1과 제품 목적 대응표 P02·P03의 원문 보존에 연결된다. `sources.csv`에는 ABL생명·흥국생명·IBK연금보험의 해외 접속 차단 응답과 금융감독원 서비스 중단 응답이 HTTP 200으로 기록되어 있다. [기관 원장 조사 기록](../../../data/registry/README.md#출처별-접근-결과-이-환경-2026-10-09).

작업 시작점 `3cb1b52`의 `detect`는 이미 표본 형식별 MIME, PDF 시그니처 및 일부 HTML 차단 문구를 검사했다. 같은 코드에 로컬 응답 픽스처를 넣어 EUC-KR 해외 접속 차단 안내, HTML MIME으로 표시된 XML 오류, 충돌하는 `Content-Type` 헤더, 문구로 식별할 수 없는 일반 안내 HTML이 모두 다운로드 검사를 통과하는 것을 재현했다. 해외 접속 차단 안내의 해시를 기준으로 둔 `detect --archive-new` 경로는 `unchanged_bytes`를 반환하고 안내문을 원본 객체와 관측으로 보관했다.

다운로드 작업 프로세스는 단일 `Content-Type`을 표본의 기대 형식과 맞추고, HTML·XHTML 본문에 문서 타입 선언 또는 알려진 HTML 시작 태그를 요구한다. HTML 바이트의 SHA-256을 원장의 `200_geoblock_notice`·`200_service_outage_notice`에 대조하고, 앞 64 KiB의 한국어·영어 지역 제한 및 서비스 중단 문구도 검사한다. 원장 읽기나 필수 열 확인이 실패하면 HTML 수집을 실패 처리한다. 거부 응답은 `fetch_failed`와 상세 사유로 보고되고 종료 코드 1에 반영된다. 이 검사는 캐시 저장, 현재 표본 해시 비교, `--archive-new`의 원본 및 관측 기록 생성보다 앞선다. [검증 코드](../../../tools/verify_sources.py).

## 로컬 회귀 증거

- 루프백 HTTPS의 실제 `detect --archive-new` 경로에서 정상 HTML과 PDF를 보관했다. 지역 차단·WAF·누락 및 중복 MIME·위장 HTML 및 PDF는 `fetch_failed`로 보고됐고 기존 캐시와 보관 파일의 바이트가 일치했다.
- 두 원장 상태에 문구로 식별할 수 없는 합성 HTTP 200 안내문의 실제 SHA-256을 각각 등록했다. 기준 해시까지 안내문과 일치해도 차단됐으며 이전 정상 보관 객체와 관측 JSON이 보존됐다. 같은 원장에 상태 `200`으로 등록한 정상 HTML은 정상 보관됐다.
- 저장소의 `sources.csv`에 기록된 해외 차단 3건과 서비스 중단 3건의 해시를 모의 응답 해시로 넣어 실제 원장 조회가 6건 모두를 식별하는 것을 확인했다.
- 단위 시험은 UTF-8 BOM, 주석, XHTML과 정상 HTML 조각, 기존 WAF·로그인 검사, 정상 페이지의 로그인 링크와 해외 접속 관련 문구, 원장 누락·열 오류를 확인했다. [회귀 시험](../../../tools/tests/test_verify_sources_fetch.py).

| 실행 명령 | 로컬 결과 |
|---|---|
| `python3 -m unittest discover -s tools/tests -p 'test_verify_sources*.py' -v` | 75개 통과, 로컬 원본 보관본 필요 시험 3개 건너뜀 |
| `python3 -m unittest discover -s tools/tests -v` | 1,821개 통과, 원본 보관본 필요 시험 5개와 구버전 botocore 대상 시험 1개 건너뜀 |
| `python3 -I -m unittest discover -s tools/ci/tests -v` | 21개 통과 |
| `python3 -m unittest discover -s tools/daemon/runner_verify/tests -v` | 81개 통과 |
| `cargo test --all --locked --offline` | 566개 통과, 1개 제외 |
| 별도 Cargo 매니페스트의 `cargo test --locked --offline` | 엔진 해시 순서 2개, 시나리오 API 4개, 온톨로지 실행기 4개 통과 |

문구 검사의 범위는 HTML 본문 앞 64 KiB의 알려진 패턴이다. 원장 해시 비교는 전체 HTML 바이트에 적용된다. 실행에는 루프백 응답과 임시 로컬 보관소를 사용했다. P02·P03의 실제 공시 확보와 R2 관측 대조는 [제품 목적 대응표](../proposals/설계검토_결과/09_제품목적_대응표.md)의 완료 증거를 따른다.
