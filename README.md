# ONJEON 온전

**소비자의 알 권리를 위한 보험 앱.** 내가 산 보장, 받지 못하는 조건, 상품 간 차이를 소비자가 직접 이해하고 판단하게 합니다.

보험 데이터·지식 기반과 이를 사용하는 첫 소비자 응용(모바일 앱·웹)의 개발 저장소다. 지식 기반은 내부 전용이며 정체성과 대상 범위는 [ADR-0018](docs/decisions/ADR-0018-보험-데이터-지식-기반의-정체성과-범위.md)을 따른다. 규칙 엔진·스키마·수집 도구·내부 API·모바일 앱 골격 등의 구현과 픽스처 검증이 있으며, 실제 전 상품 데이터·트윈·소비자 화면의 연결은 미완료다. 현황은 설계도 §11, 첫 출시 완료 판정은 [09_제품목적_대응표](docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md)의 완료 증거를 따른다.

**구현의 단일 기준은 [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md)다.** 목적(정보 비대칭 해소), 범위, 계층, 공유 어휘, 설계 불변식, 구현 순서와 관문을 고정한다. 다른 문서와 충돌하면 설계도를 따른다(ADR-0011).

## 문서·데이터·개발 도구

| 경로 | 내용 |
|---|---|
| `docs/BLUEPRINT.md` | **설계도. 단일 기준** |
| `docs/PRINCIPLES.md` | 불변 원칙 10개와 PR 체크리스트 |
| `docs/masterplan/ONJEON_Masterplan_v0.3.md` | 제1부(제품·UX·아키텍처) + 제2부(수집·라벨링·검증) |
| `docs/masterplan/ONJEON_Masterplan_v0.4_제3부_구현계획.md` | 제3부: 앱·사이트 구현 계획, 일정, 위험 |
| `docs/review/2026-10-08_Masterplan_v0.3_평가.md` | v0.3 평가와 보완 권고 |
| `docs/design/README.md` | 선택된 무드 원본, 네 화면 견본, 상태별 UX/UI 구현 기준 |
| `docs/design/화면_조작_설계서.md` | 내 설계 탭 화면·조작 상세 부록(시안 실측 치수·색, 조작, 보장·불이익 비교 모델). 상위: CONSUMER_FLOW_SPEC |
| `docs/masterplan/가격_수집_명세.md` | 가격 수집 상세 부록(조건·특약 라인·가격 분모·검증·지표). 상위: PREMIUM_DATA_CONTRACT |
| `docs/data/DATA_PIPELINE_CONTRACT.md` | 수집·분모·라벨·변경 전파·검증·릴리스 실행 계약 |
| `docs/decisions/` | ADR 0001 스택, 0002 픽스처 우선, 0003 엔진 단일 구현, 0004 대상 범위, 0005 PDF 가져오기, 0006 AI 검수, 0007 단일 완성 출시, 0008 첫 출시 범위, 0009 원구상 복원과 화면·데이터 계약, 0010 선택 화면과 공개 가격, 0011 설계도 채택, 0012 설계도 실행계약과 구현 추적, 0013 전체 대상 목록 우선, 0014 V1 검증 결과의 설계 반영, 0015 원본 보관소 S3, 0016 원본 보관소 R2, 0017 R2 비용 제한, 0018 보험 데이터·지식 기반의 정체성과 범위, 0019 제품 완료와 작업 계약 한정 채택. 결정 기록 `DEC-*.md`(결정 게이트 D-xx·O-xx와 `DEC-CANON-*`)도 같은 디렉터리에 있다. 이 목록은 시험(`tools/tests/test_readme_index.py`)이 디렉터리와 대조한다 |
| `docs/blueprint/VOCABULARY.md` | 상태 어휘 생성 문서(정본 `packages/schemas/vocabulary.json`, `tools/vocab_check.py --write`로 생성, 직접 수정 금지) |
| `docs/blueprint/validation/` | V1 설계 검증 자료: 표본 목록·수집 기록·발췌·인코딩·GAP 보고·화면 연결·검사 실행 기록. 서비스 데이터가 아니다. 안내: `docs/blueprint/validation/README.md` |
| `docs/blueprint/proposals/설계검토_결과/` | 설계 검토 결과 01 코드설계 · 02 구현계약 · 03 작업명세 · 04 자동개발명세 · 05 VM 실행 준비 · 06 검토사항 점검 · 07 수정 대응표 · 08 요구 추적표 · 09 제품 목적 대응표. ADR-0019로 09는 제품 완료 증거 기준, `tasks.json`은 데몬 작업 소스·개별 수락 기준으로 BLUEPRINT 하위에 한정 채택했다. `daemon_rules.json`은 실행 기준만 유지하며 묶음 전체·공통 PR 기준 채택은 제외한다. 자동 개발 입력 `tasks.json`·`daemon_rules.json`, 재검토 요청과 검증 기록도 같은 디렉터리에 있다(안내: 디렉터리의 `README.md`) |
| `data/registry/` | 수집 대상 기관의 1차 근거 목록·접근 결과·미확보 사유. ADR-0018 범위를 따르며 상품·특약·판매본 분모 열거는 미완료다([README](data/registry/README.md)) |
| `infra/r2/` | 현재 원본·파생 보관소인 Cloudflare R2의 작업 명세·비용 정책·체크포인트. ADR-0016이 S3 선택을 대체했고 비용 제한은 ADR-0017을 따른다([README](infra/r2/README.md)) |
| `infra/s3/` | `*.cfn.yaml`은 ADR-0015 당시의 AWS 대안 정의로 보존한다. ADR-0016 이후 미사용·미배포이며 현재 설정은 `infra/r2/`를 따른다([README](infra/s3/README.md)) |
| `tools/daemon/` | T-OP-00 모의 전이·검증 코어와 T-OP-09 실행기 검증 도구. 개발 도구의 검증은 상주 데몬 가동 승인이나 출시 완료 증거가 아니다([README](tools/daemon/README.md)) |

우선순위는 불변 원칙 → 제2부 → 제3부 → 제1부 순이다. 제3부 §56의 사용자 결정은 이 순서보다 우선한다.

가족력·개인정보는 ADR-0009, 공개 가격·화면은 ADR-0010, 설계도와 세부 계약은 ADR-0011·0012를 따른다. 가족력 선택 입력을 유지하고 상담·포털·실견적은 비활성이다. 화면 이미지는 `docs/design/`에 보관하며 실제 상품·지급 계산 결과가 아니다.

최신: [소비자 화면 설계](docs/design/CONSUMER_FLOW_SPEC.md) · [가격 데이터 수집 명세](docs/data/PREMIUM_DATA_CONTRACT.md) · ADR-0010. 공개 가격 수집·표시·예산 비교는 첫 출시 범위이며 개인 실견적 연계와 구분한다. 가격 열 대외 공개 표시는 D-18(O10) 외부 검토 담당 지정 뒤이다([DEC-D-18](docs/decisions/DEC-D-18.md), 범위 축소 아님). 동일 조건·묶음 규칙(O04)은 [DEC-O04](docs/decisions/DEC-O04.md)로 기록됐다.

세부 구현 계약: [시스템·데이터·수락 계약](docs/blueprint/SYSTEM_CONTRACT.md) · [요구사항 26개와 수락 사례](docs/blueprint/REQUIREMENTS.md) · [결정 원장](docs/blueprint/DECISIONS.md). 단일 진입점은 계속 `docs/BLUEPRINT.md`다(ADR-0012). [ADR-0019](docs/decisions/ADR-0019-제품-완료와-작업-계약-한정-채택.md)의 09·[tasks.json](docs/blueprint/proposals/설계검토_결과/tasks.json)은 그 하위의 제품 완료·작업 계약이며 상위 계약을 우선한다.

감리 후속: 준태님의 2026-10-13 R2 토큰 미폐기 결정([DEC-D-04](docs/decisions/DEC-D-04.md))을 O13·§12·VM 실행 준비·작업명세에 반영했다. [정정 내용과 검증 증거](docs/blueprint/audits/2026-10-26_o13_d04_ruling.md)를 참조한다. `cfut_` 규칙과 D-04·O14·O17 접근 관문은 유지한다.
