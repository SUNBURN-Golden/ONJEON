## 목적과 설계 연결

- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A1·A2(보장·제한 주장의 근거와 판을 추가 전용으로 저장), A4(가격을 조건·구성·기준일·근거와 함께 보존); Q1·Q2·Q4·Q7(주장·가격의 근거 사슬 저장·조회); L3(필드·가격 후보 저장), L4(ReviewDecision 연결, 불완전 결정 거부), L5(구획·조항·본문 판·계열·노드의 정규 저장), L7(불변 후보 검사와 승격 기록); I7(조건·구성·기준일·근거 없는 가격은 비교 자격을 얻지 못함, 원시 관측은 분리 보존), I12(공개 DB의 `data_writer`·`knowledge_writer` 경계 준수), I14(불일치·불완전 검수 결정으로는 accepted 불가), I16(승격은 검사한 스냅샷의 추가 전용 기록); M1(데이터 척추 위의 지식 저장소), M2(뼈대 관통의 저장 계층)
- 해결하는 소비자 질문: 보장·제한·가격의 근거와 판은 무엇이며, 무엇이 미확보(gap)·미검수(pending/hold)인가. 화면 변화는 없다
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R03·R04(본문 판·계열과 원본 해시 참조 저장), R06(라벨 주장의 근거·검수 연결), R08(accepted⇒ReviewDecision, B2·B3 거부), R10·R11·R12(가격 원시 보존과 비교 자격 판정의 분리), R21·R22(supersedes·correction_reason·conflict로만 바뀌는 추가 전용 정정). 이 변경은 저장·검증 기반이며 해당 요구 전체의 UI·출시 수락을 뜻하지 않는다
- 관련 결정 ID / ADR: ADR-0001(기술 스택), ADR-0002(합성 픽스처 우선: 시험은 `fixture_only`), ADR-0006(이종 계열 검수: ReviewDecision 관문), ADR-0011·ADR-0012(설계도 위계와 구현 추적), ADR-0016(원본 보관소 R2: allowlist의 출처), ADR-0018(지식 기반의 정체성과 범위). 결정 ID 없음
- 설계 변경인가, 기존 설계 구현인가: 기존 설계(02_구현계약 §1.1·§1.2·§8.2·C-18) 구현. 제품 범위·추천 기준·어휘·정본 문서 변경 없음

## 과제와 작성 정보

- 과제 ID: **T-KN-04** (zone knowledge, stage S1, 선행 T-CT-05·T-KN-02 병합됨), 수정 라운드 4
- 작성에 참여한 모델 역할·실행 경로: 빌더 역할 둘. 크레이트 작성과 수정 라운드 2~3은 OpenAI 계열 빌더가 API 실행 경로에서, 수정 라운드 4는 Anthropic 계열 빌더가 감독 프로세스가 연 코딩 에이전트 CLI 세션에서 맡았다. 둘 다 작업 트리 `wt/T-KN-04` 안에서만 작업했고, 임시 PostgreSQL 클러스터는 `/tmp`에 두고 끝나고 지웠다. 라운드 1 기록(`evidence/fix_round_1.log`)은 계열 없이 "coding agent; local worktree command line"으로만 남아 있다. 모델 식별자 원문은 적지 않는다. 하위 에이전트 위임·외부 모델 호출 없음
- 대상 SHA: 이 PR의 head 커밋이 대상이다. 라운드 4 독립 리뷰(BLOCK)의 대상은 head `d011da6144f895b2f536aeddd7e02be474375be5`였고, 이번 수정은 그 위의 미커밋 작업 트리 변경이다. 검증한 파일 내용은 `services/knowledge/evidence/review_target_round_4.json`의 SHA-256 목록으로 고정한다. 커밋·푸시는 감독 프로세스가 하므로 새 head SHA는 커밋 직후 PR 본문에 기입하고 독립 리뷰를 그 SHA에 고정한다
- 독립 리뷰 상태: 라운드 4 리뷰어는 OpenAI 계열이라 라운드 2~3 작성 계열과 같았다(리뷰어 자신의 지적). 독립 리뷰는 두 작성 계열(OpenAI·Anthropic) 모두와 다른 계열이 새 head SHA에 고정해 수행해야 한다. GitHub에는 아직 리뷰·코멘트가 없다. 감독 프로세스는 PR #173의 설명을 이 파일 내용으로 바꿔야 한다. 현재 설명은 이전 본문이며 `packages/knowledge` 경로를 참조한다. 이 과제의 코드는 `services/knowledge/**`에만 있다

## 변경 내용

- 데이터·스키마·라벨·규칙·API 영향: `services/knowledge` 크레이트(`src/lib.rs`, `src/postgres_store.rs`)와 보조 마이그레이션 `migrations/001_repository.sql`(이번 라운드 변경 없음). 공용 파일은 `Cargo.toml`의 workspace members 한 줄과 Cargo가 재생성한 `Cargo.lock`뿐이다. 기존 infra 스키마·어휘·정본 문서는 수정하지 않았다
  - 주장은 `ingest_assertion`·`ingest_corrections`로 추가만 하고 수정 API가 없다(`compile_fail` 문서 시험). 정정은 새 ID와 `supersedes`·`correction_reason`, 분기는 `conflict`로 묶는다
  - B1(`packages/fixtures/**`·`docs/blueprint/**` 경로, 상대·절대·부모 이동·심볼릭 링크)·B2(origin=fixture accepted)·B3(origin만 pipeline으로 고친 사본)을 주장과 가격 모두에서 거부하고, DB 제약이 같은 입력을 다시 거부함을 확인한다
  - 라운드 4 수정 1: K7 누락. 온톨로지 경계가 `public.node` 형식(`kind` 열 = 클래스, `attrs` = 온톨로지 속성)을 펼칠 때 열의 `kind`를 유지해 `attrs.kind=감액`을 읽지 못했다. 이제 `kind` 열을 `class`로 옮기고 `attrs`를 펼치되 제약 열(`id`·`label`·`origin`·`onto_version`·`recorded_at`)은 `attrs`가 덮어쓰지 못한다. 이미 `class`가 있는 온톨로지 형식 노드는 `kind`를 속성으로 유지한다. 적용 대상 없는 observed 감액은 K7 위반이며 승격되지 않는다
  - 라운드 4 수정 2: `scope_relation` 영속. 온톨로지는 대상(`object`)과 값(`value`)을 함께 쓰지만 `chk_assertion_object_xor_value`는 하나만 허용한다. 닫힌 역변환 하나를 추가했다. 대상만 열에 넣고 값은 같은 트랜잭션의 `knowledge.record_extension`에만 둔 뒤, 스냅샷이 NULL인 값 열을 확장 행에서 되돌린다. 다른 술어는 DB의 XOR 제약이 그대로 적용된다
  - 라운드 4 수정 3: 원본 행의 목록 검사. `insert_record("raw_assets", …)`가 R2 관측 목록 밖 해시와 `raw:sha256:<해시>`가 아닌 `id`를 거부한다. 후보 검사는 참조되지 않은 원본 행을 포함해 모든 원본 행을 목록과 다시 대조하며(B4), 서비스를 거치지 않고 들어온 행도 승격을 막는다
  - R2 allowlist는 두 기존 목록 형식(해시 58개)을 읽고 다운로드 검증 실패·불일치 항목을 제외한다. `raw`·`seg`·`clause`·`obs`·`premium` 근거를 원본까지 해소한다
  - 공백(`gaps`)과 확보 작업(`acquisition_tasks`) 상태는 독립 필드다. 문의 초안 생성은 없다
  - 가격: `source_as_of` 하나가 기준일이고 `missing_dimensions`는 실제 공백과 일치해야 한다. 조건 없는 원시 관측은 `knowledge.raw_premium_observation`에 비교 불가로 보존한다
- 화면에서 보장·제외·가격·미확인을 표시하는 변화: 없음
- 기존 결과·버전·캐시·개인정보 영향: 없음. 제품 화면·캐시·개인 DB 변경 없음. 공개 DB의 K8 개인 식별자 거부와 역할 경계를 그대로 따른다

## 검증과 한계

- 수락 사례와 기대 결과:
  - 수정 API 없음·supersedes만: `compile_fail` 문서 시험, `assertion_is_append_only_and_changes_by_supersedes`, DB `append_only` 트리거 거부
  - B1~B3: `fixture_rejection`, `b1_normalizes_parent_paths_and_forbids_blueprint_and_symlinks`, r26 A-box의 accepted 주장 전부에 대한 B1/B2/B3 거부, DB `chk_fixture_never_accepted`·`chk_accepted_needs_decision` 재확인
  - 제약 위반 집합의 승격 거부: `violating_candidate_is_not_promoted`, `canonical_c0_is_checked_and_cannot_be_promoted`, `k7_reads_reductions_in_the_persisted_node_shape`(적용 대상 없음 → K7·승격 거부, `applies_to`·`value=없음`·비감액 → 통과), `ontology_shaped_nodes_keep_their_class`, `scope_relations_keep_object_and_value_for_k4_and_k12`(순환 → K4, universe 없는 accepted → K12), `raw_assets_are_allowlisted_at_load_and_at_candidate_check`
  - 공백·작업 상태 독립: `gap_and_acquisition_task_states_are_independent`
  - `price-raw-kept-comparison-gated`: 원시 가격 보존, 실제 공백 목록, 비교 자격의 조건·검수 관문
  - `profile-historical-vs-service`: 같은 T-KN-02 r26 A-box에서 이력 제약 0건·질문 11/11, 서비스 적재 B1~B3 거부
  - DB 왕복: 재접속 복원, 지연 K10 롤백·충돌, 외부 적재 행 재검사, `scope_relation`의 `object` 열·NULL `value` 열·확장 행 값 → 재접속 후 `value="narrower"`·K4, `public.node` 형식 감액 노드 → 재접속 후 K7, 목록 밖 원본 행(서비스 거부 + 직접 삽입 뒤 B4·승격 거부·`knowledge.candidate` 0행)
- 실제 수행한 검증 및 결과(`services/knowledge/evidence/fix_round_4_*.log`, 작업 트리 경로는 `<worktree>`로 치환):
  - `bash services/knowledge/test.sh`: **25/25 통과**(단위 1, 저장소 21, r26 1, DB 1, 문서 1), PostgreSQL 17.11 임시 클러스터, 실제 `data_writer`·`knowledge_writer` 권한(`fix_round_4_db.log`)
  - `cargo test --locked --workspace`: **412 통과, 0 실패, 2 ignored**(knowledge DB 시험은 `test.sh`에서 실행, twin-runtime 픽스처 재생성 도구는 최신성 검증 시험 통과)(`fix_round_4_workspace.log`)
  - `cargo clippy --locked --workspace --all-targets -- -D warnings`, `cargo fmt --all -- --check`: 통과(`fix_round_4_lint.log`, `fix_round_4_format.log`)
  - `bash infra/db/public/test.sh`: **166/166 통과**(`fix_round_4_schema.log`)
  - `python3 -I tools/ci/check_leak.py`, `python3 -I tools/ci/check_skeleton.py`: 통과. `SkeletonRuntime` **2/2 통과**(`fix_round_4_static.log`)
  - 허용 경로 검사: 변경 파일은 `services/knowledge/**`뿐이다. `git diff --check` 통과(`fix_round_4_summary.log`)
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: 합성·픽스처·로컬 PostgreSQL 검증. 실제 상품 정확도, 실제 원문 검수, 사용자 검증, 출시 승인이 아니다
- 미정 또는 지원하지 않는 동작: 대상·값 동시 저장의 역변환은 `scope_relation`에만 적용한다. 다른 술어가 둘을 함께 보내면 DB가 거부한다. K12의 실제 계산에는 코드 체계 universe가 필요하며 이 크레이트는 universe를 호출자에게 받는다. 후보 저장은 내부 제약 검사 결과이며 공개 ReleaseManifest 발행이 아니다. production 릴리스의 B5/B10·그림자 비교·공개 API·비교·정렬·예산 API는 T-KN-07 등 후속 과제다. round 2의 CI 검사기 전체 자기 시험은 기존 `packages/ontology` 구역 의존성 위반 3건으로 18/20이었고(`fix_round_2_baseline.log`), 해당 파일과 CI 정책은 허용 경로 밖이라 라운드 3·4에서 재실행한 것으로 표시하지 않는다
- 스켈레톤 비노출·누출 정적 검사: 위 정적 검사와 런타임 비노출 시험 2개 통과. 시험 전용 행은 `fixture_only`·`origin=fixture`이고 제품 코드에 시안 숫자·임시 데이터·미연결 경로가 없다. 비밀값·모델 식별자 원문·원문 발췌 없음

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다.
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다. 해당 없음: 규칙·라벨 변경 없음, 가격은 저장·자격 판정 검증만.
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [ ] 설계와 구현의 상태를 요구사항 추적표에 반영했다 — `docs/blueprint/**`는 금지 경로라 반영하지 않았다. 병합 후 별도 갱신 필요.
- [ ] 새 head SHA에 고정된, 두 작성 계열과 다른 계열의 독립 리뷰 및 원격 CI 성공 기록 — 감독 프로세스의 커밋 뒤 필요.
