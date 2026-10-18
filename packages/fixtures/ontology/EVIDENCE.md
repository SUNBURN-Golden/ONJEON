# T-KN-02 증거

- 과제: T-KN-02. 기준 커밋 `fd05605`(main 병합 직후). 리뷰 대상 SHA는 감독자가 커밋한 HEAD이며 커밋 시점에 붙는다.
- 작성: 구현자 역할의 AI 에이전트(Claude 계열) 단독, 감독자가 띄운 워크트리 `wt/T-KN-02`의 비대화형 세션. 독립 리뷰는 작성 계열이 아닌 리뷰어가 대상 SHA에 고정해서 해야 한다(아직 없음).
- 산출: `abox_cases.json`(시안 onto-0.2에서 `convert_from_proposal.py`로 생성, `--check`로 재현 확인), `rules/*.json`(fixture_only 그대로), `id_map.json`(옛 ID→정식 ID 감사용).
- 변환: raw·구획·조항 ID를 02 §6.1 정식 evidence_ref(`raw:sha256:`·`seg:`·`clause:`)로 바꿨다. 해시나 쪽 범위가 없는 자료는 값을 지어내지 않고 `_formal_ref_exceptions`에 둔다. 시안에서 일부 주장만 `origin=fixture`였으므로 변환기가 전 주장(66개)에 `origin=fixture`를 붙인다. `_review_note`는 시안 그대로 유지(시험이 대조). 릴리스 내용 해시는 멤버 ID·origin 변경 때문에 재계산했다.
- 시험(`packages/ontology/tests/fixture_origin/main.rs`, 크레이트 `onjeon-ontology`): 전 주장 origin=fixture·`_review_note` 유지·ReviewDecision 없음 / 전 규칙 fixture_only·규칙 엔진 적재 / 문서 해시와 16자 접두가 Git 고정 R2 목록 `archive_listing_raw.json`에 없음 / 정식 evidence_ref 형식과 예외 목록 / 이력 프로필 통과·서비스 프로필 표시 / 표식 변이 탐지.
- 실행: `cargo test -p onjeon-ontology` → `cargo_test.log`(실패 0, fixture_origin 6개 통과), `cargo clippy --all-targets -- -D warnings`·`cargo fmt --all -- --check` 통과, `tools/ci/check_leak.py`·`check_skeleton.py` 통과.
- 범위 밖: 서비스 적재기 거부(B1~B3)·릴리스 빌더 거부(B5)는 이 과제가 검사하지 않는다.
- 요구 ID와 PR 템플릿의 A·Q·L·I·M은 감독자가 PR 본문에서 채운다. 비밀값·모델 식별자·원문 발췌 없음(주장의 note는 요약문).
- 경로: 변경은 `packages/fixtures/ontology/**`와 `packages/ontology/tests/fixture_origin/**`. 후자는 spec의 produces 밖일 수 있으니 감독자가 allowed_paths를 확인해야 한다.
