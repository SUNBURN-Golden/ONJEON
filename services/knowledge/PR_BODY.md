## 목적과 설계 연결

- 정보 비대칭(A), 소비자 질문(Q), 계층(L), 불변식(I), 마일스톤(M): A1·A2(보장·제한 주장의 근거와 판 보존), A4(가격과 조건 보존); Q1·Q2·Q4·Q7(보장·제한·가격과 근거 조회); L3(후보 저장), L4(검수 결정 연결), L5(구획·본문 판·계열·노드), L7(후보 검사·승격 기록); I7(가격 비교 자격의 조건·구성·기준일·근거), I12(공개 DB 역할 경계), I14(불완전 검수 거부), I16(추가 전용 후보 기록); M1(데이터 척추), M2(뼈대 관통의 저장 계층).
- 해결하는 소비자 질문: 보장·제한·가격의 근거와 판은 무엇이며, 무엇이 미확보·미검수인가. 제품 화면 변경 없음.
- 요구 ID (`docs/blueprint/REQUIREMENTS.md`): R03·R04(본문 판·계열과 원본 해시), R06(라벨 주장 근거·검수), R08(accepted⇒ReviewDecision, B2·B3 거부), R10·R11·R12(원시 가격 보존과 비교 자격 분리), R21·R22(supersedes·correction_reason·conflict). 저장·검증 기반의 구현이며 각 요구의 UI·출시 수락 전체를 뜻하지 않는다.
- 관련 결정 ID / ADR: ADR-0001·0002·0006·0011·0012·0016·0018. 새 결정 없음.
- 설계 변경인가, 기존 설계 구현인가: 02_구현계약 §1.1·§1.2·§8.2·C-18의 기존 설계 구현. 제품 범위·추천 기준·어휘·정본 문서 변경 없음.

## 과제와 작성 정보

- 과제 ID: **T-KN-04**, zone knowledge, stage S1, 수정 라운드 5.
- 작성 역할·계열·실행 경로: 기존 기록상 크레이트 작성과 라운드 2~3은 OpenAI 계열 빌더의 API 실행 경로, 라운드 4는 Anthropic 계열 빌더의 감독 프로세스가 연 코딩 에이전트 CLI 세션이다. 라운드 5는 OpenAI 계열 빌더의 API 코딩 에이전트 세션과 로컬 명령 도구로 수행했다. 라운드 1은 계열이 기록되지 않았다. 작업 트리는 `wt/T-KN-04`이며 하위 에이전트 위임·외부 모델 호출 없음. 모델 식별자 원문 없음.
- 검증 기준 SHA: **06feb70ba3d22c277c1743893d76652f1aa4cad1** 위의 미커밋 라운드 5 변경. 파일 해시는 `services/knowledge/evidence/review_target_round_5.json`에 기록한다. 이 SHA는 수정 후 리뷰 대상 SHA가 아니다. **감독 프로세스가 커밋·푸시한 후 실제 새 head SHA를 이 PR 설명의 리뷰 대상 SHA에 기입해야 한다.** 이번 세션은 커밋·푸시·GitHub 호출 금지다.
- PR 게시 상태: 이 파일은 감독 프로세스가 PR #173 설명으로 게시할 초안이다. 리뷰어 보고상 라이브 설명의 A/Q/L/I/M·R 매핑과 작성·대상 SHA 정보는 미반영이었다. 이번 세션에서는 원격 상태를 조회하거나 수정하지 않았다. 파일 저장만으로 PR 템플릿 수락 조건을 충족하지 않는다.
- 독립 리뷰 상태: **미충족**. 기존 OpenAI 계열 리뷰는 작성 계열과 같아 적격 독립 리뷰가 아니다. 새 head SHA에 고정된, 알려진 작성 계열(OpenAI·Anthropic) 모두와 다른 계열의 리뷰와 실제 리뷰 제출이 필요하다. 로컬 파일 해시는 독립 리뷰 증거가 아니다.

## 변경 내용

- 데이터·스키마·라벨·규칙·API 영향: `services/knowledge/**`의 추가 전용 PostgreSQL 저장소와 검사 경계. 이번 라운드에서 공용 Cargo 파일·infra 스키마·보조 마이그레이션은 변경하지 않았다.
  - `ingest_assertion`·`ingest_corrections`는 새 ID만 추가한다. 수정 API가 없으며 정정은 `supersedes`·`correction_reason`, 분기는 `conflict`로 연결한다.
  - 구획·조항·본문 판·계열·노드·검수 결정을 저장·조회한다. `scope_relation`의 대상은 정규 열, 값은 같은 트랜잭션의 확장 행에 두고 재접속 시 복원한다.
  - 검사 지문은 정규 `fingerprint_rule`·`fingerprint_sha256`에서 만들며 NULL도 우선한다. 확장 `fingerprint`가 판 구성과 같아도 정규 지문이 다르면 K16으로 승격을 거부한다. 정규 지문이 판과 맞으면 확장 지문 충돌이 승격을 막지 않는다.
  - DB 노드는 기본값을 포함해 항상 `attrs`를 갖는다. 이 형식의 검사 클래스는 정규 `kind`가 결정하며 확장 `class`·`attrs.class`는 가리지 못한다. 메타데이터 없는 CodeSet은 K3으로 승격을 거부한다. 오프라인 온톨로지 형식과 기존 K7 감액 속성 해석을 유지한다.
  - B1은 픽스처·설계 문서 입력 경로를 상대·절대·부모 이동·심볼릭 링크까지 거부한다. B2는 fixture accepted, B3는 결정 없는 accepted를 주장·가격 모두에서 거부한다. PostgreSQL 제약도 재확인한다.
  - R2 관측 목록의 검증된 해시만 허용한다. 모든 원본 행과 간접 근거 사슬을 후보 검사에서 다시 확인한다. K1~K16 위반 후보는 승격되지 않는다.
  - 공백과 확보 작업의 상태는 독립 필드다. 문의 초안 생성 없음. 가격 원시 관측은 조건 공백을 기록하고 비교 불가로 보존하며 비교 자격은 별도로 검증한다.
- 화면에서 보장·제외·가격·미확인을 표시하는 변화: 없음.
- 기존 결과·버전·캐시·개인정보 영향: 공개 후보 검사 강화. 공개 API·개인 DB·제품 화면·캐시 변경 없음. 공개 DB의 K8과 역할 경계를 유지한다.

## 검증과 한계

- 수락 사례와 기대 결과:
  - `canonical_fingerprint_columns_gate_edition_confirmation`: 규칙·해시 충돌은 K16, NULL·불완전 쌍은 K14, 정규 지문 일치는 통과.
  - `canonical_node_kind_overrides_conflicting_classes`: 최상위·attrs 클래스 충돌에도 메타데이터 없는 CodeSet은 K3 4건과 승격 거부.
  - DB 회귀 `canonical_segment_fingerprint_blocks_extension_bypass_after_reconnect`·`canonical_node_class_blocks_extension_bypass_after_reconnect`: 실제 충돌 값 보존 확인, 재접속 후 K16·K3, 승격 거부와 후보 0행, 정규 지문 일치 시 승격 성공. 비어 있는 마이그레이션 완료 DB를 시험마다 복제하여 다른 위반의 간섭을 막는다.
  - 추가 전용 API·DB, B1~B3, 정정·충돌, K7·K4·K12, R2 원본 재검사, 공백·작업 독립 상태에 대한 기존 시험도 통과.
  - 필수 `profile-historical-vs-service`: 동일 r26 A-box의 이력 위반 0건·질문 11/11, 서비스 B1~B3 거부. 필수 `price-raw-kept-comparison-gated`: 원시 보존과 비교 자격 관문 통과.
- 실제 수행한 검증 및 결과 (`services/knowledge/evidence/fix_round_5_*.log`, 경로는 `<worktree>`로 치환):
  - `bash services/knowledge/test.sh`: **29 통과, 0 실패, 0 ignored** (단위 1·저장소 23·r26 1·PostgreSQL 3·문서 1). PostgreSQL 17.11, 실제 data_writer·knowledge_writer 권한. 로그 `fix_round_5_db.log`.
  - `cargo test --locked --workspace`: **414 통과, 0 실패, 4 ignored**. knowledge DB 3개는 위 명령에서 실행했다. 나머지는 twin-runtime 픽스처 재생성 도구이며 최신성 검증은 통과했다. 로그 `fix_round_5_workspace.log`.
  - `cargo clippy --locked --workspace --all-targets -- -D warnings`·`cargo fmt --all -- --check`: 통과. 로그 `fix_round_5_lint.log`·`fix_round_5_format.log`.
  - `bash infra/db/public/test.sh`: **166 통과, 0 실패**. 로그 `fix_round_5_schema.log`.
  - `python3 -I tools/ci/check_leak.py`·`python3 -I tools/ci/check_skeleton.py`·`python3 -I -m unittest discover -s tools/ci/tests -k SkeletonRuntime`: 통과, 런타임 비노출 **2/2**. 로그 `fix_round_5_static.log`.
  - `git diff --check`·허용 경로 검사: 통과. 로그 `fix_round_5_summary.log`.
- 합성 검증 / 실제 원문 검증 / 사용자 검증 중 해당 범위: fixture_only 합성 시험과 로컬 PostgreSQL. 실제 상품 정확도·원문 검수·사용자 검증·출시 승인을 뜻하지 않는다.
- 미정 또는 지원하지 않는 동작: 후보 저장은 내부 검사 기록이며 production ReleaseManifest가 아니다. B5/B10·그림자 비교·공개 API는 후속 과제다. 문의 초안·가격 비교·정렬·예산 API 없음. `scope_relation`만 대상·값 동시 저장을 역변환하며 K12 계산의 실제 universe는 호출자가 제공한다. CI 검사기 전체 자기 시험은 이번 라운드에 실행하지 않았다. 과거 기존 의존성 위반은 round 2 기록에 남아 있다.
- 미완료 수락 조건: 감독 프로세스의 새 head SHA 확정, 이 설명의 실제 PR 게시, 그 SHA에 고정된 작성 계열 외 독립 리뷰 제출 및 원격 CI 확인. 이 로컬 수정으로 해당 항목을 완료 처리하지 않는다.

## 확인

- [x] `docs/BLUEPRINT.md` 및 `docs/PRINCIPLES.md` 체크리스트를 확인했다.
- [x] 범위·개인정보·추천 기준 변경을 단순 구현 변경으로 숨기지 않았다.
- [x] 규칙/가격/라벨 변경의 근거·버전·영향 사례를 연결했다. 규칙·라벨 변경 없음, 가격은 저장·자격 판정 검증이다.
- [x] CI 성공을 실제 상품 정확도나 출시 승인으로 표현하지 않았다.
- [ ] 설계와 구현의 상태를 요구사항 추적표에 반영했다. 금지 경로이므로 감독 프로세스의 별도 갱신 필요.
- [ ] 실제 PR 설명에 A/Q/L/I/M·R·작성 정보·새 대상 SHA를 게시했다. 감독 프로세스 작업.
- [ ] 새 head SHA에 고정된 작성 계열 외 독립 리뷰와 원격 CI가 있다. 감독 프로세스 작업.
