## 목적과 설계 연결

- 과제: **T-KN-04**, zone=knowledge, stage=S1, fix round 3.
- A1·A2(보장·제한의 근거), A4(가격과 조건); Q1·Q2·Q3·Q4·Q7; L3·L4·L5·L7; I1·I6·I7·I12·I14·I16; M1·M2·M4.
- 요구 ID: **R03, R04, R06, R08, R10, R11, R12, R21, R22**. 이 변경은 저장·검증 기반이며 해당 요구 전체의 UI·출시 수락을 뜻하지 않는다.
- 소비자 질문: 보장·제한·가격의 근거와 판은 무엇이며, 미확보·미검수 정보는 무엇인가?
- 관련 결정: ADR-0001, ADR-0003, ADR-0006, ADR-0011, ADR-0012. 기존 구현 계약 §1.1·§1.2·§8.2·C-18 구현이며 제품 범위·추천 기준 변경 없음.

## 변경 내용

기존 저장소는 프로세스 종료 시 내용이 사라졌고, 소문자 c0·간접 근거·가격 검수·충돌 구성원·가격 기준일에 검사 우회 또는 형식 불일치가 있었다. PostgreSQL 어댑터로 T-CT-05의 실제 제약을 통과해 저장하고, 재접속 시 복원한다. 분기 정정과 충돌은 한 트랜잭션에서 저장한다.

- round 3: main의 twin-runtime·collect·criteria와 이 과제의 knowledge 워크스페이스 등록을 모두 보존해 Cargo 충돌을 해결했다. `Cargo.lock`은 Cargo로 재생성하고 기존 의존성 버전을 유지했다. 서비스 동작 변경은 없다.
- 구현: `services/knowledge/src/lib.rs`, `services/knowledge/src/postgres_store.rs`.
- 추가 마이그레이션: `services/knowledge/migrations/001_repository.sql`. 기존 infra 스키마는 수정하지 않는다. 조건 미확보 원시 가격과 온톨로지 부가 속성의 영속 경로를 제공한다.
- R2 목록 두 형식의 해시 58개를 읽고, 조항·구획·관측·가격 근거를 원본까지 해소한다. 후보 검사에서도 다시 확인한다.
- 주장 수정 API를 제거하고 supersedes만 제공한다. 충돌은 검사기가 읽는 `assertions`에 연결한다.
- 주장·가격 모두 fixture accepted와 ReviewDecision 누락·불완전 결정을 거부한다. 공백 상태와 작업 상태는 독립이다.
- 문서 역할·criticality·가격 기준일은 온톨로지 검사 직전에 변환한다. 가격 입력에 중복 기준일을 요구하지 않는다.
- 제품 화면·캐시·개인 DB 변경 없음. 원시 관측의 보존은 비교 자격 승인과 별개다.

## 검증과 한계

- `bash services/knowledge/test.sh`: **21/21 통과**(문서 compile-fail 1개 포함). PostgreSQL 17.11, 실제 `knowledge_writer` 권한, 재접속 복원, B2/B3 및 가격 DB 제약 재확인, c0, 지연 K10 롤백·충돌, 외부 적재 근거 재검사.
- `profile-historical-vs-service`: 같은 T-KN-02 r26 A-box 이력 제약 **0**, 질문 **11/11**, 서비스 적재 B1~B3 거부.
- `price-raw-kept-comparison-gated`: 원시 가격 보존, 실제 공백 목록, 비교 자격의 조건·검수 관문. eligible 가격은 `source_as_of`만으로 K13 통과.
- `cargo test --locked --workspace`: **408 통과, 0 실패, 2 ignored**. knowledge DB 시험은 별도 `test.sh`에서 실제 실행했다. 다른 ignored는 twin-runtime 픽스처 재생성 도구이며 최신성 검증 시험은 통과했다.
- `cargo clippy --locked --workspace --all-targets -- -D warnings`, `cargo fmt --all -- --check`: 통과.
- `bash infra/db/public/test.sh`: **166/166 통과**.
- 누출·스켈레톤 정적 검사: 통과. `SkeletonRuntime`: **2/2 통과**(로컬 시험 서버와 양성·음성 대조).
- `store`, `fixture_rejection`, `edition_conflict`는 전체 서비스 시험에 포함되어 통과했다.
- 최신 로그: `services/knowledge/evidence/fix_round_3_{db,workspace,lint,format,schema,static,merge,summary}.log`.
- 미해결 충돌 0건, 허용 경로 공백 검사 통과. 전체 staged diff 공백 검사는 main에서 들어온 허용 경로 밖 네 파일에서 실패했다. 해당 index blob이 `MERGE_HEAD`와 같은지 확인했고 수정하지 않았다(`fix_round_3_merge.log`).
- round 2의 CI 검사기 전체 자기 시험: **18/20**, 기존 `packages/ontology` 구역 의존성 위반 3건 때문에 두 시험 실패. 당시 기준 SHA의 사본과 작업 트리를 비교해 동일함을 확인했다. 해당 파일과 CI 정책은 허용 경로 밖이다. round 3에서는 이 전체 자기 시험을 다시 실행하지 않았다.
- 합성·픽스처·로컬 PostgreSQL 검증이다. 실제 상품 정확도, 실제 원문 검수, 사용자 검증, 출시 승인으로 표시하지 않는다. 공개 릴리스 발행·test 결정 배제(B10)는 릴리스 빌더의 범위다.

## 작성과 리뷰 대상

- 작성 참여: 기존 round 1 코드는 기준 SHA에 보존돼 있다. 이번 수정은 **OpenAI 계열의 Codex 구현자 역할 1개**가 API 실행 경로에서 작성·시험했다. 외부 모델 호출·하위 에이전트 위임 없음. 모델 식별자 원문을 기록하지 않는다.
- 작업 경로: `/workspace/onjeon-run/wt/T-KN-04`; 이번 수정은 `services/knowledge/**`, workspace members의 knowledge 등록을 보존한 `Cargo.toml`, Cargo로 재생성한 `Cargo.lock`이다. main에서 이미 병합된 나머지 파일은 수정하지 않았다.
- 대상 HEAD: **64a366e184c06e55d247a2410d6d8547256f6617**. 병합 대상 main: **bbcdb0bf07410a9212aeb3dc95dfbb469960cee1**. 이번 수정은 병합 중인 미커밋 작업 트리다. 검증한 파일 내용은 `services/knowledge/evidence/review_target_round_3.json`의 SHA-256 목록으로 고정한다. 기존 `review_target.json`은 round 2의 역사 기록이다.
- 독립 리뷰 상태: 작성과 다른 계열의 새 리뷰 결과는 아직 없다. 사용자 지시에 따라 이 작업에서는 커밋·푸시·GitHub 호출을 하지 않았다. 충돌 해결은 stage했고 병합 커밋은 감독자가 수행한다. 새 커밋 SHA 및 원격 CI run은 아직 존재하지 않으며 완료로 표기하지 않는다. 감독자의 커밋 후 그 SHA에 고정한 독립 리뷰와 CI 실행이 필요하다.

## 확인

- [x] BLUEPRINT와 PRINCIPLES 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 구현 변경으로 숨기지 않았다.
- [x] 저장된 근거와 판을 유지하고 fixture·미검수 값의 승격을 차단한다. 실제 라벨·가격 근거를 새로 생성하지 않는다.
- [x] 로컬 시험 성공을 상품 정확도·출시 승인으로 표현하지 않았다.
- [x] 이 서비스 README에 구현 상태와 미구현 범위를 기록했다. 보호된 요구 추적표는 수정하지 않았다.
- [x] 비밀값·모델 식별자 원문·원문 발췌를 추가하지 않았다.
- [ ] 새 SHA에 고정된 다른 작성 계열의 독립 리뷰 및 원격 CI 성공 기록.
