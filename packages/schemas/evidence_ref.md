# evidence_ref 문법

정본은 `docs/blueprint/proposals/설계검토_결과/02_구현계약.md` §6.1(검토용 묶음, 채택 전)이다. 이 문서는 그 문법을 `json/common.schema.json`의 정규식으로 옮긴 것이고, 정규식과 이 표가 어긋나면 시험이 실패한다(`codegen/tests/test_schemas.py` `EvidenceRefs`). 문법을 검사하는 파서·검증기·픽스처 ID 변환기는 `src/evidence_ref.rs`(T-CT-04)이고 `cargo test -p onjeon-contracts evidence_ref`로 시험한다.

| 스키마 정의 | 형식 | 비고 |
|---|---|---|
| `SegmentRef` | `seg:<raw_sha12>:p<from>-<to>:<doc_role>:<seg_rule_ver>` | 문서 구획. `raw_sha12`는 원본 SHA-256 앞 12자(충돌 시 전체 64자까지 확장 허용). `doc_role`은 어휘 축 `doc_role`의 값 모양(소문자 snake_case)이다 |
| `ClauseRef` | `clause:<segment_ref>/<path_slug>#p<page>:<추출기>@<판>[@x,y,w,h]` | 조항은 구획 안에 있다. 재추출은 새 ID. 좌표는 선택 |
| `EditionRef` | `ted:<ulid>` | 약관 본문 판. 파일 해시가 아니다 |
| `PremiumRef` | `premium:<ulid>` | 가격 관측 |
| `AssertionRef` | `assertion:<ulid>` | 주장 참조(근거 목록 안) |
| `RuleEvidenceRef` | `rule:<rule_id>@<rule_version>#<content_hash12>` | 규칙 |
| `ObservationRef` | `obs:src:<org>/<channel>/<n>/<RFC3339>/<sha16>` | 원본 관측 |
| `RawRef` | `raw:sha256:<64hex>` | 불변 원본 |
| `EvaluationRef` | `eval:<ulid>` | 평가 결과 |
| `CriterionRef` | `crit:<slug>@<version>` | 판단 기준의 판 |

`EvidenceRef`는 위 열 개의 합집합이다. `<ulid>`는 Crockford base32 26자(`I L O U` 제외)다.

## 근거 역할과 허용 참조

`basis`는 약관·별표 구획의 `ClauseRef`, `cross_check`는 요약서·안내 쪽 구획의 `ClauseRef`, `observation`은 `ObservationRef`·`SegmentRef`·`RawRef`·공시 행 `ClauseRef`만 쓴다(02 §6.1). 이 역할별 제한은 스키마가 아니라 릴리스 빌더와 DB 제약의 몫이다(스키마는 모양만 본다).

## 열린 항목 (구현자가 정하지 않았다)

- 주장 ID는 02 §1.1에서 `a:<ulid>`이고 §6.1의 `assertion_ref`는 `assertion:<ulid>`다. 스키마는 둘을 각각 그대로 둔다: `Assertion.id`·`assertion_refs`·`evidence_assertion_ids`는 `a:`, `evidence[].ref`는 `assertion:`. 하나로 맞출지는 T-CT-04(문법 검사기)와 설계 담당이 정한다.
- `<path_slug>`의 문자 집합, `<seg_rule_ver>`·`<추출기>`·`<판>`의 형식이 02에 없다. 지금은 공백과 `#`을 뺀 글자(`path_slug`), `[A-Za-z0-9._-]`(나머지)를 허용한다.
- 픽스처 지역 ID(`hana_2601_3d#c_2_1_art1_1`, `seg:hana_r2_1` 같은 것)는 정식 문법이 아니며 이 정규식에 맞지 않는다(시험이 거부를 확인한다). 픽스처 적재기가 정식 형식으로 변환하되 `origin=fixture`는 유지한다(02 §6.1).

## 파서·검증기 (`src/evidence_ref.rs`, T-CT-04)

- `parse(text)`: 위 문법이 허용하는 문자열만 받는다. 받은 문자열은 `ParsedRef`의 `Display`로 **바이트 그대로** 되돌아온다(왕복). 열 종류 모두 시험한다. 왕복을 위해 문법보다 좁힌 곳: 쪽 번호·기준 판은 앞 0 없는 10진수, `obs`의 소스는 `src:<org>/<channel>/<n>` 세 부분이며 시각은 실제로 존재하는 RFC 3339, 쪽 범위는 1쪽 이상이고 오름차순.
- `validate(text)`: `parse`에 문법만으로 못 보는 검사를 더한다. 조항의 쪽이 구획 쪽 범위 안에 있고 좌표가 양수다. 역할별 허용 참조(`basis` 등)는 여기서 보지 않는다.
- `kind_of(text)`: 종류만 돌려준다.
- `FixtureIdMap`: 픽스처 지역 ID(`seg:hana_r2_1`, `hana_2601_3d#c_2_1_art1_1`)를 정식 `evidence_ref`로 바꾼다. 매핑 표(원본 SHA-256, 쪽 범위, 문서 역할, 구획 규칙 판, 추출 판)는 호출하는 쪽이 준다. 표에 없거나 쪽이 범위 밖이거나 SHA가 64자 소문자 16진이 아니면 오류다. 결과는 `origin=fixture`(`FixtureRef::ORIGIN`)를 달고 나오며 변환이 fixture를 서비스 데이터로 승격하지 않는다(02 §8).
- Rust 문법과 `json/common.schema.json`의 정규식이 같은 열 가지 모양을 기술하는지 시험이 확인한다(`evidence_ref_matches_the_schema_alternatives`).
