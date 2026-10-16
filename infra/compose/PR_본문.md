## 목적과 설계 연결

- 과제 ID: **T-OP-01** (로컬 Compose: Postgres, S3 호환 객체 저장소, 큐). 구역 infra·ops, 단계 S0
- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): 소비자 기능이 아니라 **개발 환경 기반**이다. 직접 해소하는 A·Q는 없고, 개인정보 경계(전체 질문 보호)를 로컬에서 재현하는 기반이다.
  - A: A1~A6 전체의 **기반**(직접 해소 없음). Q: Q1~Q7 전체의 기반, 개인 영역 보호는 Q5·Q6 쪽
  - L: 공개 영역(L0~L7)과 **개인 영역**의 저장·권한·로그 분리(BLUEPRINT §4 마지막 문단)를 로컬 환경에서 구현. L1(원본 보존)이 쓸 객체 저장소 자리
  - I: **I12**(공개/개인 저장·권한 분리)의 로컬 기반 — 스키마 제약은 M1이라 I12를 "구현"으로 바꾸지 않는다. **I11**(개인 영역 DB가 질의문을 로그에 남기지 않음)의 서버 설정 부분. I13(워커 권한)은 다루지 않음
  - M: **M1**(공개/개인 분리 DB 스키마 초안)이 올라탈 로컬 환경. M0·V0·V1 변경 없음
- 해결하는 소비자 질문: 없음(운영 기반)
- 요구 ID: **R23**(개인자료 최소화·삭제 — 저장·권한 분리의 로컬 기반만. 삭제 작업·누출 시험은 후속), R20 경계(개인 영역에 DNA 등 민감 자료를 넣지 않는 원칙의 저장소 쪽 전제). 다른 R은 건드리지 않음
- 관련 결정 ID / ADR: ADR-0001(스택. **객체 저장소를 MinIO에서 바꿨다** — 아래 한계), 제3부 §48.1·§48.2·§48.4
- 설계 변경인가, 기존 설계 구현인가: 기존 설계 구현. 단 ADR-0001·§48.2의 "로컬 MinIO" 표기와 구현이 다르다(제안 상태 항목). 문서는 허용 경로 밖이라 고치지 않았고, 갱신이 필요하다

## 변경 내용

- `infra/compose/`: `docker-compose.yml`(공개 DB, 개인 DB, S3 호환 저장소, 버킷 생성, 영역 권한 확인), `up.sh`/`down.sh`(+`lib.sh`), `.env.example`(비밀값 없음), `initdb/`(앱 역할·영역 표지·PostgreSQL 기반 큐 `queue.jobs`), `scripts/`(버킷 생성·권한 확인), `smoke.sh`, `tests/test_compose_static.py`(28건), `README.md`, `evidence/`
- `infra/README.md`: infra 디렉터리 색인(신규)
- 데이터·스키마·라벨·규칙·API 영향: 없음. 도메인 스키마는 만들지 않았고 큐 테이블만 있다. `vocabulary.json`은 건드리지 않았다(큐 상태값은 인프라 작업 상태)
- 화면 표시 변화: 없음
- 기존 결과·버전·캐시·개인정보 영향: 없음. 제품 코드·시안 숫자·임시 데이터 없음. 로컬 전용이며 합성 자료만 쓴다는 점을 README에 적었다

## 검증과 한계

- 대상 SHA: 부모 `8d4c9d3bda3164b62699d0a8e773edaf7bee992c`(브랜치 `grokbot/onjeon-T-OP-01`, `main` 병합 시점). 커밋·푸시는 감독 프로세스가 하므로 PR head SHA는 이 문서에 쓸 수 없다. **독립 리뷰는 PR head SHA에 고정해 감독 프로세스가 배정해야 하며, 리뷰어는 작성 계열이 아니어야 한다.**
- 작성 참여 모델 역할·실행 경로: 빌더 역할 하나(작성·시험 실행). 실행 경로는 감독 프로세스가 연 코딩 에이전트 CLI 세션이고 이 작업 트리 안에서만 일했다(임시 시험 도구는 `/tmp`). 모델 식별자 원문은 적지 않는다.
- 실행한 명령과 결과(이 작업 트리, Docker 없는 VM):
  - `bash infra/compose/smoke.sh` → **정적 시험 28건 OK(1건 skip: shellcheck 미설치)**, 이어서 **`LIVE: SKIPPED (docker compose 없음)`**, 종료 코드 0. `evidence/smoke.log`
  - `python3 tools/vocab_check.py`, `python3 tools/validation_check.py` → OK
  - `python3 -m unittest discover -s tools/tests`(CI 단계와 같은 명령) → 305건 OK(6건 skip: 기존 시험). `evidence/repo_unittest_summary.log`
  - 구성요소 직접 실행(Docker 대체): 실제 PostgreSQL 16.14 서버 둘에서 초기화 스크립트와 smoke의 DB 검사 26항목 OK(`evidence/component_postgres.log`); 실제 SeaweedFS 4.48에서 신원 파일·`init-objects.sh`(생성·재실행)·`check-objects.sh` 16항목 OK, 끊긴 엔드포인트에서는 16항목 모두 FAIL로 나옴(`evidence/component_object_store.log`); compose YAML 해석 OK(`evidence/compose_yaml_parse.log`). 재현 스크립트는 `evidence/harness/`
  - 시험이 실제로 잡는지 확인: 정적 시험 대상 구성에 변이 5가지(평문 비밀번호, 0.0.0.0 포트, 볼륨 공유, `latest` 태그, 환경 변수 공유)를 넣어 각각 해당 시험이 실패함을 확인했다
- **확인하지 못한 것(중요):** 이 VM에는 Docker가 없어 **`docker compose up` 자체와 `smoke.sh` 2단계(실제 기동 시험)를 실행하지 못했다.** 인수 기준 "새 클론에서 한 명령으로 뜨고 내려간다"와 "개인 DB와 공개 DB가 다른 자격 증명으로 뜬다"는 위의 구성요소 실행(DB 초기화와 권한, 저장소 권한)과 `up.sh`/`down.sh`의 제어 흐름·호출 인자 확인(docker 대역 사용, 실제 compose 동작 검증이 아님)으로 **간접 확인**했을 뿐이다. 이미지 당김, 컨테이너 안 healthcheck, 마운트한 초기화 스크립트 실행, 네트워크 이름 해석, aws-cli v2, `up --wait` 순서, 종료 뒤 자원 정리는 미확인이다. **Docker가 있는 머신에서 `ONJEON_SMOKE_REQUIRE_DOCKER=1 bash infra/compose/smoke.sh`를 한 번 실행해 `LIVE: PASSED`를 확인해야 이 과제를 완료로 볼 수 있다.**
- 합성 검증 / 실제 원문 검증 / 사용자 검증: 모두 해당 없음(제품 데이터 없음)
- 알려진 한계
  - 객체 저장소가 **MinIO가 아니라 SeaweedFS 4.48**이다. 2026-10-16 현재 `minio/minio`·`minio/mc` 이미지가 Docker Hub에서 조회되지 않고 MinIO 저장소가 보관(archived) 상태다. S3 API만 쓰므로 교체 가능하다. §48.2·ADR-0001 표기 갱신 필요(허용 경로 밖)
  - `tests/`가 `tools/tests`가 아니라 CI(`ci.yml`)가 돌리지 않는다. CI에 넣으려면 `.github/workflows/` 수정이 필요해 이 과제에서 하지 않았다
  - 이미지는 태그 고정이고 다이제스트 고정이 아니다. 로컬은 운영의 R2/S3 보호(쓰기 한 번만 등)를 흉내 내지 않는다. pgvector 없음
- 스켈레톤 비노출·누출 정적 검사: 이 디렉터리에 해당하는 항목은 정적 시험의 비밀값·모델 식별자·비밀처럼 보이는 문자열 검사로 갈음했다. 저장소 전체의 스켈레톤 비노출 시험 대상(화면·API)은 이 과제에 없다
- DECISION_REQUIRED 없음: 되돌릴 수 없거나 비용·법무·비밀값·운영에 관한 결정이 필요하지 않았다. 객체 저장소 제품 교체는 로컬 개발 도구 선택이며 제안 상태 항목이다

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다(개인 영역은 별도 서버·신원으로 분리, 로그 설정 포함).
- [x] 규칙/가격/라벨 변경 없음 — 해당 없음.
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다. 이 PR은 실제 컨테이너 기동을 확인하지 못했다고 위에 적었다.
- [ ] 설계와 구현의 상태를 요구사항 추적표에 반영했다 — 추적표는 `docs/blueprint/REQUIREMENTS.md`(금지 경로)라 이 PR에서 반영하지 않았다.
