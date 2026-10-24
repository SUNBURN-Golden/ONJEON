# T-KN-01 증거

- 과제: T-KN-01 (`packages/ontology`, 크레이트 `onjeon-ontology`). 대상 기준 커밋: 처음에는 `57f14e7`(main), 수정 라운드 4에서 `origin/main` `464ba25`를 병합했다. 리뷰 대상 HEAD는 `6e08f5d`(수정 라운드 2) 위에 라운드 4의 병합·변경을 감독자가 커밋한 SHA다(커밋 시점에 붙는다).
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

## 수정 라운드 4
- 실패 원인: 세 라운드 연속 `CI FAIL:no-ci-runs`. 코드·시험 실패가 아니라 PR #126이 main과 `Cargo.toml`(`workspace.members`: main은 `packages/api-types`를, 이 가지는 `packages/ontology`를 같은 줄에 더함)에서 충돌 상태였고, GitHub는 충돌 중인 PR에 `pull_request` 워크플로를 실행하지 않으므로 체크 실행이 하나도 생기지 않았다. 라운드 1~3은 이 원인을 보지 못했다.
- 조치: `origin/main`(`464ba25`)을 이 가지에 병합(merge, force push 없음). `Cargo.toml`은 두 의도를 모두 유지(members 4개, main 대비 한 줄 차이 = 이 과제의 크레이트 추가). `Cargo.lock`은 cargo가 재생성(main 대비 `onjeon-ontology` 항목 추가만, `cargo metadata --locked` 통과). 병합 커밋은 감독자가 만든다.
- main의 `onjeon-contracts`(어휘 1.6.0 적응, T-CT-02)에서 `checks::ORIGIN_FIXTURE`가 `&str`에서 `AssertionOrigin` 상수로 바뀌어 `src/check.rs`의 서비스 프로필 검사 한 줄을 `ORIGIN_FIXTURE.as_str()` 비교로 맞췄다(A-box의 `origin`은 문자열로 읽는다). 동작·시험 결과 변화 없음.
- 실행(병합 뒤): 감독자 test_cmd 전체 통과 — `vocab_check`(45축·228값), `validation_check` + `--selftest`(변이 38 전부 포착), `tools/tests` 388 OK(skipped=6), `cargo fmt --all -- --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test --all`(실패 0), `spec_check` 44/44·72/72. `cargo test -p onjeon-ontology` 67 통과·0 실패 → `cargo_test.log`(재생성, 경로는 `<repo>`로 치환). `clippy.log` 재생성(경고 없음, fmt-ok). CI `design-specs` 작업도 같은 명령으로 실행: 참조 러너 빌드 + `ontology_check.py` → 질문 11/11·제약 변이 15/15·릴리스·문서 모델 25/25 전체 통과.
- main의 `tools/ci`(T-CT-06) 정적 검사: `check_leak`(누출 없음)·`check_skeleton`(플래그 off, 비노출)·`check_bootstrap`과 각 `--selftest`, `tools/ci/tests` 통과.
- 열린 항목(이 과제의 allowed_paths 밖): `tools/ci/check_deps.py`가 `onjeon-ontology`의 dev-dependency `onjeon-rules-engine`(twin 구역)을 DEP-ZONE(`packages/ontology/Cargo.toml`)·IMP-ZONE(`tests/common/mod.rs`)으로 보고한다. 골든 질문 11의 결과(지급 금액)를 실제 엔진으로 재현하는 시험 전용 의존이며 라이브러리에는 링크되지 않는다. `infra/ci/deps.json`의 `dependency_exceptions`에 `{from: onjeon-ontology, to: onjeon-rules-engine, kind: dev}`(T-CT-01의 contracts→rules-engine 예외와 같은 방식)를 더하면 두 보고가 사라진다. 그 파일은 여기서 고칠 수 없고, `check_deps`는 아직 CI·test_cmd에 연결되어 있지 않다.
- 경로: 변경 파일 30개 전부 allowed_paths 안(`packages/ontology/**`, `packages/schemas/ontology/tbox.json`, `Cargo.toml` 한 줄, `Cargo.lock`). main에서 병합되어 들어온 파일은 main과 같으므로 이 과제의 변경이 아니다.
