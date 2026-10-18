# T-KN-01 증거

- 과제: T-KN-01 (`packages/ontology`, 크레이트 `onjeon-ontology`). 대상 기준 커밋: `57f14e7`(main) 위의 작업 트리. 리뷰 대상 HEAD `6e40c50`(수정 라운드 2 변경은 감독자가 커밋할 때 새 SHA가 붙는다).
- 작성: 구현자 역할의 AI 에이전트(Claude 계열) 단독, 실행 경로는 감독자가 띄운 워크트리(`wt/T-KN-01`)의 비대화형 에이전트 세션. 독립 리뷰는 작성 계열이 아닌 리뷰어가 대상 SHA에 고정해서 해야 한다(아직 없음).
- 실행한 명령과 로그: `cargo test -p onjeon-ontology` → `cargo_test.log`(통과 67개, 실패 0), `cargo clippy --workspace --all-targets -- -D warnings` + `cargo fmt --check` → `clippy.log`(경고 없음).
- 다른 크레이트: `cargo test -p onjeon-contracts -p onjeon-rules-engine` 통과(워크스페이스 멤버 추가 영향 없음 확인).
- 요구 ID: R03(상품 버전 식별: K14·K16, edition_*), R08(근거 없는 결과 차단: K1, 프로필), P06(제약 K1~K16·릴리스 고정). PR 템플릿의 A·Q·L·I·M 항목은 감독자가 PR 본문에서 채운다.
- 골든 대응(참조 구현 21/21): 질문 11 `golden.rs`, 제약 변이 15 `mutations.rs`, I1~I7 `releases.rs`, D1~D9 `editions.rs`, E1~E4 `input_link.rs`, P1 `profile.rs`. r24 K1 위반 정확히 1건, r25·r26 0건. 세 릴리스의 내용 해시가 `tests/golden/reference_results.txt`와 일치.
- 필수 시험 ID 11개 → 함수: `edition_not_auto_by_fingerprint`, `edition_composition_annex`, `edition_bundle_split_files`, `edition_annex_missing_unconfirmed`, `edition_ocr_normalization`, `edition_annex_content_changed`, `edition_integrated_vs_separate_file`, `edition_repack_same`, `edition_one_rider_revised_in_integrated`, `release_future_supersedes_frozen`, `profile_check_flags_fixture`.
- 시험 전용 데이터: `tests/golden/**` 디렉터리 전체가 시험 전용(일부 레코드에만 origin=fixture, 규칙 파일은 publication_state=fixture_only; 서비스 데이터 아님. note 필드는 요약 문구이고 약관 원문 발췌가 아니다). 제품 코드(`src/`)에는 사례 데이터·합성 전체집합이 없다.
- 한계: `packages/ontology/README.md`의 "알려진 차이와 한계" 참조(해시가 input_stage_edition을 덮지 않음, 내장 전체집합 없음 등).
- allowed_paths 밖 수정 없음: `packages/ontology/**`, `packages/schemas/ontology/tbox.json`, `Cargo.toml`(멤버 한 줄), `Cargo.lock`(cargo 재생성).

- 수정 라운드 1: `in_range`가 글자를 가로지르는 범위(`C00-D48`)를 (글자, 두 자리) 순서로 비교하고, 마이너 자릿수가 붙은 범위 경계는 `BadCode`로 거부한다(시험 `range_spans_letters`, `range_bound_with_minor_is_rejected`). 알려진 한계: `edition_status`는 accepted `realizes`의 결정 출처를 보지 않아 지문 일치 승인은 K14로만 잡힌다(참조 구현과 동일), `resolve_chain`은 `View::integrity`를 보지 않는다, 리뷰 결정의 `covers`는 구획 자체 지문에 묶이지 않는다. 필수 시험 ID의 하이픈은 함수명에서 밑줄이다.

## 수정 라운드 2
- `edition_status`: accepted `realizes`의 `decision.by`가 `review_decision`/`fixture_assumption`이 아니면(예: `fingerprint_match`) 지문이 일치해도 `identity_unconfirmed`. 입력 단계(`resolve_chain`)가 이 상태로 막는다. K14는 별도로 유지(D3은 K14만).
- `scope_relation`: 코드가 빈 `CodeUniverse`는 `not_comparable`.
- K4: narrower/broader 순환을 길이와 무관하게 검사(참조 구현은 narrower 2-순환만).
- 알려진 한계(유지): `resolve_chain`은 `View::integrity`(K15)를 보지 않는다 — 호출자가 `check_constraints`를 먼저 돌린다. 내용 해시는 참조 구현·골든대로 `input_stage_edition`을 포함하지 않는다(T-KN-07 서비스 릴리스 구성 시 결정 필요).
