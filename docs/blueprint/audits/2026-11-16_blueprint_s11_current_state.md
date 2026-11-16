# Audit 6 — BLUEPRINT §9.2·§11 현재 구현과 관문 증거 대조

기록일: 2026-11-16(KST), 대조 기준일: 2026-11-15(UTC). 노드: `audit6-blueprint-s11-current-state`.
연결: BLUEPRINT A1~A6·Q1~Q7·L0~L9·M0~M6, 09 P01~P19의 완료 증거 추적.
이 기록은 문서 현황 finding의 증거이며 제품 목적 행을 닫는 출시 증거가 아니다.

## 확인과 정정

| 항목 | 소스·관측 | 반영 |
|---|---|---|
| §9.2 현재 판정 누락 | 수락 관문만 있고 생성 타입·DB 초안·수집/문서 복원·온톨로지/트윈 입력·모바일 프레임과의 관계가 불분명했다 | 현재 구현·판정 열을 추가해 모든 마일스톤의 구현 범위와 남은 증거를 분리했다. M0는 엔진 범위 완료, V0는 기관 분모만 완료, V1·M1~M6는 관문 미통과로 유지한다 |
| M1 구현과 I7·I12 | `packages/schemas/codegen/generated/`의 세 언어 생성 타입, `infra/db/`의 공개·개인 SQL·역할·제약과 기존 시험 기록이 있다. DB README는 검토본·미연결 및 I7 저장 조건의 차이를 밝힌다 | §9.2 M1·§11 DB·실행 환경 행에 부분 구현과 한계를 명시한다. §8의 전체 불변식을 완료로 승격하지 않는다 |
| M2 이후 구현 범위 | `services/collect/`, `services/docproc/`, `packages/ontology/`, `packages/twin-runtime/`, `apps/mobile/`에 컴포넌트 구현이 있다 | 실제 L1~L9·화면 근거 사슬·hold·그림자 비교와 구분하고, 상품·특약 미열거·O19, 실제 비교·PDF·두 안 비교·출시 증거 부족을 각 관문에 연결한다 |
| §11 출시 판정기 누락 | `tools/release_readiness/check.py`, 비어 있는 `docs/release-readiness/evidence/readiness.json` | 판정기 구현과 완료 증거 부재를 명시한다. 실제 실행 결과 P행 19개·기능 64개 모두 open, closed/excluded=0, 종료 1을 기록한다. 작업 상태 미등록은 미구현을 증명하지 않으므로 코드 존재 여부와 구분한다 |
| V1·현재 수치 | 2026-10-09 보고서는 완전 재현 8/14. 현재 Cargo 목록 266 + doctest 3, 실제 조항 7, 변조 40, 어휘 49는 기존 자동 생성 표와 일치 | 과거 관측과 최신 로컬 검증을 구분한다. 파생 6건·실제 이종 계열 검수·S1·S6는 미완료로 유지한다. R2 관측이나 시험 수를 새로 지어내지 않는다 |
| 기준일·결정 색인 | 기존 상단·§11은 2026-11-10 | 두 절 대조일을 실행 시각의 UTC 날짜인 2026-11-15로 맞추고 기존 절차로 ADR·DEC 37개 색인을 재생성한다. 결정 내용·가동 승인·출시 범위는 바꾸지 않는다 |

## 회귀 검사와 실행 증거

`tools/tests/test_blueprint_current_state.py`는 각 마일스톤에 수락 조건과
현재 판정이 별도로 있는지, M1·M2 구현 경로와 잔여 증거, V1 역사 기록,
후속 마일스톤의 미통과 상태, §11 DB 검토본·출시 판정기·현재 소스 경로를
검사한다. 출시 수치는 실제 정본·현재 등록부를 기존 판정기로 읽은 결과와
대조한다. 코드·작업 시험 등록을 관측 작업 상태나 출시 증거로 사용하지 않는다.
새 시험은 기존 CI의 `tools/tests` 전체 발견에 포함된다.

수정 전 같은 시험의 실패 기록은 [before.log](../../../tools/evidence/audit6-blueprint-s11-current-state/before.log),
수정 후 집중·전체 시험·관문 검사 결과는 [실행 증거](../../../tools/evidence/audit6-blueprint-s11-current-state/README.md)에 연결한다.

| 최종 로컬 검증 | 결과 | 증거 |
|---|---|---|
| 새 회귀·BLUEPRINT 관련 시험 | 7개·71개 각각 통과 | [집중](../../../tools/evidence/audit6-blueprint-s11-current-state/focused.log), [관련 전체](../../../tools/evidence/audit6-blueprint-s11-current-state/blueprint-tests.log) |
| Python 전체(README 명령) | 1,646개 중 1,640개 통과, 기존 건너뜀 6개, 실패·오류 0 | [실행 로그](../../../tools/evidence/audit6-blueprint-s11-current-state/python-tests.log) |
| Rust 전체·온톨로지 실행기 | 532개 통과·기존 무시 1개, 실행기 4개 통과 | [Rust](../../../tools/evidence/audit6-blueprint-s11-current-state/rust-tests.log), [실행기](../../../tools/evidence/audit6-blueprint-s11-current-state/ontology-tests.log) |
| 실제 완료 등록부 판정 | P행 open=19, 기능 open=64, closed/excluded=0, 종료 1(미완료) | [현재 판정](../../../tools/evidence/audit6-blueprint-s11-current-state/readiness.json) |
| 허용 경로·보호 파일·링크·공백 | 정상 | [검사 기록](../../../tools/evidence/audit6-blueprint-s11-current-state/scope.log) |

첫 Python 전체 실행에서 상단 KST 날짜와 §11의 자동 UTC 날짜 불일치를
검출해 상단도 UTC로 고쳤다. 수정 후 격리 실행은 실패 0·건너뜀 72개였으며,
사용자 설치 boto3를 읽는 README의 일반 명령으로 재실행해 66개 검사도 추가
확인했다. 최종 건너뜀 6개는 원본·로컬 보관본 부재와 구버전 SDK 분기다.
새 회귀 검사에는 건너뜀이 없다. 실패 이력과 각 명령·종료 코드는 위 실행
증거 README에 남긴다.

## 범위와 한계

로컬 문서·시험·검사만 수행한다. DB 행의 실행 근거는 `infra/db/`의 기존
기록이며 이번 노드에서 운영 DB나 비공개 원본을 읽지 않는다. Flutter 기능
화면·이해도 시험 완료를 선언하지 않는다. GitHub 호출·commit·push·비밀값
조회·R2/실제 AI 제공자/프로덕션 접근이 없으며, 보호 문서·정본 결정·실행
관문을 바꾸지 않는다. P01~P19 완료와 T-OP-08 출시 판정은 여전히 별도다.
