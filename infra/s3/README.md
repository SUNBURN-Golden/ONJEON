# 원본 보관소 (S3, ap-northeast-2) — 쓰지 않음, AWS 대안

**2026-10-09 사용자 결정으로 보관소는 Cloudflare R2다(ADR-0016, `infra/r2/`).** 이 디렉터리는 AWS로 옮길 경우의 정의로 남긴다.

결정: ADR-0015. 계약: `docs/data/DATA_PIPELINE_CONTRACT.md` §3.1. 이 디렉터리는 버킷 정의와 구성 절차다. 비밀키는 이 문서·Git·로그·대화에 쓰지 않는다.

## 1. 무엇을 만드나

| 버킷 | 담는 것 | 키 |
|---|---|---|
| `onjeon-raw-sources-<suffix>` | 공시 PDF·HTML·보험료표 원본(받은 바이트 그대로)과 수집 관측 기록 | `objects/sha256/<aa>/<bb>/<sha256>`, `observations/<source_id>/<시각>_<해시앞16>.json` |
| `onjeon-derived-sources-<suffix>` | 원본에서 만든 추출·OCR 결과 | `derived/<원본 sha256>/<종류>/<도구>@<버전>/<파일>` |

두 버킷 공통(`source-archive.cfn.yaml`): 서울 리전 강제, 버전 관리, 공개 접근 4종 차단, 버킷 소유자 강제(ACL 없음), 저장 시 암호화(SSE-S3, 버킷 키), TLS 아닌 요청 거부, 조건부 쓰기(`If-None-Match: *`)가 아닌 PutObject 거부(덮어쓰기 차단), 수집 주체의 삭제·수명주기·버전 관리 변경·정책 변경 거부, 스택 삭제 시 버킷 보존(`DeletionPolicy: Retain`).

Object Lock은 이 템플릿에서 켜지 않는다. 보존 기간과 해제 권한이 승인되면(§4) 기존 버전 관리 버킷에 `PutObjectLockConfiguration`으로 적용한다.

개인 계약·건강·가족력·DNA 자료는 이 버킷들에 넣지 않는다. 개인 영역은 별도 계정·버킷·키로 분리한다(BLUEPRINT §4).

## 2. 사용자가 할 설정

1. **IAM 역할 두 개**를 만든다(콘솔 또는 IaC).
   - 수집 역할 `onjeon-source-collector`: 두 버킷에 `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`만. 삭제 권한 없음(버킷 정책이 한 번 더 막는다).
   - 검증 역할 `onjeon-source-verifier`: 두 버킷에 `s3:GetObject`, `s3:GetObjectVersion`, `s3:ListBucket`, `s3:ListBucketVersions`만.
   - GitHub에서 쓸 경우 신뢰 정책은 OIDC(`token.actions.githubusercontent.com`)로, `sub`를 `repo:SUNBURN-Golden/ONJEON:ref:refs/heads/main`으로 제한한다. 장기 액세스 키를 GitHub Secrets에 넣지 않는다.
2. **스택 배포**(관리자 권한, 서울 리전):
   ```bash
   aws cloudformation deploy --region ap-northeast-2 \
     --stack-name onjeon-source-archive \
     --template-file infra/s3/source-archive.cfn.yaml \
     --parameter-overrides NameSuffix=<고유 접미사> \
       CollectorPrincipalArn=<수집 역할 ARN> VerifierPrincipalArn=<검증 역할 ARN>
   ```
3. **이 Claude 세션이 쓰게 하려면** 클라우드 환경 설정(세션 제목 표시줄의 환경 메뉴 → Edit)의 Network secrets 또는 환경 변수에 아래를 넣는다. 수집 역할의 단기 자격 증명을 권장한다. 대화창에 붙여 넣지 않는다.

   | 변수 | 값 |
   |---|---|
   | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, (단기면) `AWS_SESSION_TOKEN` | 수집 역할 자격 증명 |
   | `ONJEON_RAW_BUCKET`, `ONJEON_DERIVED_BUCKET` | 배포된 버킷 이름 |

   2026-10-09 현재 이 환경의 `AWS_ACCESS_KEY_ID`·`AWS_SECRET_ACCESS_KEY`에는 실제 키가 아닌 14자 자리표시자가 들어 있어 AWS가 `InvalidAccessKeyId`로 거부했다(STS·S3 모두). S3 엔드포인트 자체는 이 환경에서 응답했다.
4. **GitHub 재검증**(선택): 저장소 변수 `ONJEON_RAW_BUCKET`, `ONJEON_DERIVED_BUCKET`, `ONJEON_VERIFIER_ROLE_ARN`을 설정한다. `sources` 워크플로는 main에 있어야 수동 실행할 수 있다.

## 3. 설정 후 첫 실행 (임시 보존본 → S3)

2026-10-09 원본 14건은 이 세션의 임시 디렉터리에서 SHA-256 경로 배치로 보존한 뒤 사용자에게 비공개 묶음으로 전달했다(`onjeon-raw-sources-20261009.tar.gz` 3조각, 합친 파일 SHA-256 `50b6ff6b341d9d7caaee92655dbdc5610b415bbcf38204a2b87cd9642492892e`; 파생 묶음은 v2 `onjeon-derived-sources-20261009-v2.tar.gz` `f6f36e54…`를 쓴다. 첫 파생 묶음 `055e5db5…`에는 잘못 연결된 파일 2개가 있다). 묶음을 푼 위치에서:

```bash
python3 tools/source_archive.py copy   --src file://$PWD/raw     --dst s3://$ONJEON_RAW_BUCKET
python3 tools/source_archive.py copy   --src file://$PWD/derived --dst s3://$ONJEON_DERIVED_BUCKET
python3 tools/source_archive.py verify --raw s3://$ONJEON_RAW_BUCKET --report verify.json     # 다시 받아 SHA-256 대조
python3 tools/verify_sources.py reproduce --raw s3://$ONJEON_RAW_BUCKET --derived s3://$ONJEON_DERIVED_BUCKET --ocr --report reproduce.json
```

`copy`는 덮어쓰지 않는다. 같은 키에 다른 바이트가 있으면 멈춘다.

## 4. Object Lock 정책 초안 (승인 전, 적용하지 않음)

정할 것과 후보. 무기한 잠금은 두지 않는다.

| 항목 | 후보 | 고려 |
|---|---|---|
| 모드 | GOVERNANCE(권장 시작점) / COMPLIANCE | COMPLIANCE는 계정 루트도 해제 못 함. 잘못 올린 객체(예: 개인정보 혼입)를 지울 수 없게 된다 |
| 기본 보존 기간 | 원본: 판매 종료 후 N년(예: 상품 판매중지일 + 보험기간 분쟁 가능 기간), 파생: 잠금 없음 | 기간은 객체별로 판매 상태가 바뀔 때 연장 가능, 단축은 GOVERNANCE 해제 권한 필요 |
| 해제 권한 | 별도 break-glass 역할 하나만 `s3:BypassGovernanceRetention`. 두 사람 승인, 사용 시 CloudTrail 경보 | 수집·검증 역할에는 절대 주지 않음(템플릿이 거부) |
| 법적 보존(Legal Hold) | 분쟁·감독 요청 시 객체 단위 | 해제는 같은 break-glass 절차 |
| 잘못 올린 객체 | 잠금 전 발견: break-glass로 삭제 기록 남김. 잠금 후 COMPLIANCE: 삭제 불가 | 개인정보가 원본 버킷에 들어가지 않게 수집 단계에서 막는 것이 우선 |

승인되면 결정 원장 O14를 닫고 ADR로 남긴 뒤 적용한다.

## 5. 검증한 것과 하지 않은 것

| 항목 | 상태 |
|---|---|
| 템플릿 문법 | `cfn-lint` 통과(2026-10-09). 실제 배포는 하지 않음 |
| 보관 도구(`tools/source_archive.py`) | 로컬 디렉터리와 S3 에뮬레이터(moto 5.2.3)에서 저장·재실행(덮어쓰기 없음)·조건부 쓰기 거부·다운로드 후 해시 대조 확인 |
| 실제 S3의 버킷 정책 동작(덮어쓰기·삭제 거부), 체크섬 거부, 암호화 | 미검증. 에뮬레이터는 버킷 정책을 평가하지 않고, 틀린 체크섬도 받아들였다 |
