# ONJEON 온전

**소비자의 알 권리를 위한 보험 앱.** 내가 산 보장, 받지 못하는 조건, 상품 간 차이를 소비자가 직접 이해하고 판단하게 합니다.

 독립 모바일 앱 + 웹 + AI API 개발 저장소. 설계 문서와 함께 규칙 엔진 첫 구현(`packages/rules-engine`)이 있다. 앱·크롤러·API는 아직 없다.

**구현의 단일 기준은 [`docs/BLUEPRINT.md`](docs/BLUEPRINT.md)다.** 목적(정보 비대칭 해소), 범위, 계층, 공유 어휘, 설계 불변식, 구현 순서와 관문을 고정한다. 다른 문서와 충돌하면 설계도를 따른다(ADR-0011).

## 문서

| 문서 | 내용 |
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
| `docs/decisions/` | ADR 0001 스택, 0002 픽스처 우선, 0003 엔진 단일 구현, 0004 대상 범위, 0005 PDF 가져오기, 0006 AI 검수, 0007 단일 완성 출시, 0008 첫 출시 범위, 0009 원구상 복원과 화면·데이터 계약, 0010 선택 화면과 공개 가격, 0011 설계도 채택 |

우선순위는 불변 원칙 → 제2부 → 제3부 → 제1부 순이다. 제3부 §56의 사용자 결정은 이 순서보다 우선한다.

가족력·개인정보는 ADR-0009, 공개 가격·화면은 ADR-0010, 설계도와 세부 계약은 ADR-0011·0012를 따른다. 가족력 선택 입력을 유지하고 상담·포털·실견적은 비활성이다. 화면 이미지는 `docs/design/`에 보관하며 실제 상품·지급 계산 결과가 아니다.

최신: [소비자 화면 설계](docs/design/CONSUMER_FLOW_SPEC.md) · [가격 데이터 수집 명세](docs/data/PREMIUM_DATA_CONTRACT.md) · ADR-0010. 공개 가격 수집·표시·예산 비교는 첫 출시 범위이며 개인 실견적 연계와 구분한다.

세부 구현 계약: [시스템·데이터·수락 계약](docs/blueprint/SYSTEM_CONTRACT.md) · [요구사항 26개와 수락 사례](docs/blueprint/REQUIREMENTS.md) · [결정 원장](docs/blueprint/DECISIONS.md). 단일 진입점은 계속 `docs/BLUEPRINT.md`다(ADR-0012).
