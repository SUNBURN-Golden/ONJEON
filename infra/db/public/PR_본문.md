## 목적과 설계 연결

- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A1~A4(보장·제한·차이·가격과 조건의 저장 기반), Q1~Q4·Q7(근거 사슬 저장), L1~L5·L7, I7·I12(+K1·K8·K14·K15 DB 방어선), M1(공개/개인 분리 DB 스키마 초안)
- 해결하는 소비자 질문: 간접. 근거 없는 주장·조건 없는 가격이 저장·공개 경로에 들어오지 못하게 하는 저장소 제약
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R03·R04·R05·R08(accepted⇒ReviewDecision), R10·R11(가격 조건·비교 자격), R23(개인/공개 분리·삭제 중 쓰기), R15(계약 스냅샷 버전 매핑 저장), R17(근거 사슬의 FK)
- 관련 결정 ID / ADR: D-09·D-10 선택안(06_검토사항_점검), ADR-0006(이종 계열 검수), ADR-0014(C0 근거는 약관), 결정 ID 없음(감리 통과 전 병합 대기)
- 설계 변경인가, 기존 설계 구현인가: 기존 설계(02_구현계약 §1.2~§1.6·§8.2) 구현. 정본 문서·어휘는 건드리지 않았다

## 과제와 작성 정보

- 과제 ID: T-CT-05 (zone contracts, stage S0, 선행 T-CT-01·T-CT-02 병합됨)
- 작성에 참여한 모델 역할·실행 경로: 빌더 역할 둘. 초기 작성과 수정 라운드 1~3은 한 빌더가, 수정 라운드 4~5는 다른 모델 계열의 빌더가 맡았다. 둘 다 감독 프로세스가 연 코딩 에이전트 CLI 세션이고 작업 트리 `wt/T-CT-05` 안에서만 작업했다(임시 시험 도구와 Docker는 `/tmp`에 두고 끝나고 지웠다). 모델 식별자 원문은 적지 않는다. 계열은 감독 상태 파일에 있으며, 독립 리뷰는 두 작성 계열 모두와 다른 계열이어야 한다
- 대상 SHA: 이 PR의 head 커밋이 대상이다. 라운드 1 리뷰 대상은 head `ceda8c4`(main에 T-CT-04 병합 뒤 병합 커밋)였고, 수정 라운드 2(구조 주장 대상 필수 `chk_structural_ref_object`, 가드 함수 `search_path` 고정·TEMP 회수, 릴리스 철회·대체 단방향, `missing_dimensions` NULL 원소 거부, production 릴리스의 fixture 노드 거부)는 그 위의 작업 트리 변경이다. 커밋·푸시는 감독 프로세스가 하므로 새 head SHA는 커밋 직후 PR 본문에 기입하고 독립 리뷰를 그 SHA에 고정한다

## 변경 내용

- 데이터·스키마·라벨·규칙·API 영향: `infra/db/` 신설. 공개 15 테이블(+보조 표 `conflict_member`)·criteria 3·개인 9, 역할 4종(NOLOGIN 그룹), 제약·트리거, 권한, `apply.sh`, 시험 `public/test.sh`(166건)·`public/tests/test_vocab_sync.py`, 실행 기록 `public/evidence/`. 코드·어휘·정본 문서 변경 없음. 어휘 도메인은 vocabulary 1.6.0과 `test_vocab_sync.py`로 대조
- 화면에서 보장·제외·가격·미확인을 표시하는 변화: 없음
- 기존 결과·버전·캐시·개인정보 영향: 없음(새 스키마). 공개 DB에는 `contract:` 등 개인 식별자가 들어가지 못하고 `personal` 역할은 공개 테이블에 쓰지 못한다

## 검증과 한계

- 수락 사례와 기대 결과: I7(조건 없는 가격 행은 삽입 거부, 자격 있는 가격은 조건·구성·기준일·근거 필수, 구성·기준일 공백 행은 자격 없음 + 공백 차원 명시), K8(6개 접두어 + jsonb·배열 은닉), accepted⇒결정(결정의 outcome까지), fixture⇒not accepted, I12(`personal` 쓰기 거부), FK 7종 존재·작동. 거부마다 이유 문구(제약 이름)를 확인하고, 변이 7종은 제약을 풀면 같은 입력이 통과함을 보인다
- 실제 수행한 검증 및 결과:
  - `bash infra/db/public/test.sh`(환경 변수 없이, `/bin/sh -c`로 감독 프로세스와 같은 방식) → `RESULT: passed=166 failed=0 / DB CONSTRAINTS: PASSED`, PostgreSQL 17.11 임시 클러스터(`public/evidence/test.log`, 수정 라운드 5에서 실행한 기록. 수정 라운드 1 뒤 재실행). `ONJEON_PG_BIN`을 명시해도 같은 결과, 잘못된 `ONJEON_PG_BIN`은 `NOT RUN`으로 실패(rc=1)하고 임시 클러스터를 남기지 않음을 확인
  - 같은 시험을 `infra/compose` 스택의 `postgres:16.15-alpine` 공개 DB 서버와 개인 DB 서버 각각에서 URL 경로(`ONJEON_DB_ADMIN_URL`, 비밀번호는 PGPASSWORD로만)로 실행 → 둘 다 149/0(수정 라운드 1 이전 기록이며 이번 변경 뒤에는 재실행하지 못했다). 이어 compose가 만든 실제 `onjeon_public`·`onjeon_private`에 `apply.sh` 적용 성공, 재적용 거부(rc=3), 앱 로그인 역할은 그룹 역할 구성원이 아니라 도메인 표를 읽지 못함, `down.sh --purge` 뒤 컨테이너·볼륨·네트워크 0(`public/evidence/test_compose_pg16.log`). 작업 VM에는 Docker가 없어 정적 바이너리를 `/tmp`에 받아 임시 데몬으로 올렸고 끝나고 지웠다
  - 저장소 시험 명령(감독 프로세스의 test_cmd와 같은 것): vocab_check·validation_check(+selftest) OK, `python3 -m unittest discover -s tools/tests` 388건 OK(skipped=6), `cargo fmt --check`·`cargo clippy -D warnings`·`cargo test --all` OK, spec_check 기계 44/44·존재 72/72
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: 합성 검증(시험 전용 행, 원문 없음). 실제 원문·상품 정확도 검증 아님
- 수정 라운드 처리: 라운드 1~5의 실패 원인은 과제 `tests` 항목이 `bash infra/db/test.sh (…)`로 적혀 `/bin/sh` 구문 오류였던 것이고, 운영자가 명령을 `bash infra/db/public/test.sh`로 바꿨다. 이후 독립 리뷰(head `042e4b4`)의 차단 지적 둘을 고쳤다: (1) 조건 없는 가격 행을 `chk_premium_conditions_required`로 거부, (2) `applies_to`의 주체가 조항(`clause:`)일 때 본문 판 FK에 걸리던 문제를 `ref_edition`이 `ted:` 주체만 보게 해 해결. 보너스로 K8 접두어 검사를 대소문자 무시로 바꿨다. 시험은 166건 통과, 0건 실패
- 미정 또는 지원하지 않는 동작: I7은 BLUEPRINT와 수락 기준을 따라 조건 없는 가격 행을 거부한다. 조건 없는 원시 관측의 별도 보존 경로(02 §1.2, T-KN-04)는 이 과제 범위 밖이며 설계 담당 확인이 필요하다. K16·K12·B1·B4와 `content_sha256` 재계산, `criteria_release`·적용 승인 관문(D-08)은 DB 범위 밖이다(`infra/db/README.md` "해석과 한계"). compose는 이 디렉터리를 자동 적용하지 않는다(연결은 `infra/compose/**` 소유 과제). CI는 이 시험을 돌리지 않는다(`.github/workflows/`는 금지 경로, 후속 필요). 17.11·16.15 외의 메이저 판은 확인하지 않았다
- 스켈레톤 비노출·누출 정적 검사: 이 디렉터리에는 화면·API 스켈레톤이 없다. `test.sh`의 정적 검사(픽스처·설계문서 경로 참조 없음, 비밀처럼 보이는 문자열 없음, 모델 식별자 문자열 없음)와 K8 트리거 시험으로 갈음한다. 시험 전용 행은 `origin=fixture`이고 제품 코드에 시안 숫자·임시 데이터·미연결 경로가 없다

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다(I7: 02 §1.2의 원시 보존과 달라진 점을 명시).
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다. 해당 없음: 규칙·라벨 변경 없음, 가격은 스키마 제약만.
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [ ] 설계와 구현의 상태를 요구사항 추적표에 반영했다 — `docs/blueprint/**`는 금지 경로라 반영하지 않았다. 병합 후 별도 갱신 필요.
