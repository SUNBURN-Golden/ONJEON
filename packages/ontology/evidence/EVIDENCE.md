# T-KN-01 증거

- 과제: T-KN-01 (`packages/ontology`, 크레이트 `onjeon-ontology`). 대상 기준 커밋: `57f14e7`(main) 위의 작업 트리. 최종 SHA는 감독자가 커밋할 때 붙는다.
- 작성: 구현자 역할의 AI 에이전트(Claude 계열) 단독. 독립 리뷰는 작성 계열이 아닌 리뷰어가 대상 SHA에 고정해서 해야 한다(아직 없음).
- 실행한 명령과 로그: `cargo test -p onjeon-ontology` → `cargo_test.log`(통과 63개, 실패 0), `cargo clippy -p onjeon-ontology --all-targets` + `cargo fmt --check` → `clippy.log`(경고 없음).
- 다른 크레이트: `cargo test -p onjeon-contracts -p onjeon-rules-engine` 통과(워크스페이스 멤버 추가 영향 없음 확인).
- 요구 ID: R03(상품 버전 식별: K14·K16, edition_*), R08(근거 없는 결과 차단: K1, 프로필), P06(제약 K1~K16·릴리스 고정). PR 템플릿의 A·Q·L·I·M 항목은 감독자가 PR 본문에서 채운다.
- 골든 대응(참조 구현 21/21): 질문 11 `golden.rs`, 제약 변이 15 `mutations.rs`, I1~I7 `releases.rs`, D1~D9 `editions.rs`, E1~E4 `input_link.rs`, P1 `profile.rs`. r24 K1 위반 정확히 1건, r25·r26 0건. 세 릴리스의 내용 해시가 `tests/golden/reference_results.txt`와 일치.
- 필수 시험 ID 11개 → 함수: `edition_not_auto_by_fingerprint`, `edition_composition_annex`, `edition_bundle_split_files`, `edition_annex_missing_unconfirmed`, `edition_ocr_normalization`, `edition_annex_content_changed`, `edition_integrated_vs_separate_file`, `edition_repack_same`, `edition_one_rider_revised_in_integrated`, `release_future_supersedes_frozen`, `profile_check_flags_fixture`.
- 시험 전용 데이터: `tests/golden/**`(전부 origin=fixture, 서비스 데이터 아님). 제품 코드(`src/`)에는 사례 데이터·합성 전체집합이 없다.
- 한계: `packages/ontology/README.md`의 "알려진 차이와 한계" 참조(해시가 input_stage_edition을 덮지 않음, 내장 전체집합 없음 등).
- allowed_paths 밖 수정 없음: `packages/ontology/**`, `packages/schemas/ontology/tbox.json`, `Cargo.toml`(멤버 한 줄), `Cargo.lock`(cargo 재생성).
