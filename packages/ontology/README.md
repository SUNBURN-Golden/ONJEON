# onjeon-ontology

온톨로지 크레이트(T-KN-01, T-box onto-0.2). DB·네트워크 의존이 없다. 계산은 규칙 엔진(`onjeon-rules-engine`)이 하고, 이 크레이트는 지식 조회·코드 소속 판정·일관성 검사·릴리스 고정만 한다.

## API

| 함수 | 하는 일 |
|---|---|
| `load_tbox(json)` | `packages/schemas/ontology/tbox.json`(onto-0.2)을 읽고 검증한다(제약은 정확히 K1~K16, 중복 ID 거부) |
| `check_constraints(view, profile) → Vec<Violation>` | K1~K16. `CheckProfile`: `historical_fixture`(사례 A-box 그대로, 위반 0 기대) / `service_conformance`(origin=fixture·`fixture_assumption`인 accepted 전부를 `PROFILE` 위반으로 나열). K12의 코드 전체집합은 프로필의 `universe`로 받는다 |
| `view(abox, release)` / `candidate_view(abox)` | 고정 릴리스가 읽는 내용만(목록 밖 주장은 보이지 않음, 제자리 수정·삭제·규칙 파일 교체는 K15) / 저장된 전부(K15 없음) |
| `freeze(abox, members, input_stage_edition) → Freeze` | `{members, rule_files, content_sha256, input_stage_edition}` |
| `service_allowed(release, coverage, notices)` | `ReleaseNotice`는 재현을 막지 않고 영향 담보의 새 계산만 제한한다. `service_allowed_for`는 판매 구성으로도 좁힌다 |
| `edition_status(view, edition)` | `confirmed` / `identity_unconfirmed` + `missing_parts` + `mismatch[{part, kind ∈ content_difference_candidate, not_comparable}]` |
| `membership(view, cat, code, as_of) → Judgement` | 범주 구성원 = ∪포함 − ∪제외. accepted만 센다. 미승인이 끼면 `Unknown`(거짓으로 바꾸지 않음) |
| `scope_relation(view, a, b, universe)` | 코드 집합에서 계산. 전체집합(공식 CodeSystem)이 없거나 소속을 모르는 코드가 있으면 `NotComparable` |
| `resolve_chain(view, configs, as_of, cov)` | 입력 단계 연결 검증(C-26, §1.7). `Blocked`이면 엔진 호출 0 |

## 판 동일성은 코드가 확정하지 않는다

지문은 검수의 근거다. 구성(본문 + 참조 별표)을 근거 묶음(그 판을 실현하는 accepted `realizes` 전부, 원본 수와 무관)이 모두 덮고 검수 없는 지문 차이가 없을 때만 `confirmed`다. 같은 정규화 규칙에서 지문이 다르면 내용 차이 후보, 규칙이 다르면(OCR 등) 비교 불가이며, `decision{by=review_decision, covers=[규칙, 지문]}` 없이는 같은 판이 아니다. 다른 판이라는 확정도 새 `TermsEdition` + `realizes`라는 검수 결정이다.

## 알려진 차이와 한계 (참조 구현 `ontology_check.py` 대비)

- **내용 해시는 members + rule_files만 덮는다.** 02_구현계약 §1.3은 `input_stage_edition`도 해시에 들어간다고 적지만, 골든 릴리스(r24~r26)의 고정 해시는 참조 구현이 만든 값이라 그 정의를 따라야 재현된다. `input_stage_edition`은 해시 옆에 실어 나르고 해시는 덮지 않는다. 서비스 릴리스 빌더(T-KN-07)가 해시 범위를 정할 때 결정할 일이다.
- 참조 구현에 없는 막힘 사유 `SimulateBlocked`(담보의 C0 미승인·미해소 충돌)를 §1.7 사유 목록에 더했다. 적용 관계 미승인(`applies_unconfirmed`)은 `ApplicationScopeUnverified`로 묶고 `held`에 원래 표기를 남긴다.
- 전체집합(`CodeUniverse`)을 이 크레이트가 내장하지 않는다. 공식 KCD 목록은 호출자가 넣는다. 골든 시험의 전체집합은 참조 구현이 쓰던 합성 목록이며 공식 목록이 아니다(시험 전용).
- `membership`의 `as_of`는 주장의 유효 기간(`valid_from/valid_to`) 필터로만 쓴다. 코드 집합의 시행일·개정차수로 고르는 판정 시점 규칙은 없다(골든 사례에 시간 있는 포함·제외 주장이 없다).
- K8은 참조 구현과 같이 공개 구역 JSON 전체에서 `contract:`·`person:`·`upload:` 부분 문자열을 찾는다.
- 설명 문장(`explain`)은 크레이트가 아니라 시험 보조(`tests/common`)에 있다. 시험은 결과·근거 사슬이 같은지 구조적으로 비교한다.
- 시험 전용 dev-dependency `onjeon-rules-engine`(골든 질문 11의 결과를 실제 엔진으로 재현, `tests/common`)은 `infra/ci/deps.json`의 구역 규칙(knowledge → contracts만)과 어긋나 `tools/ci/check_deps.py`가 보고한다. 라이브러리(`src/`)는 엔진에 링크되지 않는다. `dependency_exceptions`에 dev 예외를 더하는 일은 그 규칙 파일을 맡은 과제의 몫이다.

## 골든 (`tests/golden/`)

토의 자료의 사례 A-box(`abox_cases.json`; 일부 레코드만 `origin=fixture`를 달고, `tests/golden/` 디렉터리 전체가 시험 전용이다)와 규칙 파일, 참조 구현의 출력(`reference_results.txt`)이다. 서비스 데이터가 아니다. 릴리스 내용 해시 세 개는 `reference_results.txt`와 일치한다(`golden.rs`).

| 시험 파일 | 골든 |
|---|---|
| `golden.rs` | 릴리스 고정, r24 K1 정확히 1건·r25·r26 0건, 범위 관계, 질문 11 |
| `mutations.rs` | 제약 변이 15 (K1~K14, K16) |
| `releases.rs` | I1(`release_future_supersedes_frozen`)~I7 |
| `editions.rs` | D1~D9 (`edition_*` 시험 ID) |
| `input_link.rs` | E1~E4, S01, S01b, T01, U01 |
| `profile.rs` | `profile_check_flags_fixture`, P1 |
| `tbox.rs` | T-box 적재, DB·네트워크 의존 없음 |

시험 ID(`edition-not-auto-by-fingerprint` 등)는 함수 이름에서 `-`를 `_`로 바꾼 것이다. 실행: `cargo test -p onjeon-ontology`.
