# defaults — 기본 필요액·참고 통계 기본값 후보(영역 C, T-KN-13)

02_구현계약 §1.5 "기본값" 행의 데이터 계약과 그 적재기다. 기본 필요액·참고 통계
기본값 **후보**는 출처가 확정된 공공 통계만, 적용 대상·갱신 주기와 함께 적재한다.
후보는 서비스 적용 승인(`criteria_application`, T-KN-14, D-08) 전에는 사용자에게
보이지 않는다. 기본값이 없으면 사용자 직접 가정만 쓴다(O05).

## 경로 상태(T-KN-13 fix round 5)

이 과제의 `allowed_paths`는 `data/criteria/defaults/**`와
`services/criteria/src/defaults/**`뿐이다. 그런데:

- `src/defaults/` 모듈은 `src/lib.rs`의 `pub mod defaults;` 선언 없이는
  컴파일되지 않는다 — `lib.rs`는 허용 경로 밖이다(빌드 라운드에서 가드가
  거부했다).
- `data/criteria/defaults/`를 만들면 `services/criteria/tests/conformance.rs`
  의 기존 단정 `assert!(!repo("data/criteria/defaults").exists())`이 깨진다 —
  시험 파일도 허용 경로 밖이라 고칠 수 없다.

fix round 1의 독립 리뷰(PR #147 @ f8ca0d8)는 이 상태를 두 차단 사유로
지적했다: 배선되지 않은 모듈은 컴파일되지 않아 필수 시험 명령
`cargo test -p onjeon-criteria defaults`가 일치 시험 0개로 끝난다(F1),
명세의 `produces` 경로 `data/criteria/defaults/**`가 트리에 없다(F2).
리뷰의 해소 경로도 같은 결론이다 — 빌더 오류가 아니라 명세 수정이다:
`allowed_paths`에 `services/criteria/src/lib.rs`와
`services/criteria/tests/conformance.rs`(또는 `services/criteria/tests/**`)를
추가한 뒤 배선·단정 갱신·데이터 경로 생성을 한 라운드에서 해야 한다.

fix round 2는 그 해소안을 작업 트리 루트 `DECISION_REQUIRED.md`로 감독
판단에 올렸으나, fix round 4부터 `DECISION_REQUIRED.md` 자체가 금지
경로에 들어갔고 fix round 5의 차단 사유는 그 파일의 존재였다. 따라서
이 라운드는 그 파일을 작업 트리에서 제거했다 — 요청 내용은 이 문서와
`evidence/PR_본문.md`에 그대로 남긴다. 허용 경로 안 해소책은 여전히
없다(`lib.rs` 배선·`conformance.rs` 단정 갱신·`Cargo.toml` 표적 선언·
`tests/` shim 전부 허용 밖 파일이 필요하다).

fix round 4는 허용 경로 안에서 `default-file.schema.json`의
`structure_item`을 적재기 규칙(수치 1개 이상)과 맞췄다. fix round 5는
문서를 이 상태로 맞추고 검증을 다시 실행해 `evidence/cargo_test_defaults.log`
§5에 기록했다: 배송 상태 필수 명령 일치 0개, 크레이트 전체 33/33,
`cargo test --all` 통과, leak·skeleton 정적 검사 0건, 프로브(임시
`pub mod defaults;`, 검증 후 되돌림) 17/17·전체 50/50·clippy 통과.

## 후보 파일 계약

후보 파일 하나 = 후보 항목 + 그 판들. 정식 적재 위치
`data/criteria/defaults/candidates/<slug>.json`:

```json
{
  "candidate": {
    "id": "def:<slug>",
    "kind": "needed_amount | reference_stat",
    "label": "...",
    "scope": { "situations": ["..."], "subjects": ["..."] },
    "update_cycle": { "kind": "annual | ... | on_source_release | irregular", "note": "..." },
    "applied": false,
    "recorded_at": "RFC3339"
  },
  "versions": [
    {
      "version": 1,
      "valid_from": "YYYY-MM-DD", "valid_to": null,
      "value": { "kind": "monetary_amount | rate | count | structure", "...": "..." },
      "sources": [{ "ref": "raw:sha256:<64>", "evidence_kind": "public_statistic" }],
      "rationale": "...",
      "recorded_at": "RFC3339",
      "origin": "pipeline | fixture"
    }
  ]
}
```

규칙(기준 파일과 같은 성격 — 적재기가 강제한다):

- **후보는 고치지 않는다.** 정정은 새 판(`version` +1)이고 `supersedes`가 바로
  이전 판(`<id>@<version-1>`)을 가리킨다. `supersedes`와 `correction_reason`은
  쌍으로만 온다.
- **출처 없는 판은 없다.** `sources`는 1개 이상이며 각 `ref`는
  `raw:sha256:<64>` RawAsset 해시뿐이다(`clause:`·`obs:`는 거부). `evidence_kind`는
  `public_statistic`뿐이다 — 법령·감독 고시·약관 사실·편집 판단은 이 경로의 출처가
  아니다. "편집 판단"이 필요한 기본값은 이 경로로 오지 않는다.
- **적용 대상·갱신 주기가 항상 있다.** `scope.situations`·`scope.subjects` 모두
  한 항목 이상, `update_cycle`은 필수다.
- **후보는 표시되지 않는다.** `applied`는 `false`만 적재된다. `applied=true`로
  바꾸는 경로는 이 저장소·이 크레이트에 없고, 서비스가 읽을 수 있는 목록
  (`for_service`)은 적용 승인 기록이 없는 한 항상 비어 있다.
- **사용자 가정이 우선한다.** 사용자 가정이 있으면 기본값은 그것을 덮지 않는다
  (§1.5 사용자 가정 행). 가정도 후보도 없으면 0이나 평균으로 채우지 않는다 —
  결과는 보류로 간다(D-08).
- **표시는 "참고 통계"다.** 결과에 실릴 때 `fact`가 아니라 "참고 통계" 배지로
  표시된다(`DisplayKind::ReferenceStatistic` — 다른 표시 종류가 없다).
- **개인 식별자는 올 수 없다.** `contract:`·`person:`·`upload:`·`del:`·
  `consent:`·`assume:` 접두어가 어느 문자열에도 있으면 거부(K8).
- **알 수 없는 키는 거부된다.**
- `id`(`def:<slug>@<n>`)는 `candidate_id`·`version`에서 파생하므로 파일에는
  쓰지 않는다.

**적재된 후보는 0건이다.** 후보 출처 `ref`는 `raw:sha256:` RawAsset 해시만 허용하고
`evidence_kind`는 `public_statistic`만 허용한다. 보존된 공공 통계 원본이 이
저장소의 원본 보관 목록에 아직 없으므로(원본 14건은 보험사 약관·상품요약서·감독
규정 표준약관·협회 공시 페이지다 — 공공 통계가 아니다) 해시가 실제 보존본을 가리키는
후보를 만들 수 없다. 출처 없는 기본값은 적재되지 않는다(O05·§1.5). 후보를 처음 넣는
작업은 보존된 공공 통계 원본의 해시와 함께 온다.

기준 릴리스(`crel:`)와 관계: 후보는 기준 판이 아니므로 `criteria/` 파일에
`default*` 키로 들어가지 않고(기준 적재기가 거부한다) 기준 릴리스의 구성원도
아니다. 서비스 적용은 `criteria_application` 기록(T-KN-14, D-08)이 판별한다.

시험 전용 자료는 배송 경로에 두지 않는다 — `origin=fixture` 표식과 함께 시험
코드(`tests.rs`) 안에 둔다. `origin=pipeline`만 배송 자료에 온다.
