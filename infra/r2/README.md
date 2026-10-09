# 원본 보관소 (Cloudflare R2)

결정: ADR-0016(사용자 결정, 2026-10-09, D14의 보관소 제공자를 AWS S3에서 R2로 바꿈). 비용 제한: ADR-0017, [BUDGET.md](BUDGET.md). **모든 R2 요청은 작업 파일(`--job`)과 예약 원장을 거친다.** 계약: `docs/data/DATA_PIPELINE_CONTRACT.md` §3.1. AWS용 정의(`infra/s3/`)는 쓰지 않지만 대안으로 남긴다.

비밀키는 이 문서·Git·로그·대화에 쓰지 않는다. 계정 엔드포인트(계정 ID 포함)도 공개 저장소에 쓰지 않고 환경 변수 `ONJEON_S3_ENDPOINT`로만 넘긴다.

## 1. 버킷

| 버킷 | 담는 것 | 키 |
|---|---|---|
| `onjeon-raw-sources` | 공시 PDF·HTML·보험료표 원본(받은 바이트 그대로)과 수집 관측 기록 | `objects/sha256/<aa>/<bb>/<sha256>`, `observations/<source_id>/<시각>_<해시앞16>.json` |
| `onjeon-derived-sources` | 원본에서 만든 추출·OCR 결과와 파생 명세 | `derived/<원본 sha256>/<종류>/<도구>@<버전>/<파일>`, `derived/<원본 sha256>/manifests/<명세 sha256>.json` |
| `onjeon-budget-ledger` | 비용 한도 예약·정산 원장(한 번만 쓰는 기록) | `ledger/v1/<순번 10자리>.json` |

개인 계약·건강·가족력·DNA 자료는 이 버킷들에 넣지 않는다.

## 2. D14 규칙별 R2 대응

R2 S3 호환 API 문서(developers.cloudflare.com/r2/api/s3/api/, tokens, bucket-locks, data-location, 2026-10-09 확인) 기준이다.

| D14 규칙 | AWS 정의(`infra/s3/`) | R2에서 | 이 저장소의 대응 | 남는 차이 |
|---|---|---|---|---|
| 비공개 | 공개 접근 4종 차단 | 버킷은 기본 비공개. 공개는 r2.dev 주소나 사용자 도메인을 켤 때만 | 두 버킷 모두 공개 주소를 켜지 않는다(사용자 확인 항목, §3) | S3 API로는 공개 설정을 확인할 수 없다 |
| 서울 리전 | 리전 고정 | 서울 없음. 위치 힌트 `apac`(아시아·태평양)는 최선 노력이고 보장이 아니다. 강제 관할은 EU·FedRAMP·US뿐 | 도구는 region `auto` | **D14의 서울 리전 조건은 R2에서 지킬 수 없다.** ADR-0016에 기록 |
| 원본·파생 분리 | 버킷 2개 | 같음 | 같음 | 없음 |
| 덮어쓰기 금지 | `If-None-Match` 없는 PutObject를 버킷 정책이 거부 | PutObject `If-None-Match` 지원. 버킷 정책 없음 | 도구의 모든 쓰기가 `If-None-Match: *`. 이미 있으면 바이트를 비교해 같으면 `already_present`, 다르면 `Conflict`로 중단 | 쓰기 권한이 있는 다른 도구는 덮어쓸 수 있다. 막으려면 버킷 잠금(§4) |
| 버전 관리 | 켬 | **미지원** | 없음 | 덮어쓰거나 지우면 되돌릴 수 없다. 버킷 잠금(§4)과 별도 사본으로 보완 |
| 저장 시 암호화 | SSE-S3 | 모든 객체를 자동 암호화. `x-amz-server-side-encryption` 헤더는 미지원 | R2에서는 이 헤더를 보내지 않는다(AWS에서는 보냄) | 없음 |
| TLS만 | `aws:SecureTransport` 거부 | S3 API 엔드포인트가 HTTPS | 도구가 R2 엔드포인트의 http를 거부 | 없음 |
| 수집 주체 삭제 권한 없음 | 버킷 정책으로 삭제 거부 | 토큰 권한은 Admin 읽기·쓰기, Admin 읽기, Object 읽기·쓰기, Object 읽기 네 가지. Object 읽기·쓰기에서 삭제를 빼는 선택지가 문서에 없다 | 도구에 삭제 명령 없음 | 삭제 가능으로 간주한다. 막으려면 버킷 잠금(§4) |
| 검증 주체 읽기만 | 검증 역할 | Object 읽기 토큰, 버킷 지정 가능 | GitHub 재검증은 이 토큰만 쓴다 | 없음 |
| 무결성 | 업로드 SHA-256 체크섬 | SHA-256 체크섬 지원(COMPOSITE). 단일 업로드에서의 검사 동작은 첫 실행에서 확인 | 업로드 때 SHA-256을 보내고, 다시 받아 모든 키의 바이트 해시를 대조(`verify-copy`) | 없음 |
| Object Lock(O14) | 승인 전 미적용 | Object Lock 미지원. 대신 **버킷 잠금**: 접두어별 규칙으로 기간·날짜·무기한 동안 삭제·덮어쓰기 금지 | 승인 전 적용하지 않는다 | §4 |

## 3. 사용자가 할 설정

1. **버킷 공개 주소 끄기 확인:** 두 버킷의 Settings에서 r2.dev 공개 접근과 사용자 도메인이 꺼져 있는지 확인한다.
2. **API 토큰**(R2 → Manage API tokens). 버킷을 지정하고 만료일을 둔다. Admin 권한 토큰은 만들지 않는다(버킷 설정·잠금 변경·버킷 삭제가 가능해진다).
   - 수집 토큰: Object Read & Write, 버킷 `onjeon-raw-sources`, `onjeon-derived-sources`, `onjeon-budget-ledger`.
   - 검증 토큰: Object Read only, 버킷 `onjeon-raw-sources`, `onjeon-derived-sources`.
   - 원장 토큰(GitHub용): Object Read & Write, 버킷 `onjeon-budget-ledger`만.
3. **이 Claude 환경에 등록**(세션 제목 표시줄의 환경 메뉴 → Edit → Network secrets, 없으면 환경 변수). 대화창에 붙여 넣지 않는다. 등록은 새 세션부터 적용된다.

   | 변수 | 값 |
   |---|---|
   | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | 수집 토큰 |
   | `ONJEON_S3_ENDPOINT` | `https://<계정 ID>.r2.cloudflarestorage.com` |

   R2 엔드포인트를 쓰면 도구는 `R2_*` 변수만 읽는다(원장은 `R2_LEDGER_*`가 있으면 그것). 이 환경의 `AWS_*` 자리표시자로 대신하지 않는다.
4. **GitHub 재검증**(선택): Secrets `ONJEON_S3_ENDPOINT`, `R2_VERIFIER_ACCESS_KEY_ID`·`R2_VERIFIER_SECRET_ACCESS_KEY`(검증 토큰), `R2_LEDGER_ACCESS_KEY_ID`·`R2_LEDGER_SECRET_ACCESS_KEY`(원장 토큰). Variables `ONJEON_RAW_BUCKET=onjeon-raw-sources`, `ONJEON_DERIVED_BUCKET=onjeon-derived-sources`. 워크플로는 main에 있어야 실행되고, 동시에 하나만 돈다.
5. **예산 알림**(권장): Billing → Billable Usage → Set Budget Alert. 이메일 알림일 뿐 과금을 막지 않는다.

## 4. 버킷 잠금 정책 초안 (O14, 승인 전 적용하지 않음)

버전 관리가 없으므로 덮어쓰기·삭제를 저장소 단에서 막는 수단은 버킷 잠금뿐이다. 무기한 잠금은 두지 않는다.

| 항목 | 후보 | 고려 |
|---|---|---|
| 대상 | 원본 버킷 `objects/`, `observations/`. 파생 버킷은 잠그지 않거나 짧게 | 파생은 다시 만들 수 있다. 원본은 다시 받을 수 없을 수 있다(동적 HTML·삭제된 공시) |
| 기간 | 기간 잠금(예: 객체 생성 후 N일). 기간과 근거는 승인 대상 | 기간 안에는 잘못 올린 객체도 못 지운다. 개인정보 혼입은 수집 단계에서 막는 것이 우선 |
| 해제 권한 | 규칙 변경은 Admin 권한 토큰이나 대시보드 계정만 가능 | 수집·검증 토큰에는 Admin 권한을 주지 않는다. 대시보드 계정 관리가 해제 권한이 된다 |

승인되면 결정 원장 O14를 닫고 ADR로 남긴 뒤 적용한다.

## 5. 실행 (모두 비용 한도 안에서)

```bash
J=infra/r2/jobs/initial-119.json; L=docs/blueprint/validation/source_checks
# 업로드: 이미 있는 키는 HEAD로 저장 SHA-256만 비교하고 바이트를 보내지 않는다
python3 -I tools/source_archive.py --job "$J#upload" copy --src file://$PWD/raw     --dst s3://onjeon-raw-sources
python3 -I tools/source_archive.py --job "$J#upload" copy --src file://$PWD/derived --dst s3://onjeon-derived-sources
# 대조: Git에 고정한 키·해시 목록과 모든 키(원본 16, 관측 42, 파생 47, 파생 명세 14)
python3 -I tools/source_archive.py --job "$J" verify-copy --expected $L/archive_listing_raw.json        --dst s3://onjeon-raw-sources
python3 -I tools/source_archive.py --job "$J" verify-copy --expected $L/archive_listing_derived_v2.json --dst s3://onjeon-derived-sources
python3 -I tools/source_archive.py --job "$J" verify --raw s3://onjeon-raw-sources
python3 -I tools/verify_sources.py --job "$J" reproduce --raw s3://onjeon-raw-sources --derived s3://onjeon-derived-sources --ocr
python3 -I tools/r2_budget.py status --job "$J"     # 남은 한도
```

종료 코드: 0 성공, 1 검사 실패, 3 쓰기 충돌(덮어쓰지 않음), 4 비용 한도 도달 또는 원장 검증 실패(요청 전 중단). 필요한 것: Python 3, `pip install "boto3>=1.35" pdfplumber==0.11.10`(boto3 1.35 미만은 조건부 쓰기를 보내지 못해 도구가 쓰기 전에 멈춘다), poppler-utils(`pdftotext`), OCR 재실행 시 tesseract(kor).

## 6. 검증한 것과 하지 않은 것 (2026-10-09)

| 항목 | 상태 |
|---|---|
| R2 엔드포인트 접속 | 이 환경에서 응답함. 자격 증명이 없어 `InvalidArgument`(Access Key 길이 14, 32여야 함)로 거부됨 |
| 실제 R2 업로드·다운로드 대조 | **하지 않음** |
| R2 경로 코드(region `auto`, SSE 헤더 생략, `If-None-Match`, 412를 기존 키로 처리, R2 자격 증명 없으면 AWS로 대신하지 않음) | `tools/tests/test_store_provider.py`에서 botocore Stubber로 요청 매개변수 확인 |
| 같은 코드로 S3 에뮬레이터(moto 5.2.3)에 원본 58키·파생 61키 업로드, 재실행 시 전부 `already_present`, 목록 대조 전부 바이트 일치, 표본 14건 해시 일치, 재현 검사 reproduced 8·derived_unverified 5·ocr_not_rerun 1 | 확인. 에뮬레이터는 R2가 아니다 |
| R2의 단일 업로드 SHA-256 체크섬 처리, `If-None-Match` 412 응답 | 첫 실제 실행에서 확인(두 번째 `copy`가 전부 `already_present`면 412 처리 확인) |
| 토큰의 삭제 권한 | 확인하지 않음. 삭제 가능으로 간주 |
