# infra/db — 공개·개인 분리 DB 스키마 (T-CT-05)

두 DB를 따로 둔다(I12, BLUEPRINT §4). 이 디렉터리는 **스키마와 제약**이다. 서비스 코드(적재기·릴리스 빌더·개인 서비스)는 T-KN-04·T-KN-07·T-PS-01 등 후속 과제이며, 여기 있는 제약은 그 서비스가 우회하지 못하는 마지막 방어선이다. 근거 문서는 `docs/blueprint/proposals/설계검토_결과/02_구현계약.md` §1.2~§1.6·§8.2(채택된 정본이 아니라 설계 담당 판단. 채택 전까지 이 스키마도 검토본 구현이다)다.

| 디렉터리 | 대상 DB | 내용 |
|---|---|---|
| `public/` | 공개 영역 DB | 역할(`00_roles.sql`), 15개 테이블(+보조 표 `conflict_member`)·제약·트리거(`01_schema.sql`), 권한(`02_grants.sql`), `apply.sh`, **시험 `test.sh`**, 어휘 대조 `tests/test_vocab_sync.py`, 실행 기록 `evidence/test.log`(임시 PostgreSQL 17)·`evidence/test_compose_pg16.log`(compose의 16.15) |
| `criteria/` | 공개 영역 DB의 `criteria` 스키마 | `criterion`·`criterion_version`·`criterion_source`(`01_criteria.sql`), 권한(`02_grants.sql`). `public/apply.sh`가 함께 적용한다 |
| `personal/` | 개인 영역 DB (다른 서버) | `personal` 스키마 9개 테이블(`01_schema.sql`), 권한, `apply.sh` |

## 적용

```sh
# 관리 역할(슈퍼유저)로, 비밀번호는 PGPASSWORD 환경 변수로 준다. 명령줄·파일에 쓰지 않는다.
bash infra/db/public/apply.sh   postgresql://<admin>@<public-db-host>:<port>/<db>
bash infra/db/personal/apply.sh postgresql://<admin>@<private-db-host>:<port>/<db>
```

마이그레이션은 한 번 적용하는 판이다(단일 트랜잭션, 다시 적용하면 거부된다). 변경은 새 번호의 파일로 낸다. `infra/compose`의 DB 초기화(`zone-init.psql`)는 앱 로그인 역할과 큐만 만들므로 순서는 *compose 기동 → apply.sh*다. 이 순서를 compose 스택(`postgres:16.15-alpine`)의 실제 두 DB(`onjeon_public`, `onjeon_private`)에서 한 번 실행해 확인했다(`public/evidence/test_compose_pg16.log` 뒷부분: 적용 성공, 재적용 거부, 앱 로그인 역할은 그룹 역할 구성원이 아니라서 도메인 표를 읽지 못함). compose는 이 디렉터리를 아직 자동 적용하지 않는다(그 연결은 `infra/compose/**` 소유 과제의 일이다).

## 시험

```sh
bash infra/db/public/test.sh    # 공개·criteria·개인 스키마를 임시 DB에 적용하고 153개 점검을 돌린다

# compose 스택(bash infra/compose/up.sh)의 공개 DB에서 돌릴 때. 관리 역할 이름은 .env의 PUBLIC_DB_ADMIN_USER,
# 비밀번호는 .env의 PUBLIC_DB_ADMIN_PASSWORD 값을 PGPASSWORD 환경 변수로만 넘긴다(명령줄·URL·파일에 쓰지 않는다).
PGPASSWORD="<.env의 PUBLIC_DB_ADMIN_PASSWORD>" ONJEON_DB_ADMIN_URL=postgresql://onjeon_pub_admin@127.0.0.1:15432/postgres bash infra/db/public/test.sh
```

시험 파일은 `infra/db/public/test.sh`다. 이 과제의 허용 경로가 `infra/db/public|personal|criteria/**`와 이 README뿐이라 `infra/db/test.sh` 자리에는 둘 수 없다.

- 서버: `ONJEON_DB_ADMIN_URL=postgresql://<슈퍼유저>@host:port/postgres`(예: compose의 공개 DB, 비밀번호는 `PGPASSWORD`)로 기존 서버를 쓰거나, `initdb`·`pg_ctl`·`psql`이 PATH(또는 `ONJEON_PG_BIN`)에 있으면 임시 클러스터를 띄운다. Debian/Ubuntu처럼 `initdb`·`pg_ctl`이 PATH에 없고 `/usr/lib/postgresql/<판>/bin`에만 있으면 그중 가장 높은 판을 스스로 찾아 쓴다(첫 줄 `server:`에 어느 바이너리를 썼는지 적는다). `ONJEON_PG_BIN`을 주면 그것이 우선이고, 거기에 바이너리가 없으면 찾지 않고 실패한다. 둘 다 없으면 **통과가 아니라 실패**(`NOT RUN`)로 끝난다. 기존 서버를 쓸 때도 임시 DB 셋만 만들었다 지우며, 클러스터 전역 역할 네 개(NOLOGIN)가 남는다.
- 거부 시험은 "실패했다"만 보지 않고 제약 이름 등 **이유 문구**를 확인한다. 마지막 변이 시험은 제약 하나를 풀고 같은 입력이 통과함을 보인다.
- `tests/test_vocab_sync.py`: SQL의 `vocab_*` 도메인이 `packages/schemas/vocabulary.json`과 값까지 같은지, `node.kind`가 온톨로지 tbox 클래스의 부분집합인지 대조한다. 어휘가 바뀌면 이 시험이 실패한다(정본은 여기서 고치지 않는다).
- `evidence/test.log`는 환경 변수 없이 `bash infra/db/public/test.sh`만 실행한 기록이다(PostgreSQL 17.11 임시 클러스터, 바이너리는 위 자동 탐색으로 찾았다). `evidence/test_compose_pg16.log`는 `infra/compose` 스택(`postgres:16.15-alpine`, 작업 VM에 임시로 올린 Docker 데몬)의 공개 DB 서버와 개인 DB 서버 각각에서 위 URL 경로로 돌린 기록(둘 다 149/0)이고, 이어서 compose가 만든 실제 두 DB에 `apply.sh`를 적용한 결과와 `down.sh --purge` 뒤 남은 것이 없음을 담았다.

## 역할 (I12)

로그인 없는 그룹 역할 4종. 서비스 계정은 이 역할의 구성원으로 만든다(`GRANT data_writer TO <계정>`). DELETE·TRUNCATE 권한은 누구에게도 없다(삭제는 개인 영역의 `deletion_job` 절차, 공개 영역은 불변).

| 역할 | 공개 DB | 개인 DB |
|---|---|---|
| `data_writer` | 관측·구획·조항·원시 가격·공백·확보 작업 쓰기, 판단 읽기 | 접근 없음 |
| `knowledge_writer` | 본문 판·계열·노드·코드 체계·검수 결정·주장·가격·충돌·공백·릴리스 쓰기, 릴리스 철회 표시 | 접근 없음 |
| `criteria_writer` | `criteria` 스키마 쓰기 | 접근 없음 |
| `personal` | **공개 지식 읽기 전용**(원본·관측·검수 결정·확보 작업은 못 읽음). 쓰기 전부 거부 | `personal` 스키마 전체(삭제 작업 표는 DELETE 불가) |

## 제약 대응표

| 요구 | 제약 | 위치 |
|---|---|---|
| I7 가격은 조건·구성·기준일·근거 없이 비교에 쓰이지 않는다 | `chk_premium_raw_vs_eligible`, `chk_premium_conditions_required`, `chk_premium_missing_*`, `evidence`·`raw_amount`·`observed_at` NOT NULL | `premium_observation` |
| K8 / I12 공개 스키마에 개인 식별자 금지 | `chk_no_private_ids` 트리거(모든 텍스트 열·jsonb 값과 키·배열), `personal` 역할의 쓰기 권한 없음 | 모든 공개·criteria 테이블 |
| accepted ⇒ ReviewDecision | `chk_accepted_needs_decision`(CHECK + 결정 outcome=accepted 확인), `review_decision`의 `chk_review_families`(계열 2개 이상)·`chk_review_accepted_complete` | `assertion`, `premium_observation` |
| fixture ⇒ not accepted | `chk_fixture_never_accepted` | `assertion`, `premium_observation` |
| K1 C0 근거 | `chk_c0_basis`(약관·특약 약관·별표 구획의 조항 + 그 구획의 accepted `realizes`) | `assertion` 트리거 |
| K14 판 동일성 | `chk_realizes_fingerprint`(지문 있는 확정 구획 + 구획 관측 근거, 원본 해시만으로는 거부) | `assertion` 트리거 |
| 구획·본문 판 FK | `fk_segment_raw`, `fk_clause_segment`, `fk_realizes_segment`, `fk_realizes_edition`, `fk_segment_of_raw`, `fk_in_segment_clause`, `fk_edition_of_lineage` | `document_segment`, `clause`, `assertion`의 생성 열 `ref_*` |
| 정정 사슬 | `chk_assertion_correction`, `chk_supersedes_linear`(지연 제약) | `assertion` |
| K15 릴리스 고정 | `release_manifest_guard`(구성원 존재·정렬·유일, production에 fixture·test 결정 금지(B10), 고정 뒤 철회 표시 외 변경 금지) | `release_manifest` |
| B8 코드 체계 | `chk_code_system_official_source`, `chk_code_system_fixture_name` | `code_system` |
| 판단 기준 판 (§1.5) | 출처 1개 이상(`chk_criterion_version_has_source`, 지연), 정정은 새 판 + `supersedes`(`chk_criterion_supersedes`, 같은 판 이중 대체 불가), 수정·삭제 불가 | `criteria.*` |
| 삭제 중 늦은 쓰기 (§7.2) | `ONJ-PS-S-031` 트리거 | 개인 `upload`·`contract_snapshot`·`user_assumption`·`evaluation`·`conclusion_dependency`·`plan` |

불변 테이블(`raw_asset`·`observation`·`document_segment`·`clause`·`terms_*`·`node`·`code_system`·`review_decision`·`assertion`·`premium_observation`·`conflict`·`conflict_member`·`gap`, `criteria.*`)은 UPDATE·DELETE·TRUNCATE가 소유자에게도 거부된다(`append_only`). 정정은 새 행이다. `acquisition_task`(운영 상태)는 가변이고 릴리스 밖이다.

## 해석과 한계 (정직한 기록)

- **I7 해석.** BLUEPRINT I7("가격은 조건·구성·기준일·근거 없이 저장되지 않는다")과 이 과제의 수락 기준("조건 없는 가격 행 삽입이 거부된다")을 따랐다: `premium_observation`은 **조건(`conditions`)이 비어 있거나 NULL이면 삽입이 거부된다**(`chk_premium_conditions_required`). 근거·금액·관측 시각도 항상 필수다. 특약 구성·기준일이 빈 행은 저장되되 `comparison_eligible=false`이고 `missing_dimensions`에 빈 차원을 정직하게 적어야 한다(적은 것과 실제 공백이 다르면 거부). `comparison_eligible=true`는 조건·구성·기준일이 모두 있고 accepted일 때만 가능하다. 조건 없는 원시 관측의 보존(02 §1.2, T-KN-04 `price-raw-kept-comparison-gated`)은 이 표의 몫이 아니며 별도 경로가 필요하다 — 설계 담당 확인 사항.
- **K16(판의 근거 묶음 완전성)·K12·B1·B4는 DB가 아니다.** 판 구성 덮음 여부, 코드 우주 비교, R2 관측 목록 대조, 적재기 경로 allowlist는 적재기·릴리스 빌더(T-KN-04·T-KN-07) 몫이다. 이 스키마는 `terms_edition.parts`(역할·지문)와 `realizes` 지문 요건까지만 강제한다. `fk_evidence_clause`는 계약대로 FK가 아니며 `evidence`는 jsonb다.
- `content_sha256` 재계산, `criteria_release`·`criteria_application`(서비스 적용 승인 관문, D-08), `release_notice`, 오류 신고 격리 테이블, `need_result`는 이 과제의 산출물 목록 밖이다.
- K8은 문자열 접두어 검사다: `contract:` 등이 **값의 시작이거나 영문·숫자·밑줄이 아닌 문자 바로 뒤**에 오면 거부한다. 자연어 설명에 우연히 들어간 같은 모양도 거부된다(허용 쪽 오류보다 거부 쪽 오류를 택했다).
- 개인 영역의 `components`·`plan.items` 등 jsonb 안쪽은 어휘 값과 필수 키만 확인한다. 나머지 모양은 `packages/schemas`의 JSON 스키마 검증 몫이다.
- 원문 발췌는 저장하지 않는다(`clause.quote_sha256`만). PDF 비밀번호 열은 없다.
- 이 스키마의 설계 근거 문서가 아직 채택본이 아니므로 이름·열은 채택 과정에서 바뀔 수 있다. 바뀌면 새 번호 마이그레이션이다.
- 시험은 PostgreSQL 17.11(임시 클러스터)과 compose가 쓰는 16.15(두 서버)에서 실행했고 결과가 같다(149/0, 수정 라운드 1 이전 기록은 16.15 쪽만 해당하며 이후 17.11에서 153/0). 다른 메이저 판은 확인하지 않았다. 생성 열, 도메인, 지연 제약 트리거, jsonb만 쓴다.
