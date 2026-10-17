## 목적과 설계 연결

- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A1~A4(보장·제한·차이·가격과 조건의 저장 기반), Q1~Q4·Q7(근거 사슬 저장), L1~L5·L7, I7·I12(+K1·K8·K14·K15 DB 방어선), M1(공개/개인 분리 DB 스키마 초안)
- 해결하는 소비자 질문: 간접. 근거 없는 주장·조건 없는 가격이 저장·공개 경로에 들어오지 못하게 하는 저장소 제약
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R03·R04·R05·R08(accepted⇒ReviewDecision), R10·R11(가격 조건·비교 자격), R23(개인/공개 분리·삭제 중 쓰기), R15(계약 스냅샷 버전 매핑 저장), R17(근거 사슬의 FK)
- 관련 결정 ID / ADR: D-09·D-10 선택안(06_검토사항_점검), ADR-0006(이종 계열 검수), ADR-0014(C0 근거는 약관), 결정 ID 없음(감리 통과 전 병합 대기)
- 설계 변경인가, 기존 설계 구현인가: 기존 설계(02_구현계약 §1.2~§1.6·§8.2) 구현. 정본 문서·어휘는 건드리지 않았다

## 과제와 작성 정보

- 과제 ID: T-CT-05 (zone contracts, stage S0, 선행 T-CT-01·T-CT-02 병합됨)
- 작성에 참여한 모델 역할·실행 경로: 빌더 역할 둘. 초기 작성과 수정 라운드 1~3은 한 빌더가, 수정 라운드 4~5는 다른 모델 계열의 빌더가 맡았다. 둘 다 감독 프로세스가 연 코딩 에이전트 CLI 세션이고 작업 트리 `wt/T-CT-05` 안에서만 작업했다(임시 시험 도구와 Docker는 `/tmp`에 두고 끝나고 지웠다). 모델 식별자 원문은 적지 않는다. 계열은 감독 상태 파일에 있으며, 독립 리뷰는 두 작성 계열 모두와 다른 계열이어야 한다
- 대상 SHA: 기준 `5e06eb5`(origin/main, T-CT-02 병합) 위의 작업 트리 변경. 커밋·푸시는 감독 프로세스가 하므로 커밋 SHA는 커밋 뒤 감독 프로세스가 기입하고 독립 리뷰를 그 SHA에 고정한다

## 변경 내용

- 데이터·스키마·라벨·규칙·API 영향: `infra/db/` 신설. 공개 15 테이블(+보조 표 `conflict_member`)·criteria 3·개인 9, 역할 4종(NOLOGIN 그룹), 제약·트리거, 권한, `apply.sh`, 시험 `public/test.sh`(149건)·`public/tests/test_vocab_sync.py`, 실행 기록 `public/evidence/`. 코드·어휘·정본 문서 변경 없음. 어휘 도메인은 vocabulary 1.6.0과 `test_vocab_sync.py`로 대조
- 화면에서 보장·제외·가격·미확인을 표시하는 변화: 없음
- 기존 결과·버전·캐시·개인정보 영향: 없음(새 스키마). 공개 DB에는 `contract:` 등 개인 식별자가 들어가지 못하고 `personal` 역할은 공개 테이블에 쓰지 못한다

## 검증과 한계

- 수락 사례와 기대 결과: I7(자격 있는 가격은 조건·구성·기준일·근거 필수, 공백 행은 자격 없음 + 공백 차원 명시), K8(6개 접두어 + jsonb·배열 은닉), accepted⇒결정(결정의 outcome까지), fixture⇒not accepted, I12(`personal` 쓰기 거부), FK 7종 존재·작동. 거부마다 이유 문구(제약 이름)를 확인하고, 변이 7종은 제약을 풀면 같은 입력이 통과함을 보인다
- 실제 수행한 검증 및 결과:
  - `bash infra/db/public/test.sh`(환경 변수 없이, `/bin/sh -c`로 감독 프로세스와 같은 방식) → `RESULT: passed=149 failed=0 / DB CONSTRAINTS: PASSED`, PostgreSQL 17.11 임시 클러스터(`public/evidence/test.log`, 수정 라운드 5에서 실행한 기록. 라운드 4 기록과 점검 149건의 내용이 같고 첫 줄에 바이너리 위치만 더해졌다). `ONJEON_PG_BIN`을 명시해도 같은 결과, 잘못된 `ONJEON_PG_BIN`은 `NOT RUN`으로 실패(rc=1)하고 임시 클러스터를 남기지 않음을 확인
  - 같은 시험을 `infra/compose` 스택의 `postgres:16.15-alpine` 공개 DB 서버와 개인 DB 서버 각각에서 URL 경로(`ONJEON_DB_ADMIN_URL`, 비밀번호는 PGPASSWORD로만)로 실행 → 둘 다 149/0. 이어 compose가 만든 실제 `onjeon_public`·`onjeon_private`에 `apply.sh` 적용 성공, 재적용 거부(rc=3), 앱 로그인 역할은 그룹 역할 구성원이 아니라 도메인 표를 읽지 못함, `down.sh --purge` 뒤 컨테이너·볼륨·네트워크 0(`public/evidence/test_compose_pg16.log`). 작업 VM에는 Docker가 없어 정적 바이너리를 `/tmp`에 받아 임시 데몬으로 올렸고 끝나고 지웠다
  - 저장소 시험 명령(감독 프로세스의 test_cmd와 같은 것): vocab_check·validation_check(+selftest) OK, `python3 -m unittest discover -s tools/tests` 388건 OK(skipped=6), `cargo fmt --check`·`cargo clippy -D warnings`·`cargo test --all` OK, spec_check 기계 44/44·존재 72/72
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: 합성 검증(시험 전용 행, 원문 없음). 실제 원문·상품 정확도 검증 아님
- 수정 라운드 처리(1~5): 다섯 라운드 모두 실패 항목은 하나, 과제의 `tests` 항목 `bash infra/db/test.sh (Compose Postgres에서 제약 시험)`이다. (1) 뒤의 괄호 설명이 명령에 붙어 있어 `/bin/sh`가 `(`에서 구문 오류를 내고 아무것도 실행하지 않는다(어떤 셸에서도 같다). (2) `infra/db/test.sh`는 이 과제의 허용 경로(`infra/db/public|personal|criteria/**`, `infra/db/README.md`) 밖이라 만들 수 없다(감독 프로세스의 경로 검사가 거부한다). 작업 트리에서는 고칠 수 없는 항목이고, 되돌릴 수 없는 결정·비용·법무·비밀값·운영 사안이 아니므로 DECISION_REQUIRED도 아니다. 대신 그 항목이 뜻하는 시험(compose Postgres에서 제약 시험)을 위와 같이 실제로 실행해 기록했다. **감독 측 조치 필요:** `tests` 항목을 `bash infra/db/public/test.sh`로 바꾸거나(설명은 별도 필드), 명령 끝의 ` (…)` 설명을 떼고 실행하도록 하기. 수정 라운드 5에서 그 명령이 감독 VM에서 환경 변수 없이 바로 통과하도록 했다: `initdb`·`pg_ctl`이 PATH에 없는 Debian 배치에서는 `test.sh`가 `/usr/lib/postgresql/<판>/bin`을 스스로 찾는다(이전에는 `ONJEON_PG_BIN`을 줘야 했다). `/bin/sh -c 'bash infra/db/public/test.sh'`로 실행해 149/0을 확인했다
- 미정 또는 지원하지 않는 동작: I7 해석(원시 보존 vs 저장 거부)은 02 §1.2를 따랐고 BLUEPRINT 문구와 다르면 설계 담당 확인이 필요하다. K16·K12·B1·B4와 `content_sha256` 재계산, `criteria_release`·적용 승인 관문(D-08)은 DB 범위 밖이다(`infra/db/README.md` "해석과 한계"). compose는 이 디렉터리를 자동 적용하지 않는다(연결은 `infra/compose/**` 소유 과제). CI는 이 시험을 돌리지 않는다(`.github/workflows/`는 금지 경로, 후속 필요). 17.11·16.15 외의 메이저 판은 확인하지 않았다
- 스켈레톤 비노출·누출 정적 검사: 이 디렉터리에는 화면·API 스켈레톤이 없다. `test.sh`의 정적 검사(픽스처·설계문서 경로 참조 없음, 비밀처럼 보이는 문자열 없음, 모델 식별자 문자열 없음)와 K8 트리거 시험으로 갈음한다. 시험 전용 행은 `origin=fixture`이고 제품 코드에 시안 숫자·임시 데이터·미연결 경로가 없다

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다(I7 해석 차이를 명시).
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다. 해당 없음: 규칙·라벨 변경 없음, 가격은 스키마 제약만.
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [ ] 설계와 구현의 상태를 요구사항 추적표에 반영했다 — `docs/blueprint/**`는 금지 경로라 반영하지 않았다. 병합 후 별도 갱신 필요.
